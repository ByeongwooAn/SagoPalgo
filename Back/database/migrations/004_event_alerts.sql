-- 기존 alerts 테이블에 가격·뉴스·공시 이벤트 식별 정보를 추가합니다.

ALTER TABLE alerts
  ADD COLUMN event_type VARCHAR(40) NULL COMMENT '발생 조건: RECOMMENDATION, PRICE_*, NEWS, DISCLOSURE' AFTER alert_type,
  ADD COLUMN event_key VARCHAR(191) NULL COMMENT '뉴스·공시처럼 한 번만 알릴 외부 이벤트 고유 키' AFTER event_type,
  ADD COLUMN stock_code VARCHAR(30) NULL COMMENT '이벤트 대상 종목 코드' AFTER event_key,
  ADD COLUMN market VARCHAR(20) NULL COMMENT '이벤트 대상 시장 코드' AFTER stock_code,
  ADD KEY idx_alerts_user_stock_event_created (user_id, stock_code, market, event_type, created_at),
  ADD UNIQUE KEY uk_alerts_user_event_key (user_id, event_type, event_key);
