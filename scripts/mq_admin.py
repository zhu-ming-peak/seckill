"""仅操控本机 WSL 的 Lab2 RocketMQ 服务/主题，不涉及 ECS。"""
from pathlib import Path
import json,subprocess,sys
MQ='/opt/lab2-rocketmq/rocketmq-all-5.5.1-bin-release'
def run(action):
    if action=='topics':
        commands=[['/usr/lib/jvm/java-17-openjdk-amd64/bin/java','-Xms32m','-Xmx128m','-Drocketmq.home.dir='+MQ,'-cp',MQ+'/lib/*','org.apache.rocketmq.tools.command.MQAdminStartup','updateTopic','-n','127.0.0.1:9876','-b','127.0.0.1:10911','-t',topic,'-r','4','-w','4'] for topic in ['Lab2OrdersV3','Lab2OrdersV3Tests','Lab2MessageDemo']]
    elif action in ('start','stop','restart'):
        commands=[['systemctl',action,'lab2-mq-broker.service']]
    elif action=='status':commands=[['systemctl','is-active','lab2-mq-namesrv','lab2-mq-broker'],['ss','-lnt']]
    else:raise ValueError('unknown local action')
    code='import subprocess,json\ncommands='+repr(commands)+'\nrows=[]\nfor c in commands:\n r=subprocess.run(c,capture_output=True,text=True)\n rows.append({"command":c,"exit_code":r.returncode,"output":r.stdout,"stderr":r.stderr})\nprint(json.dumps(rows,ensure_ascii=False))\n'
    r=subprocess.run(['wsl','-d','Ubuntu','-u','root','--exec','python3'],input=code.encode(),capture_output=True)
    if r.returncode:raise RuntimeError(r.stderr.decode('utf-8',errors='replace'))
    return json.loads(r.stdout.decode())
if __name__=='__main__':print(json.dumps(run(sys.argv[1]),ensure_ascii=False,indent=2))
