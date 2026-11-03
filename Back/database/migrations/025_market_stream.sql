-- 공개 KIS KRX 시세만 기록합니다. 계좌/주문 원장을 변경하지 않습니다.
CREATE TABLE IF NOT EXISTS market_stream_events (
  event_id CHAR(64) NOT NULL PRIMARY KEY,
  stock_code CHAR(6) NOT NULL,
  event_type VARCHAR(10) NOT NULL,
  market_at DATETIME(6) NOT NULL,
  received_at DATETIME(6) NOT NULL,
  payload LONGTEXT NOT NULL,
  CONSTRAINT chk_market_stream_event_json CHECK (JSON_VALID(payload)),
  CONSTRAINT chk_market_stream_event_type CHECK (event_type IN ('TRADE','QUOTE')),
  INDEX idx_market_stream_stock_time(stock_code,market_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS market_stream_minutes (
  stock_code CHAR(6) NOT NULL,
  minute_at DATETIME(6) NOT NULL,
  payload LONGTEXT NOT NULL,
  PRIMARY KEY(stock_code,minute_at),
  CONSTRAINT chk_market_stream_minute_json CHECK (JSON_VALID(payload))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
