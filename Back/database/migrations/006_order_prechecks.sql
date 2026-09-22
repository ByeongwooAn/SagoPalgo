-- 실제 주문 전 안전 검증 결과를 보존하는 감사 로그 테이블입니다.
-- 이 마이그레이션은 주문 실행 API를 추가하지 않습니다.

CREATE TABLE IF NOT EXISTS order_prechecks (
  order_precheck_id BIGINT NOT NULL AUTO_INCREMENT COMMENT '주문 사전검증 PK',
  user_id BIGINT NOT NULL COMMENT '로컬 사용자 FK',
  stock_code VARCHAR(30) NOT NULL COMMENT '종목 코드',
  stock_name VARCHAR(100) NOT NULL COMMENT '종목명',
  market VARCHAR(20) NOT NULL COMMENT '시장 코드',
  order_side VARCHAR(10) NOT NULL COMMENT '주문 방향: BUY, SELL',
  order_type VARCHAR(10) NOT NULL DEFAULT 'LIMIT' COMMENT '주문 유형: 현재 LIMIT만 지원',
  requested_price DECIMAL(18, 2) NOT NULL COMMENT '사용자가 검토한 지정가',
  quantity DECIMAL(18, 4) NOT NULL COMMENT '사용자가 검토한 수량',
  estimated_amount DECIMAL(18, 2) NOT NULL COMMENT '지정가와 수량을 곱한 예상 주문금액',
  quote_provider VARCHAR(30) NOT NULL COMMENT '비교 현재가 Provider',
  current_price DECIMAL(18, 2) NOT NULL COMMENT '검증 시점 현재가',
  order_available_cash DECIMAL(18, 2) NOT NULL DEFAULT 0 COMMENT '검증 시점 KB 주문가능현금',
  orderable_quantity DECIMAL(18, 4) NOT NULL DEFAULT 0 COMMENT '검증 시점 KB 주문가능수량',
  order_enabled BOOLEAN NOT NULL DEFAULT FALSE COMMENT '검증 시점 주문 스위치',
  eligible BOOLEAN NOT NULL DEFAULT FALSE COMMENT '모든 사전검증 통과 여부',
  blocker_summary VARCHAR(1000) NULL COMMENT '실패한 안전 검사 요약',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '검증 시각',
  PRIMARY KEY (order_precheck_id),
  KEY idx_order_prechecks_user_created (user_id, created_at),
  KEY idx_order_prechecks_user_stock_created (user_id, stock_code, created_at),
  CONSTRAINT fk_order_prechecks_user
    FOREIGN KEY (user_id) REFERENCES users (user_id)
    ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='실제 주문 전 안전 검증 감사 로그';
