-- 019 이후 백업 후 적용. 기존 SENDING/가드/반환 결과를 자동 변경하지 않습니다.
CREATE TABLE IF NOT EXISTS manual_order_reservation_aborts (
  command_id CHAR(36) NOT NULL PRIMARY KEY,
  user_id BIGINT NOT NULL,
  execution_key CHAR(36) NOT NULL,
  account_fingerprint CHAR(64) NOT NULL,
  aborted_at DATETIME(6) NOT NULL,
  CONSTRAINT fk_manual_abort_dispatch FOREIGN KEY(command_id) REFERENCES manual_order_dispatches(command_id),
  CONSTRAINT fk_manual_abort_user FOREIGN KEY(user_id) REFERENCES users(user_id)
) ENGINE=InnoDB COMMENT='전송 시작과 경쟁해 먼저 확정된 로컬 예약 중단 감사';

-- 하나의 ALTER로 교체합니다. 반복 적용해도 기존 행과 가드는 변경하지 않습니다.
ALTER TABLE manual_order_dispatches
  DROP CHECK chk_manual_dispatch_phase,
  ADD CONSTRAINT chk_manual_dispatch_phase CHECK (phase IN ('RESERVED','DISPATCHING','RETURNED','ABORTED'));
