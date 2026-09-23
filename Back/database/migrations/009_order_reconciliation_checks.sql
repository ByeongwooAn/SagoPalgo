-- 불명확한 주문의 읽기 전용 KB 조회 결과를 감사 기록으로 남깁니다.
CREATE TABLE IF NOT EXISTS order_reconciliation_checks (
  order_reconciliation_check_id BIGINT NOT NULL AUTO_INCREMENT,
  order_approval_id BIGINT NOT NULL,
  user_id BIGINT NOT NULL,
  order_date DATE NOT NULL,
  order_no CHAR(10) NOT NULL,
  complete_scan BOOLEAN NOT NULL,
  pages_scanned INT NOT NULL,
  match_count INT NOT NULL,
  review_status VARCHAR(30) NOT NULL,
  checked_at DATETIME NOT NULL,
  PRIMARY KEY (order_reconciliation_check_id),
  KEY idx_order_reconciliation_checks_approval_checked (order_approval_id, checked_at),
  CONSTRAINT fk_order_reconciliation_checks_approval FOREIGN KEY (order_approval_id)
    REFERENCES order_approvals (order_approval_id) ON DELETE CASCADE,
  CONSTRAINT fk_order_reconciliation_checks_user FOREIGN KEY (user_id)
    REFERENCES users (user_id) ON DELETE CASCADE,
  CONSTRAINT chk_order_reconciliation_checks_status
    CHECK (review_status IN ('INCOMPLETE_SCAN', 'NO_MATCH_IN_SCAN', 'MATCHES_REQUIRE_REVIEW'))
) ENGINE=InnoDB COMMENT='불명확한 주문의 읽기 전용 조회 감사 기록';
