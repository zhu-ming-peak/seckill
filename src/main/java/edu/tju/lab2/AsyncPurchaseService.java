package edu.tju.lab2;

import java.util.List;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AsyncPurchaseService {
    private final SeckillMapper orders;
    private final RequestMapper requests;
    private final RedisStockGate gate;
    private final ProductCache products;
    public record Receipt(String requestId,long activityId,String userId,String state,
                          String code,String message,Order order){}
    public AsyncPurchaseService(SeckillMapper orders,RequestMapper requests,RedisStockGate gate,ProductCache products){
        this.orders=orders;this.requests=requests;this.gate=gate;this.products=products;
    }
    public List<Activity> activities(){return orders.asyncActivities().stream().map(a->a.withProduct(products.get(a.productId()))).toList();}
    public Activity activity(long id){
        ActivityData row=orders.asyncActivity(id);
        if(row==null)throw new BusinessException("NOT_FOUND","活动不存在",404);
        return row.withProduct(products.get(row.productId()));
    }
    public Receipt view(RequestRow r){
        return new Receipt(r.requestId(),r.activityId(),r.userId(),r.state(),r.failureCode(),
            switch(r.state()){case "SUCCESS"->"购买成功，订单已生成";case "FAILED"->"DB_STOCK_EXHAUSTED".equals(r.failureCode())?"库存已不足，本次请求未成功":"购买发生冲突，本次未生成新订单";default->"请求已受理，正在等待处理";},
            "SUCCESS".equals(r.state())?orders.byRequest(r.requestId()):null);
    }
    public Receipt result(String id,String user){
        RequestRow r=requests.get(id);
        if(r==null||!r.userId().equals(user))throw new BusinessException("NOT_FOUND","未找到该用户的请求",404);
        return view(r);
    }
    public List<Receipt> list(String user){return requests.userRequests(user).stream().map(this::view).toList();}
    @Transactional
    public Receipt accept(long activity,String user,String requestId){
        // 先取得活动行锁，再做一致性查询，避免 REPEATABLE-READ 快照先于锁等待建立。
        Activity a=orders.lockActivity(activity);
        if(a==null)throw new BusinessException("NOT_FOUND","活动不存在",404);
        RequestRow previous=requests.get(requestId);
        if(previous!=null){
            if(previous.activityId()!=activity||!previous.userId().equals(user))
                throw new BusinessException("REQUEST_CONFLICT","请求编号已用于其他请求",409);
            return view(previous);
        }
        if(orders.byRequest(requestId)!=null)throw new BusinessException("REQUEST_CONFLICT","请求编号已用于历史订单",409);
        if(orders.byBuyer(activity,user)!=null)throw new BusinessException("ALREADY_PURCHASED","本场活动已购买",409);
        if(requests.buyer(activity,user)!=null)throw new BusinessException("ALREADY_REQUESTED","本场活动已有受理记录，请查询原请求",409);
        switch(a.getState()){
            case "UPCOMING"->throw new BusinessException("NOT_STARTED","活动尚未开始",409);
            case "ENDED"->throw new BusinessException("ENDED","活动已经结束",409);
            case "DISABLED"->throw new BusinessException("DISABLED","活动暂未开放",409);
            case "SOLD_OUT"->throw new BusinessException("SOLD_OUT","商品已售罄",409);
            default->{}
        }
        gate.rebuild(a,requests.pending(activity));
        String token=UUID.randomUUID().toString();
        gate.reserveAsyncInTransaction(a,user,token);
        if(requests.insert(new RequestMapper.NewRequest(requestId,activity,user,token,a.productName(),a.seckillPrice()))!=1)
            throw new BusinessException("ENDED","活动状态已变化，未受理",409);
        return view(requests.get(requestId));
    }
}
