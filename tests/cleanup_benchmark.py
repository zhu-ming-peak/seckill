"""仅清理给定性能试验清单的专用数据；先验证归属、保存快照，不碰展示活动。"""
from pathlib import Path
import argparse,json
from benchmark import ROOT,Database,Redis,dump,psutil,subprocess
def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--env-file',type=Path,default=ROOT.parent/'实验记录/本机私用/app-env.json');a=p.parse_args()
    folder=a.run.resolve();m=json.loads((folder/'manifest.json').read_text(encoding='utf-8'));rid=m['run_id'];ids=m['fixtures'];pidfile=folder/'active-process.json'
    if pidfile.exists():
        active=json.loads(pidfile.read_text(encoding='utf-8'))
        try:
            process=psutil.Process(active['pid'])
            if active['jar'] in ' '.join(process.cmdline()):raise RuntimeError('本轮测试应用仍在运行，未清理')
        except psutil.NoSuchProcess:pass
    assert ids and len(ids)==len(set(ids)) and all(910000<=i<=919999 for i in ids)
    config=json.loads(a.env_file.read_text(encoding='utf-8'));redis=Redis(config)
    assert redis.call('PING')=='PONG'  # 删除数据库记录前先确认缓存清理路径可用。
    db=Database(config);mark=','.join(['%s']*len(ids));args=tuple(ids)
    activities=db.query('SELECT * FROM seckill_activity WHERE id IN ('+mark+')',args)
    assert all(x['title'].startswith('bench:'+rid+':') for x in activities),'活动归属不符，未清理'
    product=db.query('SELECT * FROM product WHERE id=%s',(m['product_id'],))
    assert len(product)==1 and product[0]['name']=='bench-'+rid,'商品归属不符，未清理'
    before={'activities':activities,'orders':db.query('SELECT * FROM seckill_order WHERE activity_id IN ('+mark+')',args),'requests':db.query('SELECT * FROM seckill_request WHERE activity_id IN ('+mark+')',args)}
    dump(folder/'cleanup-before.json',before)
    with db.connect() as connection:
        connection.begin()
        try:
            with connection.cursor() as cur:
                cur.execute('SELECT id,title FROM seckill_activity WHERE id IN ('+mark+') FOR UPDATE',args)
                assert all(x['title'].startswith('bench:'+rid+':') for x in cur.fetchall())
                for table in ['seckill_request','seckill_order']:cur.execute('DELETE FROM '+table+' WHERE activity_id IN ('+mark+')',args)
                cur.execute('DELETE FROM seckill_activity WHERE id IN ('+mark+')',args)
                cur.execute('DELETE FROM product WHERE id=%s',(m['product_id'],))
            connection.commit()
        except Exception:connection.rollback();raise
    prefix='lab2:bench:'+rid+':';cursor='0';keys=[]
    try:
        while True:
            cursor,batch=redis.call('SCAN',cursor,'MATCH',prefix+'*','COUNT',200);keys.extend(batch)
            if cursor=='0':break
        assert all(k.startswith(prefix) for k in keys)
        if keys:redis.call('DEL',*keys)
    finally:redis.close()
    assert not db.query('SELECT id FROM seckill_activity WHERE id IN ('+mark+')',args)
    demo=json.loads(json.dumps(db.demo(),default=str));assert demo==m['demo_before'],'展示数据与测试前不一致'
    result={'status':'PASS','run_id':rid,'deleted_activities':len(activities),'deleted_orders':len(before['orders']),'deleted_requests':len(before['requests']),'deleted_redis_keys':len(set(keys)),'demo_unchanged':True,'snapshot':'cleanup-before.json'}
    dump(folder/'cleanup-result.json',result);print(json.dumps(result))
if __name__=='__main__':
    keep=subprocess.Popen(['wsl','-d','Ubuntu','--exec','sleep','infinity'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
    try:main()
    finally:keep.terminate()
