"""真实异步接口验证。暂停点需要消费者已停止；恢复后继续核对同一请求。"""
from pathlib import Path
import argparse,datetime,json,time,urllib.request,urllib.error,uuid
def main():
    p=argparse.ArgumentParser();p.add_argument('--base',default='http://127.0.0.1:18092');p.add_argument('--output',type=Path,required=True);p.add_argument('--pause-at-accepted',action='store_true');p.add_argument('--resume-from',type=Path);a=p.parse_args()
    record=json.loads(a.resume_from.read_text(encoding='utf-8')) if a.resume_from else {'user':'stageD_'+uuid.uuid4().hex[:12],'requestId':str(uuid.uuid4()),'results':[]}
    user=record['user'];rid=record['requestId'];rows=record['results']
    def request(path,status,body=None,code=None):
        req=urllib.request.Request(a.base+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=10) as r:value=json.load(r);actual=r.status
        except urllib.error.HTTPError as e:value=json.load(e);actual=e.code
        assert actual==status,(path,actual,value)
        if code:assert value.get('code')==code,(path,value)
        rows.append({'path':path,'method':'POST' if body is not None else 'GET','status':actual,'code':value.get('code') if isinstance(value,dict) else None,'passed':True})
        return value
    body={'userId':user,'requestId':rid};result_path='/api/requests/'+rid+'?userId='+user
    try:
        if not a.resume_from:
            health=request('/health',200);assert health['mode']=='ASYNC' and health['redis']=='PONG'
            request('/api/activities',200)
            record['stockBefore']=request('/api/activities/1',200)['stock']
            receipt=request('/api/activities/1/orders',202,body);assert receipt['state']=='ACCEPTED' and receipt['order'] is None
            record['accepted']=receipt
            request('/api/requests/'+rid+'?userId=another_user',404,code='NOT_FOUND')
            request('/api/activities/999999',404,code='NOT_FOUND')
            request('/api/activities/1/orders',409,{'userId':'other_'+user,'requestId':rid},'REQUEST_CONFLICT')
            for aid,code in [(2,'NOT_STARTED'),(3,'ENDED'),(4,'DISABLED'),(5,'SOLD_OUT')]:
                request(f'/api/activities/{aid}/orders',409,{'userId':user,'requestId':str(uuid.uuid4())},code)
            request('/api/activities/1/orders',400,{'userId':'bad space','requestId':str(uuid.uuid4())},'INVALID_ARGUMENT')
            request('/api/requests?userId=bad%20space',400,code='INVALID_ARGUMENT')
            if a.pause_at_accepted:
                assert request('/api/activities/1/orders',202,body)['requestId']==rid
                assert request(result_path,200)['state']=='ACCEPTED'
                assert request('/api/orders?userId='+user,200)==[]
                assert request('/api/requests?userId='+user,200)[0]['state']=='ACCEPTED'
                assert request('/api/activities/1',200)['stock']==record['stockBefore']-1
                request('/api/activities/1/orders',409,{'userId':user,'requestId':str(uuid.uuid4())},'ALREADY_REQUESTED')
                record['stage']='PAUSED_ACCEPTED';return
        deadline=time.monotonic()+90
        while True:
            receipt=request(result_path,200)
            if receipt['state']!='ACCEPTED':break
            if time.monotonic()>deadline:raise RuntimeError('请求仍受理中，保留编号以供核对')
            time.sleep(.5)
        assert receipt['state']=='SUCCESS' and receipt['order'] is not None,receipt
        record['completed']=receipt
        assert request('/api/activities/1/orders',200,body)['order']['id']==receipt['order']['id']
        request('/api/activities/1/orders',409,{'userId':user,'requestId':str(uuid.uuid4())},'ALREADY_PURCHASED')
        assert len(request('/api/orders?userId='+user,200))==1
        assert request('/api/orders/by-request/'+rid+'?userId='+user,200)['id']==receipt['order']['id']
        assert request('/api/activities/1',200)['stock']==record['stockBefore']-1
        record['stage']='SUCCESS'
    finally:
        record['checked_at']=datetime.datetime.now().astimezone().isoformat();a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'stage':record.get('stage'),'checks':len(rows),'user':user,'requestId':rid},ensure_ascii=False))
if __name__=='__main__':main()
