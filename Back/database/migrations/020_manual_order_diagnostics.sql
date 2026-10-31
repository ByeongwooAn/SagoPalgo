-- 진단은 전송 결과/제출 가드/잠금을 변경하지 않습니다. 기존 DB 백업 후 적용합니다.
CREATE TABLE IF NOT EXISTS manual_order_diagnostics (
  diagnostic_id CHAR(36) NOT NULL PRIMARY KEY,
  command_id CHAR(36) NOT NULL,
  user_id BIGINT NOT NULL,
  order_no CHAR(10) NOT NULL,
  phase_before VARCHAR(24) NOT NULL,
  state VARCHAR(12) NOT NULL,
  report_json JSON NULL,
  created_at DATETIME(6) NOT NULL,
  completed_at DATETIME(6) NULL,
  KEY idx_manual_diagnostic_command (command_id,created_at),
  CONSTRAINT fk_manual_diagnostic_command FOREIGN KEY (command_id) REFERENCES manual_order_commands(command_id),
  CONSTRAINT fk_manual_diagnostic_user FOREIGN KEY (user_id) REFERENCES users(user_id),
  CONSTRAINT chk_manual_diagnostic_state CHECK (state IN ('REQUESTED','COMPLETED'))
) ENGINE=InnoDB COMMENT='잠금을 유지하는 SENDING 읽기 전용 수동 진단';
