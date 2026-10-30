-- 仅用于 lab2_seckill，不删除数据库或已有表。
CREATE DATABASE IF NOT EXISTS lab2_seckill CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin;
USE lab2_seckill;
CREATE TABLE IF NOT EXISTS product (
  id BIGINT PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  description VARCHAR(500) NOT NULL,
  regular_price DECIMAL(10,2) NOT NULL,
  CONSTRAINT ck_product_price CHECK (regular_price > 0)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS seckill_activity (
  id BIGINT PRIMARY KEY,
  product_id BIGINT NOT NULL,
  title VARCHAR(100) NOT NULL,
  seckill_price DECIMAL(10,2) NOT NULL,
  initial_stock INT NOT NULL,
  stock INT NOT NULL,
  start_time DATETIME(6) NOT NULL,
  end_time DATETIME(6) NOT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
  CONSTRAINT fk_activity_product FOREIGN KEY (product_id) REFERENCES product(id),
  CONSTRAINT ck_activity_stock CHECK (initial_stock >= 0 AND stock >= 0 AND stock <= initial_stock),
  CONSTRAINT ck_activity_price CHECK (seckill_price > 0),
  CONSTRAINT ck_activity_time CHECK (end_time > start_time),
  CONSTRAINT ck_activity_status CHECK (status IN ('ACTIVE','DISABLED'))
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS seckill_order (
  id CHAR(36) PRIMARY KEY,
  request_id VARCHAR(64) NOT NULL,
  activity_id BIGINT NOT NULL,
  user_id VARCHAR(64) NOT NULL,
  product_name VARCHAR(100) NOT NULL,
  unit_price DECIMAL(10,2) NOT NULL,
  quantity INT NOT NULL DEFAULT 1,
  status VARCHAR(16) NOT NULL DEFAULT 'SUCCESS',
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  CONSTRAINT uk_order_request UNIQUE (request_id),
  CONSTRAINT uk_order_buyer UNIQUE (activity_id,user_id),
  CONSTRAINT fk_order_activity FOREIGN KEY (activity_id) REFERENCES seckill_activity(id),
  CONSTRAINT ck_order_quantity CHECK (quantity = 1),
  CONSTRAINT ck_order_price CHECK (unit_price > 0),
  CONSTRAINT ck_order_status CHECK (status = 'SUCCESS'),
  INDEX ix_order_user_created (user_id,created_at)
) ENGINE=InnoDB;
