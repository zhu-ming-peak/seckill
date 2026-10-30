"""对运行中的数据库版执行接口验证；创建一笔带独立验证用户的真实实验订单。"""
from pathlib import Path
import argparse
import datetime
import json
import urllib.error
import urllib.parse
import urllib.request
import uuid

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--base",default="http://127.0.0.1:18092")
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    results=[]
    user="verify_"+uuid.uuid4().hex[:12]
    request_id=str(uuid.uuid4())
    def request(path,expected,body=None,code=None):
        data=json.dumps(body).encode() if body is not None else None
        req=urllib.request.Request(args.base+path,data=data,headers={"Content-Type":"application/json"})
        try:
            with urllib.request.urlopen(req,timeout=10) as response: status,value=response.status,json.load(response)
        except urllib.error.HTTPError as e: status,value=e.code,json.load(e)
        assert status==expected,(path,status,value)
        if code: assert value.get("code")==code,(path,value)
        results.append({"path":path,"method":"POST" if body is not None else "GET","status":status,"code":value.get("code") if isinstance(value,dict) else None,"passed":True})
        return value
    try:
        assert request("/health",200)["database"]=="UP"
        items=request("/api/activities",200)
        assert {a["state"] for a in items}=={"OPEN","UPCOMING","ENDED","DISABLED","SOLD_OUT"},"请使用尚未售罄的初始化演示数据运行"
        request("/api/activities/999999",404,code="NOT_FOUND")
        before=request("/api/activities/1",200)["stock"]
        body={"userId":user,"requestId":request_id}
        order=request("/api/activities/1/orders",200,body)
        assert request("/api/activities/1/orders",200,body)["id"]==order["id"]
        assert request("/api/activities/1",200)["stock"]==before-1
        request("/api/activities/1/orders",409,{"userId":user,"requestId":str(uuid.uuid4())},"ALREADY_PURCHASED")
        request("/api/orders/by-request/"+request_id+"?userId="+user,200)
        request("/api/orders/by-request/"+request_id+"?userId=another_user",404,code="NOT_FOUND")
        for activity,code in [(2,"NOT_STARTED"),(3,"ENDED"),(4,"DISABLED"),(5,"SOLD_OUT")]:
            request(f"/api/activities/{activity}/orders",409,{"userId":user,"requestId":str(uuid.uuid4())},code)
        request("/api/activities/1/orders",400,{"userId":"bad space","requestId":str(uuid.uuid4())},"INVALID_ARGUMENT")
        request("/api/activities/1/orders",400,{"requestId":str(uuid.uuid4())},"INVALID_ARGUMENT")
        request("/api/orders?userId=bad%20space",400,code="INVALID_ARGUMENT")
        assert len(request("/api/orders?userId="+user,200))==1
    finally:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps({"checked_at":datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),"base":args.base,"user":user,"results":results},ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"接口验证通过：{len(results)} 项；验证用户 {user}，保留 1 笔实验订单。")
