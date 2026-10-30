"""本机 build/test/run 入口，读取项目外应用配置，不读取或保存管理员密码。"""
from pathlib import Path
import argparse
import json
import os
import shutil
import subprocess
import sys
import socket
import time
import hashlib

ROOT=Path(__file__).resolve().parents[1]

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=["build","test","run"])
    p.add_argument("--env-file",type=Path,default=Path(os.environ.get("LAB2_ENV_FILE",ROOT.parent/"实验记录/本机私用/app-env.json")))
    p.add_argument("--maven",default=os.environ.get("MAVEN_BIN") or shutil.which("mvn") or r"E:\Java\apache-maven-3.9.16\bin\mvn.cmd")
    args=p.parse_args()
    env=os.environ.copy()
    env["MAVEN_OPTS"]=(env.get("MAVEN_OPTS","")+" -Dfile.encoding=UTF-8 -Dsun.stdout.encoding=UTF-8 -Dsun.stderr.encoding=UTF-8").strip()
    if args.env_file.exists(): env.update({k:str(v) for k,v in json.loads(args.env_file.read_text(encoding="utf-8")).items()})
    if args.action in ["test","run"] and not env.get("DB_PASSWORD"):
        sys.exit("缺少应用数据库配置。先初始化数据库，或通过 --env-file 指定项目外配置。")
    keep=None
    if os.name=="nt" and args.action in ["test","run"] and env.get("REDIS_HOST")=="127.0.0.1":
        def redis_port_open():
            try:
                with socket.create_connection(('127.0.0.1',int(env.get('REDIS_PORT','6379'))),timeout=1):return True
            except OSError:return False
        # systemd 服务本身不能保证 WSL 在无客户端时保持运行。
        # 为本次运行保持发行版，结束时终止此入口创建的保活客户端，不改网络规则。
        keep=subprocess.Popen(['wsl','-d','Ubuntu','--exec','sleep','infinity'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
        if not redis_port_open():
            until=time.monotonic()+15
            while not redis_port_open() and time.monotonic()<until:time.sleep(.25)
            if not redis_port_open():
                keep.terminate()
                sys.exit('本机 Redis 不可达，请检查 WSL 的 lab2-redis 服务。')
    if args.action=="run":
        jar=ROOT/"target/seckill-lab2-0.2.0-cache.jar"
        if not jar.exists():
            if keep is not None:keep.terminate()
            sys.exit("尚未打包，请先运行 build。")
        # 从独立运行副本启动，避免 Windows 锁住 target 中的下一次构建产物。
        runtime=ROOT.parent/'实验记录/本机私用/runtime'
        runtime.mkdir(parents=True,exist_ok=True)
        copied=runtime/(jar.stem+'-'+hashlib.sha256(jar.read_bytes()).hexdigest()[:12]+'.jar')
        if not copied.exists():shutil.copy2(jar,copied)
        java=Path(env["JAVA_HOME"])/"bin/java.exe" if env.get("JAVA_HOME") and os.name=="nt" else shutil.which("java")
        command=[str(java),"-Xms128m","-Xmx384m","-jar",str(copied)]
    else:
        command=[args.maven,"--batch-mode","--no-transfer-progress","-Dstyle.color=never"]
        command += ["test"] if args.action=="test" else ["-DskipTests","package"]
    try: result=subprocess.run(command,cwd=ROOT,env=env).returncode
    finally:
        if keep is not None:keep.terminate()
    sys.exit(result)

