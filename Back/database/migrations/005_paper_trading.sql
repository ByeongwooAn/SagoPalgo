-- 기존 거래 기록 테이블을 AI 신호 기반 모의매매 원장으로 확장합니다.

ALTER TABLE trade_records
  ADD COLUMN recommendation_id BIGINT NULL COMMENT '가상 매수의 근거가 된 AI 추천' AFTER holding_id,
  ADD COLUMN execution_mode VARCHAR(20) NOT NULL DEFAULT 'PAPER' COMMENT '실행 구분: PAPER, LIVE' AFTER trade_type,
  ADD COLUMN realized_profit DECIMAL(18, 2) NOT NULL DEFAULT 0 COMMENT '매도 시 확정된 손익' AFTER quantity,
  ADD KEY idx_trade_records_recommendation_id (recommendation_id),
  ADD KEY idx_trade_records_user_mode_date (user_id, execution_mode, trade_date);
