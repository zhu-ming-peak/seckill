package edu.tju.lab2;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicLong;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class ProductCache {
    private static final Logger log=LoggerFactory.getLogger(ProductCache.class);
    private final SeckillMapper mapper;
    private final StringRedisTemplate redis;
    private final ObjectMapper json;
    private final boolean enabled;
    private final long ttl;
    private final String prefix;
    private final AtomicLong hits=new AtomicLong(),misses=new AtomicLong(),databaseReads=new AtomicLong();
    public long databaseReadCount(){return databaseReads.get();}
    public record Lookup(Product product,String source) { }
    public ProductCache(SeckillMapper mapper,StringRedisTemplate redis,ObjectMapper json,
        @Value("${seckill.redis-enabled}") boolean enabled,
        @Value("${seckill.product-cache-ttl-seconds}") long ttl,
        @Value("${seckill.redis-prefix}") String prefix) {
        this.mapper=mapper;this.redis=redis;this.json=json;this.enabled=enabled;
        this.ttl=Math.max(1,ttl);this.prefix=prefix;
    }
    public String key(long id) {return prefix+"product:"+id;}
    public Product get(long id) {return lookup(id).product();}
    public Lookup lookup(long id) {
        if(enabled) {
            try {
                String value=redis.opsForValue().get(key(id));
                if(value!=null) {
                    Product p=json.readValue(value,Product.class);
                    hits.incrementAndGet();log.info("PRODUCT_CACHE_HIT product={}",id);
                    return new Lookup(p,"HIT");
                }
            } catch(Exception e) {log.warn("PRODUCT_CACHE_READ_FALLBACK product={} type={}",id,e.getClass().getSimpleName());}
        }
        misses.incrementAndGet();databaseReads.incrementAndGet();
        Product p=mapper.product(id);
        if(p==null) throw new BusinessException("NOT_FOUND","商品不存在",404);
        if(enabled) {
            try {redis.opsForValue().set(key(id),json.writeValueAsString(p),Duration.ofSeconds(ttl));}
            catch(Exception e) {log.warn("PRODUCT_CACHE_FILL_FAILED product={} type={}",id,e.getClass().getSimpleName());}
        }
        log.info("PRODUCT_CACHE_MISS product={}",id);
        return new Lookup(p,enabled?"MISS":"BYPASS");
    }
    public void invalidate(long id) {if(enabled)redis.delete(key(id));}
    @Transactional
    public void update(Product p) {
        if(p.name()==null || p.name().isBlank() || p.name().length()>100 || p.description()==null
            || p.description().length()>500 || p.regularPrice()==null || p.regularPrice().signum()<=0)
            throw new BusinessException("INVALID_ARGUMENT","商品资料不合法",400);
        if(mapper.updateProduct(p)!=1)throw new BusinessException("NOT_FOUND","商品不存在",404);
        if(enabled) TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization(){
            @Override public void afterCommit(){
                try {invalidate(p.id());log.info("PRODUCT_CACHE_INVALIDATED product={}",p.id());}
                catch(Exception e){log.warn("PRODUCT_CACHE_INVALIDATION_FAILED product={} rely_on_ttl=true",p.id());}
            }
        });
    }
}
