package edu.tju.lab2;

import java.math.BigDecimal;
import java.util.*;
import java.util.concurrent.*;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.transaction.support.TransactionTemplate;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(properties={"seckill.redis-enabled=true","seckill.warmup-enabled=false","seckill.redis-prefix=lab2:test:redis:","seckill.product-cache-ttl-seconds=2"})
class RedisIntegrationTest extends DatabaseIntegrationTest {
    @Autowired StringRedisTemplate redis;
    @Autowired ProductCache products;
    @Autowired RedisStockGate gate;
    @Override @AfterEach void clean(){
        super.clean();
        List<String> keys=new ArrayList<>();
        for(long id=900001;id<=900010;id++)keys.add(gate.key(id));
        keys.add(products.key(900001));
        redis.delete(keys);
    }
    @Test void cacheMissThenHitOnlyReadsDatabaseOnce(){
        long before=products.databaseReadCount();
        assertEquals("MISS",products.lookup(900001).source());
        assertEquals("HIT",products.lookup(900001).source());
        assertEquals(before+1,products.databaseReadCount());
        assertTrue(redis.getExpire(products.key(900001))>0);
    }
    @Test void cacheExpiresAndReloads() throws Exception {
        products.get(900001);
        Thread.sleep(2200);
        assertFalse(Boolean.TRUE.equals(redis.hasKey(products.key(900001))));
        assertEquals("MISS",products.lookup(900001).source());
    }
    @Test void committedUpdateInvalidatesCache(){
        products.get(900001);
        products.update(new Product(900001,"更新后的商品","缓存失效验证",new BigDecimal("23.00")));
        assertFalse(Boolean.TRUE.equals(redis.hasKey(products.key(900001))));
        assertEquals("更新后的商品",products.get(900001).name());
        assertEquals(new BigDecimal("23.00"),products.get(900001).regularPrice());
    }
    @Test void rolledBackUpdateLeavesOldCommittedProduct(){
        products.get(900001);
        assertThrows(IllegalStateException.class,()->new TransactionTemplate(transactions).executeWithoutResult(s->{
            products.update(new Product(900001,"不应保留的修改","rollback",new BigDecimal("99.00")));
            throw new IllegalStateException("模拟事务失败");
        }));
        assertEquals("事务测试商品",products.get(900001).name());
        assertEquals(new BigDecimal("20.00"),mapper.product(900001).regularPrice());
    }
    @Test void rollbackCompensatesRedisOnce(){
        assertThrows(IllegalStateException.class,()->new TransactionTemplate(transactions).executeWithoutResult(s->{
            service.place(900001,"compensate","compensate-request");
            throw new IllegalStateException("rollback");
        }));
        assertEquals("8",redis.opsForHash().get(gate.key(900001),"stock"));
        assertNull(redis.opsForHash().get(gate.key(900001),"user:compensate"));
        assertEquals(8,service.activity(900001).stock());
    }
    @Test void luaAtomicallyLimitsReservationsAndCompensationIsIdempotent() throws Exception {
        Activity a=mapper.activity(900001);
        ExecutorService pool=Executors.newFixedThreadPool(12);
        List<Callable<Long>> work=new ArrayList<>();
        for(int i=0;i<32;i++){int n=i;work.add(()->gate.reserveRaw(a,"raw"+n,"token"+n));}
        List<Integer> winners=new ArrayList<>();
        try {
            List<Future<Long>> values=pool.invokeAll(work,20,TimeUnit.SECONDS);
            for(int i=0;i<values.size();i++)if(values.get(i).get()==0)winners.add(i);
        }finally{pool.shutdownNow();}
        assertEquals(8,winners.size());
        assertEquals("0",redis.opsForHash().get(gate.key(a.id()),"stock"));
        int n=winners.get(0);
        assertEquals(1,gate.finish(a.id(),"raw"+n,"token"+n,false));
        assertEquals(0,gate.finish(a.id(),"raw"+n,"token"+n,false));
        assertEquals("1",redis.opsForHash().get(gate.key(a.id()),"stock"));
        assertEquals(0,gate.finish(a.id(),"raw"+n,"old-token",false));
    }
    @Test void sameBuyerGetsOneAtomicReservation(){
        Activity a=mapper.activity(900001);
        assertEquals(8,gate.warm(a));
        assertEquals(0,gate.reserveRaw(a,"one","first"));
        assertEquals(7,gate.warm(a));
        assertEquals(2,gate.reserveRaw(a,"one","second"));
        assertEquals("7",redis.opsForHash().get(gate.key(a.id()),"stock"));
        assertEquals(1,gate.finish(a.id(),"one","first",true));
        assertEquals(0,gate.finish(a.id(),"one","first",false));
        assertEquals("7",redis.opsForHash().get(gate.key(a.id()),"stock"));
    }
}
