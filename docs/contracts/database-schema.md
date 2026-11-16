# 사고팔고 DB 설계서

이 문서는 사고팔고 개인용 Windows 투자 어시스턴트의 MySQL 기준 DB 설계입니다. 현재 구조는 공개 회원 서비스가 아니라 내 PC에서 한 명의 로컬 사용자가 쓰는 프로그램을 기준으로 합니다.

## 1. 설계 원칙

- 모든 개인 투자 데이터는 `user_id=1` 로컬 소유자를 기준으로 묶는다.
- 로그인, JWT, OAuth refresh token 저장소는 사용하지 않는다.
- 추천 결과는 단일 점수만 저장하지 않고, 점수를 만든 세부 근거를 함께 저장한다.
- 보유 종목은 매수가, 수량, 손절 기준, 익절 기준을 저장해 매도 추천의 입력값으로 사용한다.
- 알림은 Windows 로컬 알림을 우선 고려하고, 외부 푸시는 확장 지점으로만 남긴다.
- AI 분석 결과는 나중에 백테스트와 설명 검증에 사용할 수 있도록 스냅샷으로 남긴다.
- 실제 주문 연동은 후순위 기능이므로 주문 테이블은 아직 만들지 않는다.

## 2. 테이블 목록

| 테이블 | 목적 | 현재 단계 |
| --- | --- | --- |
| `users` | 로컬 데이터 소유자 프로필 | 필수 |
| `user_capital` | 투자 가능 자본금과 리스크 설정 | 구현됨 |
| `watchlist` | 관심 종목 관리 | 구현됨 |
| `holdings` | 보유 종목과 손절/익절 기준 | 구현됨 |
| `trade_records` | 실제 주문과 분리된 모의매매 원장 | 구현됨 |
| `order_prechecks` | 실제 주문 전 안전 검증 감사 로그 | 구현됨 |
| `recommendations` | AI 추천 결과 본문 | 구현됨 |
| `recommendation_reasons` | 추천 점수 산출 근거 | 구현됨 |
| `alerts` | 앱 알림 내역과 Windows 전달/읽음 상태 | 구현 완료 |
| `device_tokens` | 장치 알림 토큰 확장 지점 | 설계 포함 |
| `analysis_snapshots` | AI 분석 결과 원본 스냅샷 | 구현됨 |
| `research_news` | 종목별 뉴스 수집 결과 | 구현됨 |
| `research_disclosures` | 종목별 전자공시 수집 결과 | 구현됨 |
| `research_sync_status` | 관심 종목별 마지막 뉴스·공시 동기화 상태 | 구현됨 |

## 3. 관계 요약

```text
users 1 ── 1 user_capital
users 1 ── N watchlist
users 1 ── N holdings
users 1 ── N trade_records
users 1 ── N order_prechecks
users 1 ── N recommendations
recommendations 1 ── N recommendation_reasons
users 1 ── N alerts
users 1 ── N device_tokens
recommendations 1 ── N alerts
recommendations 1 ── N analysis_snapshots
research_news     N ── 1 stock_code (논리 관계)
research_disclosures N ── 1 stock_code (논리 관계)
users 1 ── N research_sync_status
```

뉴스와 공시는 여러 관심 종목과 분석 흐름에서 함께 쓰는 참조 데이터이므로 특정 `user_id`에 종속하지 않습니다. 현재는 종목코드로 연결하며 별도 종목 마스터 FK는 두지 않습니다.

## 4. 핵심 테이블 상세

### 4.1 `users`

로그인 계정이 아니라 개인용 데이터의 로컬 소유자를 나타내는 테이블입니다. 기존 FK 구조를 단순하게 유지하기 위해 남겨두며, 기본값은 `user_id=1`, `auth_provider=LOCAL`, `provider_user_id=personal-owner`입니다.

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| `user_id` | BIGINT | 로컬 사용자 PK |
| `auth_provider` | VARCHAR(20) | `LOCAL` |
| `provider_user_id` | VARCHAR(100) | 로컬 소유자 식별값 |
| `email` | VARCHAR(255) | 로컬 식별용 이메일 |
| `nickname` | VARCHAR(50) | 프로그램 표시 이름 |
| `profile_image_url` | VARCHAR(500) | 현재 개인용 모드에서는 미사용 |
| `role` | VARCHAR(20) | `USER` |
| `status` | VARCHAR(20) | `ACTIVE` |
| `created_at` | DATETIME | 생성일 |
| `updated_at` | DATETIME | 수정일 |

