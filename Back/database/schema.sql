-- 사고팔고 MySQL 스키마 1차 초안입니다.
-- 이 파일은 Spring Boot + MyBatis 백엔드 구현 전에 DB 구조를 고정하기 위한 기준 파일입니다.
-- 실제 운영 반영 전에는 마이그레이션 도구(Flyway 또는 Liquibase)로 옮겨 관리하는 것을 권장합니다.

CREATE DATABASE IF NOT EXISTS sagopalgo
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_0900_ai_ci;

USE sagopalgo;

-- 개인용 로컬 사용자 테이블입니다.
-- 로그인 계정이 아니라 보유/관심/자본금 데이터를 하나의 로컬 소유자로 묶는 루트 테이블입니다.
CREATE TABLE IF NOT EXISTS users (
  user_id BIGINT NOT NULL AUTO_INCREMENT COMMENT '사용자 PK',
  auth_provider VARCHAR(20) NOT NULL COMMENT '프로필 출처: LOCAL',
  provider_user_id VARCHAR(100) NOT NULL COMMENT '로컬 소유자 식별값',
  email VARCHAR(255) NULL COMMENT '로컬 사용자 식별용 이메일',
  nickname VARCHAR(50) NOT NULL COMMENT '프로그램에 표시할 로컬 사용자 이름',
  profile_image_url VARCHAR(500) NULL COMMENT '현재 개인용 모드에서는 사용하지 않음',
  role VARCHAR(20) NOT NULL DEFAULT 'USER' COMMENT '로컬 권한: USER',
  status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE' COMMENT '로컬 프로필 상태: ACTIVE',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생성 시각',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정 시각',
  PRIMARY KEY (user_id),
  UNIQUE KEY uk_users_provider_user (auth_provider, provider_user_id),
  KEY idx_users_email (email)
) ENGINE=InnoDB COMMENT='개인용 로컬 사용자';

INSERT IGNORE INTO users (user_id, auth_provider, provider_user_id, email, nickname, profile_image_url, role, status)
VALUES (1, 'LOCAL', 'personal-owner', 'local@sagopalgo.local', '개인 사용자', NULL, 'USER', 'ACTIVE');

