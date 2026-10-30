package edu.tju.lab2;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(properties={"seckill.redis-enabled=true","seckill.warmup-enabled=false","spring.data.redis.port=16398",
    "spring.data.redis.connect-timeout=200ms","spring.data.redis.timeout=200ms","seckill.redis-prefix=lab2:test:outage:"})
class RedisOutageTest {
    @Autowired ProductCache products;
    @Autowired SeckillService service;
    @Autowired JdbcTemplate jdbc;
    @BeforeEach void prepare(){
        clean();
        jdbc.update("INSERT INTO product VALUES(900020,'故障测试商品','Redis 故障验证',10.00)");
        jdbc.update("INSERT INTO seckill_activity VALUES(900020,900020,'故障测试',5.00,3,3,NOW()-INTERVAL 1 HOUR,NOW()+INTERVAL 1 DAY,'ACTIVE')");
    }
    @AfterEach void clean(){
        jdbc.update("DELETE FROM seckill_order WHERE activity_id=900020");
        jdbc.update("DELETE FROM seckill_activity WHERE id=900020");
        jdbc.update("DELETE FROM product WHERE id=900020");
    }
    @Test void productReadFallsBackToMysql(){assertEquals("故障测试商品",products.get(900020).name());}
    @Test void reservationFailureDoesNotDecrementMysql(){
        assertThrows(org.springframework.data.redis.RedisConnectionFailureException.class,
            ()->service.place(900020,"outage-user","outage-request"));
        assertEquals(3,jdbc.queryForObject("SELECT stock FROM seckill_activity WHERE id=900020",Integer.class));
        assertEquals(0,jdbc.queryForObject("SELECT COUNT(*) FROM seckill_order WHERE activity_id=900020",Integer.class));
    }
}
