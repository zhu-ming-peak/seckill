-- 仅初始化缺失的演示数据；重复执行不重置库存、不覆盖订单。
USE lab2_seckill;
INSERT IGNORE INTO product(id,name,description,regular_price) VALUES
(1,'青瓷随行杯','温润青瓷，日常随行。实验演示商品，不产生真实交易。',69.00),
(2,'轻量机械键盘','让每一次敲击更从容。实验演示商品。',299.00),
(3,'桌面收纳套装','把桌面留给灵感。实验演示商品。',99.00);
INSERT IGNORE INTO seckill_activity(id,product_id,title,seckill_price,initial_stock,stock,start_time,end_time,status) VALUES
(1,1,'今日限量 · 青瓷随行杯',19.90,30,30,NOW(6)-INTERVAL 1 HOUR,NOW(6)+INTERVAL 7 DAY,'ACTIVE'),
(2,2,'明日开抢 · 机械键盘',99.00,10,10,NOW(6)+INTERVAL 1 DAY,NOW(6)+INTERVAL 2 DAY,'ACTIVE'),
(3,3,'往期活动 · 收纳套装',29.90,8,8,NOW(6)-INTERVAL 2 DAY,NOW(6)-INTERVAL 1 DAY,'ACTIVE'),
(4,3,'暂未开放 · 收纳套装',39.90,5,5,NOW(6)-INTERVAL 1 HOUR,NOW(6)+INTERVAL 1 DAY,'DISABLED'),
(5,1,'售罄演示 · 青瓷随行杯',9.90,0,0,NOW(6)-INTERVAL 1 HOUR,NOW(6)+INTERVAL 1 DAY,'ACTIVE');
