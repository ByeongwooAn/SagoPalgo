-- 016 적용 DB를 백업한 뒤 실행. 원래 전송 결과와 제출 가드는 변경하지 않습니다.
CREATE TABLE IF NOT EXISTS manual_order_reconciliation_preparations (
  command_id CHAR(36) NOT NULL PRIMARY KEY,
  user_id BIGINT NOT NULL,
  account_fingerprint CHAR(64) NOT NULL,
  order_no CHAR(10) NOT NULL,
  token_hash CHAR(64) NOT NULL,
  expires_at DATETIME NOT NULL,
  checked_at DATETIME NOT NULL,
  CONSTRAINT fk_manual_reconcile_preparation_command FOREIGN KEY (command_id) REFERENCES manual_order_commands(command_id),
  CONSTRAINT fk_manual_reconcile_preparation_user FOREIGN KEY (user_id) REFERENCES users(user_id)
) ENGINE=InnoDB COMMENT='미확정 신규 주문 전량 체결 대조의 90초 확인';

CREATE TABLE IF NOT EXISTS manual_order_reconciliations (
  command_id CHAR(36) NOT NULL PRIMARY KEY,
  user_id BIGINT NOT NULL,
  account_fingerprint CHAR(64) NOT NULL,
  order_date CHAR(8) NOT NULL,
  order_no CHAR(10) NOT NULL,
  order_time CHAR(6) NOT NULL,
  filled_quantity DECIMAL(18,4) NOT NULL,
  confirmed_at DATETIME NOT NULL,
  UNIQUE KEY uq_manual_reconciled_broker_order (account_fingerprint, order_date, order_no),
  CONSTRAINT fk_manual_reconcile_command FOREIGN KEY (command_id) REFERENCES manual_order_commands(command_id),
  CONSTRAINT fk_manual_reconcile_user FOREIGN KEY (user_id) REFERENCES users(user_id)
) ENGINE=InnoDB COMMENT='사용자가 확정한 KB 신규 주문 전량 체결 대조 감사 기록';
