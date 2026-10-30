"""通过 WSL 调用本机 redis-cli；密码不进入命令行或输出。"""
from pathlib import Path
import json,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
def redis_commands(commands):
    config=json.loads((ROOT.parent/'实验记录/本机私用/app-env.json').read_text(encoding='utf-8'))
    code="""import sys,json,os,subprocess
p=PAYLOAD
os.environ['REDISCLI_AUTH']=p['password']
rows=[]
for command in p['commands']:
 r=subprocess.run(['redis-cli','--raw']+command,capture_output=True,text=True)
 rows.append({'command':command,'exit_code':r.returncode,'output':r.stdout.strip(),'stderr':r.stderr.strip()})
print(json.dumps(rows,ensure_ascii=False))
"""
    code=code.replace('PAYLOAD',repr({'password':config['REDIS_PASSWORD'],'commands':commands}))
    p=subprocess.run(['wsl','-d','Ubuntu','--exec','python3'],input=code.encode(),capture_output=True)
    if p.returncode:raise RuntimeError('WSL redis-cli failed')
    return json.loads(p.stdout.decode('utf-8'))
if __name__=='__main__':
    print(json.dumps(redis_commands([sys.argv[1:]]),ensure_ascii=False,indent=2))
