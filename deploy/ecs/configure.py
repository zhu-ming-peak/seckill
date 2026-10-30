"""配置全新的 ECS 实验环境；保留生成的应用凭据，重复执行不重置订单。"""
from pathlib import Path
import hashlib,json,os,pwd,secrets,shutil,subprocess,time
ROOT=Path('/opt/lab2-seckill');STAGE=ROOT/'staging';CONF=Path('/etc/lab2-seckill')
def run(args,**kwargs):return subprocess.run(args,check=True,**kwargs)
def write(path,text,mode=0o644):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8');path.chmod(mode)
assert os.geteuid()==0
manifest=json.loads((STAGE/'assets.json').read_text())
assert hashlib.sha256((STAGE/'app.jar').read_bytes()).hexdigest()==manifest['application_sha256']
for item in manifest['downloads']:
    assert hashlib.new(item['algorithm'],(STAGE/item['name']).read_bytes()).hexdigest()==item['checksum']
try:
    account=pwd.getpwnam('lab2');assert account.pw_shell=='/usr/sbin/nologin' and account.pw_dir=='/var/lib/lab2-seckill'
except KeyError:run(['useradd','--system','--home-dir','/var/lib/lab2-seckill','--shell','/usr/sbin/nologin','lab2'])
for name in ['/var/lib/lab2-seckill','/var/lib/lab2-rocketmq','/var/lib/redis/lab2']:
    run(['install','-d','-m','750','-o','redis' if '/redis/' in name else 'lab2','-g','redis' if '/redis/' in name else 'lab2',name])
CONF.mkdir(mode=0o700,exist_ok=True);CONF.chmod(0o700)
credentials=CONF/'credentials.json'
if credentials.exists():c=json.loads(credentials.read_text())
else:
    c={'DB_PASSWORD':secrets.token_urlsafe(32),'REDIS_PASSWORD':secrets.token_urlsafe(32)}
    write(credentials,json.dumps(c),0o600)
java=ROOT/'java17'
if not (java/'bin/java').exists():
    java.mkdir(exist_ok=True);run(['tar','-xzf',str(STAGE/manifest['java_archive']),'-C',str(java),'--strip-components=1','--no-same-owner'])
mqroot=Path('/opt/lab2-rocketmq');mq=mqroot/'rocketmq-all-5.5.1-bin-release'
if not mq.exists():mqroot.mkdir(exist_ok=True);run(['unzip','-q',str(STAGE/manifest['mq_archive']),'-d',str(mqroot)])
release=ROOT/'releases'/manifest['application_release'];release.mkdir(parents=True,exist_ok=True)
jar=release/'app.jar'
if jar.exists():assert hashlib.sha256(jar.read_bytes()).hexdigest()==manifest['application_sha256']
else:shutil.copy2(STAGE/'app.jar',jar);jar.chmod(0o644)
current=ROOT/'current'
if current.is_symlink():assert current.resolve()==release.resolve()
elif current.exists():raise RuntimeError('Unexpected current path; no replacement')
else:current.symlink_to(release,target_is_directory=True)
def mysql(sql):
    r=subprocess.run(['mysql','--no-defaults','--protocol=socket','-uroot','--batch','--skip-column-names','--default-character-set=utf8mb4'],input=sql.encode(),capture_output=True)
    if r.returncode:raise RuntimeError('MySQL initialization failed; credential-bearing SQL not printed')
    return r.stdout.decode().strip()
