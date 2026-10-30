-- 手动执行：仅重置 ID 1..5 的演示活动，会删除这些活动的实验订单。
-- 不在应用启动时自动执行，不影响其他活动。执行前保留需要的实验结果。
USE lab2_seckill;
START TRANSACTION;
DELETE FROM seckill_order WHERE activity_id IN (1,2,3,4,5);
UPDATE seckill_activity SET stock=initial_stock WHERE id IN (1,2,3,4,5);
UPDATE seckill_activity SET start_time=NOW(6)-INTERVAL 1 HOUR,end_time=NOW(6)+INTERVAL 7 DAY,status='ACTIVE' WHERE id=1;
UPDATE seckill_activity SET start_time=NOW(6)+INTERVAL 1 DAY,end_time=NOW(6)+INTERVAL 2 DAY,status='ACTIVE' WHERE id=2;
UPDATE seckill_activity SET start_time=NOW(6)-INTERVAL 2 DAY,end_time=NOW(6)-INTERVAL 1 DAY,status='ACTIVE' WHERE id=3;
UPDATE seckill_activity SET start_time=NOW(6)-INTERVAL 1 HOUR,end_time=NOW(6)+INTERVAL 1 DAY,status='DISABLED' WHERE id=4;
UPDATE seckill_activity SET start_time=NOW(6)-INTERVAL 1 HOUR,end_time=NOW(6)+INTERVAL 1 DAY,status='ACTIVE' WHERE id=5;
COMMIT;
