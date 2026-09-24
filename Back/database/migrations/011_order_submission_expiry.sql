-- 기존 READY 기록은 발급 당시 예약 기한이 없으므로 새 제출 권한으로 사용하지 않습니다.
ALTER TABLE order_submission_guards
  ADD COLUMN expires_at DATETIME(6) NULL AFTER status;

UPDATE order_submission_guards
SET status = 'LEGACY_REVIEW', updated_at = CURRENT_TIMESTAMP
WHERE status = 'READY';

ALTER TABLE order_submission_guards
  ADD CONSTRAINT chk_order_submission_guards_ready_expiry
    CHECK (status <> 'READY' OR expires_at IS NOT NULL);