-- 사용자 자본금과 리스크 설정 테이블입니다.
-- 기획서의 핵심 원칙인 종목당 투자 비율과 1회 거래 손실 제한을 계산하는 기준이 됩니다.
CREATE TABLE IF NOT EXISTS user_capital (
  capital_id BIGINT NOT NULL AUTO_INCREMENT COMMENT '자본금 설정 PK',
  user_id BIGINT NOT NULL COMMENT '설정 소유 사용자',
  available_capital DECIMAL(18, 2) NOT NULL DEFAULT 0 COMMENT '투자 가능 자본금',
  risk_per_trade_rate DECIMAL(5, 4) NOT NULL DEFAULT 0.0200 COMMENT '1회 거래 손실 허용 비율, 기본 2%',
  recommended_min_position DECIMAL(18, 2) NOT NULL DEFAULT 0 COMMENT '종목당 최소 권장 투자금',
  recommended_max_position DECIMAL(18, 2) NOT NULL DEFAULT 0 COMMENT '종목당 최대 권장 투자금',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생성 시각',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정 시각',
  PRIMARY KEY (capital_id),
  UNIQUE KEY uk_user_capital_user_id (user_id),
  CONSTRAINT fk_user_capital_user
    FOREIGN KEY (user_id) REFERENCES users (user_id)
    ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='사용자 자본금 및 리스크 설정';

-- 관심 종목 테이블입니다.
-- 사용자가 분석과 알림을 받고 싶은 종목을 저장합니다.
CREATE TABLE IF NOT EXISTS watchlist (
  watchlist_id BIGINT NOT NULL AUTO_INCREMENT COMMENT '관심 종목 PK',
  user_id BIGINT NOT NULL COMMENT '관심 종목 소유 사용자',
  stock_code VARCHAR(30) NOT NULL COMMENT '종목 코드',
  stock_name VARCHAR(100) NOT NULL COMMENT '종목명',
  market VARCHAR(20) NOT NULL COMMENT '시장: KOSPI, KOSDAQ, NASDAQ, NYSE 등',
  alert_enabled BOOLEAN NOT NULL DEFAULT TRUE COMMENT '추천 알림 수신 여부',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생성 시각',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정 시각',
  PRIMARY KEY (watchlist_id),
  UNIQUE KEY uk_watchlist_user_stock_market (user_id, stock_code, market),
  KEY idx_watchlist_user_id (user_id),
  CONSTRAINT fk_watchlist_user
    FOREIGN KEY (user_id) REFERENCES users (user_id)
    ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='관심 종목';

-- 보유 종목 테이블입니다.
-- 매수 이후 손익 계산과 매도 추천의 기준 데이터로 사용됩니다.
CREATE TABLE IF NOT EXISTS holdings (
  holding_id BIGINT NOT NULL AUTO_INCREMENT COMMENT '보유 종목 PK',
  user_id BIGINT NOT NULL COMMENT '보유 종목 소유 사용자',
  stock_code VARCHAR(30) NOT NULL COMMENT '종목 코드',
  stock_name VARCHAR(100) NOT NULL COMMENT '종목명',
  market VARCHAR(20) NOT NULL COMMENT '시장: KOSPI, KOSDAQ, NASDAQ, NYSE 등',
  buy_price DECIMAL(18, 2) NOT NULL COMMENT '평균 매수가',
  quantity DECIMAL(18, 4) NOT NULL COMMENT '보유 수량',
  buy_date DATE NOT NULL COMMENT '매수일',
  stop_loss_rate DECIMAL(6, 3) NOT NULL COMMENT '손절 기준 수익률',
  take_profit_rate DECIMAL(6, 3) NOT NULL COMMENT '익절 기준 수익률',
  status VARCHAR(30) NOT NULL DEFAULT 'HOLDING' COMMENT '상태: HOLDING, PARTIAL_TAKE_PROFIT, STOP_LOSS_WATCH, SOLD',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생성 시각',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정 시각',
  PRIMARY KEY (holding_id),
  KEY idx_holdings_user_status (user_id, status),
  KEY idx_holdings_user_stock (user_id, stock_code, market),
  CONSTRAINT fk_holdings_user
    FOREIGN KEY (user_id) REFERENCES users (user_id)
    ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='보유 종목';

-- 매수/매도 거래 기록 테이블입니다.
-- 보유 종목의 변경 이력을 남겨 수익률 추적과 감사 로그에 활용합니다.
CREATE TABLE IF NOT EXISTS trade_records (
  trade_record_id BIGINT NOT NULL AUTO_INCREMENT COMMENT '거래 기록 PK',
  user_id BIGINT NOT NULL COMMENT '거래 사용자',
  holding_id BIGINT NULL COMMENT '연결된 보유 종목, 매도 완료 후에도 기록 보존을 위해 NULL 허용',
  stock_code VARCHAR(30) NOT NULL COMMENT '종목 코드',
  stock_name VARCHAR(100) NOT NULL COMMENT '종목명',
  market VARCHAR(20) NOT NULL COMMENT '시장',
  trade_type VARCHAR(20) NOT NULL COMMENT '거래 유형: BUY, SELL',
  trade_price DECIMAL(18, 2) NOT NULL COMMENT '거래 가격',
  quantity DECIMAL(18, 4) NOT NULL COMMENT '거래 수량',
  trade_date DATETIME NOT NULL COMMENT '거래 시각',
  memo VARCHAR(500) NULL COMMENT '사용자 메모 또는 시스템 설명',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생성 시각',
  PRIMARY KEY (trade_record_id),
  KEY idx_trade_records_user_date (user_id, trade_date),
  KEY idx_trade_records_holding_id (holding_id),
  CONSTRAINT fk_trade_records_user
    FOREIGN KEY (user_id) REFERENCES users (user_id)
    ON DELETE CASCADE,
  CONSTRAINT fk_trade_records_holding
    FOREIGN KEY (holding_id) REFERENCES holdings (holding_id)
    ON DELETE SET NULL
) ENGINE=InnoDB COMMENT='투자 거래 기록';

-- AI 추천 결과 테이블입니다.
-- 매수/매도/관망 판단의 대표 결과와 점수를 저장합니다.
CREATE TABLE IF NOT EXISTS recommendations (
  recommendation_id BIGINT NOT NULL AUTO_INCREMENT COMMENT '추천 PK',
  user_id BIGINT NOT NULL COMMENT '추천 대상 사용자',
  stock_code VARCHAR(30) NOT NULL COMMENT '종목 코드',
  stock_name VARCHAR(100) NOT NULL COMMENT '종목명',
  market VARCHAR(20) NOT NULL COMMENT '시장',
  recommendation_type VARCHAR(20) NOT NULL COMMENT '추천 유형: BUY, SELL, HOLD',
  status VARCHAR(30) NOT NULL COMMENT '추천 상태: BUY_STRONG, WATCH, NEUTRAL, RISK 등',
  score INT NOT NULL COMMENT '0~100 추천 점수',
  entry_price DECIMAL(18, 2) NULL COMMENT '권장 진입 가격',
  stop_loss_rate DECIMAL(6, 3) NULL COMMENT '손절 기준 수익률',
  take_profit_rate DECIMAL(6, 3) NULL COMMENT '익절 기준 수익률',
  ai_summary TEXT NULL COMMENT '사용자에게 보여줄 AI 설명',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생성 시각',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정 시각',
  PRIMARY KEY (recommendation_id),
  KEY idx_recommendations_user_created (user_id, created_at),
  KEY idx_recommendations_stock_created (stock_code, market, created_at),
  CONSTRAINT fk_recommendations_user
    FOREIGN KEY (user_id) REFERENCES users (user_id)
    ON DELETE CASCADE,
  CONSTRAINT chk_recommendations_score
    CHECK (score BETWEEN 0 AND 100)
) ENGINE=InnoDB COMMENT='AI 매수/매도 추천';

-- 추천 점수 산출 근거 테이블입니다.
-- RSI, MACD, 거래량, 뉴스 등 조건별 점수를 따로 저장해 추천의 설명 가능성을 확보합니다.
CREATE TABLE IF NOT EXISTS recommendation_reasons (
  reason_id BIGINT NOT NULL AUTO_INCREMENT COMMENT '추천 사유 PK',
  recommendation_id BIGINT NOT NULL COMMENT '연결된 추천',
  reason_type VARCHAR(30) NOT NULL COMMENT '사유 유형: RSI, MACD, VOLUME, NEWS, FOREIGN_BUY, MARKET',
  label VARCHAR(50) NOT NULL COMMENT '앱에 표시할 짧은 라벨',
  description VARCHAR(500) NOT NULL COMMENT '사용자에게 보여줄 추천 사유 설명',
  score INT NOT NULL DEFAULT 0 COMMENT '해당 사유가 더한 점수',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생성 시각',
  PRIMARY KEY (reason_id),
  KEY idx_recommendation_reasons_recommendation (recommendation_id),
  CONSTRAINT fk_recommendation_reasons_recommendation
    FOREIGN KEY (recommendation_id) REFERENCES recommendations (recommendation_id)
    ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='AI 추천 점수 산출 근거';

-- 알림 대상 장치 토큰 테이블입니다.
-- Windows 로컬 알림 구현 전까지는 향후 외부 푸시/장치 연동 확장 지점으로 둡니다.
CREATE TABLE IF NOT EXISTS device_tokens (
  device_token_id BIGINT NOT NULL AUTO_INCREMENT COMMENT '기기 토큰 PK',
  user_id BIGINT NOT NULL COMMENT '토큰 소유 사용자',
  fcm_token VARCHAR(500) NOT NULL COMMENT '외부 푸시 또는 장치 알림 토큰',
  device_type VARCHAR(20) NOT NULL DEFAULT 'WINDOWS' COMMENT '기기 유형: WINDOWS, ANDROID, IOS',
  is_active BOOLEAN NOT NULL DEFAULT TRUE COMMENT '현재 알림 발송에 사용할 수 있는 토큰인지 여부',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생성 시각',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정 시각',
  PRIMARY KEY (device_token_id),
  UNIQUE KEY uk_device_tokens_fcm_token (fcm_token),
  KEY idx_device_tokens_user_active (user_id, is_active),
  CONSTRAINT fk_device_tokens_user
    FOREIGN KEY (user_id) REFERENCES users (user_id)
    ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='사용자 장치 알림 토큰';

-- 앱 알림 히스토리 테이블입니다.
-- 로컬 프로그램 표시 여부와 읽음 상태를 함께 관리합니다.
CREATE TABLE IF NOT EXISTS alerts (
  alert_id BIGINT NOT NULL AUTO_INCREMENT COMMENT '알림 PK',
  user_id BIGINT NOT NULL COMMENT '알림 수신 사용자',
  recommendation_id BIGINT NULL COMMENT '연결된 추천, 시장 공지처럼 추천과 무관한 알림은 NULL',
  alert_type VARCHAR(30) NOT NULL COMMENT '알림 유형: BUY, SELL, MARKET, RISK',
  title VARCHAR(100) NOT NULL COMMENT '알림 제목',
  body VARCHAR(500) NOT NULL COMMENT '알림 본문',
  is_read BOOLEAN NOT NULL DEFAULT FALSE COMMENT '앱 내 읽음 여부',
  sent_at DATETIME NULL COMMENT '외부 푸시 또는 로컬 알림 발송 시각',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생성 시각',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정 시각',
  PRIMARY KEY (alert_id),
  KEY idx_alerts_user_read_created (user_id, is_read, created_at),
  KEY idx_alerts_recommendation_id (recommendation_id),
  CONSTRAINT fk_alerts_user
    FOREIGN KEY (user_id) REFERENCES users (user_id)
    ON DELETE CASCADE,
  CONSTRAINT fk_alerts_recommendation
    FOREIGN KEY (recommendation_id) REFERENCES recommendations (recommendation_id)
    ON DELETE SET NULL
) ENGINE=InnoDB COMMENT='앱 알림 히스토리';

-- AI 분석 스냅샷 테이블입니다.
-- Python AI 서버가 반환한 기술지표/뉴스/시장 분석 원본을 보관해 백테스트와 디버깅에 활용합니다.
CREATE TABLE IF NOT EXISTS analysis_snapshots (
  snapshot_id BIGINT NOT NULL AUTO_INCREMENT COMMENT '분석 스냅샷 PK',
  user_id BIGINT NOT NULL COMMENT '분석 대상 사용자',
  recommendation_id BIGINT NULL COMMENT '이 분석으로 생성된 추천',
  stock_code VARCHAR(30) NOT NULL COMMENT '종목 코드',
  market VARCHAR(20) NOT NULL COMMENT '시장',
  analysis_type VARCHAR(30) NOT NULL COMMENT '분석 유형: TECHNICAL, NEWS, MARKET, TOTAL',
  score INT NULL COMMENT '분석 점수',
  raw_payload JSON NOT NULL COMMENT 'AI 서버 응답 원본 JSON',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생성 시각',
  PRIMARY KEY (snapshot_id),
  KEY idx_snapshots_user_created (user_id, created_at),
  KEY idx_snapshots_stock_created (stock_code, market, created_at),
  KEY idx_snapshots_recommendation_id (recommendation_id),
  CONSTRAINT fk_analysis_snapshots_user
    FOREIGN KEY (user_id) REFERENCES users (user_id)
    ON DELETE CASCADE,
  CONSTRAINT fk_analysis_snapshots_recommendation
    FOREIGN KEY (recommendation_id) REFERENCES recommendations (recommendation_id)
    ON DELETE SET NULL,
  CONSTRAINT chk_analysis_snapshots_score
    CHECK (score IS NULL OR score BETWEEN 0 AND 100)
) ENGINE=InnoDB COMMENT='AI 분석 결과 스냅샷';
