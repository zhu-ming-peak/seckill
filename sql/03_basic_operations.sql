-- 在独立事务中演示新增、查询、修改、删除；演示记录最终删除。
USE lab2_seckill;
START TRANSACTION;
INSERT INTO product(id,name,description,regular_price) VALUES(800001,'CRUD 演示商品','仅供基础数据库操作验证',10.00);
SELECT id,name,regular_price FROM product WHERE id=800001;
UPDATE product SET regular_price=12.00 WHERE id=800001;
SELECT id,name,regular_price FROM product WHERE id=800001;
DELETE FROM product WHERE id=800001;
COMMIT;
SELECT COUNT(*) AS remaining_demo_rows FROM product WHERE id=800001;
-- 事务回滚：更改不会保留。
START TRANSACTION;
UPDATE product SET regular_price=regular_price+1 WHERE id=1;
SELECT id,regular_price AS value_inside_transaction FROM product WHERE id=1;
ROLLBACK;
SELECT id,regular_price AS value_after_rollback FROM product WHERE id=1;
