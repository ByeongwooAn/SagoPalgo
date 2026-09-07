# 사고팔고 DB 설계서

이 문서는 사고팔고 MVP와 이후 확장 기능을 고려한 MySQL 기준 DB 1차 설계입니다.

## 1. 설계 원칙

- 모든 사용자 데이터는 `user_id`를 기준으로 분리한다.
- 추천 결과는 단일 점수만 저장하지 않고, 점수를 만든 세부 근거를 함께 저장한다.
- 보유 종목은 매수가, 수량, 손절 기준, 익절 기준을 저장해 매도 추천의 입력값으로 사용한다.
- 알림은 FCM 발송 여부와 앱 내 읽음 상태를 모두 추적한다.
- AI 분석 결과는 나중에 백테스트와 설명 검증에 사용할 수 있도록 스냅샷으로 남긴다.
- 실제 주문 연동은 4단계 기능이므로 MVP DB에는 주문 테이블을 만들지 않고, 설계 확장 지점만 남긴다.

## 2. 테이블 목록

| 테이블 | 목적 | MVP 여부 |
| --- | --- | --- |
| `users` | 회원 계정과 기본 프로필 | 필수 |
| `refresh_tokens` | JWT refresh token 관리 | 필수 |
| `user_capital` | 사용자 자본금과 리스크 설정 | 필수 |
| `watchlist` | 관심 종목 관리 | 필수 |
| `holdings` | 보유 종목과 손절/익절 기준 | 2단계 |
| `trade_records` | 매수/매도 기록 | 2단계 |
| `recommendations` | AI 추천 결과 본문 | MVP |
| `recommendation_reasons` | 추천 점수 산출 근거 | MVP |
| `alerts` | 앱 알림 내역 | MVP |
| `device_tokens` | FCM 토큰 관리 | MVP |
| `analysis_snapshots` | AI 분석 결과 원본 스냅샷 | 2단계 |

## 3. 관계 요약

```text
users 1 ── N refresh_tokens
users 1 ── 1 user_capital
users 1 ── N watchlist
users 1 ── N holdings
users 1 ── N trade_records
users 1 ── N recommendations
recommendations 1 ── N recommendation_reasons
users 1 ── N alerts
users 1 ── N device_tokens
recommendations 1 ── N alerts
recommendations 1 ── N analysis_snapshots
```

## 4. 핵심 테이블 상세

### 4.1 `users`

Google/Naver 소셜 로그인에 필요한 계정 테이블입니다.

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| `user_id` | BIGINT | 사용자 PK |
| `auth_provider` | VARCHAR(20) | `GOOGLE`, `NAVER` |
| `provider_user_id` | VARCHAR(100) | Google `sub` 또는 Naver `response.id` |
| `email` | VARCHAR(255) | 소셜 제공자에서 동의받은 이메일, 없을 수 있음 |
| `nickname` | VARCHAR(50) | 앱 표시 이름 |
| `profile_image_url` | VARCHAR(500) | 소셜 프로필 이미지 URL |
| `role` | VARCHAR(20) | `USER`, `ADMIN` |
| `status` | VARCHAR(20) | `ACTIVE`, `SUSPENDED`, `DELETED` |
| `created_at` | DATETIME | 생성일 |
| `updated_at` | DATETIME | 수정일 |

### 4.2 `user_capital`

사용자의 투자 가능 자본금과 리스크 기준을 저장합니다.

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| `capital_id` | BIGINT | PK |
| `user_id` | BIGINT | 사용자 FK |
| `available_capital` | DECIMAL(18,2) | 투자 가능 자본금 |
| `risk_per_trade_rate` | DECIMAL(5,4) | 1회 거래 손실 허용 비율 |
| `recommended_min_position` | DECIMAL(18,2) | 종목당 최소 권장 투자금 |
| `recommended_max_position` | DECIMAL(18,2) | 종목당 최대 권장 투자금 |

### 4.3 `watchlist`

사용자가 관심 종목으로 등록한 종목을 저장합니다.

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| `watchlist_id` | BIGINT | PK |
| `user_id` | BIGINT | 사용자 FK |
| `stock_code` | VARCHAR(30) | 종목 코드 |
| `stock_name` | VARCHAR(100) | 종목명 |
| `market` | VARCHAR(20) | `KOSPI`, `KOSDAQ`, `NASDAQ`, `NYSE` |
| `alert_enabled` | BOOLEAN | 추천 알림 수신 여부 |

### 4.4 `holdings`

