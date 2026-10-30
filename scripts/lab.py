"""本机 build/test/run 入口，读取项目外应用配置，不读取或保存管理员密码。"""
from pathlib import Path
import argparse
import json
import os
import shutil
import subprocess
import sys

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
    if args.action=="run":
        jar=ROOT/"target/seckill-lab2-0.1.0-db.jar"
        if not jar.exists(): sys.exit("尚未打包，请先运行 build。")
        java=Path(env["JAVA_HOME"])/"bin/java.exe" if env.get("JAVA_HOME") and os.name=="nt" else shutil.which("java")
        command=[str(java),"-Xms128m","-Xmx384m","-jar",str(jar)]
    else:
        command=[args.maven,"--batch-mode","--no-transfer-progress","-Dstyle.color=never"]
        command += ["test"] if args.action=="test" else ["-DskipTests","package"]
    sys.exit(subprocess.run(command,cwd=ROOT,env=env).returncode)

