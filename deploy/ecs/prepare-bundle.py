"""在本机生成待传输的 ECS 部署包，实际 JAR 与各文件校验值入清单。"""
from pathlib import Path
import argparse,hashlib,json,shutil,subprocess,tarfile
ROOT=Path(__file__).resolve().parents[2]
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--jar',type=Path,default=ROOT/'target/seckill-lab2-0.3.0-async.jar');p.add_argument('--jar-source-commit',required=True,help='实际构建该 JAR 的源码提交，不能用当前 HEAD 猜测');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    if any((out/name).exists() for name in ['app.jar','assets.json','deployment-files.tar']):raise RuntimeError('输出文件已存在，拒绝覆盖旧部署材料')
    lock=json.loads((ROOT/'deploy/ecs/assets.lock.json').read_text(encoding='utf-8'))
    commit=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True,check=True).stdout.strip()
    jar_commit=subprocess.run(['git','rev-parse','--verify',a.jar_source_commit+'^{commit}'],cwd=ROOT,capture_output=True,text=True,check=True).stdout.strip()
    dirty=bool(subprocess.run(['git','status','--porcelain'],cwd=ROOT,capture_output=True,check=True).stdout)
    shutil.copy2(a.jar,out/'app.jar')
    manifest={**lock,'application_release':'v0.3.0-async-'+jar_commit[:7],'application_source_commit':jar_commit,'deployment_material_commit':commit,'source_tree_dirty':dirty,'application_sha256':hashlib.sha256((out/'app.jar').read_bytes()).hexdigest()}
    (out/'assets.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    with tarfile.open(out/'deployment-files.tar','w') as t:
        for name in ['prepare-system.sh','fetch-assets.py','configure.py','ecsctl.py']:t.add(ROOT/'deploy/ecs'/name,arcname=name)
        for name in ['01_schema.sql','02_seed.sql','06_async_requests.sql']:t.add(ROOT/'sql'/name,arcname=name)
        t.add(out/'assets.json',arcname='assets.json')
    print(json.dumps({'output':str(out),'commit':commit,'source_tree_dirty':dirty,'application_sha256':manifest['application_sha256']},ensure_ascii=False))
