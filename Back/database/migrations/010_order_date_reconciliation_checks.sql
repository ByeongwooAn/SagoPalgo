-- 주문번호를 모를 때 날짜별 읽기 전용 조회의 요약만 감사 기록으로 남깁니다.
CREATE TABLE IF NOT EXISTS order_date_reconciliation_checks (
  order_date_reconciliation_check_id BIGINT NOT NULL AUTO_INCREMENT,
  order_approval_id BIGINT NOT NULL,
  user_id BIGINT NOT NULL,
  order_date DATE NOT NULL,
  complete_scan BOOLEAN NOT NULL,
  pages_scanned INT NOT NULL,
  row_count INT NOT NULL,
  item_limit_reached BOOLEAN NOT NULL,
  checked_at DATETIME NOT NULL,
  PRIMARY KEY (order_date_reconciliation_check_id),
  KEY idx_order_date_reconciliation_checks_approval_checked (order_approval_id, checked_at),
  CONSTRAINT fk_order_date_reconciliation_checks_approval FOREIGN KEY (order_approval_id)
    REFERENCES order_approvals (order_approval_id) ON DELETE CASCADE,
  CONSTRAINT fk_order_date_reconciliation_checks_user FOREIGN KEY (user_id)
    REFERENCES users (user_id) ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='주문번호 없는 날짜별 주문 조회 감사 요약';
