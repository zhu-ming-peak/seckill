"""本机闭环 HTTP 对比：历史 JAR、专用活动、逐请求原始数据、事务可见性观察。

不会重置展示活动；用应用账户操作自己在清单中创建的实验数据。依赖见 requirements-benchmark.txt。
"""
from pathlib import Path
import argparse,collections,concurrent.futures,csv,datetime,hashlib,http.client,json,math,os,platform,random,socket,statistics,subprocess,sys,threading,time,uuid
ROOT=Path(__file__).resolve().parents[1]
LOCAL_SITE=ROOT.parent/'实验记录/本机私用/stageE-python'
if LOCAL_SITE.exists():sys.path.insert(0,str(LOCAL_SITE))
import psutil
import pymysql

def dump(path,value):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
def percentile(values,p):
    v=sorted(values)
    if not v:return None
    k=(len(v)-1)*p;lo=math.floor(k);hi=math.ceil(k)
    return v[lo]+(v[hi]-v[lo])*(k-lo)
def latency(values):
    return {'mean_ms':statistics.mean(values),'p50_ms':percentile(values,.5),'p95_ms':percentile(values,.95),'p99_ms':percentile(values,.99),'max_ms':max(values)} if values else {}

class Redis:
    """本机实验使用的最小 RESP 客户端，密码只在进程内传入 AUTH。"""
    def __init__(self,c):
        self.socket=socket.create_connection((c['REDIS_HOST'],int(c['REDIS_PORT'])),timeout=5);self.stream=self.socket.makefile('rb')
        self.call('AUTH',c['REDIS_PASSWORD'])
    def read(self):
        line=self.stream.readline();kind=line[:1];body=line[1:-2]
        if kind==b'+':return body.decode()
        if kind==b'-':raise RuntimeError('Redis command failed')
        if kind==b':':return int(body)
        if kind==b'$':
            n=int(body)
            if n<0:return None
            value=self.stream.read(n);assert self.stream.read(2)==b'\r\n';return value.decode()
        if kind==b'*':return [self.read() for _ in range(int(body))]
        raise RuntimeError('Redis protocol error')
    def call(self,*args):
        values=[str(x).encode() for x in args]
        self.socket.sendall(b'*'+str(len(values)).encode()+b'\r\n'+b''.join(b'$'+str(len(v)).encode()+b'\r\n'+v+b'\r\n' for v in values));return self.read()
    def close(self):self.stream.close();self.socket.close()

class Client:
    def __init__(self,port):self.port=port;self.conn=None
    def call(self,path,body=None):
        start=time.perf_counter();status=0;data={};headers={};error=None
        try:
            if self.conn is None:self.conn=http.client.HTTPConnection('127.0.0.1',self.port,timeout=30)
            payload=json.dumps(body).encode() if body is not None else None
            self.conn.request('POST' if body is not None else 'GET',path,body=payload,headers={'Content-Type':'application/json','Connection':'keep-alive'})
            r=self.conn.getresponse();status=r.status;headers={k.lower():v for k,v in r.getheaders()};raw=r.read();data=json.loads(raw)
        except Exception as e:
            error=type(e).__name__
            if self.conn:self.conn.close();self.conn=None
        end=time.perf_counter()
        return {'start':start,'end':end,'latency_ms':(end-start)*1000,'status':status,'data':data,'cache':headers.get('x-product-cache'),'error':error}
    def close(self):
        if self.conn:self.conn.close()

class Database:
    def __init__(self,c):self.c=c
    def connect(self):
        return pymysql.connect(host=self.c['DB_HOST'],port=int(self.c['DB_PORT']),user=self.c['DB_USER'],password=self.c['DB_PASSWORD'],database=self.c['DB_NAME'],charset='utf8mb4',autocommit=True,cursorclass=pymysql.cursors.DictCursor,connect_timeout=5,read_timeout=15)
    def query(self,sql,args=()):
        with self.connect() as db:
            with db.cursor() as cur:cur.execute(sql,args);return cur.fetchall()
    def execute(self,sql,args=()):
        with self.connect() as db:
            with db.cursor() as cur:return cur.execute(sql,args)
    def demo(self):
        return {'activities':self.query('SELECT * FROM seckill_activity WHERE id IN (1,2,3,4,5) ORDER BY id'),'orders':self.query('SELECT * FROM seckill_order WHERE activity_id IN (1,2,3,4,5) ORDER BY id'),'requests':self.query('SELECT * FROM seckill_request WHERE activity_id IN (1,2,3,4,5) ORDER BY request_id')}

