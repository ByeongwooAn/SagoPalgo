-- 기존 승인은 계좌 설정과 묶여 있지 않으므로 새 예약 권한으로 승격하지 않습니다.
ALTER TABLE order_approvals
  ADD COLUMN account_fingerprint CHAR(64) NULL AFTER token_hash;

UPDATE order_submission_guards g
JOIN order_approvals a ON a.order_approval_id = g.order_approval_id
SET g.status = 'LEGACY_REVIEW', g.updated_at = CURRENT_TIMESTAMP
WHERE g.status = 'READY' AND a.account_fingerprint IS NULL;
