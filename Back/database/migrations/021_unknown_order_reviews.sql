-- 기존 주문·제출/변경 가드·전량 체결 확정 기록을 변경하지 않습니다. 백업 후 적용하세요.
CREATE TABLE IF NOT EXISTS manual_order_review_preparations (
  command_id CHAR(36) NOT NULL PRIMARY KEY,
  user_id BIGINT NOT NULL,
  review_id CHAR(36) NOT NULL UNIQUE,
  account_fingerprint CHAR(64) NOT NULL,
  token_hash CHAR(64) NOT NULL,
  evidence_hash CHAR(64) NOT NULL,
  evidence_json JSON NOT NULL,
  expires_at DATETIME(6) NOT NULL,
  checked_at DATETIME(6) NOT NULL,
  CONSTRAINT fk_manual_review_prepare_command FOREIGN KEY(command_id) REFERENCES manual_order_commands(command_id),
  CONSTRAINT fk_manual_review_prepare_user FOREIGN KEY(user_id) REFERENCES users(user_id)
) ENGINE=InnoDB COMMENT='UNKNOWN 잔량·변경 대조의 90초 확인 준비';

CREATE TABLE IF NOT EXISTS manual_order_reviews (
  review_id CHAR(36) NOT NULL PRIMARY KEY,
  command_id CHAR(36) NOT NULL,
  user_id BIGINT NOT NULL,
  account_fingerprint CHAR(64) NOT NULL,
  token_hash CHAR(64) NOT NULL,
  evidence_json JSON NOT NULL,
  confirmed_at DATETIME(6) NOT NULL,
  KEY idx_manual_review_command(command_id,confirmed_at),
  CONSTRAINT fk_manual_review_command FOREIGN KEY(command_id) REFERENCES manual_order_commands(command_id),
  CONSTRAINT fk_manual_review_user FOREIGN KEY(user_id) REFERENCES users(user_id)
) ENGINE=InnoDB COMMENT='사용자 확인한 UNKNOWN 대조 관찰. 잠금 해제 근거가 아님';
