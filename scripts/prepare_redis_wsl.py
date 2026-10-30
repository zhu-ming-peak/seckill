"""安装本机 WSL Redis；凭据保存在项目外配置，不打印。"""
from pathlib import Path
import json,os,secrets,subprocess,sys
root=Path(__file__).resolve().parents[1]
private=root.parent/'实验记录/本机私用/app-env.json'
config=json.loads(private.read_text(encoding='utf-8'))
password=config.get('REDIS_PASSWORD') or secrets.token_urlsafe(32)
config.update(REDIS_HOST='127.0.0.1',REDIS_PORT='6379',REDIS_PASSWORD=password)
private.write_text(json.dumps(config,indent=2),encoding='utf-8')
script=(root/'deploy/redis/install-wsl.sh').read_text(encoding='utf-8')
# URL-safe 生成密码仅含字母数字、下划线、短横线，作为 Bash 字面量传入标准输入。
command="import sys,json,os,subprocess\np=json.loads("+repr(json.dumps({'password':password,'script':script}))+ ")\nos.environ['LAB2_REDIS_PASSWORD']=p['password']\nsys.exit(subprocess.run(['bash','-c',p['script']],stdin=subprocess.DEVNULL).returncode)\n"
result=subprocess.run(['wsl','-d','Ubuntu','-u','root','--exec','python3'],input=command.encode())
print('WSL installer exit code:',result.returncode)
sys.exit(result.returncode)
