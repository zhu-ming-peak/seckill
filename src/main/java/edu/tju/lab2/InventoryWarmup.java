package edu.tju.lab2;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@Component
public class InventoryWarmup {
    private final SeckillMapper mapper;
    private final RedisStockGate gate;
    private final TransactionTemplate tx;
    private final boolean enabled;
    public InventoryWarmup(SeckillMapper mapper,RedisStockGate gate,PlatformTransactionManager manager,
        @Value("${seckill.warmup-enabled:true}")boolean enabled){
        this.mapper=mapper;this.gate=gate;this.tx=new TransactionTemplate(manager);this.enabled=enabled;
    }
    @EventListener(ApplicationReadyEvent.class)
    public void initialize(){
        if(!enabled||!gate.enabled)return;
        for(ActivityData data:mapper.activityDataList()) {
            if(!"ACTIVE".equals(data.status())||!data.endTime().isAfter(data.serverTime()))continue;
            tx.executeWithoutResult(status->{
                Activity a=mapper.lockActivity(data.id());
                LoggerFactory.getLogger(getClass()).info("STOCK_WARMUP activity={} redisStock={} databaseStock={}",a.id(),gate.warm(a),a.stock());
            });
        }
    }
}
