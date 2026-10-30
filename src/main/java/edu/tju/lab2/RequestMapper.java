package edu.tju.lab2;
import org.apache.ibatis.annotations.*;
import java.util.List;
import java.math.BigDecimal;

@Mapper
public interface RequestMapper {
    @Select("SELECT * FROM seckill_request WHERE request_id=#{id}") RequestRow get(String id);
    @Select("SELECT * FROM seckill_request WHERE request_id=#{id} FOR UPDATE") RequestRow lock(String id);
    @Select("SELECT * FROM seckill_request WHERE activity_id=#{activity} AND user_id=#{user}")
    RequestRow buyer(@Param("activity")long activity,@Param("user")String user);
    @Select("SELECT * FROM seckill_request WHERE activity_id=#{activity} AND state='ACCEPTED' ORDER BY request_id")
    List<RequestRow> pending(long activity);
    @Select("SELECT * FROM seckill_request WHERE user_id=#{user} ORDER BY accepted_at DESC LIMIT 30")
    List<RequestRow> userRequests(String user);
    record NewRequest(String requestId,long activityId,String userId,String token,String productName,BigDecimal acceptedPrice){}
    @Insert("""
        INSERT INTO seckill_request(request_id,activity_id,user_id,token,product_name,accepted_price)
        SELECT #{requestId},#{activityId},#{userId},#{token},#{productName},#{acceptedPrice}
        FROM seckill_activity WHERE id=#{activityId} AND status='ACTIVE'
        AND start_time<=CURRENT_TIMESTAMP(6) AND end_time>CURRENT_TIMESTAMP(6)
        """) int insert(NewRequest row);
    @Select("SELECT * FROM seckill_request WHERE state='ACCEPTED' AND next_send_at<=NOW(6) ORDER BY next_send_at LIMIT 20")
    List<RequestRow> due();
    @Update("UPDATE seckill_request SET next_send_at=NOW(6)+INTERVAL 10 SECOND,send_count=send_count+1 WHERE request_id=#{id} AND state='ACCEPTED' AND next_send_at<=NOW(6)")
    int claim(String id);
    // 消费提交可能早于生产者收到发送确认；终态也保留消息关联，但不重新打开请求。
    @Update("UPDATE seckill_request SET next_send_at=CASE WHEN state='ACCEPTED' THEN NOW(6)+INTERVAL 30 SECOND ELSE next_send_at END,last_message_id=#{messageId} WHERE request_id=#{id}")
    int sent(@Param("id")String id,@Param("messageId")String messageId);
    @Update("UPDATE seckill_request SET next_send_at=NOW(6)+INTERVAL 2 SECOND WHERE request_id=#{id} AND state='ACCEPTED'")
    int sendFailed(String id);
    @Update("UPDATE seckill_request SET processing_attempts=processing_attempts+1 WHERE request_id=#{id}") int attempt(String id);
    @Update("UPDATE seckill_request SET state='SUCCESS',order_id=#{orderId},failure_code=NULL WHERE request_id=#{id}")
    int success(@Param("id")String id,@Param("orderId")String orderId);
    @Update("UPDATE seckill_request SET state='FAILED',failure_code=#{code} WHERE request_id=#{id}")
    int fail(@Param("id")String id,@Param("code")String code);
    @Select("SELECT * FROM seckill_request WHERE state<>'ACCEPTED' AND redis_done=0 ORDER BY updated_at LIMIT 50")
    List<RequestRow> terminalUnreconciled();
    @Update("UPDATE seckill_request SET redis_done=1 WHERE request_id=#{id} AND state<>'ACCEPTED'") int redisDone(String id);
}