### 4.2 `user_capital`

사용자의 투자 가능 자본금과 리스크 기준을 저장합니다.

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| `capital_id` | BIGINT | PK |
| `user_id` | BIGINT | 로컬 사용자 FK |
| `available_capital` | DECIMAL(18,2) | 투자 가능 자본금 |
| `risk_per_trade_rate` | DECIMAL(5,4) | 1회 거래 손실 허용 비율 |
| `recommended_min_position` | DECIMAL(18,2) | 종목당 최소 권장 투자금 |
| `recommended_max_position` | DECIMAL(18,2) | 종목당 최대 권장 투자금 |

### 4.3 `watchlist`

분석과 알림을 받고 싶은 종목을 저장합니다.

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| `watchlist_id` | BIGINT | PK |
| `user_id` | BIGINT | 로컬 사용자 FK |
| `stock_code` | VARCHAR(30) | 종목 코드 |
| `stock_name` | VARCHAR(100) | 종목명 |
| `market` | VARCHAR(20) | `KOSPI`, `KOSDAQ`, `NASDAQ`, `NYSE` |
| `alert_enabled` | BOOLEAN | 추천 알림 수신 여부 |

### 4.4 `holdings`

보유 종목과 매도 추천 계산에 필요한 기준값을 저장합니다.

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| `holding_id` | BIGINT | PK |
| `user_id` | BIGINT | 로컬 사용자 FK |
| `stock_code` | VARCHAR(30) | 종목 코드 |
| `stock_name` | VARCHAR(100) | 종목명 |
| `market` | VARCHAR(20) | 시장 |
| `buy_price` | DECIMAL(18,2) | 평균 매수가 |
| `quantity` | DECIMAL(18,4) | 수량 |
| `buy_date` | DATE NULL | 실제 매수일. KB 응답 미제공 시 NULL |
| `stop_loss_rate` | DECIMAL(6,3) | 손절 기준 |
| `take_profit_rate` | DECIMAL(6,3) | 익절 기준 |
| `status` | VARCHAR(30) | `HOLDING`, `PARTIAL_TAKE_PROFIT`, `STOP_LOSS_WATCH`, `SOLD` |
| `source` | VARCHAR(20) | `MANUAL` 또는 `KB` |
| `source_account_key` | CHAR(64) NULL | KB 연결 지문. API Key·계좌번호 원문은 저장하지 않음 |
| `source_synced_at` | DATETIME NULL | KB 스냅샷 마지막 반영 시각 UTC |

`uq_holdings_import(user_id, source_account_key, stock_code)`로 같은 KB 연결의 종목 중복을 막습니다. 수동 등록분은 지문이 NULL이므로 기존 복수 매수 기록을 유지합니다. 기존 DB에는 `015_kb_portfolio_import.sql`을 한 번 적용합니다.

### 4.5 `recommendations`

AI가 생성한 매수/매도/관망 판단의 대표 결과를 저장합니다.

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| `recommendation_id` | BIGINT | PK |
| `user_id` | BIGINT | 로컬 사용자 FK |
| `stock_code` | VARCHAR(30) | 종목 코드 |
| `stock_name` | VARCHAR(100) | 종목명 |
| `market` | VARCHAR(20) | 시장 |
| `recommendation_type` | VARCHAR(20) | `BUY`, `SELL`, `HOLD` |
| `status` | VARCHAR(30) | `BUY_STRONG`, `BUY_WATCH`, `HOLD`, `TAKE_PROFIT`, `STOP_LOSS_WATCH`, `RISK` |
| `score` | INT | 0~100 추천 점수 |
| `entry_price` | DECIMAL(18,2) | 권장 진입가 |
| `stop_loss_rate` | DECIMAL(6,3) | 손절 기준 |
| `take_profit_rate` | DECIMAL(6,3) | 익절 기준 |
| `ai_summary` | TEXT | AI 설명 |

### 4.6 `recommendation_reasons`

추천 점수를 구성한 세부 사유를 저장합니다.

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| `reason_id` | BIGINT | PK |
| `recommendation_id` | BIGINT | 추천 FK |
| `reason_type` | VARCHAR(30) | `RISK`, `PRICE`, `NEWS`, `DISCLOSURE` |
| `label` | VARCHAR(50) | 화면 표시 라벨 |
| `description` | VARCHAR(500) | 사용자에게 보여줄 설명 |
| `score` | INT | 해당 조건이 더한 점수 |

