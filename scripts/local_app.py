"""启动/停止本项目的本机演示副本；只终止清单中且命令行匹配的 Java 进程。"""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,time,urllib.request
ROOT=Path(__file__).resolve().parents[1]
PRIVATE=ROOT.parent/'实验记录/本机私用'
MANIFEST=PRIVATE/'app-process.json'
def command_line(pid):
    query=f"[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; (Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}' -ErrorAction Stop).CommandLine"
    r=subprocess.run(['powershell','-NoProfile','-Command',query],capture_output=True,text=True,encoding='utf-8')
    if r.returncode:raise RuntimeError('无法核验进程，未对进程执行操作')
    return r.stdout.strip()
def stop():
    if not MANIFEST.exists():return
    info=json.loads(MANIFEST.read_text(encoding='utf-8'))
    line=command_line(info['pid'])
    if not line:return
    if info['jar'] not in line or 'java' not in line.lower():raise RuntimeError('进程与本项目清单不符，未停止')
    subprocess.run(['powershell','-NoProfile','-Command',f"Stop-Process -Id {int(info['pid'])} -ErrorAction Stop"],check=True)
    if info.get('wsl_pid'):
        line=command_line(info['wsl_pid'])
        if 'wsl' in line.lower() and 'sleep infinity' in line:subprocess.run(['powershell','-NoProfile','-Command',f"Stop-Process -Id {int(info['wsl_pid'])} -ErrorAction Stop"],check=True)
    print('已停止清单匹配的本项目演示进程',info['pid'])
def start(consumer):
    if MANIFEST.exists():
        old=json.loads(MANIFEST.read_text(encoding='utf-8'))
        if command_line(old['pid']):raise RuntimeError('清单中的进程仍存在，请先检查并停止')
    env=os.environ.copy();env.update({k:str(v) for k,v in json.loads((PRIVATE/'app-env.json').read_text(encoding='utf-8')).items()})
    env.update(MQ_ENABLED='true',MQ_CONSUMER_ENABLED=str(consumer=='running').lower(),REDIS_PREFIX='lab2:v3:')
    jar=ROOT/'target/seckill-lab2-0.3.0-async.jar'
    digest=hashlib.sha256(jar.read_bytes()).hexdigest()
    runtime=PRIVATE/'runtime';runtime.mkdir(exist_ok=True)
    copied=runtime/(jar.stem+'-'+digest[:12]+'.jar')
    if not copied.exists():shutil.copy2(jar,copied)
    java=str(Path(env.get('JAVA_HOME',r'E:\Java\jdk-17'))/'bin/java.exe')
    log=PRIVATE/('app-async-'+time.strftime('%Y%m%d-%H%M%S')+'.log')
    keep=subprocess.Popen(['wsl','-d','Ubuntu','--exec','sleep','infinity'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
    with log.open('ab') as output:
        process=subprocess.Popen([java,'-Xms128m','-Xmx384m','-jar',str(copied)],cwd=ROOT,env=env,stdout=output,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    info={'pid':process.pid,'wsl_pid':keep.pid,'jar':str(copied),'sha256':digest,'port':int(env.get('APP_PORT','18092')),'consumer':consumer,'log':str(log)}
    MANIFEST.write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
    for _ in range(50):
        if process.poll() is not None:raise RuntimeError('启动失败，请检查项目外运行日志')
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{info['port']}/health",timeout=2) as response:
                result=json.load(response)
            if result.get('version')=='0.3.0-async' and result.get('rocketmq')=='CLIENTS_STARTED':print(json.dumps({'pid':process.pid,'consumer':consumer,'health':result},ensure_ascii=False));return
        except (OSError,ValueError):pass
        time.sleep(.5)
    raise RuntimeError('启动尚未就绪，请检查日志；不会擅自结束进程')
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['start','stop','status']);parser.add_argument('--consumer',choices=['running','paused'],default='running');args=parser.parse_args()
    if args.action=='stop':stop()
    elif args.action=='start':start(args.consumer)
    elif MANIFEST.exists():
        info=json.loads(MANIFEST.read_text(encoding='utf-8'));print(json.dumps({**info,'running':bool(command_line(info['pid']))},ensure_ascii=False,indent=2))
