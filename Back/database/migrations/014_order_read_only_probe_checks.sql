-- 수동 KB 주문 이력 읽기 전용 점검의 민감값 없는 결과만 보관합니다.
CREATE TABLE IF NOT EXISTS order_read_only_probe_checks (
  probe_check_id BIGINT NOT NULL AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  status VARCHAR(30) NOT NULL,
  order_date CHAR(8) NOT NULL,
  checked_at DATETIME NOT NULL,
  PRIMARY KEY (probe_check_id),
  KEY idx_order_read_only_probe_user_checked (user_id, checked_at, probe_check_id),
  CONSTRAINT fk_order_read_only_probe_user FOREIGN KEY (user_id)
    REFERENCES users (user_id) ON DELETE CASCADE,
  CONSTRAINT chk_order_read_only_probe_status
    CHECK (status IN ('VERIFIED', 'UNVERIFIED', 'CONFIGURATION_BLOCKED'))
) ENGINE=InnoDB COMMENT='KB 주문 이력 읽기 전용 수동 점검 요약';