### 4.7 `alerts`

Windows 프로그램 안에서 보여줄 알림 히스토리를 관리합니다.

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| `alert_id` | BIGINT | PK |
| `user_id` | BIGINT | 로컬 사용자 FK |
| `recommendation_id` | BIGINT | 연결된 추천 FK, 없을 수 있음 |
| `alert_type` | VARCHAR(30) | `BUY`, `SELL`, `MARKET`, `RISK`, `PRICE`, `NEWS`, `DISCLOSURE`, `PORTFOLIO` |
| `event_type` | VARCHAR(40) | `RECOMMENDATION`, `PRICE_*`, `NEWS`, `DISCLOSURE`, `PORTFOLIO_POSITION_OVERWEIGHT`, `PORTFOLIO_TOTAL_LOSS` |
| `event_key` | VARCHAR(191) | 뉴스·공시의 정확한 중복 방지 키, 가격·포트폴리오 이벤트는 `NULL` |
| `stock_code` | VARCHAR(30) | 이벤트 대상 종목 코드 |
| `market` | VARCHAR(20) | 이벤트 대상 시장 코드 |
| `title` | VARCHAR(100) | 알림 제목 |
| `body` | VARCHAR(500) | 알림 본문 |
| `is_read` | BOOLEAN | 앱 내 읽음 여부 |
| `sent_at` | DATETIME | 로컬 알림 또는 외부 푸시 발송 시각 |

### 4.8 `analysis_snapshots`

AI 서버가 계산한 분석 결과 원본을 JSON으로 보관합니다.

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| `snapshot_id` | BIGINT | PK |
| `user_id` | BIGINT | 로컬 사용자 FK |
| `recommendation_id` | BIGINT | 추천 FK |
| `stock_code` | VARCHAR(30) | 종목 코드 |
| `analysis_type` | VARCHAR(30) | `TECHNICAL`, `NEWS`, `MARKET`, `TOTAL` |
| `score` | INT | 분석 점수 |
| `raw_payload` | JSON | AI 서버 응답 원본 |

### 4.9 `research_news`

네이버 뉴스 등 외부 Provider에서 수집한 종목별 뉴스의 정규화 결과를 저장합니다.

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| `news_id` | BIGINT | PK |
| `provider` | VARCHAR(30) | `NAVER_NEWS` 등 Provider 코드 |
| `content_key` | CHAR(64) | Provider, 종목코드, 원문 URL 기반 SHA-256 키 |
| `stock_code` | VARCHAR(30) | 연결 종목 코드 |
| `stock_name` | VARCHAR(100) | 연결 종목명 |
| `title` | VARCHAR(500) | HTML 강조 태그를 제거한 기사 제목 |
| `link` | VARCHAR(1000) | 뉴스 원문 링크 |
| `summary` | TEXT | Provider가 제공한 기사 요약 |
| `published_at` | DATETIME | 뉴스 발행 시각, 없을 수 있음 |
| `created_at` | DATETIME | 최초 수집 시각 |
| `updated_at` | DATETIME | 마지막 수집 시각 |

### 4.10 `research_disclosures`

OpenDART에서 수집한 공시를 접수번호 기준으로 저장합니다.

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| `disclosure_id` | BIGINT | PK |
| `provider` | VARCHAR(30) | `OPEN_DART` 등 Provider 코드 |
| `stock_code` | VARCHAR(30) | 연결 종목 코드 |
| `corp_code` | VARCHAR(20) | DART 회사 고유번호 |
| `corp_name` | VARCHAR(100) | 공시 회사명 |
| `report_name` | VARCHAR(500) | 공시 보고서명 |
| `receipt_number` | VARCHAR(30) | DART 접수번호 |
| `submitter_name` | VARCHAR(100) | 공시 제출인명 |
| `receipt_date` | DATE | 공시 접수일 |
| `link` | VARCHAR(1000) | DART 공시 원문 링크 |
| `created_at` | DATETIME | 최초 수집 시각 |
| `updated_at` | DATETIME | 마지막 수집 시각 |

### 4.11 `research_sync_status`

