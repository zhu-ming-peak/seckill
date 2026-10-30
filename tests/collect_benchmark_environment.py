"""测量后只读核对软件版本与 WSL 资源视图，凭据不写入输出。"""
from pathlib import Path
import argparse,importlib.metadata,json,os,subprocess,time
from benchmark import ROOT,Database,Redis,dump
def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--env-file',type=Path,default=ROOT.parent/'实验记录/本机私用/app-env.json');a=p.parse_args()
    c=json.loads(a.env_file.read_text(encoding='utf-8'));db=Database(c);r=Redis(c)
    try:redis_info=dict(line.split(':',1) for line in r.call('INFO','server').splitlines() if ':' in line and not line.startswith('#'))
    finally:r.close()
    mysql=db.query('SELECT VERSION() AS version,@@transaction_isolation AS isolation_level,@@innodb_buffer_pool_size AS innodb_buffer_pool_bytes,@@max_connections AS max_connections')[0]
    java=subprocess.run([r'E:\Java\jdk-17\bin\java.exe','-version'],capture_output=True,text=True).stderr.strip()
    mq='/opt/lab2-rocketmq/rocketmq-all-5.5.1-bin-release'
    command=['wsl','-d','Ubuntu','-u','root','--exec','/usr/lib/jvm/java-17-openjdk-amd64/bin/java','-Xms32m','-Xmx128m','-Drocketmq.home.dir='+mq,'-cp',mq+'/lib/*','org.apache.rocketmq.tools.command.MQAdminStartup','clusterList','-n','127.0.0.1:9876']
    broker=subprocess.run(command,capture_output=True,check=True);raw=broker.stdout.decode('utf-8',errors='replace');assert 'V5_5_1' in raw or '5.5.1' in raw,'Broker 版本核验失败'
    (a.run/'broker-version.txt').write_text(raw,encoding='utf-8')
    code="import json,os,platform\nm={}\nfor l in open('/proc/meminfo'):\n k,v=l.split(':',1)\n if k in ['MemTotal','MemAvailable']:m[k]=v.strip()\nprint(json.dumps({'kernel':platform.release(),'logical_cpus':os.cpu_count(),'memory':m}))"
    wsl=subprocess.run(['wsl','-d','Ubuntu','--exec','python3','-c',code],capture_output=True,check=True)
    value={'verified_at_unix':time.time(),'verification':'read-only after measurement; components not reconfigured between rounds','mysql':mysql,'redis':{k:redis_info[k] for k in ['redis_version','arch_bits','os']},'rocketmq':{'version':'5.5.1','evidence':'MQAdmin clusterList broker response'},'java':java,'python_packages':{k:importlib.metadata.version(k) for k in ['PyMySQL','psutil','matplotlib','numpy']},'wsl':json.loads(wsl.stdout.decode())}
    dump(a.run/'environment.json',value);print(json.dumps(value,ensure_ascii=False))
if __name__=='__main__':main()
