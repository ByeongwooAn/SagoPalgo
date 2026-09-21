-- 기존 사고팔고 데이터베이스에 뉴스·공시 저장소를 추가하는 증분 SQL입니다.
-- 이미 테이블이 있으면 변경하지 않으므로 반복 실행할 수 있습니다.

CREATE TABLE IF NOT EXISTS research_news (
  news_id BIGINT NOT NULL AUTO_INCREMENT COMMENT '뉴스 PK',
  provider VARCHAR(30) NOT NULL COMMENT '뉴스 Provider 코드',
  content_key CHAR(64) NOT NULL COMMENT 'Provider, 종목코드, 원문 URL 기반 SHA-256 중복 제거 키',
  stock_code VARCHAR(30) NOT NULL COMMENT '연결 종목 코드',
  stock_name VARCHAR(100) NOT NULL COMMENT '연결 종목명',
  title VARCHAR(500) NOT NULL COMMENT 'HTML 강조 태그를 제거한 기사 제목',
  link VARCHAR(1000) NOT NULL COMMENT '뉴스 원문 링크',
  summary TEXT NULL COMMENT '검색 API가 제공한 기사 요약',
  published_at DATETIME NULL COMMENT '뉴스 발행 시각',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '최초 수집 시각',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '마지막 수집 시각',
  PRIMARY KEY (news_id),
  UNIQUE KEY uk_research_news_provider_key (provider, content_key),
  KEY idx_research_news_stock_published (stock_code, published_at),
  KEY idx_research_news_updated (updated_at)
) ENGINE=InnoDB COMMENT='종목별 뉴스 수집 결과';

CREATE TABLE IF NOT EXISTS research_disclosures (
  disclosure_id BIGINT NOT NULL AUTO_INCREMENT COMMENT '공시 PK',
  provider VARCHAR(30) NOT NULL COMMENT '공시 Provider 코드',
  stock_code VARCHAR(30) NOT NULL COMMENT '연결 종목 코드',
  corp_code VARCHAR(20) NOT NULL COMMENT 'DART 회사 고유번호',
  corp_name VARCHAR(100) NOT NULL COMMENT '공시 회사명',
  report_name VARCHAR(500) NOT NULL COMMENT '공시 보고서명',
  receipt_number VARCHAR(30) NOT NULL COMMENT 'DART 접수번호',
  submitter_name VARCHAR(100) NULL COMMENT '공시 제출인명',
  receipt_date DATE NULL COMMENT '공시 접수일',
  link VARCHAR(1000) NOT NULL COMMENT 'DART 공시 원문 링크',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '최초 수집 시각',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '마지막 수집 시각',
  PRIMARY KEY (disclosure_id),
  UNIQUE KEY uk_research_disclosures_provider_receipt (provider, receipt_number),
  KEY idx_research_disclosures_stock_date (stock_code, receipt_date),
  KEY idx_research_disclosures_updated (updated_at)
) ENGINE=InnoDB COMMENT='종목별 전자공시 수집 결과';
