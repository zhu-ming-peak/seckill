package edu.tju.lab2;

import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@Component
public class AsyncInventoryReconciler {
    private final RequestMapper requests;
    private final SeckillMapper orders;
    private final RedisStockGate gate;
    private final TransactionTemplate tx;
    public AsyncInventoryReconciler(RequestMapper requests,SeckillMapper orders,RedisStockGate gate,PlatformTransactionManager manager){
        this.requests=requests;this.orders=orders;this.gate=gate;this.tx=new TransactionTemplate(manager);
    }
    public void rebuild(long activity){
        tx.executeWithoutResult(status->{
            Activity a=orders.lockActivity(activity);
            if(a!=null)gate.rebuild(a,requests.pending(activity));
        });
    }
    public void terminal(String id){
        RequestRow r=requests.get(id);
        if(r==null||"ACCEPTED".equals(r.state())||r.redisDone()!=0)return;
        gate.finish(r.activityId(),r.userId(),r.token(),"SUCCESS".equals(r.state()));
        requests.redisDone(id);
    }
    public void tick(){
        for(RequestRow row:requests.terminalUnreconciled()){
            try{terminal(row.requestId());}catch(Exception e){LoggerFactory.getLogger(getClass()).warn("REDIS_REPAIR_PENDING request={}",row.requestId());}
        }
        for(ActivityData a:orders.activityDataList()){
            if(a.endTime().isAfter(a.serverTime())||!requests.pending(a.id()).isEmpty()){
                try{rebuild(a.id());}catch(Exception e){LoggerFactory.getLogger(getClass()).warn("REDIS_REBUILD_PENDING activity={}",a.id());}
            }
        }
    }
}