class Monitor:
    def __init__(self,app_pid,mysql_port=3306):
        self.stop=threading.Event();self.rows=[];self.processes={'app':psutil.Process(app_pid),'generator':psutil.Process()}
        # Windows 存在同名监护进程，不能按 mysqld.exe 名称取第一个。
        owners={c.pid for c in psutil.net_connections(kind='tcp') if c.status==psutil.CONN_LISTEN and c.laddr.port==mysql_port and c.pid}
        if len(owners)!=1:raise RuntimeError('不能唯一确认本机 MySQL 监听进程，未开始测量')
        server=psutil.Process(owners.pop())
        if server.name().lower()!='mysqld.exe':raise RuntimeError('数据库端口进程名称不符')
        self.processes['mysql']=server;self.mysql_port=mysql_port
    def sample(self):
        value={'time':time.perf_counter(),'unix':time.time(),'host_cpu_pct':psutil.cpu_percent(),'host_available_mib':psutil.virtual_memory().available/2**20}
        for name,p in self.processes.items():
            try:
                t=p.cpu_times();value[name+'_cpu_seconds']=t.user+t.system;value[name+'_rss_mib']=p.memory_info().rss/2**20;value[name+'_pid']=p.pid
            except (psutil.NoSuchProcess,psutil.AccessDenied):value[name+'_unavailable']=True
        self.rows.append(value)
        value['mysql_listen_port']=self.mysql_port
        value['mysql_probe_valid']=True
    def begin(self):
        self.sample()
        def poll():
            while not self.stop.wait(.2):self.sample()
        self.thread=threading.Thread(target=poll);self.thread.start();return self
    def finish(self):
        self.stop.set();self.thread.join();self.sample();return self.rows
    @staticmethod
    def summary(rows):
        measured=rows[1:] or rows
        result={'resource_samples':len(rows),'host_cpu_pct_max':max(r['host_cpu_pct'] for r in measured),'host_available_mib_min':min(r['host_available_mib'] for r in rows)}
        elapsed=rows[-1]['time']-rows[0]['time']
        for name in ['app','mysql','generator']:
            r=[x for x in rows if name+'_cpu_seconds' in x]
            if len(r)>1:
                result[name+'_cpu_seconds']=r[-1][name+'_cpu_seconds']-r[0][name+'_cpu_seconds']
                result[name+'_cpu_pct_one_core']=result[name+'_cpu_seconds']/elapsed*100
                result[name+'_rss_mib_max']=max(x[name+'_rss_mib'] for x in r)
        return result

