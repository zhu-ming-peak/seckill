package edu.tju.lab2;

import java.util.*;
import java.util.concurrent.*;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(properties={"seckill.mq-enabled=false","seckill.redis-enabled=true","seckill.warmup-enabled=false","seckill.redis-prefix=lab2:test:async:"})
class AsyncWorkflowTest {
    @Autowired AsyncPurchaseService service;
    @Autowired AsyncOrderProcessor processor;
    @Autowired AsyncInventoryReconciler repair;
    @Autowired RequestMapper requests;
    @Autowired SeckillMapper orders;
    @Autowired RedisStockGate gate;
    @Autowired StringRedisTemplate redis;
    @Autowired JdbcTemplate jdbc;
    @Autowired PlatformTransactionManager transactions;
    @BeforeEach void setup(){
        cleanup();
        jdbc.update("INSERT INTO product VALUES(900100,'异步验证商品','专用测试数据',30.00)");
        jdbc.update("INSERT INTO seckill_activity VALUES(900100,900100,'异步测试',9.90,4,4,NOW()-INTERVAL 1 HOUR,NOW()+INTERVAL 1 DAY,'ACTIVE')");
    }
    @AfterEach void cleanup(){
        jdbc.update("DELETE FROM seckill_request WHERE activity_id=900100");
        jdbc.update("DELETE FROM seckill_order WHERE activity_id=900100");
        jdbc.update("DELETE FROM seckill_activity WHERE id=900100");
        jdbc.update("DELETE FROM product WHERE id=900100");
        redis.delete(List.of(gate.key(900100),"lab2:test:async:product:900100"));
    }
    @Test void acceptanceIsDurableButNotAnOrder(){
        var receipt=service.accept(900100,"buyer","pending-1");
        assertEquals("ACCEPTED",receipt.state());assertNull(receipt.order());
        assertEquals(4,orders.activity(900100).stock());
        assertEquals(3,service.activity(900100).stock());
        assertEquals("3",redis.opsForHash().get(gate.key(900100),"stock"));
        assertNull(orders.byRequest("pending-1"));
    }
    @Test void duplicateConsumptionCreatesOneOrder(){
        service.accept(900100,"buyer","duplicate-message");
        for(int i=0;i<10;i++)processor.process("duplicate-message",900100);
        repair.terminal("duplicate-message");
        assertEquals("SUCCESS",requests.get("duplicate-message").state());
        assertEquals(1,requests.get("duplicate-message").processingAttempts());
        assertEquals(3,orders.activity(900100).stock());
        assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM seckill_order WHERE activity_id=900100",Integer.class));
        assertEquals("SUCCESS",service.accept(900100,"buyer","duplicate-message").state());
    }
    @Test void lateSendAcknowledgementKeepsCorrelationWithoutReopeningRequest(){
        service.accept(900100,"fast-consumer","late-send-ack");
        processor.process("late-send-ack",900100);
        assertEquals(1,requests.sent("late-send-ack","broker-message-id"));
        assertEquals("SUCCESS",requests.get("late-send-ack").state());
        assertEquals("broker-message-id",requests.get("late-send-ack").lastMessageId());
        assertTrue(requests.due().stream().noneMatch(r->r.requestId().equals("late-send-ack")));
    }
    @Test void retrySameRequestDoesNotReserveAgain(){
        service.accept(900100,"buyer","same-request");String token=requests.get("same-request").token();
        service.accept(900100,"buyer","same-request");
        assertEquals(token,requests.get("same-request").token());
        assertEquals("3",redis.opsForHash().get(gate.key(900100),"stock"));
        assertThrows(BusinessException.class,()->service.accept(900100,"buyer","different-request"));
    }
    @Test void acceptanceRollbackRestoresCapacity(){
        assertThrows(IllegalStateException.class,()->new TransactionTemplate(transactions).executeWithoutResult(s->{
            service.accept(900100,"rollback","rollback-accepted");throw new IllegalStateException("simulated failure");
        }));
        assertNull(requests.get("rollback-accepted"));
        assertEquals("4",redis.opsForHash().get(gate.key(900100),"stock"));
    }
    @Test void consumerFailureCanBeRetriedWithoutPartialOrder(){
        service.accept(900100,"retry","consumer-failure");
        assertThrows(IllegalStateException.class,()->new TransactionTemplate(transactions).executeWithoutResult(s->{
            processor.process("consumer-failure",900100);throw new IllegalStateException("simulated post-insert failure");
        }));
        assertEquals("ACCEPTED",requests.get("consumer-failure").state());assertNull(orders.byRequest("consumer-failure"));
        assertEquals(4,orders.activity(900100).stock());
        processor.process("consumer-failure",900100);repair.terminal("consumer-failure");
        assertEquals("SUCCESS",requests.get("consumer-failure").state());
    }
    @Test void rebuildRecoversPendingReservationsAndOrphans(){
        service.accept(900100,"pending","recover-pending");
        redis.delete(gate.key(900100));repair.rebuild(900100);
        assertEquals("3",redis.opsForHash().get(gate.key(900100),"stock"));
        assertEquals(requests.get("recover-pending").token(),redis.opsForHash().get(gate.key(900100),"user:pending"));
        gate.reserveRaw(orders.activity(900100),"orphan","orphan-token");
        repair.rebuild(900100);
        assertNull(redis.opsForHash().get(gate.key(900100),"user:orphan"));
        assertEquals("3",redis.opsForHash().get(gate.key(900100),"stock"));
    }
    @Test void acceptedRequestsSurviveActivityEnd(){
        service.accept(900100,"queued","end-after-accept");
        jdbc.update("UPDATE seckill_activity SET start_time=NOW()-INTERVAL 2 DAY,end_time=NOW()-INTERVAL 1 DAY WHERE id=900100");
        processor.process("end-after-accept",900100);repair.terminal("end-after-accept");
        assertEquals("SUCCESS",requests.get("end-after-accept").state());
        assertEquals(3,orders.activity(900100).stock());
    }
    @Test void permanentInventoryFailureIsQueryableAndReconciled(){
        service.accept(900100,"failure","db-stock-failure");
        jdbc.update("UPDATE seckill_activity SET stock=0 WHERE id=900100");
        processor.process("db-stock-failure",900100);repair.terminal("db-stock-failure");repair.rebuild(900100);
        assertEquals("FAILED",service.result("db-stock-failure","failure").state());
        assertEquals("DB_STOCK_EXHAUSTED",requests.get("db-stock-failure").failureCode());
        assertEquals("0",redis.opsForHash().get(gate.key(900100),"stock"));
        assertNull(orders.byRequest("db-stock-failure"));
    }
    @Test void concurrentRequestsCannotOverReserve() throws Exception{
        var pool=Executors.newFixedThreadPool(12);List<Callable<String>> work=new ArrayList<>();
        for(int i=0;i<16;i++){int n=i;work.add(()->{try{return service.accept(900100,"async"+n,"async-"+n).state();}catch(BusinessException e){return e.code;}});}
        try{
            var outcomes=pool.invokeAll(work,30,TimeUnit.SECONDS);long accepted=0;
            for(var f:outcomes)if("ACCEPTED".equals(f.get()))accepted++;
            assertEquals(4,accepted);assertEquals(4,requests.pending(900100).size());
            assertEquals("0",redis.opsForHash().get(gate.key(900100),"stock"));
            for(var r:requests.pending(900100)){processor.process(r.requestId(),900100);repair.terminal(r.requestId());}
            repair.rebuild(900100);assertEquals(0,orders.activity(900100).stock());
            assertEquals(4,jdbc.queryForObject("SELECT COUNT(*) FROM seckill_order WHERE activity_id=900100",Integer.class));
        }finally{pool.shutdownNow();}
    }
}