수동 동기화와 관심 종목 스케줄 동기화의 마지막 결과를 종목별로 저장합니다.

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| `sync_status_id` | BIGINT | PK |
| `user_id` | BIGINT | 로컬 사용자 FK |
| `stock_code` | VARCHAR(30) | 동기화 대상 종목 코드 |
| `stock_name` | VARCHAR(100) | 동기화 대상 종목명 |
| `trigger_type` | VARCHAR(20) | `MANUAL`, `SCHEDULED` |
| `status` | VARCHAR(20) | `SUCCESS`, `PARTIAL`, `FAILED`, `SKIPPED` |
| `news_count` | INT | 동기화 후 저장 뉴스 건수 |
| `disclosure_count` | INT | 동기화 후 저장 공시 건수 |
| `provider_success_count` | INT | 성공 Provider 수 |
| `provider_failure_count` | INT | 실패 Provider 수 |
| `provider_disabled_count` | INT | 비활성 Provider 수 |
| `message` | VARCHAR(500) | 마지막 결과 요약 |
| `last_attempted_at` | DATETIME | 마지막 시도 시각 |
| `last_succeeded_at` | DATETIME | 마지막 성공 또는 부분 성공 시각 |

### 4.12 `trade_records`

AI 매수 신호와 사용자의 모의매도 결과를 실제 증권사 주문과 분리해 저장합니다. 현재 API는 `execution_mode=PAPER` 행만 생성하고 조회합니다.

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| `trade_record_id` | BIGINT | 모의 거래 PK |
| `user_id` | BIGINT | 로컬 사용자 FK |
| `holding_id` | BIGINT | 실제 보유 종목 연결 확장 지점, 없을 수 있음 |
| `recommendation_id` | BIGINT | 모의매수 근거가 된 AI 추천 ID, 없을 수 있음 |
| `stock_code` | VARCHAR(30) | 종목 코드 |
| `stock_name` | VARCHAR(100) | 종목명 |
| `market` | VARCHAR(20) | 시장 코드 |
| `trade_type` | VARCHAR(20) | `BUY`, `SELL` |
| `execution_mode` | VARCHAR(20) | 현재는 `PAPER`, 향후 `LIVE`와 분리 |
| `trade_price` | DECIMAL(18,2) | 서버가 확인한 체결 시점 현재가 |
| `quantity` | DECIMAL(18,4) | 가상 체결 수량 |
| `realized_profit` | DECIMAL(18,2) | 매도 시 평균 원가법으로 확정한 손익 |
| `trade_date` | DATETIME | 가상 체결 시각 |
| `memo` | VARCHAR(500) | AI 신호 또는 매도 설명 |

### 4.13 `order_prechecks`

지정가 주문안을 KB 계좌 자원과 안전 한도에 대조한 결과를 저장합니다. 이 테이블의 행은 주문 접수나 체결을 의미하지 않습니다.

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| `order_precheck_id` | BIGINT | 사전검증 PK |
| `user_id` | BIGINT | 로컬 사용자 FK |
| `stock_code`, `stock_name`, `market` | VARCHAR | 검토 대상 종목 |
| `order_side`, `order_type` | VARCHAR | `BUY`/`SELL`, 현재는 `LIMIT` |
| `requested_price`, `quantity` | DECIMAL | 사용자가 검토한 지정가와 수량 |
| `estimated_amount` | DECIMAL | 예상 주문금액 |
| `quote_provider`, `current_price` | VARCHAR, DECIMAL | 검증 시점 비교 시세 |
| `order_available_cash` | DECIMAL | 검증 시점 KB 주문가능현금 |
| `orderable_quantity` | DECIMAL | 검증 시점 KB 주문가능수량 |
| `order_enabled` | BOOLEAN | 검증 시점 주문 스위치 상태 |
| `eligible` | BOOLEAN | 모든 사전검증 통과 여부 |
| `blocker_summary` | VARCHAR(1000) | 실패 조건 요약 |
| `created_at` | DATETIME | 검증 시각 |

## 5. 인덱스 전략

