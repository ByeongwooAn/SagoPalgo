-- 기존 사고팔고 데이터베이스에 관심 종목 뉴스·공시 동기화 상태를 추가합니다.
-- 이미 테이블이 있으면 변경하지 않으므로 반복 실행할 수 있습니다.

CREATE TABLE IF NOT EXISTS research_sync_status (
  sync_status_id BIGINT NOT NULL AUTO_INCREMENT COMMENT '동기화 상태 PK',
  user_id BIGINT NOT NULL COMMENT '관심 종목 소유자',
  stock_code VARCHAR(30) NOT NULL COMMENT '종목 코드',
  stock_name VARCHAR(100) NOT NULL COMMENT '종목명',
  trigger_type VARCHAR(20) NOT NULL COMMENT '동기화 실행 방식: MANUAL, SCHEDULED',
  status VARCHAR(20) NOT NULL COMMENT '최종 상태: SUCCESS, PARTIAL, FAILED, SKIPPED',
  news_count INT NOT NULL DEFAULT 0 COMMENT '동기화 후 저장 뉴스 건수',
  disclosure_count INT NOT NULL DEFAULT 0 COMMENT '동기화 후 저장 공시 건수',
  provider_success_count INT NOT NULL DEFAULT 0 COMMENT '성공 Provider 수',
  provider_failure_count INT NOT NULL DEFAULT 0 COMMENT '실패 Provider 수',
  provider_disabled_count INT NOT NULL DEFAULT 0 COMMENT '비활성 Provider 수',
  message VARCHAR(500) NOT NULL COMMENT '마지막 동기화 결과 요약',
  last_attempted_at DATETIME NOT NULL COMMENT '마지막 동기화 시도 시각',
  last_succeeded_at DATETIME NULL COMMENT '마지막 성공 또는 부분 성공 시각',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '최초 상태 생성 시각',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '상태 수정 시각',
  PRIMARY KEY (sync_status_id),
  UNIQUE KEY uk_research_sync_status_user_stock (user_id, stock_code),
  KEY idx_research_sync_status_attempted (last_attempted_at),
  CONSTRAINT fk_research_sync_status_user
    FOREIGN KEY (user_id) REFERENCES users (user_id)
    ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='관심 종목 뉴스·공시 동기화 상태';
