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