보유 종목과 매도 추천 계산에 필요한 기준값을 저장합니다.

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| `holding_id` | BIGINT | PK |
| `user_id` | BIGINT | 사용자 FK |
| `stock_code` | VARCHAR(30) | 종목 코드 |
| `stock_name` | VARCHAR(100) | 종목명 |
| `market` | VARCHAR(20) | 시장 |
| `buy_price` | DECIMAL(18,2) | 평균 매수가 |
| `quantity` | DECIMAL(18,4) | 수량 |
| `buy_date` | DATE | 매수일 |
| `stop_loss_rate` | DECIMAL(6,3) | 손절 기준 |
| `take_profit_rate` | DECIMAL(6,3) | 익절 기준 |
| `status` | VARCHAR(30) | `HOLDING`, `PARTIAL_TAKE_PROFIT`, `STOP_LOSS_WATCH`, `SOLD` |

### 4.5 `recommendations`

AI가 생성한 매수/매도 추천의 핵심 결과를 저장합니다.

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| `recommendation_id` | BIGINT | PK |
| `user_id` | BIGINT | 사용자 FK |
| `stock_code` | VARCHAR(30) | 종목 코드 |
| `stock_name` | VARCHAR(100) | 종목명 |
| `market` | VARCHAR(20) | 시장 |
| `recommendation_type` | VARCHAR(20) | `BUY`, `SELL`, `HOLD` |
| `status` | VARCHAR(30) | `BUY_STRONG`, `WATCH`, `NEUTRAL`, `RISK`, `SELL_TAKE_PROFIT`, `SELL_STOP_LOSS` |
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
| `reason_type` | VARCHAR(30) | `RSI`, `MACD`, `VOLUME`, `NEWS`, `FOREIGN_BUY`, `MARKET` |
| `label` | VARCHAR(50) | 화면 표시 라벨 |
| `description` | VARCHAR(500) | 사용자에게 보여줄 설명 |
| `score` | INT | 해당 조건이 더한 점수 |

### 4.7 `alerts`

FCM 발송 및 앱 내 알림 히스토리를 관리합니다.

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| `alert_id` | BIGINT | PK |
| `user_id` | BIGINT | 사용자 FK |
| `recommendation_id` | BIGINT | 연결된 추천 FK, 없을 수 있음 |
| `alert_type` | VARCHAR(30) | `BUY`, `SELL`, `MARKET`, `RISK` |
| `title` | VARCHAR(100) | 알림 제목 |
| `body` | VARCHAR(500) | 알림 본문 |
| `is_read` | BOOLEAN | 앱 내 읽음 여부 |
| `sent_at` | DATETIME | FCM 발송 시각 |

### 4.8 `analysis_snapshots`

AI 서버가 계산한 분석 결과 원본을 JSON으로 보관합니다.

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| `snapshot_id` | BIGINT | PK |
| `user_id` | BIGINT | 사용자 FK |
| `recommendation_id` | BIGINT | 추천 FK |
| `stock_code` | VARCHAR(30) | 종목 코드 |
| `analysis_type` | VARCHAR(30) | `TECHNICAL`, `NEWS`, `MARKET`, `TOTAL` |
| `score` | INT | 분석 점수 |
| `raw_payload` | JSON | AI 서버 응답 원본 |

## 5. 인덱스 전략

| 인덱스 | 대상 | 이유 |
| --- | --- | --- |
| `uk_users_provider_user` | `users(auth_provider, provider_user_id)` | 소셜 계정 중복 방지와 로그인 조회 |
| `idx_users_email` | `users.email` | 고객 지원/계정 검색용 이메일 조회 |
| `uk_watchlist_user_stock_market` | `watchlist(user_id, stock_code, market)` | 관심 종목 중복 방지 |
| `idx_holdings_user_status` | `holdings(user_id, status)` | 사용자별 보유 종목 조회 |
| `idx_recommendations_user_created` | `recommendations(user_id, created_at)` | 최신 추천 목록 조회 |
| `idx_alerts_user_read_created` | `alerts(user_id, is_read, created_at)` | 알림 목록/읽음 필터 |
| `idx_snapshots_stock_created` | `analysis_snapshots(stock_code, market, created_at)` | 종목별 분석 이력 조회 |

## 6. MVP 개발 시 우선 생성 테이블

1. `users`
2. `refresh_tokens`
3. `user_capital`
4. `watchlist`
5. `recommendations`
6. `recommendation_reasons`
7. `device_tokens`
8. `alerts`

`holdings`, `trade_records`, `analysis_snapshots`는 2단계에서 바로 필요하므로 SQL에는 포함해두되, API 구현 우선순위는 MVP 이후로 둡니다.
