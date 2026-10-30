-- KB에서 가져온 보유 스냅샷을 수동 등록분과 구분합니다.
-- 계좌 원문 대신 서버에서 생성한 연결 지문을 저장합니다.
ALTER TABLE holdings
  MODIFY COLUMN buy_date DATE NULL COMMENT '매수일: KB 조회 미제공 시 NULL',
  ADD COLUMN source VARCHAR(20) NOT NULL DEFAULT 'MANUAL' AFTER status,
  ADD COLUMN source_account_key CHAR(64) NULL AFTER source,
  ADD COLUMN source_synced_at DATETIME NULL AFTER source_account_key,
  ADD UNIQUE KEY uq_holdings_import (user_id, source_account_key, stock_code);
