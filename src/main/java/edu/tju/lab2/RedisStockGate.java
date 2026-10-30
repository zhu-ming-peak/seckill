package edu.tju.lab2;

import java.time.Duration;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ClassPathResource;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Component
public class RedisStockGate {
    private static final Logger log=LoggerFactory.getLogger(RedisStockGate.class);
    private final StringRedisTemplate redis;
    private final String prefix;
    public final boolean enabled;
    private final DefaultRedisScript<Long> reserve=new DefaultRedisScript<>(),complete=new DefaultRedisScript<>(),warm=new DefaultRedisScript<>();
    public RedisStockGate(StringRedisTemplate redis,@Value("${seckill.redis-enabled}")boolean enabled,
                          @Value("${seckill.redis-prefix}")String prefix) {
        this.redis=redis;this.enabled=enabled;this.prefix=prefix;
        reserve.setLocation(new ClassPathResource("redis/reserve.lua"));reserve.setResultType(Long.class);
        complete.setLocation(new ClassPathResource("redis/complete.lua"));complete.setResultType(Long.class);
        warm.setLocation(new ClassPathResource("redis/warm.lua"));warm.setResultType(Long.class);
    }
    public String key(long activityId){return prefix+"activity:{"+activityId+"}:reservation";}
    public String ping(){return enabled?redis.execute((org.springframework.data.redis.core.RedisCallback<String>)c->c.ping()):"NOT_USED";}
    public Long warm(Activity a){
        return redis.execute(warm,List.of(key(a.id())),Integer.toString(a.stock()),
            Long.toString(Math.max(86400,Duration.between(a.serverTime(),a.endTime()).getSeconds()+86400)));
    }
    public long reserveRaw(Activity a,String user,String token){
        long ttl=Math.max(86400,Duration.between(a.serverTime(),a.endTime()).getSeconds()+86400);
        Long r=redis.execute(reserve,List.of(key(a.id())),Integer.toString(a.stock()),user,token,Long.toString(ttl));
        if(r==null)throw new BusinessException("CACHE_UNAVAILABLE","库存服务暂时不可用",503);
        return r;
    }
    public long finish(long activity,String user,String token,boolean commit){
        Long r=redis.execute(complete,List.of(key(activity)),user,token,commit?"COMMIT":"ROLLBACK");
        return r==null?0:r;
    }
    public void reserveInTransaction(Activity a,String user,String token){
        if(!enabled)return;
        if(!TransactionSynchronizationManager.isSynchronizationActive())throw new IllegalStateException("reservation requires transaction");
        long result;
        try {result=reserveRaw(a,user,token);}
        catch(org.springframework.dao.DataAccessException e) {
            log.error("RESERVATION_RECONCILE_REQUIRED activity={} token={} stage=reserve",a.id(),token);
            throw e;
        }
        if(result==1)throw new BusinessException("SOLD_OUT","缓存库存已售罄",409);
        if(result==2)throw new BusinessException("RESERVATION_EXISTS","该用户已有购买或待核对的预扣记录",409);
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization(){
            @Override public void afterCompletion(int status){
                // UNKNOWN 不能当作已回滚；保留预扣，人工核对后恢复。
                if(status==STATUS_UNKNOWN){log.error("RESERVATION_RECONCILE_REQUIRED activity={} token={}",a.id(),token);return;}
                try {finish(a.id(),user,token,status==STATUS_COMMITTED);}
                catch(Exception e){log.error("RESERVATION_RECONCILE_REQUIRED activity={} token={} completion={}",a.id(),token,status);}
            }
        });
    }
}
