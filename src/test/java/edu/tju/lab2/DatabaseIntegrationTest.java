package edu.tju.lab2;

import java.util.*;
import java.util.concurrent.*;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.transaction.PlatformTransactionManager;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class DatabaseIntegrationTest {
    @Autowired SeckillService service;
    @Autowired SeckillMapper mapper;
    @Autowired JdbcTemplate jdbc;
    @Autowired PlatformTransactionManager transactions;
    // 仅使用测试专用 ID 900001..900010，不清理展示活动与用户订单。
    @BeforeEach void prepare() {
        clean();
        jdbc.update("INSERT INTO product VALUES(900001,'事务测试商品','自动化验证专用',20.00)");
        jdbc.update("""
            INSERT INTO seckill_activity VALUES
            (900001,900001,'并发测试',9.90,8,8,NOW(6)-INTERVAL 1 HOUR,NOW(6)+INTERVAL 1 DAY,'ACTIVE'),
            (900002,900001,'未开始',9.90,5,5,NOW(6)+INTERVAL 1 DAY,NOW(6)+INTERVAL 2 DAY,'ACTIVE'),
            (900003,900001,'已结束',9.90,5,5,NOW(6)-INTERVAL 2 DAY,NOW(6)-INTERVAL 1 DAY,'ACTIVE'),
            (900004,900001,'已停用',9.90,5,5,NOW(6)-INTERVAL 1 HOUR,NOW(6)+INTERVAL 1 DAY,'DISABLED')
            """);
    }
    @AfterEach void clean() {
        jdbc.update("DELETE FROM seckill_order WHERE activity_id BETWEEN 900001 AND 900010");
        jdbc.update("DELETE FROM seckill_activity WHERE id BETWEEN 900001 AND 900010");
        jdbc.update("DELETE FROM product WHERE id=900001");
    }
    @Test void createsOrderAndRetriesIdempotently() {
        Order first=service.place(900001,"buyer1","retry-1");
        Order retried=service.place(900001,"buyer1","retry-1");
        assertEquals(first.id(),retried.id());
        assertEquals(7,service.activity(900001).stock());
        assertEquals(1,countOrders());
        assertEquals("9.90",first.unitPrice().toPlainString());
    }
    @Test void repeatBuyerIsRejectedWithoutChangingStock() {
        service.place(900001,"buyer1","purchase-1");
        assertEquals("ALREADY_PURCHASED",assertThrows(BusinessException.class,
            ()->service.place(900001,"buyer1","purchase-2")).code);
        assertEquals(7,service.activity(900001).stock());
    }
    @Test void invalidActivitiesDoNotCreateOrders() {
        for (long id:new long[]{900002,900003,900004,999999}) {
            assertThrows(BusinessException.class,()->service.place(id,"buyer","invalid-"+id));
        }
        assertEquals(0,countOrders());
    }
    @Test void resultDoesNotReturnAnotherUsersOrder() {
        service.place(900001,"owner","private-order");
        assertThrows(BusinessException.class,()->service.result("private-order","other"));
    }
    @Test void transactionRollbackRestoresInventoryAndOrder() {
        TransactionTemplate tx=new TransactionTemplate(transactions);
        assertThrows(IllegalStateException.class,()->tx.executeWithoutResult(status->{
            service.place(900001,"rollback-user","rollback-1");
            throw new IllegalStateException("模拟外层业务失败，整个事务回滚");
        }));
        assertEquals(8,service.activity(900001).stock());
        assertNull(mapper.byRequest("rollback-1"));
    }
    @Test void concurrentRequestsNeverOversell() throws Exception {
        List<Callable<String>> calls=new ArrayList<>();
        for(int i=0;i<32;i++) { final int n=i;
            calls.add(()->{try { service.place(900001,"parallel"+n,"parallel-"+n); return "SUCCESS"; }
                catch(BusinessException e) {return e.code;}});
        }
        List<String> results=execute(calls);
        assertEquals(8,Collections.frequency(results,"SUCCESS"));
        assertEquals(24,Collections.frequency(results,"SOLD_OUT"));
        assertEquals(0,service.activity(900001).stock());
        assertEquals(8,countOrders());
    }
    @Test void concurrentDuplicateBuyerGetsOneOrder() throws Exception {
        List<Callable<String>> calls=new ArrayList<>();
        for(int i=0;i<16;i++) { final int n=i;
            calls.add(()->{try { service.place(900001,"same-user","same-"+n);return "SUCCESS"; }
                catch(BusinessException e) {return e.code;}});
        }
        List<String> results=execute(calls);
        assertEquals(1,Collections.frequency(results,"SUCCESS"));
        assertEquals(15,Collections.frequency(results,"ALREADY_PURCHASED"));
        assertEquals(7,service.activity(900001).stock());
        assertEquals(1,countOrders());
    }
    @Test void conflictingRequestRollsBackOtherActivityStock() {
        jdbc.update("UPDATE seckill_activity SET start_time=NOW(6)-INTERVAL 1 HOUR WHERE id=900002");
        service.place(900001,"one","shared-request");
        assertEquals("REQUEST_CONFLICT",assertThrows(BusinessException.class,
            ()->service.place(900002,"two","shared-request")).code);
        assertEquals(5,service.activity(900002).stock());
    }
    private int countOrders() {return jdbc.queryForObject("SELECT COUNT(*) FROM seckill_order WHERE activity_id BETWEEN 900001 AND 900010",Integer.class);}
    private List<String> execute(List<Callable<String>> calls) throws Exception {
        ExecutorService pool=Executors.newFixedThreadPool(12);
        try {List<String> values=new ArrayList<>(); for(Future<String> f:pool.invokeAll(calls,30,TimeUnit.SECONDS)) values.add(f.get());return values;}
        finally {pool.shutdownNow();}
    }
}
