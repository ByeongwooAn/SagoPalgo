-- 기존 모의 기록은 시세·신호 증거와 KRW 요청 ID가 NULL인 상태로 보존합니다.
-- 통화별 ALTER 문은 각각 한 번에 적용되며, 한쪽만 적용된 경우 다시 실행할 수 있습니다.
SET @krw_paper_ddl = IF(
  EXISTS (SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'trade_records' AND COLUMN_NAME = 'quote_market_at'),
  'SELECT 1',
  'ALTER TABLE trade_records
    ADD COLUMN request_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NULL,
    ADD COLUMN quote_provider VARCHAR(32) NULL,
    ADD COLUMN quote_market_at DATETIME(6) NULL,
    ADD COLUMN quote_received_at DATETIME(6) NULL,
    ADD COLUMN signal_basis_date DATE NULL,
    ADD COLUMN signal_model_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
    ADD COLUMN signal_expires_at DATETIME(6) NULL,
    ADD UNIQUE KEY uk_paper_krw_request (user_id, request_id)'
);
PREPARE krw_paper_stmt FROM @krw_paper_ddl;
EXECUTE krw_paper_stmt;
DEALLOCATE PREPARE krw_paper_stmt;

SET @usd_paper_ddl = IF(
  EXISTS (SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'paper_us_trades' AND COLUMN_NAME = 'quote_market_at'),
  'SELECT 1',
  'ALTER TABLE paper_us_trades
    ADD COLUMN quote_provider VARCHAR(32) NULL,
    ADD COLUMN quote_market_at DATETIME(6) NULL,
    ADD COLUMN quote_received_at DATETIME(6) NULL,
    ADD COLUMN signal_basis_date DATE NULL,
    ADD COLUMN signal_model_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
    ADD COLUMN signal_expires_at DATETIME(6) NULL'
);
PREPARE usd_paper_stmt FROM @usd_paper_ddl;
EXECUTE usd_paper_stmt;
DEALLOCATE PREPARE usd_paper_stmt;
