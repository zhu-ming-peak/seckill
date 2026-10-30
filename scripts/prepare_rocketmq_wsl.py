"""从 Apache 官方发行源下载并校验 RocketMQ，在本机 WSL 安装独立服务。"""
from pathlib import Path
import hashlib,json,re,subprocess,urllib.request
ROOT=Path(__file__).resolve().parents[1]
cache=ROOT.parent/'实验记录/本机私用/downloads'
cache.mkdir(parents=True,exist_ok=True)
name='rocketmq-all-5.5.1-bin-release.zip'
url='https://dist.apache.org/repos/dist/release/rocketmq/5.5.1/'+name
archive=cache/name
checksum=urllib.request.urlopen(url+'.sha512',timeout=60).read().decode()
if not archive.exists():
    with urllib.request.urlopen(url,timeout=120) as response, archive.open('wb') as output:
        while block:=response.read(1024*1024):output.write(block)
digest=hashlib.sha512(archive.read_bytes()).hexdigest()
expected=''.join(re.findall(r'\b(?:[0-9a-fA-F]{128}|[0-9a-fA-F]{8})\b',checksum)).lower()
assert len(expected)==128 and digest.lower()==expected,'Apache SHA512 verification failed'
print('Apache RocketMQ 5.5.1 SHA512 verified',flush=True)
(cache/'rocketmq-sha512.json').write_text(json.dumps({'source':url,'sha512':digest}),encoding='utf-8')
wsl_archive='/mnt/'+archive.drive[0].lower()+archive.as_posix()[2:]
payload={'archive':wsl_archive,'script':(ROOT/'deploy/rocketmq/install-wsl.sh').read_text(encoding='utf-8')}
code='import os,json,subprocess,sys\np='+repr(payload)+'\nos.environ["LAB2_ROCKETMQ_ARCHIVE"]=p["archive"]\nsys.exit(subprocess.run(["bash","-c",p["script"]],stdin=subprocess.DEVNULL).returncode)\n'
result=subprocess.run(['wsl','-d','Ubuntu','-u','root','--exec','python3'],input=code.encode())
raise SystemExit(result.returncode)
