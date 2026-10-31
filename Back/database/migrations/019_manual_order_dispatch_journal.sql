-- 기존 SENDING은 자동 변환하지 않습니다. 백업 후 적용하며 실주문 스위치는 변경하지 않습니다.
CREATE TABLE IF NOT EXISTS manual_order_dispatches (
  command_id CHAR(36) NOT NULL PRIMARY KEY,
  user_id BIGINT NOT NULL,
  execution_key CHAR(36) NOT NULL,
  phase VARCHAR(16) NOT NULL,
  outcome_status VARCHAR(12) NULL,
  order_no CHAR(10) NULL,
  result_code VARCHAR(30) NULL,
  process_code VARCHAR(30) NULL,
  reserved_at DATETIME(6) NOT NULL,
  started_at DATETIME(6) NULL,
  returned_at DATETIME(6) NULL,
  CONSTRAINT fk_manual_dispatch_command FOREIGN KEY (command_id) REFERENCES manual_order_commands(command_id),
  CONSTRAINT fk_manual_dispatch_user FOREIGN KEY (user_id) REFERENCES users(user_id),
  CONSTRAINT chk_manual_dispatch_phase CHECK (phase IN ('RESERVED','DISPATCHING','RETURNED')),
  CONSTRAINT chk_manual_dispatch_outcome CHECK (outcome_status IS NULL OR outcome_status IN ('ACCEPTED','REJECTED','UNKNOWN'))
) ENGINE=InnoDB COMMENT='실제 전송 시작과 반환 결과의 독립 커밋 기록';

CREATE TABLE IF NOT EXISTS manual_order_dispatch_recoveries (
  command_id CHAR(36) NOT NULL PRIMARY KEY,
  user_id BIGINT NOT NULL,
  previous_status VARCHAR(12) NOT NULL,
  recovered_status VARCHAR(12) NOT NULL,
  order_no CHAR(10) NOT NULL,
  recovered_at DATETIME(6) NOT NULL,
  CONSTRAINT fk_manual_dispatch_recovery_command FOREIGN KEY (command_id) REFERENCES manual_order_commands(command_id),
  CONSTRAINT fk_manual_dispatch_recovery_user FOREIGN KEY (user_id) REFERENCES users(user_id)
) ENGINE=InnoDB COMMENT='SENDING 저장 결과 수동 복구 감사 기록';
