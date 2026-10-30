USE lab2_seckill;
SELECT VERSION() AS mysql_version,@@transaction_isolation AS transaction_isolation;
SHOW TABLES;
SELECT a.id,a.title,a.initial_stock,a.stock,COUNT(o.id) AS orders,
       a.initial_stock-a.stock-COUNT(o.id) AS inventory_difference
FROM seckill_activity a LEFT JOIN seckill_order o ON o.activity_id=a.id GROUP BY a.id;
SELECT activity_id,user_id,COUNT(*) AS duplicate_count FROM seckill_order
GROUP BY activity_id,user_id HAVING COUNT(*)>1;
SELECT id,request_id,activity_id,user_id,product_name,unit_price,quantity,status,created_at
FROM seckill_order ORDER BY created_at DESC LIMIT 20;
-- 异步版需要先执行 06_async_requests.sql。以下值与订单查询分开取样，活跃写入时可能有时序差。
SELECT a.id,a.stock AS database_remaining,
 (SELECT COUNT(*) FROM seckill_request r WHERE r.activity_id=a.id AND state='ACCEPTED') AS accepted,
 a.stock-(SELECT COUNT(*) FROM seckill_request r WHERE r.activity_id=a.id AND state='ACCEPTED') AS expected_redis_available
FROM seckill_activity a;
SELECT request_id,activity_id,user_id,state,failure_code,order_id,send_count,last_message_id,processing_attempts,redis_done
FROM seckill_request ORDER BY accepted_at DESC LIMIT 30;
