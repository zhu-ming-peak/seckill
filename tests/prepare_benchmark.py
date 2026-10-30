"""按固定 Git 标签导出到项目外，逐版运行原有测试并构建；不改当前工作树。"""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,tarfile,time,urllib.request,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
TAGS=['v0.1.0-db','v0.2.0-cache','v0.3.0-async']
def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--env-file',type=Path,default=ROOT.parent/'实验记录/本机私用/app-env.json');a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    try:
        with urllib.request.urlopen('http://127.0.0.1:18092/health',timeout=2):pass
    except OSError:pass
    else:raise RuntimeError('先停止演示应用，避免测试请求被后台扫描')
    env=os.environ.copy();env.update({k:str(v) for k,v in json.loads(a.env_file.read_text(encoding='utf-8')).items()})
    env.setdefault('JAVA_HOME',r'E:\Java\jdk-17');env['MAVEN_OPTS']='-Dfile.encoding=UTF-8 -Dsun.stdout.encoding=UTF-8 -Dsun.stderr.encoding=UTF-8'
    maven=env.get('MAVEN_BIN',r'E:\Java\apache-maven-3.9.16\bin\mvn.cmd')
    keep=subprocess.Popen(['wsl','-d','Ubuntu','--exec','sleep','infinity'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
    rows=[]
    try:
        for tag in TAGS:
            commit=subprocess.run(['git','rev-parse',tag],cwd=ROOT,capture_output=True,text=True,check=True).stdout.strip()
            target=out/tag
            if target.exists():raise RuntimeError('构建目录已存在；请选新的输出目录，不覆盖旧证据')
            archive=out/(tag+'.tar')
            subprocess.run(['git','archive','--format=tar','-o',str(archive),tag],cwd=ROOT,check=True)
            target.mkdir()
            with tarfile.open(archive) as source:source.extractall(target,filter='data')
            log=out/(tag+'-build.log');started=time.time()
            with log.open('wb') as stream:
                result=subprocess.run([maven,'--batch-mode','--no-transfer-progress','-Dstyle.color=never','test','package'],cwd=target,env=env,stdout=stream,stderr=subprocess.STDOUT)
            if result.returncode:raise RuntimeError('历史版本构建/测试失败，日志：'+str(log))
            suites=[ET.parse(f).getroot() for f in (target/'target/surefire-reports').glob('TEST-*.xml')]
            counts={k:sum(int(s.get(k,'0')) for s in suites) for k in ['tests','failures','errors','skipped']}
            assert counts['tests']>0 and counts['failures']==counts['errors']==counts['skipped']==0
            jar=target/'target'/('seckill-lab2-'+tag[1:]+'.jar')
            rows.append({'tag':tag,'commit':commit,'jar':str(jar),'jar_sha256':hashlib.sha256(jar.read_bytes()).hexdigest(),'tests':counts,'build_seconds':time.time()-started})
            (out/'artifacts.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({'tag':tag,'tests':counts,'build':'PASS'}),flush=True)
    finally:keep.terminate()
if __name__=='__main__':main()