class Experiment:
    def __init__(self,args):
        self.args=args;self.out=args.output.resolve()
        check=Client(18092)
        try:
            if check.call('/health')['status']==200:raise RuntimeError('请先停止演示应用，再运行性能测试')
        finally:check.close()
        if (self.out/'manifest.json').exists():raise RuntimeError('输出清单已存在，不覆盖既有试验；请换新的目录')
        self.out.mkdir(parents=True,exist_ok=True)
        self.c=json.loads(args.env_file.read_text(encoding='utf-8'));self.db=Database(self.c);self.redis=Redis(self.c)
        self.artifacts=json.loads(args.artifacts.read_text(encoding='utf-8'));self.run_id=uuid.uuid4().hex[:10]
        self.rows=[];self.functional=[];self.fixtures=[];self.prefix='lab2:bench:'+self.run_id+':'
        self.app=None;self.current={};self.zero=time.perf_counter();self.keep=None
        used={r['id'] for r in self.db.query('SELECT id FROM seckill_activity WHERE id BETWEEN 910000 AND 919999 UNION SELECT id FROM product WHERE id BETWEEN 910000 AND 919999')}
        self.base=next(n for n in range(910000,919800,200) if not any(n<=x<n+200 for x in used));self.next_id=self.base+1
        self.manifest={'run_id':self.run_id,'driver_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'mysql_probe':'unique LISTEN PID on configured MySQL port; PID stored in each sample','created_at':datetime.datetime.now().astimezone().isoformat(),'artifacts':self.artifacts,'base_id':self.base,'product_id':self.base,'fixtures':self.fixtures,'config':{'concurrency':[1,8,16],'repetitions':3,'read_seconds':args.read_seconds,'burst_requests':128,'burst_stock':128,'http_port':args.port,'jdbc_pool_max':12,'jvm_heap_mib':[128,384],'cache_ttl_seconds':3600,'observation_interval_seconds':.1,'http_timeout_seconds':30,'drain_timeout_seconds':90,'mq_topic':'Lab2OrdersBenchE','mq_dispatch_batch':20,'mq_dispatch_delay_ms':2000,'metrics':'closed-loop persistent HTTP per worker; first committed DB visibility for completion'},'system':{'platform':platform.platform(),'python':sys.version,'logical_cpus':psutil.cpu_count(),'physical_cpus':psutil.cpu_count(logical=False),'total_memory_mib':psutil.virtual_memory().total/2**20,'cpu_frequency':psutil.cpu_freq()._asdict() if psutil.cpu_freq() else None},'demo_before':self.db.demo()}
        self.save_manifest()
        self.db.execute('INSERT INTO product(id,name,description,regular_price) VALUES(%s,%s,%s,30.00)',(self.base,'bench-'+self.run_id,'Stage E dedicated disposable fixture'))
    def save_manifest(self):dump(self.out/'manifest.json',self.manifest)
    def emit(self,event,**kw):
        row={'time':datetime.datetime.now().astimezone().isoformat(),'event':event,**kw};print(json.dumps(row,ensure_ascii=False),flush=True)
        with (self.out/'events.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
    def fixture(self,stock,label,status='ACTIVE',timing='open'):
        aid=self.next_id;self.next_id+=1;assert aid<self.base+200
        self.fixtures.append(aid);self.save_manifest()
        times={'open':('-1 HOUR','1 DAY'),'upcoming':('1 DAY','2 DAY'),'ended':('-2 DAY','-1 DAY')}
        start,end=times[timing]
        sql='INSERT INTO seckill_activity VALUES(%s,%s,%s,9.90,%s,%s,NOW(6)+INTERVAL '+start+',NOW(6)+INTERVAL '+end+',%s)'
        self.db.execute(sql,(aid,self.base,'bench:'+self.run_id+':'+label,stock,stock,status));return aid
    def start(self,artifact,rep):
        self.stop()
        with socket.socket() as check:
            if check.connect_ex(('127.0.0.1',self.args.port))==0:raise RuntimeError('测试端口已被占用，未结束其他进程')
        jar=Path(artifact['jar']);assert hashlib.sha256(jar.read_bytes()).hexdigest()==artifact['jar_sha256']
        env=os.environ.copy();env.update({k:str(v) for k,v in self.c.items()});version=artifact['tag'][1:]
        self.current={'version':version,'rep':rep,'prefix':self.prefix+version+':r'+str(rep)+':'}
        env.update(APP_PORT=str(self.args.port),APP_ADDRESS='127.0.0.1',REDIS_PREFIX=self.current['prefix'],PRODUCT_CACHE_TTL_SECONDS='3600',MQ_ENABLED='true',MQ_CONSUMER_ENABLED='true',ROCKETMQ_TOPIC='Lab2OrdersBenchE',ROCKETMQ_CONSUMER_GROUP='lab2-bench-'+self.run_id)
        java=str(Path(env.get('JAVA_HOME',r'E:\Java\jdk-17'))/'bin/java.exe')
        with (self.out/(version+'-r'+str(rep)+'.log')).open('wb') as stream:
            self.app=subprocess.Popen([java,'-Xms128m','-Xmx384m','-jar',str(jar)],cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        dump(self.out/'active-process.json',{'pid':self.app.pid,'jar':str(jar),**self.current})
        cli=Client(self.args.port);deadline=time.monotonic()+45
        try:
            while time.monotonic()<deadline:
                if self.app.poll() is not None:raise RuntimeError('测试应用启动失败，见原始日志')
                r=cli.call('/health')
                if r['status']==200 and r['data'].get('version')==version and (not self.async_mode() or r['data'].get('rocketmq')=='CLIENTS_STARTED'):break
                time.sleep(.25)
            else:raise RuntimeError('测试应用启动超时')
        finally:cli.close()
        self.emit('app_ready',**self.current,pid=self.app.pid)
    def stop(self):
        if self.app and self.app.poll() is None:self.app.terminate();self.app.wait(timeout=15)
        self.app=None
    def async_mode(self):return self.current.get('version')=='0.3.0-async'
    def persist_raw(self,name,requests,resources,trace=None):
        dest=self.out/'raw';dest.mkdir(exist_ok=True)
        with (dest/(name+'-requests.jsonl')).open('w',encoding='utf-8') as f:
            for r in requests:f.write(json.dumps(r,ensure_ascii=False,default=str)+'\n')
        dump(dest/(name+'-resources.json'),resources)
        if trace is not None:dump(dest/(name+'-completion.json'),trace)
    def summarize(self,kind,name,concurrency,requests,start,end,resources,**extra):
        values=[r['latency_ms'] for r in requests]
        row={'kind':kind,'name':name,'version':self.current['version'],'rep':self.current['rep'],'concurrency':concurrency,'request_count':len(requests),'elapsed_seconds':end-start,'response_rps':len(requests)/(end-start),'http_2xx':sum(200<=r['status']<300 for r in requests),'transport_errors':sum(r['status']==0 for r in requests),'http_5xx':sum(r['status']>=500 for r in requests),'statuses':dict(collections.Counter(str(r['status']) for r in requests)),**latency(values),**Monitor.summary(resources),**extra}
        self.rows.append(row);dump(self.out/'summary.json',self.rows);self.emit('scenario_done',kind=kind,version=row['version'],rep=row['rep'],concurrency=concurrency,requests=len(requests),rps=round(row['response_rps'],2),p95_ms=round(row['p95_ms'],2),**{k:row[k] for k in ['orders','completion_p95_ms','invariant_pass'] if k in row})
        return row
    def read_load(self,aid,concurrency,seconds,measure=True):
        name=f"{self.current['version']}-r{self.current['rep']}-read-c{concurrency}";ready=threading.Barrier(concurrency+1);release=threading.Event();deadline=[0]
        def worker():
            cli=Client(self.args.port);result=[];ready.wait();release.wait()
            try:
                while time.perf_counter()<deadline[0]:
                    r=cli.call('/api/activities/'+str(aid));r.pop('data',None);result.append(r)
            finally:cli.close()
            return result
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures=[pool.submit(worker) for _ in range(concurrency)];ready.wait();monitor=Monitor(self.app.pid,int(self.c['DB_PORT'])).begin();start=time.perf_counter();deadline[0]=start+seconds;release.set();requests=[r for f in futures for r in f.result()];end=time.perf_counter();resources=monitor.finish()
        assert all(r['status']==200 and not r['error'] for r in requests),'unexpected read error'
        if measure:self.persist_raw(name,requests,resources);self.summarize('read',name,concurrency,requests,start,end,resources)
    def snapshot(self,aid):
        a=self.db.query('SELECT id,initial_stock,stock FROM seckill_activity WHERE id=%s',(aid,))[0]
        orders=self.db.query('SELECT id,request_id,user_id,created_at FROM seckill_order WHERE activity_id=%s ORDER BY created_at,id',(aid,))
        requests=self.db.query('SELECT request_id,state,order_id,send_count,processing_attempts,redis_done FROM seckill_request WHERE activity_id=%s ORDER BY request_id',(aid,))
        a.update(orders=orders,requests=requests,accepted=sum(r['state']=='ACCEPTED' for r in requests),failed=sum(r['state']=='FAILED' for r in requests))
        a['inventory_difference']=a['initial_stock']-a['stock']-len(orders)
        a['duplicate_buyers']=len(orders)-len({o['user_id'] for o in orders})
        if self.current['version']!='0.1.0-db':
            fields=self.redis.call('HGETALL',self.current['prefix']+'activity:{'+str(aid)+'}:reservation');h=dict(zip(fields[::2],fields[1::2]));a['redis_stock']=int(h['stock']) if 'stock' in h else None;a['redis_pending']=sum(k.startswith('token:') and v=='PENDING' for k,v in h.items())
        a['invariant_pass']=a['inventory_difference']==a['duplicate_buyers']==a['accepted']==a['failed']==0 and (self.current['version']=='0.1.0-db' or (a['redis_stock']==a['stock'] and a['redis_pending']==0))
        return a
    def burst(self,aid,concurrency,count,label='write',measure=True,same_user=False,expected_orders=None):
        name=f"{self.current['version']}-r{self.current['rep']}-{label}-c{concurrency}";ready=threading.Barrier(concurrency+1);release=threading.Event();observer_stop=threading.Event();observed={};trace=[];observer_errors=[]
        with self.db.connect() as db:
            def observe():
                try:
                    with db.cursor() as cur:
                        while not observer_stop.is_set():
                            cur.execute('SELECT request_id FROM seckill_order WHERE activity_id=%s',(aid,));ids=[x['request_id'] for x in cur.fetchall()];now=time.perf_counter()
                            for rid in ids:observed.setdefault(rid,now)
                            trace.append({'time':now,'orders':len(ids)})
                            observer_stop.wait(.1)
                except Exception as e:observer_errors.append(type(e).__name__)
            watch=threading.Thread(target=observe);watch.start()
            def worker(index):
                cli=Client(self.args.port);result=[];ready.wait();release.wait()
                try:
                    for i in range(index,count,concurrency):
                        user=('same' if same_user else str(i));rid=self.run_id+'-'+str(aid)+'-'+str(i)
                        r=cli.call('/api/activities/'+str(aid)+'/orders',{'userId':'bench_'+self.run_id+'_'+str(aid)+'_'+user,'requestId':rid})
                        r.update(request_id=rid,index=i,code=r['data'].get('code'),response_state=r['data'].get('state'));r.pop('data',None);result.append(r)
                finally:cli.close()
                return result
            monitor=Monitor(self.app.pid,int(self.c['DB_PORT'])).begin()
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
                    futures=[pool.submit(worker,i) for i in range(concurrency)];ready.wait();start=time.perf_counter();release.set();requests=[r for f in futures for r in f.result()];response_end=time.perf_counter()
                accepted={r['request_id'] for r in requests if r['status'] in (200,202)};deadline=time.monotonic()+90
                while not accepted.issubset(observed) and time.monotonic()<deadline:
                    if observer_errors:raise RuntimeError('completion observer failed')
                    time.sleep(.05)
                assert accepted.issubset(observed),'accepted requests did not complete within drain deadline'
            finally:observer_stop.set();watch.join();resources=monitor.finish()
        assert not observer_errors
        for r in requests:r['completion_observed_ms']=(observed[r['request_id']]-r['start'])*1000 if r['request_id'] in observed else None
        # ACK 后 Redis 修复可能晚于订单可见性，分开等待核对，不计入完成延迟。
        until=time.monotonic()+20
        while True:
            snapshot=self.snapshot(aid)
            if snapshot['invariant_pass'] or time.monotonic()>until:break
            time.sleep(.1)
        assert snapshot['invariant_pass'],snapshot
        if expected_orders is not None:assert len(snapshot['orders'])==expected_orders,snapshot
        assert not any(r['status']==0 or r['status']>=500 for r in requests),'unexpected request failure'
        completed=[r['completion_observed_ms'] for r in requests if r['completion_observed_ms'] is not None]
        end=max(observed.values()) if observed else response_end
        trace_value={'activity_id':aid,'start':start,'response_end':response_end,'last_completion_observed':end,'trace':trace,'snapshot':snapshot,'poll_interval_seconds':.1}
        if measure:
            self.persist_raw(name,requests,resources,trace_value)
            self.summarize(label,name,concurrency,requests,start,response_end,resources,activity_id=aid,accepted=len(accepted),orders=len(snapshot['orders']),completion_seconds=end-start,completed_orders_per_second=len(snapshot['orders'])/(end-start),completion_mean_ms=statistics.mean(completed) if completed else None,completion_p50_ms=percentile(completed,.5),completion_p95_ms=percentile(completed,.95),completion_p99_ms=percentile(completed,.99),invariant_pass=True)
        return requests,snapshot
    def functional_checks(self):
        cli=Client(self.args.port);checks=[];aid=self.fixture(2,'functional');user='functional_'+self.run_id+'_'+self.current['version'].replace('.','_');rid=uuid.uuid4().hex
        def call(path,status,body=None,code=None):
            r=cli.call(path,body);assert r['status']==status,(path,r)
            if code:assert r['data'].get('code')==code,(path,r)
            checks.append({'path':path,'status':status,'code':r['data'].get('code'),'pass':True});return r['data']
        try:
            call('/api/activities/'+str(aid),200)
            call('/api/activities/'+str(aid)+'/orders',202 if self.async_mode() else 200,{'userId':user,'requestId':rid})
            until=time.monotonic()+90
            while not self.db.query('SELECT id FROM seckill_order WHERE request_id=%s',(rid,)) and time.monotonic()<until:time.sleep(.1)
            order=call('/api/orders/by-request/'+rid+'?userId='+user,200)
            retried=call('/api/activities/'+str(aid)+'/orders',200,{'userId':user,'requestId':rid})
            assert (retried['order']['id'] if self.async_mode() else retried['id'])==order['id']
            call('/api/activities/'+str(aid)+'/orders',409,{'userId':user,'requestId':uuid.uuid4().hex},'ALREADY_PURCHASED')
            call('/api/orders/by-request/'+rid+'?userId=not_owner',404,code='NOT_FOUND')
            for timing,enabled,stock,code in [('upcoming','ACTIVE',2,'NOT_STARTED'),('ended','ACTIVE',2,'ENDED'),('open','DISABLED',2,'DISABLED'),('open','ACTIVE',0,'SOLD_OUT')]:
                invalid=self.fixture(stock,'invalid-'+code,enabled,timing)
                call('/api/activities/'+str(invalid)+'/orders',409,{'userId':user,'requestId':uuid.uuid4().hex},code)
            call('/api/activities/999999999',404,code='NOT_FOUND')
            call('/api/activities/'+str(aid)+'/orders',400,{'userId':'bad space','requestId':uuid.uuid4().hex},'INVALID_ARGUMENT')
            if self.async_mode():assert call('/api/requests/'+rid+'?userId='+user,200)['state']=='SUCCESS'
        finally:cli.close()
        # 售罄与重复用户用不同活动；不把 409 当作未知系统错误。
        requests,over=self.burst(self.fixture(8,'oversell'),16,32,'oversell',measure=False,expected_orders=8)
        assert sum(r['status'] in (200,202) for r in requests)==8 and sum(r['code']=='SOLD_OUT' for r in requests)==24
        requests,duplicate=self.burst(self.fixture(8,'duplicate'),16,16,'duplicate',measure=False,same_user=True,expected_orders=1)
        assert sum(r['status'] in (200,202) for r in requests)==1
        entry={'version':self.current['version'],'checks':checks,'oversell':over,'duplicate_buyer':duplicate,'passed':True};self.functional.append(entry);dump(self.out/'functional.json',self.functional)
        self.emit('functional_pass',version=self.current['version'],http_checks=len(checks),oversell_orders=8,duplicate_orders=1)
    def cache_probe(self):
        cli=Client(self.args.port);key=self.current['prefix']+'product:'+str(self.base);labels=['MISS']*100+['HIT']*100;random.Random(20261030+self.current['rep']).shuffle(labels);requests=[]
        monitor=Monitor(self.app.pid,int(self.c['DB_PORT'])).begin();start=time.perf_counter()
        try:
            for label in labels:
                if label=='MISS':self.redis.call('DEL',key)
                else:
                    fill=cli.call('/api/products/'+str(self.base));assert fill['status']==200
                r=cli.call('/api/products/'+str(self.base));assert r['status']==200 and r['cache']==label,r
                r.pop('data',None);r['condition']=label;requests.append(r)
        finally:cli.close();resources=monitor.finish()
        end=time.perf_counter();name=f"cache-r{self.current['rep']}";self.persist_raw(name,requests,resources)
        for label in ['MISS','HIT']:
            selected=[r for r in requests if r['condition']==label]
            self.rows.append({'kind':'cache','name':name+'-'+label,'version':self.current['version'],'rep':self.current['rep'],'concurrency':1,'condition':label,'request_count':len(selected),**latency([r['latency_ms'] for r in selected]),'elapsed_includes_control_seconds':end-start})
        dump(self.out/'summary.json',self.rows);self.emit('cache_pass',rep=self.current['rep'],miss=100,hit=100)
    def create_topic(self):
        mq='/opt/lab2-rocketmq/rocketmq-all-5.5.1-bin-release'
        command=['wsl','-d','Ubuntu','-u','root','--exec','/usr/lib/jvm/java-17-openjdk-amd64/bin/java','-Xms32m','-Xmx128m','-Drocketmq.home.dir='+mq,'-cp',mq+'/lib/*','org.apache.rocketmq.tools.command.MQAdminStartup','updateTopic','-n','127.0.0.1:9876','-b','127.0.0.1:10911','-t','Lab2OrdersBenchE','-r','4','-w','4']
        with (self.out/'topic-create.log').open('wb') as f:subprocess.run(command,stdout=f,stderr=subprocess.STDOUT,check=True)
    def run(self):
        self.keep=subprocess.Popen(['wsl','-d','Ubuntu','--exec','sleep','infinity'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            self.create_topic();self.emit('run_start',run_id=self.run_id,base=self.base)
            for rep in range(1,4):
                ordered=self.artifacts[rep-1:]+self.artifacts[:rep-1]
                for artifact in ordered:
                    self.start(artifact,rep)
                    read_activity=self.fixture(10,'read-'+self.current['version']+'-r'+str(rep))
                    self.read_load(read_activity,4,1,measure=False)
                    # 写路径预热单独活动，不混进正式样本。
                    self.burst(self.fixture(16,'warm-write'),4,16,'warm',measure=False,expected_orders=16)
                    if rep==1:self.functional_checks()
                    levels=[1,8,16];levels=levels[rep-1:]+levels[:rep-1]
                    for c in levels:
                        self.read_load(read_activity,c,self.args.read_seconds)
                        self.burst(self.fixture(128,'write-r'+str(rep)+'-c'+str(c)),c,128,expected_orders=128)
                    if self.current['version']=='0.2.0-cache':self.cache_probe()
                    self.stop()
            self.manifest['demo_after']=self.db.demo();assert self.manifest['demo_before']==self.manifest['demo_after'],'展示数据发生变化'
            self.manifest['status']='PASS';self.manifest['completed_at']=datetime.datetime.now().astimezone().isoformat();self.save_manifest()
            self.emit('run_complete',scenarios=len(self.rows),functional_versions=len(self.functional))
        except Exception as e:
            self.manifest['status']='FAILED';self.manifest['failure_type']=type(e).__name__;self.save_manifest();self.emit('run_failed',type=type(e).__name__);raise
        finally:
            self.stop()
            if self.keep:self.keep.terminate()
            self.redis.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--artifacts',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--env-file',type=Path,default=ROOT.parent/'实验记录/本机私用/app-env.json');p.add_argument('--port',type=int,default=18093);p.add_argument('--read-seconds',type=float,default=4);a=p.parse_args()
    # 在首次建立 Redis 连接前保活 WSL；无现成演示进程时也可独立复现。
    keep=subprocess.Popen(['wsl','-d','Ubuntu','--exec','sleep','infinity'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        config=json.loads(a.env_file.read_text(encoding='utf-8'));until=time.monotonic()+15
        while True:
            try:
                with socket.create_connection((config['REDIS_HOST'],int(config['REDIS_PORT'])),timeout=1):break
            except OSError:
                if time.monotonic()>until:raise RuntimeError('本机 Redis 未就绪')
                time.sleep(.25)
        Experiment(a).run()
    finally:keep.terminate()
