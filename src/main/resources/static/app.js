const $=id=>document.getElementById(id);
const labels={OPEN:'正在进行',UPCOMING:'即将开始',ENDED:'已经结束',SOLD_OUT:'已售罄',DISABLED:'暂未开放'};
let activities=[],filter='ALL',toastTimer;
const requests=new Map(JSON.parse(sessionStorage.getItem('seckill-requests')||'[]'));
function remember(){sessionStorage.setItem('seckill-requests',JSON.stringify([...requests]));}
const money=value=>Number(value).toFixed(2);
const time=value=>value?value.replace('T',' ').slice(0,19):'';
function el(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e;}
function notify(text,error=false){clearTimeout(toastTimer);$('toast').textContent=text;$('toast').className='toast'+(error?' error':'');$('toast').hidden=false;toastTimer=setTimeout(()=>$('toast').hidden=true,6000);}
async function api(url,options={}){const response=await fetch(url,options);let data;try{data=await response.json();}catch{throw new Error('服务暂时不可用，请稍后重试');}if(!response.ok)throw Object.assign(new Error(data.message||'请求未完成'),{business:true,retryable:response.status>=500});return data;}
function user(){const value=$('user-id').value.trim();if(!/^[A-Za-z0-9_-]{1,64}$/.test(value))throw new Error('用户编号请使用 1–64 位字母、数字、下划线或短横线');return value;}
function render(){
 const cards=$('cards');cards.replaceChildren();const selected=activities.filter(a=>filter==='ALL'||a.state===filter);
 $('load-state').textContent=selected.length?'':'暂无符合条件的活动';
 for(const a of selected){
  const card=el('article','card'),art=el('div','product-art');
  art.append(el('span','badge'+(a.state==='OPEN'?' open':''),labels[a.state]||a.state),el('span','glyph',a.productId===1?'青瓷':a.productId===2?'轻键':'有序'));
  const body=el('div','card-body');body.append(el('h3','',a.productName),el('p','description',a.description));
  const price=el('div','price-row'),now=el('span','price');now.append(el('small','','¥'),document.createTextNode(money(a.seckillPrice)));price.append(now,el('span','old-price','¥'+money(a.regularPrice)));body.append(price);
  const stock=el('div','stock-row');stock.append(el('span','',`剩余 ${a.stock} / ${a.initialStock} 件`),el('span','','每人限购 1 件'));body.append(stock);
  const bar=el('div','stockbar'),fill=el('span');fill.style.width=(a.initialStock?100*a.stock/a.initialStock:0)+'%';bar.append(fill);body.append(bar);
  const pending=requests.get(a.id+':'+$('user-id').value.trim());
  const buy=el('button','buy',pending?'查询处理结果':a.state==='OPEN'?'立即秒杀':labels[a.state]||'暂不可参与');buy.type='button';buy.disabled=a.state!=='OPEN'&&!pending;buy.addEventListener('click',()=>pending?pollRequest(pending,$('user-id').value.trim()):purchase(a,buy));body.append(buy,el('p','date',`活动结束 ${time(a.endTime)}`));card.append(art,body);cards.append(card);
 }
}
async function load(){try{activities=await api('/api/activities');render();}catch(e){$('load-state').textContent='活动加载失败，请刷新重试';notify(e.message,true);}}
async function orders(){
 try{
  const id=user(),[data,receipts]=await Promise.all([api('/api/orders?userId='+encodeURIComponent(id)),api('/api/requests?userId='+encodeURIComponent(id))]);
  $('order-count').textContent=data.length+' 笔';$('orders').replaceChildren();$('requests').replaceChildren();
  for(const r of receipts){
   const key=r.activityId+':'+id;
   if(r.state==='ACCEPTED')requests.set(key,r.requestId);else if(requests.get(key)===r.requestId)requests.delete(key);
   if(r.state!=='SUCCESS'){
    const item=el('div','order');item.append(el('strong','',r.state==='ACCEPTED'?'请求已受理 · 正在处理':'本次请求未成功'),el('div','order-meta',r.message),el('div','order-meta','请求 '+r.requestId));
    if(r.state==='ACCEPTED'){const check=el('button','quiet','刷新处理结果');check.type='button';check.addEventListener('click',()=>pollRequest(r.requestId,id));item.append(check);}
    $('requests').append(item);
   }
  }
  remember();render();
  if(!data.length)$('orders').append(el('p','empty','尚无成功订单；受理中的请求会在完成后显示。'));
  for(const o of data){const item=el('div','order'),head=el('div','order-head');head.append(el('strong','',o.productName),el('span','success','购买成功'));item.append(head,el('div','order-meta',`¥${money(o.unitPrice)} × ${o.quantity} · ${time(o.createdAt)}`),el('div','order-meta','订单 '+o.id));$('orders').append(item);}
 }catch(e){notify(e.message,true);}
}
async function pollRequest(requestId,id){
 try{
  for(let i=0;i<40;i++){
   const receipt=await api('/api/requests/'+encodeURIComponent(requestId)+'?userId='+encodeURIComponent(id));
   if(receipt.state!=='ACCEPTED'){
    requests.delete(receipt.activityId+':'+id);remember();notify(receipt.message,receipt.state==='FAILED');
    if($('user-id').value.trim()===id){await orders();await load();}return;
   }
   if(i===0&&$('user-id').value.trim()===id)await orders();
   await new Promise(resolve=>setTimeout(resolve,750));
  }
  notify('请求仍在处理，可稍后刷新处理结果。');
 }catch(e){notify('暂时未取得最终结果，请保留原请求并稍后查询。',true);}
}
async function purchase(a,button){
 let id;try{id=user();}catch(e){notify(e.message,true);return;}
 const key=a.id+':'+id,requestId=requests.get(key)||crypto.randomUUID();requests.set(key,requestId);remember();button.disabled=true;button.textContent='正在提交…';
 try{const receipt=await api('/api/activities/'+a.id+'/orders',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({userId:id,requestId})});notify(receipt.message);await orders();await load();if(receipt.state==='ACCEPTED')await pollRequest(requestId,id);}
 catch(e){if(e.business&&!e.retryable){requests.delete(key);remember();}notify(e.message+(e.business?'':'；请查询请求状态或使用原请求重试。'),true);}
 finally{await load();}
}
$('refresh').addEventListener('click',load);$('load-orders').addEventListener('click',orders);
document.querySelectorAll('[data-filter]').forEach(button=>button.addEventListener('click',()=>{filter=button.dataset.filter;document.querySelectorAll('[data-filter]').forEach(b=>b.classList.toggle('selected',b===button));render();}));
load();orders();
