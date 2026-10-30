USE lab2_seckill;
-- 请求记录同时作为持久化 outbox；既有订单和库存不重置。
CREATE TABLE IF NOT EXISTS seckill_request (
  request_id VARCHAR(64) PRIMARY KEY,
  activity_id BIGINT NOT NULL,
  user_id VARCHAR(64) NOT NULL,
  token CHAR(36) NOT NULL,
  product_name VARCHAR(100) NOT NULL,
  accepted_price DECIMAL(10,2) NOT NULL,
  state VARCHAR(16) NOT NULL DEFAULT 'ACCEPTED',
  failure_code VARCHAR(64) NULL,
  order_id CHAR(36) NULL,
  accepted_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  send_count INT NOT NULL DEFAULT 0,
  next_send_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  last_message_id VARCHAR(128) NULL,
  processing_attempts INT NOT NULL DEFAULT 0,
  redis_done INT NOT NULL DEFAULT 0,
  UNIQUE KEY uk_request_buyer(activity_id,user_id),
  KEY ix_request_dispatch(state,next_send_at),
  KEY ix_request_reconcile(state,redis_done),
  CONSTRAINT fk_request_activity FOREIGN KEY(activity_id) REFERENCES seckill_activity(id),
  CONSTRAINT ck_request_state CHECK(state IN ('ACCEPTED','SUCCESS','FAILED')),
  CONSTRAINT ck_request_price CHECK(accepted_price>0)
) ENGINE=InnoDB;
