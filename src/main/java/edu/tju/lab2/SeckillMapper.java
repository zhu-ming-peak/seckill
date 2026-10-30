package edu.tju.lab2;

import java.util.List;
import org.apache.ibatis.annotations.*;

@Mapper
public interface SeckillMapper {
    @Select("SELECT id,name,description,regular_price FROM product WHERE id=#{id}")
    Product product(long id);
    @Update("UPDATE product SET name=#{name},description=#{description},regular_price=#{regularPrice} WHERE id=#{id}")
    int updateProduct(Product product);
    @Select("SELECT a.*,CURRENT_TIMESTAMP(6) AS server_time FROM seckill_activity a ORDER BY id")
    List<ActivityData> activityDataList();
    @Select("SELECT a.*,CURRENT_TIMESTAMP(6) AS server_time FROM seckill_activity a WHERE id=#{id}")
    ActivityData activityData(long id);
    String ACTIVITY_SELECT = """
        SELECT a.id,a.product_id,a.title,p.name AS product_name,p.description,p.regular_price,
               a.seckill_price,a.initial_stock,a.stock,a.start_time,a.end_time,a.status,
               CURRENT_TIMESTAMP(6) AS server_time
        FROM seckill_activity a JOIN product p ON p.id=a.product_id
        """;
    @Select(ACTIVITY_SELECT + " ORDER BY a.id")
    List<Activity> activities();
    @Select(ACTIVITY_SELECT + " WHERE a.id=#{id}")
    Activity activity(long id);
    @Select(ACTIVITY_SELECT + " WHERE a.id=#{id} FOR UPDATE")
    Activity lockActivity(long id);
    @Select("SELECT * FROM seckill_order WHERE request_id=#{requestId}")
    Order byRequest(String requestId);
    @Select("SELECT * FROM seckill_order WHERE activity_id=#{activityId} AND user_id=#{userId}")
    Order byBuyer(@Param("activityId") long activityId, @Param("userId") String userId);
    @Select("SELECT * FROM seckill_order WHERE user_id=#{userId} ORDER BY created_at DESC,id DESC LIMIT 100")
    List<Order> userOrders(String userId);
    @Update("""
        UPDATE seckill_activity SET stock=stock-1 WHERE id=#{id} AND stock>0
        AND status='ACTIVE' AND start_time<=CURRENT_TIMESTAMP(6) AND end_time>CURRENT_TIMESTAMP(6)
        """)
    int decrement(long id);
    @Insert("""
        INSERT INTO seckill_order(id,request_id,activity_id,user_id,product_name,unit_price,quantity,status)
        VALUES(#{id},#{requestId},#{activityId},#{userId},#{productName},#{unitPrice},1,'SUCCESS')
        """)
    int insertOrder(Order order);
}
