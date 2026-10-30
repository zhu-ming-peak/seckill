"""ECS 本机管理与只读快照。仅处理 lab2 单元；不输出生成的应用密码。"""
from pathlib import Path
import argparse,json,os,shutil,subprocess,time,urllib.request
CONF=Path('/etc/lab2-seckill')
UNITS=['mysql','lab2-redis','lab2-mq-namesrv','lab2-mq-broker','lab2-seckill']
def run(args):
    r=subprocess.run(args,capture_output=True,text=True)
    return {'exit_code':r.returncode,'output':r.stdout.strip(),'stderr':r.stderr.strip()}
def query(sql):
    r=run(['mysql','--no-defaults','--protocol=socket','-uroot','--batch','--default-character-set=utf8mb4','-D','lab2_seckill','-e',sql])
    if r['exit_code']:raise RuntimeError('Snapshot SQL failed')
    lines=r['output'].splitlines()
    return [dict(zip(lines[0].split('\t'),line.split('\t'))) for line in lines[1:]] if lines else []
def redis(command):
    c=json.loads((CONF/'credentials.json').read_text());env=os.environ.copy();env['REDISCLI_AUTH']=c['REDIS_PASSWORD']
    r=subprocess.run(['redis-cli','--raw']+command,capture_output=True,text=True,env=env)
    if r.returncode:raise RuntimeError('Redis snapshot failed')
    return r.stdout.strip()
def wait():
    until=time.monotonic()+75
    while time.monotonic()<until:
        try:
            with urllib.request.urlopen('http://127.0.0.1:18092/health',timeout=3) as r:value=json.load(r)
            if value.get('rocketmq')=='CLIENTS_STARTED' and value.get('redis')=='PONG':return value
        except (OSError,ValueError):pass
        time.sleep(.5)
    raise RuntimeError('Application health deadline exceeded')
def snapshot():
    activities=query('SELECT id,initial_stock,stock FROM seckill_activity ORDER BY id')
    orders=query('SELECT id,request_id,activity_id,user_id,product_name,unit_price,quantity,status,created_at FROM seckill_order ORDER BY created_at,id')
    requests=query('SELECT request_id,activity_id,user_id,state,failure_code,order_id,accepted_at,send_count,last_message_id,processing_attempts,redis_done FROM seckill_request ORDER BY accepted_at,request_id')
    for a in activities:
        matching=[o for o in orders if o['activity_id']==a['id']];pending=[r for r in requests if r['activity_id']==a['id'] and r['state']=='ACCEPTED']
        fields=redis(['HGETALL','lab2:ecs:v3:activity:{'+a['id']+'}:reservation']).splitlines();h=dict(zip(fields[::2],fields[1::2]))
        a.update(order_count=len(matching),accepted=len(pending),expected_available=int(a['stock'])-len(pending),redis_available=int(h['stock']) if 'stock' in h else None,redis_pending=sum(k.startswith('token:') and v=='PENDING' for k,v in h.items()),inventory_difference=int(a['initial_stock'])-int(a['stock'])-len(matching))
    processes=[]
    for unit in UNITS:
        state=run(['systemctl','show',unit,'--property=ActiveState,SubState,MainPID,MemoryCurrent,MemoryHigh,MemoryMax,NRestarts'])
        props=dict(line.split('=',1) for line in state['output'].splitlines() if '=' in line)
        if props.get('MainPID','0')!='0':props['ps']=run(['ps','-p',props['MainPID'],'-o','pid=,user=,rss=,comm='])['output']
        processes.append({'unit':unit,**props})
    return {'checked_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'hostname':os.uname().nodename,'health':wait(),'activities':activities,'orders':orders,'requests':requests,'services':processes,'memory':run(['free','-m']),'disk':run(['df','-h','/']),'ports':run(['ss','-lnt']),'default_java_path':os.path.realpath(shutil.which('java')),'default_java':run(['java','-version']),'mysql_version':query('SELECT VERSION() AS version,@@transaction_isolation AS isolation_level'),'redis_version':run(['redis-server','--version']),'java17':run(['/opt/lab2-seckill/java17/bin/java','-version']),'iptables_ha':run(['iptables','-C','INPUT','!','-i','lo','-p','tcp','--dport','10912','-j','DROP'])['exit_code'],'ip6tables_ha':run(['ip6tables','-C','INPUT','!','-i','lo','-p','tcp','--dport','10912','-j','DROP'])['exit_code']}
def consumer(enabled):
    subprocess.run(['systemctl','stop','lab2-seckill'],check=True)
    file=CONF/'app.env';lines=file.read_text().splitlines();lines=[('MQ_CONSUMER_ENABLED='+str(enabled).lower()) if x.startswith('MQ_CONSUMER_ENABLED=') else x for x in lines]
    temporary=CONF/'app.env.tmp';temporary.write_text('\n'.join(lines)+'\n');temporary.chmod(0o600);temporary.replace(file)
    subprocess.run(['systemctl','start','lab2-seckill'],check=True);return wait()
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['snapshot','restart-app','pause-consumer','resume-consumer','restart-components']);p.add_argument('--output',type=Path);a=p.parse_args()
    assert os.geteuid()==0
    if a.action=='restart-app':subprocess.run(['systemctl','restart','lab2-seckill'],check=True);wait()
    elif a.action=='pause-consumer':consumer(False)
    elif a.action=='resume-consumer':consumer(True)
    elif a.action=='restart-components':
        subprocess.run(['systemctl','stop','lab2-seckill','lab2-mq-broker','lab2-mq-namesrv','lab2-redis','mysql'],check=True)
        subprocess.run(['systemctl','start','mysql','lab2-redis','lab2-mq-namesrv','lab2-mq-broker','lab2-seckill'],check=True);wait()
    value=snapshot()
    if a.output:a.output.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(value,ensure_ascii=False,indent=2))