| 인덱스 | 대상 | 이유 |
| --- | --- | --- |
| `uk_users_provider_user` | `users(auth_provider, provider_user_id)` | 로컬 소유자 중복 방지 |
| `idx_users_email` | `users.email` | 로컬 프로필 확인용 |
| `uk_watchlist_user_stock_market` | `watchlist(user_id, stock_code, market)` | 관심 종목 중복 방지 |
| `idx_holdings_user_status` | `holdings(user_id, status)` | 보유 종목 조회 |
| `idx_trade_records_recommendation_id` | `trade_records(recommendation_id)` | AI 추천과 가상 매수 연결 |
| `idx_trade_records_user_mode_date` | `trade_records(user_id, execution_mode, trade_date)` | 사용자별 모의매매 원장 조회 |
| `idx_order_prechecks_user_created` | `order_prechecks(user_id, created_at)` | 사용자별 최근 사전검증 감사 로그 조회 |
| `idx_order_prechecks_user_stock_created` | `order_prechecks(user_id, stock_code, created_at)` | 종목별 사전검증 이력 조회 |
| `idx_recommendations_user_created` | `recommendations(user_id, created_at)` | 최신 추천 목록 조회 |
| `idx_alerts_user_read_created` | `alerts(user_id, is_read, created_at)` | 알림 목록/읽음 필터 |
| `idx_alerts_user_stock_event_created` | `alerts(user_id, stock_code, market, event_type, created_at)` | 가격 이벤트 쿨다운 조회 |
| `uk_alerts_user_event_key` | `alerts(user_id, event_type, event_key)` | 뉴스·공시 이벤트 중복 방지 |
| `idx_snapshots_stock_created` | `analysis_snapshots(stock_code, market, created_at)` | 종목별 분석 이력 조회 |
| `uk_research_news_provider_key` | `research_news(provider, content_key)` | 같은 종목의 같은 뉴스 중복 방지 |
| `idx_research_news_stock_published` | `research_news(stock_code, published_at)` | 종목·기간별 뉴스 조회 |
| `uk_research_disclosures_provider_receipt` | `research_disclosures(provider, receipt_number)` | 같은 공시 중복 방지 |
| `idx_research_disclosures_stock_date` | `research_disclosures(stock_code, receipt_date)` | 종목·기간별 공시 조회 |
| `uk_research_sync_status_user_stock` | `research_sync_status(user_id, stock_code)` | 사용자·종목별 상태 한 행 유지 |
| `idx_research_sync_status_attempted` | `research_sync_status(last_attempted_at)` | 최근 동기화 상태 점검 |

## 6. 우선 사용 테이블

1. `users`
2. `user_capital`
3. `watchlist`
4. `holdings`
5. `recommendations`
6. `recommendation_reasons`
7. `alerts`
8. `research_news`
9. `research_disclosures`
10. `research_sync_status`
11. `trade_records`
12. `order_prechecks`

`trade_records`는 모의매매 API에서 사용하고 `order_prechecks`는 주문 전 검증 결과만 저장하며, 어느 테이블도 실제 증권사 주문을 수행했다는 의미가 아닙니다. `device_tokens`는 설계에는 포함되어 있지만 실제 API는 외부 푸시가 필요해질 때 붙입니다. `recommendations`, `recommendation_reasons`, `analysis_snapshots`는 통합 분석 실행 시 함께 저장합니다.

## 022. 전송 전 예약 중단 감사

`manual_order_reservation_aborts`는 command_id PK/전송기록 FK, user_id FK, execution_key, account_fingerprint, aborted_at(DATETIME(6))을 저장합니다. `manual_order_dispatches.phase` CHECK에 ABORTED를 추가하며 원본 주문과 가드는 변경하지 않습니다. 실제 pending 제외는 감사와 전송 기록의 소유권·키·계좌·시각·미시작 조건 일치를 요구합니다. 기존 DB는 [022 백업·적용](../orders/reserved-order-abort.md)이 필요하고 신규 schema.sql에도 포함됩니다. 메인 PC 021까지 점검 이후 022 운영 적용은 미실행입니다.

2026-11-02 메인 PC에서 백업 후 022 적용과 필수 컬럼·PK/FK·ABORTED 단계 CHECK를 확인했습니다. 읽기 전용 배포 점검은 [실제 일부 변경 후속 문서](../orders/manual-partial-order-changes.md)를 따릅니다. Ubuntu 별도 DB의 상태와 실제 주문 결과 검증을 의미하지 않습니다.

## 023. 계좌 관찰 저장·이력

`kb_account_observations`는 로컬 사용자 FK·내부 연결 HMAC·저장 요청 UUID·조회일·PENDING/COMPLETED/FAILED 상태, 불변 관찰 JSON·SHA-256과 UTC DATETIME(6) 메타데이터를 저장합니다. `(user_id,request_id)`와 `(user_id,observation_id)`는 UNIQUE이고 연결별 목록은 `(user_id,account_binding,record_id)` 인덱스를 사용합니다. LONGTEXT의 JSON_VALID와 상태 CHECK는 본문·결과·실패 코드·완료 시각의 일관성을 검사합니다.

