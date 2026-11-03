-- 연구 자료 변경 이력: 공급자 원문 전체나 인증값은 저장하지 않습니다.
CREATE TABLE IF NOT EXISTS research_journal_clock (
  singleton TINYINT NOT NULL PRIMARY KEY,
  last_id BIGINT NOT NULL,
  CHECK(singleton=1 AND last_id>=0)
) ENGINE=InnoDB;
INSERT IGNORE INTO research_journal_clock VALUES(1,0);
CREATE TABLE IF NOT EXISTS research_item_heads (
  kind VARCHAR(12) NOT NULL,
  provider VARCHAR(30) NOT NULL,
  stock_code VARCHAR(30) NOT NULL,
  item_key CHAR(64) NOT NULL,
  revision BIGINT NOT NULL,
  content_hash CHAR(64),
  PRIMARY KEY(kind,provider,stock_code,item_key),
  CHECK(kind IN ('NEWS','DISCLOSURE') AND revision>=0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS research_versions (
  change_id BIGINT NOT NULL PRIMARY KEY,
  kind VARCHAR(12) NOT NULL,
  provider VARCHAR(30) NOT NULL,
  stock_code VARCHAR(30) NOT NULL,
  item_key CHAR(64) NOT NULL,
  revision BIGINT NOT NULL,
  content_hash CHAR(64) NOT NULL,
  payload LONGTEXT NOT NULL,
  observed_at DATETIME(6) NOT NULL,
  origin VARCHAR(20) NOT NULL,
  UNIQUE KEY uk_research_revision(kind,provider,stock_code,item_key,revision),
  INDEX idx_research_change_stock(stock_code,change_id),
  CONSTRAINT chk_research_version_payload CHECK(JSON_VALID(payload)),
  CONSTRAINT chk_research_version_origin CHECK(origin IN ('LEGACY_BASELINE','OBSERVED')),
  CONSTRAINT fk_research_version_head FOREIGN KEY(kind,provider,stock_code,item_key)
    REFERENCES research_item_heads(kind,provider,stock_code,item_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS research_checkpoints (
  provider VARCHAR(30) NOT NULL,
  stock_code VARCHAR(30) NOT NULL,
  scope_key CHAR(64) NOT NULL,
  through_date DATE NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  PRIMARY KEY(provider,stock_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
