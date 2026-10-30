package edu.tju.lab2;

import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

@SpringBootTest(properties={"seckill.mq-enabled=true","seckill.mq-topic=Lab2OrdersV3Tests",
    "seckill.mq-consumer-group=lab2-tests-v3","seckill.mq-consumer-enabled=false",
    "seckill.mq-initial-delay=600000","seckill.reconcile-initial-delay=600000",
    "seckill.warmup-enabled=false","seckill.redis-prefix=lab2:test:mq:"})
class RocketMqIntegrationTest {
    @Autowired AsyncPurchaseService service;
    @Autowired RequestMapper requests;
    @Autowired AsyncBackgroundWorker dispatcher;
    @Autowired JdbcTemplate jdbc;
    @Autowired StringRedisTemplate redis;
    @Autowired RedisStockGate gate;
    @MockitoSpyBean RocketMqGateway gateway;
    @MockitoSpyBean AsyncOrderProcessor processor;
    @BeforeEach void setup(){
        gateway.stopConsumer();clean();
        jdbc.update("INSERT INTO product VALUES(900200,'真实消息验证','专用测试记录',20.00)");
        jdbc.update("INSERT INTO seckill_activity VALUES(900200,900200,'消息测试',8.00,3,3,NOW()-INTERVAL 1 HOUR,NOW()+INTERVAL 1 DAY,'ACTIVE')");
    }
    @AfterEach void clean(){
        gateway.stopConsumer();
        jdbc.update("DELETE FROM seckill_request WHERE activity_id=900200");
        jdbc.update("DELETE FROM seckill_order WHERE activity_id=900200");
        jdbc.update("DELETE FROM seckill_activity WHERE id=900200");
        jdbc.update("DELETE FROM product WHERE id=900200");
        redis.delete(List.of(gate.key(900200),"lab2:test:mq:product:900200"));
    }
    @Test void pendingQueueAndDuplicateMessagesUseRealBroker() throws Exception{
        String id=UUID.randomUUID().toString();service.accept(900200,"mq-user",id);
        dispatcher.dispatch();
        assertEquals("ACCEPTED",requests.get(id).state());assertEquals(1,requests.get(id).sendCount());
        assertNull(service.result(id,"mq-user").order());
        gateway.startConsumer();awaitSuccess(id);
        gateway.publish(id);gateway.publish(id);
        verify(processor,timeout(15000).atLeast(3)).process(id,900200);
        assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM seckill_order WHERE activity_id=900200",Integer.class));
        assertEquals(1,requests.get(id).processingAttempts());
    }
    @Test void outboxRetriesAnAmbiguousSendFailure() throws Exception{
        String id=UUID.randomUUID().toString();service.accept(900200,"send-retry",id);
        doThrow(new Exception("injected send timeout")).doCallRealMethod().when(gateway).publish(id);
        dispatcher.dispatch();
        assertEquals("ACCEPTED",requests.get(id).state());assertEquals(1,requests.get(id).sendCount());
        jdbc.update("UPDATE seckill_request SET next_send_at=NOW(6) WHERE request_id=?",id);
        gateway.startConsumer();dispatcher.dispatch();awaitSuccess(id);
        assertEquals(2,requests.get(id).sendCount());
    }
    @Test void consumerExceptionTriggersRealBrokerRedelivery() throws Exception{
        String id=UUID.randomUUID().toString();service.accept(900200,"consume-retry",id);
        doThrow(new IllegalStateException("injected transient consumer error")).doCallRealMethod().when(processor).process(id,900200);
        gateway.startConsumer();dispatcher.dispatch();awaitSuccess(id);
        verify(processor,atLeast(2)).process(id,900200);
        assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM seckill_order WHERE activity_id=900200",Integer.class));
    }
    private void awaitSuccess(String id) throws Exception{
        long until=System.nanoTime()+45_000_000_000L;
        while(System.nanoTime()<until){if("SUCCESS".equals(requests.get(id).state()))return;Thread.sleep(100);}
        fail("MQ request remained "+requests.get(id).state());
    }
}
