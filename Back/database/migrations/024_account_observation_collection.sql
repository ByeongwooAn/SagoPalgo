-- 자동 수집의 실행 소유권·대기·중단 상태. 시세/주문/원장을 변경하지 않습니다.
CREATE TABLE IF NOT EXISTS kb_account_observation_collectors (
  user_id BIGINT NOT NULL,
  account_binding CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  state VARCHAR(20) NOT NULL,
  active_request_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
  active_order_date CHAR(8) CHARACTER SET ascii COLLATE ascii_bin NULL,
  last_request_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
  last_storage_state VARCHAR(20) NULL,
  last_snapshot_status VARCHAR(20) NULL,
  failure_code VARCHAR(40) NULL,
  next_due_at DATETIME(6) NOT NULL,
  started_at DATETIME(6) NULL,
  completed_at DATETIME(6) NULL,
  PRIMARY KEY(user_id,account_binding),
  UNIQUE KEY uk_account_collector_active(user_id,active_request_id),
  CONSTRAINT fk_account_collector_user FOREIGN KEY(user_id) REFERENCES users(user_id),
  CONSTRAINT chk_account_collector_last CHECK (
    (last_request_id IS NULL AND last_storage_state IS NULL AND last_snapshot_status IS NULL)
    OR (last_request_id IS NOT NULL AND last_storage_state IS NOT NULL AND (
      (last_storage_state='COMPLETED' AND last_snapshot_status IS NOT NULL
        AND last_snapshot_status IN ('SUCCESS','PARTIAL','FAILED','DISABLED'))
      OR (last_storage_state='FAILED' AND last_snapshot_status IS NULL)))
  ),
  CONSTRAINT chk_account_collector_state CHECK (
    (state='IDLE' AND active_request_id IS NULL AND active_order_date IS NULL AND failure_code IS NULL)
    OR (state='ACTIVE' AND active_request_id IS NOT NULL AND active_order_date IS NOT NULL
      AND started_at IS NOT NULL AND completed_at IS NULL AND failure_code IS NULL)
    OR (state='PAUSED' AND active_request_id IS NULL AND active_order_date IS NULL
      AND last_request_id IS NOT NULL AND failure_code IS NOT NULL AND started_at IS NOT NULL
      AND completed_at IS NOT NULL AND failure_code IN
        ('SNAPSHOT_PARTIAL','SNAPSHOT_FAILED','SNAPSHOT_DISABLED','SNAPSHOT_UNUSABLE','OBSERVATION_FAILED','CONTEXT_CHANGED'))
  )
) ENGINE=InnoDB COMMENT='KB 관찰 자동 수집 소유권. ACTIVE는 시간만으로 해제하지 않음';
