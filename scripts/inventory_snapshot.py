"""只读快照：MySQL 订单/持久请求，与 Redis 可用库存分别核对。"""
from pathlib import Path
import argparse,datetime,json,os,subprocess
from redis_local import redis_commands
ROOT=Path(__file__).resolve().parents[1]
def query(sql):
    c=json.loads((ROOT.parent/'实验记录/本机私用/app-env.json').read_text(encoding='utf-8'));env=os.environ.copy();env['MYSQL_PWD']=c['DB_PASSWORD']
    mysql=os.environ.get('MYSQL_BIN',r'C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe')
    r=subprocess.run([mysql,'--protocol=TCP','-h',c['DB_HOST'],'-u',c['DB_USER'],'-D',c['DB_NAME'],'--batch','--default-character-set=utf8mb4'],input=sql.encode('utf-8'),capture_output=True,env=env)
    if r.returncode:raise RuntimeError('只读核对失败')
    lines=r.stdout.decode('utf-8').splitlines();keys=lines[0].split('\t')
    return [dict(zip(keys,line.split('\t'))) for line in lines[1:]]
def snapshot():
    activities=query("SELECT a.id,a.initial_stock,a.stock AS mysql_stock,(SELECT COUNT(*) FROM seckill_order o WHERE o.activity_id=a.id) AS orders,(SELECT COUNT(*) FROM seckill_request r WHERE r.activity_id=a.id AND r.state='ACCEPTED') AS accepted FROM seckill_activity a WHERE a.id IN (1,2,3,4,5) ORDER BY a.id")
    for a in activities:
        gate=redis_commands([['HGETALL','lab2:v3:activity:{'+a['id']+'}:reservation']])[0]['output'].splitlines();fields=dict(zip(gate[::2],gate[1::2]))
        a['redis_available']=int(fields['stock']) if 'stock' in fields else None
        a['redis_pending']=sum(k.startswith('token:') and v=='PENDING' for k,v in fields.items())
        a['inventory_difference']=int(a['initial_stock'])-int(a['mysql_stock'])-int(a['orders'])
        a['expected_available']=int(a['mysql_stock'])-int(a['accepted'])
    return {'checked_at':datetime.datetime.now().astimezone().isoformat(),'activities':activities,'requests':query('SELECT request_id,activity_id,user_id,state,order_id,send_count,last_message_id,processing_attempts,redis_done FROM seckill_request ORDER BY accepted_at DESC LIMIT 30')}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();value=snapshot();a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(value,ensure_ascii=False,indent=2))
