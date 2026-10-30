package edu.tju.lab2;

import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AsyncOrderProcessor {
    private final RequestMapper requests;
    private final SeckillMapper orders;
    public AsyncOrderProcessor(RequestMapper requests,SeckillMapper orders){this.requests=requests;this.orders=orders;}
    @Transactional
    public void process(String requestId,long activityId){
        Activity a=orders.lockActivity(activityId);
        RequestRow r=requests.lock(requestId);
        if(r==null||r.activityId()!=activityId)throw new IllegalArgumentException("request mismatch");
        if(!"ACCEPTED".equals(r.state()))return;
        requests.attempt(requestId);
        Order existing=orders.byRequest(requestId);
        if(existing!=null){requests.success(requestId,existing.id());return;}
        if(a==null||orders.byBuyer(activityId,r.userId())!=null){requests.fail(requestId,"PURCHASE_CONFLICT");return;}
        // 已在有效期受理的请求即使排队跨过活动结束时间仍然履约；价格使用受理快照。
        if(orders.decrementAccepted(activityId)!=1){requests.fail(requestId,"DB_STOCK_EXHAUSTED");return;}
        Order order=new Order(UUID.randomUUID().toString(),requestId,activityId,r.userId(),r.productName(),r.acceptedPrice(),1,"SUCCESS",null);
        orders.insertOrder(order);
        requests.success(requestId,order.id());
    }
}
