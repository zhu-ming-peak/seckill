-- 手动执行：仅重置 ID 1..5 的演示活动，会删除这些活动的实验订单。
-- 不在应用启动时自动执行，不影响其他活动。执行前保留需要的实验结果。
-- 异步版：必须先停止所有应用/生产者/消费者，保存并核对 ACCEPTED 请求。
-- 此脚本会一并删除 1..5 的持久请求；不要在需要履约的请求尚未处理时使用。
-- 执行后只删除相应活动的 lab2:v3:activity:{id}:reservation 键，再启动异步版重建。
-- 老 Broker 消息可能仍存在；UUID 请求编号不可复用，已删除请求的旧消息仅记录告警后确认。
USE lab2_seckill;
START TRANSACTION;
DELETE FROM seckill_request WHERE activity_id IN (1,2,3,4,5);
DELETE FROM seckill_order WHERE activity_id IN (1,2,3,4,5);
UPDATE seckill_activity SET stock=initial_stock WHERE id IN (1,2,3,4,5);
UPDATE seckill_activity SET start_time=NOW(6)-INTERVAL 1 HOUR,end_time=NOW(6)+INTERVAL 7 DAY,status='ACTIVE' WHERE id=1;
UPDATE seckill_activity SET start_time=NOW(6)+INTERVAL 1 DAY,end_time=NOW(6)+INTERVAL 2 DAY,status='ACTIVE' WHERE id=2;
UPDATE seckill_activity SET start_time=NOW(6)-INTERVAL 2 DAY,end_time=NOW(6)-INTERVAL 1 DAY,status='ACTIVE' WHERE id=3;
UPDATE seckill_activity SET start_time=NOW(6)-INTERVAL 1 HOUR,end_time=NOW(6)+INTERVAL 1 DAY,status='DISABLED' WHERE id=4;
UPDATE seckill_activity SET start_time=NOW(6)-INTERVAL 1 HOUR,end_time=NOW(6)+INTERVAL 1 DAY,status='ACTIVE' WHERE id=5;
COMMIT;
