-- 국내 원화 모의 거래 기록과 독립된 미국주식 달러 원장입니다.

CREATE TABLE IF NOT EXISTS paper_us_accounts (
  user_id BIGINT NOT NULL,
  initial_capital DECIMAL(18, 2) NOT NULL,
  PRIMARY KEY (user_id),
  CONSTRAINT fk_paper_us_accounts_user
    FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
  CONSTRAINT chk_paper_us_capital CHECK (initial_capital > 0)
) ENGINE=InnoDB COMMENT='미국주식 USD 가상 계좌';

CREATE TABLE IF NOT EXISTS paper_us_trades (
  trade_record_id BIGINT NOT NULL AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  request_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  stock_code VARCHAR(30) NOT NULL,
  stock_name VARCHAR(100) NOT NULL,
  market VARCHAR(20) NOT NULL,
  trade_type VARCHAR(20) NOT NULL,
  trade_price DECIMAL(18, 4) NOT NULL,
  quantity DECIMAL(18, 4) NOT NULL,
  realized_profit DECIMAL(18, 2) NOT NULL DEFAULT 0,
  trade_date DATETIME(6) NOT NULL,
  memo VARCHAR(500) NULL,
  PRIMARY KEY (trade_record_id),
  UNIQUE KEY uk_paper_us_request (user_id, request_id),
  KEY idx_paper_us_trades_user_record (user_id, trade_record_id),
  CONSTRAINT fk_paper_us_trades_account
    FOREIGN KEY (user_id) REFERENCES paper_us_accounts (user_id) ON DELETE CASCADE,
  CONSTRAINT chk_paper_us_trade CHECK (
    market IN ('NASDAQ', 'NYSE', 'AMEX') AND trade_type IN ('BUY', 'SELL')
    AND trade_price > 0 AND quantity > 0
  )
) ENGINE=InnoDB COMMENT='미국주식 USD 가상 체결 원장';
