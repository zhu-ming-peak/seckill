package edu.tju.lab2;

import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(name="seckill.mq-enabled",havingValue="true")
public class AsyncBackgroundWorker {
    private final RequestMapper requests;
    private final RocketMqGateway gateway;
    private final AsyncInventoryReconciler repair;
    public AsyncBackgroundWorker(RequestMapper requests,RocketMqGateway gateway,AsyncInventoryReconciler repair){this.requests=requests;this.gateway=gateway;this.repair=repair;}
    @Scheduled(fixedDelayString="${seckill.mq-dispatch-delay:2000}",initialDelayString="${seckill.mq-initial-delay:1000}")
    public void dispatch(){
        for(RequestRow row:requests.due()){
            if(requests.claim(row.requestId())!=1)continue;
            try{requests.sent(row.requestId(),gateway.publish(row.requestId()));}
            catch(Exception e){requests.sendFailed(row.requestId());LoggerFactory.getLogger(getClass()).warn("OUTBOX_RETRY request={} type={}",row.requestId(),e.getClass().getSimpleName());}
        }
    }
    @Scheduled(fixedDelayString="${seckill.reconcile-delay:15000}",initialDelayString="${seckill.reconcile-initial-delay:3000}")
    public void reconcile(){repair.tick();}
}
