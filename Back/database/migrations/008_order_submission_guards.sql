-- 승인 건마다 하나의 제출 예약만 허용합니다. 이 테이블 자체는 주문을 전송하지 않습니다.
CREATE TABLE IF NOT EXISTS order_submission_guards (
  order_approval_id BIGINT NOT NULL,
  user_id BIGINT NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'READY',
  reserved_at DATETIME NULL,
  uncertain_at DATETIME NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  PRIMARY KEY (order_approval_id),
  KEY idx_order_submission_guards_user_created (user_id, created_at),
  CONSTRAINT fk_order_submission_guards_approval FOREIGN KEY (order_approval_id)
    REFERENCES order_approvals (order_approval_id) ON DELETE CASCADE,
  CONSTRAINT fk_order_submission_guards_user FOREIGN KEY (user_id)
    REFERENCES users (user_id) ON DELETE CASCADE,
  CONSTRAINT chk_order_submission_guards_status
    CHECK (status IN ('READY', 'RESERVED', 'UNCERTAIN', 'LEGACY_REVIEW'))
) ENGINE=InnoDB COMMENT='승인별 단일 제출 예약 및 불명확 응답 차단 상태';

-- 기존 승인 기록은 새 전송 권한으로 승격하지 않고 수동 검토 상태로만 보존합니다.
INSERT INTO order_submission_guards (
  order_approval_id, user_id, status, created_at, updated_at
)
SELECT a.order_approval_id, a.user_id, 'LEGACY_REVIEW',
       COALESCE(a.acknowledged_at, a.created_at), COALESCE(a.acknowledged_at, a.created_at)
FROM order_approvals a
WHERE a.status = 'ACKNOWLEDGED'
  AND NOT EXISTS (
    SELECT 1 FROM order_submission_guards g WHERE g.order_approval_id = a.order_approval_id
  );