외부 조회 전 예약을 커밋하고, 결과 저장은 별도 트랜잭션입니다. 실패한 결과 저장이 롤백돼도 예약은 남아 같은 ID의 재관찰을 막습니다. 기존 보유·자본금·주문/원장·가드는 수정하지 않습니다. [023 SQL](../../Back/database/migrations/023_account_observation_history.sql)은 기존 설치에서 백업 후 적용하고, 신규 schema.sql에는 같은 테이블을 포함합니다. 이번 작업의 운영 DB 적용은 미실행입니다. [API·복구·격리 검증](../accounts/account-observation-history.md)을 참고합니다.

## 024. 계좌 관찰 자동 수집 상태

`kb_account_observation_collectors`는 `(user_id,account_binding)` PK·사용자 FK, IDLE/ACTIVE/PAUSED, 실행 중 UUID·조회일, 직전 저장/관찰 상태·차단 코드와 UTC DATETIME(6) 시각을 저장합니다. `(user_id,active_request_id)` UNIQUE와 상태/종료 결과 CHECK로 중복 소유권과 불가능한 조합을 제한합니다. 관찰 본문은 기존 023에 보존합니다.

실행을 독립 트랜잭션으로 커밋한 뒤 관찰하며, ACTIVE는 시간 경과·재시작·설정 OFF로 해제하지 않습니다. 기존 UUID의 저장된 종료 결과만 대조해 IDLE/PAUSED로 바꿉니다. [024 SQL](../../Back/database/migrations/024_account_observation_collection.sql)은 기존 설치에서 백업 후 별도 적용해야 하며 신규 schema.sql에도 같은 정의를 추가했습니다. 운영 적용은 미실행이고 [수집·복구 계약](../accounts/account-observation-collection.md)을 따릅니다.

## 025·026. 공개 시세·연구 변경 이력

[025](../../Back/database/migrations/025_market_stream.sql)는 `market_stream_events`와 `market_stream_minutes`, [026](../../Back/database/migrations/026_research_incremental.sql)은 `research_journal_clock`·`research_item_heads`·`research_versions`·`research_checkpoints`를 추가합니다. 기존 DB에는 schema.sql 수정만으로 자동 적용되지 않습니다. 계약은 [실시간 수집](../market-data/realtime-data-pipeline.md)과 [저장 자료 내보내기](../market-data/stored-dataset-export.md)를 따릅니다.

2026-11-06 메인 PC에서 전체 DB 백업·압축 검증 후 두 마이그레이션을 적용했습니다. [복구 기록](../market-data/public-tick-collection-recovery.md)에서 원래 32개 테이블 보존·새 공개 테이블 6개·공개 API 200·실제 표본 1,081행 입력 대조를 확인했습니다. Ubuntu 별도 DB·장기 수집·주문 체결을 검증한 결과가 아니며 운영 수집 설정은 OFF입니다.


## 027. 커밋 이후 로컬 입력 공개 관측

[027](../../Back/database/migrations/027_market_input_availability.sql)은 `market_stream_availability`에 event_id PK/FK·원문 해시·JVM clock_domain·커밋/공개 관측 DATETIME(6)·단조 경과 ns·시계 품질과 순서 CHECK를 추가합니다. 기존 025/026 행은 수정하지 않으며 과거 공개 시각을 소급 생성하지 않습니다. [공개 순서·V2 계약·시계 한계](../market-data/committed-input-availability.md)를 따릅니다.

2026-11-06 메인 PC에서 전체 DB 백업/압축 검증 후 적용했습니다. 기존 이벤트 1,199건 해시와 비스트림 테이블 36개 불변, 신규 실제 이벤트/공개 관측 5건을 확인했습니다. 관측은 기본 OFF이며 Ubuntu 적용·운영 백엔드 재배포·외부 전략 수신 검증을 뜻하지 않습니다.


후속 [U02 연구용 입력 수신](../market-data/strategy-input-receipts.md)은 025/026/027을 읽는 전달 API와 로컬 파일 영수증을 추가하며 새 마이그레이션은 없습니다. 현재 프로세스의 실제 123건 공개/수신 연결을 확인했습니다. 영수증은 계좌·주문 원장이나 실제 모델 소비 기록을 대체하지 않습니다.