mysql((STAGE/'01_schema.sql').read_text())
exists=mysql("SELECT COUNT(*) FROM mysql.user WHERE User='lab2_app' AND Host='localhost'")
if exists=='0':mysql("CREATE USER 'lab2_app'@'localhost' IDENTIFIED BY '"+c['DB_PASSWORD']+"'; GRANT SELECT,INSERT,UPDATE,DELETE ON lab2_seckill.* TO 'lab2_app'@'localhost';")
mysql((STAGE/'02_seed.sql').read_text());mysql((STAGE/'06_async_requests.sql').read_text())
env={'APP_ADDRESS':'127.0.0.1','APP_PORT':'18092','DB_HOST':'127.0.0.1','DB_PORT':'3306','DB_NAME':'lab2_seckill','DB_USER':'lab2_app','DB_PASSWORD':c['DB_PASSWORD'],'REDIS_HOST':'127.0.0.1','REDIS_PORT':'6379','REDIS_PASSWORD':c['REDIS_PASSWORD'],'REDIS_PREFIX':'lab2:ecs:v3:','REDIS_ENABLED':'true','MQ_ENABLED':'true','MQ_CONSUMER_ENABLED':'true','ROCKETMQ_NAMESRV_ADDR':'127.0.0.1:9876','ROCKETMQ_TOPIC':'Lab2OrdersV3','ROCKETMQ_CONSUMER_GROUP':'lab2-orders-ecs-v3'}
write(CONF/'app.env',''.join(k+'='+v+'\n' for k,v in env.items()),0o600)
write('/etc/redis/lab2.conf',f'''bind 127.0.0.1
protected-mode yes
port 6379
requirepass {c['REDIS_PASSWORD']}
daemonize no
supervised systemd
dir /var/lib/redis/lab2
appendonly yes
appendfsync everysec
save 60 1000
maxmemory 96mb
maxmemory-policy noeviction
logfile ""
''',0o640)
run(['chown','root:redis','/etc/redis/lab2.conf'])
write('/etc/lab2-rocketmq/namesrv.properties','listenPort=9876\nbindAddress=127.0.0.1\n')
write('/etc/lab2-rocketmq/broker.properties','''brokerClusterName=Lab2Cluster
brokerName=lab2-ecs-broker
brokerId=0
brokerIP1=127.0.0.1
bindAddress=127.0.0.1
namesrvAddr=127.0.0.1:9876
listenPort=10911
haListenPort=10912
storePathRootDir=/var/lib/lab2-rocketmq/store
storePathCommitLog=/var/lib/lab2-rocketmq/store/commitlog
mappedFileSizeCommitLog=16777216
mappedFileSizeConsumeQueue=600000
brokerRole=ASYNC_MASTER
flushDiskType=SYNC_FLUSH
autoCreateTopicEnable=false
autoCreateSubscriptionGroup=true
fileReservedTime=24
deleteWhen=04
diskMaxUsedSpaceRatio=85
transientStorePoolEnable=false
''')
units=Path('/etc/systemd/system')
write(units/'lab2-redis.service','''[Unit]
Description=Lab2 Redis ECS
After=network.target
[Service]
Type=notify
User=redis
Group=redis
ExecStart=/usr/bin/redis-server /etc/redis/lab2.conf
Restart=on-failure
MemoryHigh=128M
MemoryMax=160M
LimitNOFILE=65535
[Install]
WantedBy=multi-user.target
''')
# HA 通配监听仅允许本机；只约束本实验新建的 10912，不更改 SSH 或其他端口。
write(ROOT/'ha-loopback-only.sh','''#!/bin/sh
set -eu
iptables -C INPUT ! -i lo -p tcp --dport 10912 -j DROP 2>/dev/null || iptables -I INPUT ! -i lo -p tcp --dport 10912 -j DROP
ip6tables -C INPUT ! -i lo -p tcp --dport 10912 -j DROP 2>/dev/null || ip6tables -I INPUT ! -i lo -p tcp --dport 10912 -j DROP
''',0o755)
for part,main,heap,limit in [('namesrv','org.apache.rocketmq.namesrv.NamesrvStartup',128,256),('broker','org.apache.rocketmq.broker.BrokerStartup',384,768)]:
    pre='ExecStartPre=+'+str(ROOT/'ha-loopback-only.sh')+'\n' if part=='broker' else ''
    after='network.target lab2-mq-namesrv.service' if part=='broker' else 'network.target'
    write(units/('lab2-mq-'+part+'.service'),f'''[Unit]
Description=Lab2 RocketMQ {part} ECS
After={after}
[Service]
Type=simple
User=lab2
Group=lab2
WorkingDirectory=/var/lib/lab2-rocketmq
Environment=JAVA_HOME={java}
Environment=ROCKETMQ_HOME={mq}
{pre}ExecStart={java}/bin/java -Xms64m -Xmx{heap}m -XX:MaxDirectMemorySize=128m --add-opens=java.base/java.nio=ALL-UNNAMED --add-opens=java.base/sun.nio.ch=ALL-UNNAMED --add-opens=java.base/java.lang=ALL-UNNAMED -Duser.home=/var/lib/lab2-rocketmq -Drocketmq.home.dir={mq} -cp {mq}/lib/* {main} -c /etc/lab2-rocketmq/{part}.properties
Restart=on-failure
RestartSec=3
TimeoutStopSec=45
MemoryHigh={limit-64}M
MemoryMax={limit}M
LimitNOFILE=65535
[Install]
WantedBy=multi-user.target
''')
write(units/'lab2-seckill.service',f'''[Unit]
Description=Lab2 async seckill ECS
After=network.target mysql.service lab2-redis.service lab2-mq-broker.service
Wants=mysql.service lab2-redis.service lab2-mq-namesrv.service lab2-mq-broker.service
[Service]
Type=simple
User=lab2
Group=lab2
WorkingDirectory=/var/lib/lab2-seckill
EnvironmentFile=/etc/lab2-seckill/app.env
ExecStart={java}/bin/java -Xms128m -Xmx384m -XX:MaxDirectMemorySize=96m -Duser.home=/var/lib/lab2-seckill -jar {current}/app.jar
Restart=on-failure
RestartSec=5
TimeoutStopSec=45
MemoryHigh=512M
MemoryMax=640M
LimitNOFILE=65535
NoNewPrivileges=true
PrivateTmp=true
[Install]
WantedBy=multi-user.target
''')
write('/etc/logrotate.d/lab2-rocketmq','''/var/lib/lab2-rocketmq/logs/rocketmqlogs/*.log /var/lib/lab2-seckill/logs/rocketmqlogs/*.log {
 daily
 maxsize 10M
 rotate 2
 compress
 missingok
 notifempty
 copytruncate
 su lab2 lab2
}
''')
run(['systemctl','daemon-reload'])
run(['systemctl','enable','--now','mysql','lab2-redis','lab2-mq-namesrv','lab2-mq-broker'])
deadline=time.monotonic()+45
while True:
    import socket
    try:
        with socket.create_connection(('127.0.0.1',10911),timeout=1):break
    except OSError:
        if time.monotonic()>deadline:raise RuntimeError('Broker did not become reachable')
        time.sleep(.5)
run([str(java/'bin/java'),'-Xms32m','-Xmx128m','-Drocketmq.home.dir='+str(mq),'-cp',str(mq/'lib/*'),'org.apache.rocketmq.tools.command.MQAdminStartup','updateTopic','-n','127.0.0.1:9876','-b','127.0.0.1:10911','-t','Lab2OrdersV3','-r','4','-w','4'])
run(['systemctl','enable','--now','lab2-seckill'])
assert os.path.realpath('/usr/bin/java')==json.loads(Path('/var/tmp/lab2-preflight.json').read_text())['default_java_path']
write(ROOT/'deployment.json',json.dumps({k:v for k,v in manifest.items() if k!='downloads'},indent=2))
print('LAB2_CONFIGURED')
