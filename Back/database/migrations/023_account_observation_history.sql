-- 읽기 관찰 이력만 추가합니다. 기존 보유·원장·주문·제출/변경 가드는 수정하지 않습니다.
CREATE TABLE IF NOT EXISTS kb_account_observations (
  record_id BIGINT NOT NULL AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  request_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  account_binding CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  order_date CHAR(8) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  storage_state VARCHAR(20) NOT NULL,
  observation_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
  snapshot_status VARCHAR(20) NULL,
  payload LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NULL,
  payload_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
  failure_code VARCHAR(40) NULL,
  created_at DATETIME(6) NOT NULL,
  completed_at DATETIME(6) NULL,
  PRIMARY KEY (record_id),
  UNIQUE KEY uk_account_observation_request (user_id,request_id),
  UNIQUE KEY uk_account_observation_snapshot (user_id,observation_id),
  KEY idx_account_observation_scope (user_id,account_binding,record_id),
  CONSTRAINT fk_account_observation_user FOREIGN KEY(user_id) REFERENCES users(user_id),
  CONSTRAINT chk_account_observation_json CHECK (payload IS NULL OR JSON_VALID(payload)),
  CONSTRAINT chk_account_observation_state CHECK (
    (storage_state='PENDING' AND observation_id IS NULL AND snapshot_status IS NULL
      AND payload IS NULL AND payload_sha256 IS NULL AND failure_code IS NULL AND completed_at IS NULL)
    OR (storage_state='COMPLETED' AND observation_id IS NOT NULL
      AND snapshot_status IS NOT NULL AND snapshot_status IN ('SUCCESS','PARTIAL','FAILED','DISABLED')
      AND payload IS NOT NULL AND payload_sha256 IS NOT NULL AND failure_code IS NULL AND completed_at IS NOT NULL)
    OR (storage_state='FAILED' AND observation_id IS NULL AND snapshot_status IS NULL
      AND payload IS NULL AND payload_sha256 IS NULL
      AND failure_code IS NOT NULL AND failure_code IN ('CONTEXT_CHANGED','OBSERVATION_FAILED') AND completed_at IS NOT NULL)
  )
) ENGINE=InnoDB COMMENT='KB 읽기 관찰 저장 요청·불변 결과. 거래 원장/주문 판정 아님';
