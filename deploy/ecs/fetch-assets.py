"""从经核验的官方地址下载两个固定发行包；校验成功才接受文件。"""
from pathlib import Path
import hashlib,json,subprocess
ROOT=Path('/opt/lab2-seckill/staging')
manifest=json.loads((ROOT/'assets.json').read_text())
for item in manifest['downloads']:
    file=ROOT/item['name'];algorithm=item['algorithm']
    def valid(path):return path.exists() and hashlib.new(algorithm,path.read_bytes()).hexdigest()==item['checksum']
    if not valid(file):
        partial=file.with_suffix(file.suffix+'.part')
        subprocess.run(['curl','-fL','--retry','2','--connect-timeout','15','--max-time','600','-o',str(partial),item['url']],check=True)
        assert valid(partial),'Official archive checksum mismatch'
        partial.replace(file)
    print(json.dumps({'verified':item['name'],'algorithm':algorithm,'bytes':file.stat().st_size}),flush=True)
print('LAB2_ASSETS_READY')
