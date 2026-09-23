-- 승인 기록은 증권사 주문이 아닙니다. 토큰 원문은 저장하지 않습니다.
CREATE TABLE IF NOT EXISTS order_approvals (
  order_approval_id BIGINT NOT NULL AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  order_precheck_id BIGINT NOT NULL,
  token_hash CHAR(64) NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'PREPARED',
  expires_at DATETIME NOT NULL,
  acknowledged_at DATETIME NULL,
  created_at DATETIME NOT NULL,
  PRIMARY KEY (order_approval_id),
  UNIQUE KEY uq_order_approvals_precheck (order_precheck_id),
  KEY idx_order_approvals_user_created (user_id, created_at),
  CONSTRAINT fk_order_approvals_user FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
  CONSTRAINT fk_order_approvals_precheck FOREIGN KEY (order_precheck_id) REFERENCES order_prechecks (order_precheck_id) ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='실주문 미전송 수동 승인 감사 기록';
