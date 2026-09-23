# 사고팔고 Spring Boot API 서버

이 폴더는 사고팔고 개인용 Windows 프로그램의 로컬 백엔드입니다. 로그인이나 다중 사용자 가입 흐름 없이 로컬 사용자 한 명을 기준으로 계좌, 보유 종목, 관심 종목, 시장 데이터, 뉴스와 공시를 조회합니다.

## 실행 전 준비

1. MySQL에서 `Back/database/schema.sql`을 실행해 데이터베이스와 기본 테이블을 생성합니다.
2. `.env.example`을 참고해 `Back/spring-server/.env`에 DB 접속 정보와 사용할 Provider 설정을 입력합니다.
3. 실제 데이터를 조회할 Provider만 `*_ENABLED=true`로 켭니다. 키가 없거나 사용하지 않는 Provider는 `false`로 둡니다.
4. 서버 시작 시 `.env`가 자동으로 로드되며, OS 환경 변수가 `.env`보다 우선합니다.
5. 아래 명령으로 전체 테스트를 실행합니다.

```powershell
.\gradlew.bat '-Dorg.gradle.project.buildDir=build-codex' test --no-daemon
```

## 개인용 사용자 구조

- `SAGOPALGO_PERSONAL_MODE_ENABLED=true`이면 모든 사용자별 API를 JWT 없이 호출합니다.
- 서버는 `SAGOPALGO_PERSONAL_MODE_USER_ID`의 로컬 사용자를 현재 사용자로 사용합니다.
- 시작 시 사용자 행이 없으면 `LOCAL/personal-owner` 사용자를 준비합니다.
- `users.user_id` 관계는 보유 종목, 관심 종목, 분석 결과를 같은 로컬 소유자 데이터로 묶기 위해 유지합니다.
- Google/Naver 로그인, JWT 재발급, 로그아웃 API는 현재 코드에 없습니다.
- 앱 접근 보호는 선택형 앱 잠금 PIN을 사용하며, 주문 기능은 기본적으로 꺼져 있습니다.

## 현재 구현된 API

| 기능 | 메서드 | 경로 |
| --- | --- | --- |
| Provider 설정 상태 | GET | `/api/v1/settings/providers` |
| KB 계좌 목록 | GET | `/api/v1/kb/accounts` |
| KB 보유 주식 | GET | `/api/v1/kb/accounts/primary/holdings` |
| KB 결제기준 잔고 | GET | `/api/v1/kb/accounts/primary/balances/settlement` |
| KB 체결기준 잔고 | GET | `/api/v1/kb/accounts/primary/balances/execution` |
| 국내주식 캔들 시세 | GET | `/api/v1/market/candles` |
| 저장된 종목 뉴스·공시 조회 | GET | `/api/v1/research/feed` |
| 종목 뉴스·공시 외부 동기화 | POST | `/api/v1/research/feed/sync` |
| 보유 종목 분석·추천 저장 | POST | `/api/v1/recommendations/analyze/{holdingId}` |
| 추천 이력 목록 | GET | `/api/v1/recommendations` |
| 추천 이력 상세 | GET | `/api/v1/recommendations/{recommendationId}` |
| 대시보드 스냅샷 | GET | `/api/v1/dashboard/snapshot` |
| 자본금 조회·수정 | GET, PUT | `/api/v1/capital` |
| 관심 종목 목록·등록 | GET, POST | `/api/v1/watchlist` |
| 관심 종목 알림 설정 | PATCH | `/api/v1/watchlist/{watchlistId}/alert` |
| 관심 종목 삭제 | DELETE | `/api/v1/watchlist/{watchlistId}` |
| 보유 종목 목록·등록 | GET, POST | `/api/v1/holdings` |
| 보유 종목 수정·삭제 | PUT, DELETE | `/api/v1/holdings/{holdingId}` |
| 종목 기본 정보 조회 | GET | `/api/v1/market/stocks/{stockCode}` |

## 시장 데이터 Provider

- 현재가 조회 순서는 `KB → KIS → Toss`입니다.
- 일·주·월봉 캔들 조회 순서는 `KB → KIS → Toss`입니다. Toss는 공식 API가 제공하는 일봉만 담당하고 주·월봉을 임의 합성하지 않습니다.
- Provider가 비활성, 미지원, 미설정 또는 일시 실패 상태이면 다음 Provider를 시도합니다.
- 모든 Provider를 사용할 수 없으면 임의 가격을 만들지 않고 사용자가 등록한 매수가를 사용합니다.
- 캔들은 등록 매수가로 만들 수 없으므로 모든 Provider가 실패하면 `EXTERNAL_DATA_ERROR`를 반환합니다.
- `/api/v1/settings/providers`는 활성화 여부, 누락된 설정 이름, fallback 순서를 반환하지만 실제 키와 계좌번호는 노출하지 않습니다.
- Toss는 OAuth2 Client Credentials로 토큰을 발급받아 국내·미국 주식 현재가, 일봉, 종목 기본 정보를 조회합니다. 기본값은 공식 URL과 경로이며 Client ID/Secret이 없거나 기능이 꺼져 있으면 호출하지 않습니다.
- Toss 현재가 응답에는 현재가와 통화만 있으므로 등락률·OHLCV를 임의 계산하지 않습니다.

캔들 조회 예시:

```powershell
Invoke-RestMethod `
  -Method Get `
  -Uri 'http://localhost:8080/api/v1/market/candles?stockCode=005930&market=KOSPI&interval=DAILY&count=60'

Invoke-RestMethod `
  -Method Get `
  -Uri 'http://localhost:8080/api/v1/market/stocks/005930?market=KOSPI'
```

`interval`은 `DAILY`, `WEEKLY`, `MONTHLY`를 지원하고 `count`는 1~100입니다. 반환 목록은 오래된 시점부터 최신 시점 순으로 정렬됩니다.

## 뉴스·공시 Provider

네이버 뉴스 검색 API와 OpenDART 공시검색 API는 서로 독립적으로 동작합니다. `POST /sync`에서 한쪽 조회가 실패해도 다른 쪽 결과를 저장하고 Provider별 `SUCCESS`, `FAILED`, `DISABLED` 상태를 반환합니다. 일반 `GET`은 외부 API를 다시 호출하지 않고 로컬 DB만 조회합니다.

- 네이버 뉴스 검색: [공식 개발가이드](https://developers.naver.com/docs/serviceapi/search/news/news.md)
- OpenDART 공시검색: [공식 개발가이드](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019001)

```dotenv
SAGOPALGO_NAVER_NEWS_ENABLED=true
SAGOPALGO_NAVER_NEWS_CLIENT_ID=발급받은-client-id
SAGOPALGO_NAVER_NEWS_CLIENT_SECRET=발급받은-client-secret

SAGOPALGO_OPEN_DART_ENABLED=true
SAGOPALGO_OPEN_DART_API_KEY=발급받은-api-key

SAGOPALGO_RESEARCH_SYNC_ENABLED=true
SAGOPALGO_RESEARCH_SYNC_CRON=0 0/30 * * * *
SAGOPALGO_RESEARCH_SYNC_ZONE=Asia/Seoul
```

외부 동기화 후 저장 결과 조회 예시:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri 'http://localhost:8080/api/v1/research/feed/sync?stockCode=005930&stockName=삼성전자&fromDate=2026-08-01&toDate=2026-09-21'

Invoke-RestMethod `
  -Method Get `
  -Uri 'http://localhost:8080/api/v1/research/feed?stockCode=005930&stockName=삼성전자&fromDate=2026-08-01&toDate=2026-09-21'
```

- 뉴스 제목과 요약은 검색 강조 HTML을 제거해 저장 가능한 일반 문자열로 정규화합니다.
- OpenDART 고유번호 파일을 애플리케이션 메모리에 캐시하고 종목코드로 회사 고유번호를 자동 해석합니다.
- 공시 링크는 DART 원문 조회 주소로 구성합니다.
- 뉴스는 Provider, 종목코드, 원문 URL 기반 키로, 공시는 Provider와 접수번호로 중복을 제거합니다.
- 같은 데이터를 다시 동기화하면 새 행을 만들지 않고 저장값과 마지막 수집 시각을 갱신합니다.
- 날짜를 생략하면 종료일은 오늘, 시작일은 기본 30일 전입니다.
- 자동 동기화를 켜면 개인 사용자의 관심 종목을 cron 주기마다 순회하며, 한 종목 실패가 다음 종목 처리를 막지 않습니다.
- `/api/v1/research/sync/status`에서 자동 수집 활성 여부와 종목별 마지막 실행 상태를 조회합니다.

기존 MySQL 데이터 볼륨에는 [`Back/database/migrations/002_research_feed_storage.sql`](../database/migrations/002_research_feed_storage.sql), [`Back/database/migrations/003_research_sync_status.sql`](../database/migrations/003_research_sync_status.sql), [`Back/database/migrations/004_event_alerts.sql`](../database/migrations/004_event_alerts.sql), [`Back/database/migrations/005_paper_trading.sql`](../database/migrations/005_paper_trading.sql), [`Back/database/migrations/006_order_prechecks.sql`](../database/migrations/006_order_prechecks.sql), [`Back/database/migrations/007_order_approvals.sql`](../database/migrations/007_order_approvals.sql), [`Back/database/migrations/008_order_submission_guards.sql`](../database/migrations/008_order_submission_guards.sql)을 순서대로 한 번 적용해야 합니다. 새 데이터 볼륨은 `Back/database/schema.sql`에서 저장 테이블을 함께 생성합니다.

## 주문 사전검증

- `POST /api/v1/orders/precheck`: 지정가·수량을 현재가, 주문가능현금·수량, 안전 한도와 대조
- `GET /api/v1/orders/prechecks?limit=20`: 최근 사전검증 감사 로그 조회
- `SAGOPALGO_KB_MAX_ORDER_AMOUNT`: 1회 최대 주문금액, 기본 100만원
- `SAGOPALGO_KB_MAX_PRICE_DEVIATION_RATE`: 현재가 대비 지정가 최대 이탈률, 기본 5%
- 실제 KB 주문 제출 API는 아직 없으며 사전검증 응답의 `canSubmit`은 항상 `false`입니다.

## 모의매매

- `GET /api/v1/paper-trading`: 모의 자산, 성과 지표, 포지션, 체결 이력 조회
- `POST /api/v1/paper-trading/recommendations/{recommendationId}/buy`: 저장된 `BUY` 추천을 실제 현재가로 가상 매수
- `POST /api/v1/paper-trading/sell`: 보유한 모의 포지션을 실제 현재가로 가상 매도
- 모든 거래는 `execution_mode=PAPER`로 저장되며 KB 주문 API를 호출하지 않습니다.
- `FALLBACK` 현재가는 평가 기준으로만 사용할 수 있고 가상 체결에는 사용할 수 없습니다.

## 추천 기준

- Python `WEIGHTED_SIGNAL_V1` 분석기는 최근 일봉, 저장 뉴스·공시, 보유 손익과 손절·익절 기준을 종합합니다.
- `POST /api/v1/recommendations/analyze/{holdingId}`는 추천 본문, 점수 근거, 분석 원문을 한 트랜잭션으로 저장합니다.
- Python 서버가 비활성 또는 실패 상태이면 `DashboardRecommendationEngine`의 규칙 결과를 같은 저장 계약으로 대체합니다.
- 대시보드는 저장된 최신 추천을 우선 표시하고, 저장 결과가 없을 때만 즉시 계산한 규칙 추천을 사용합니다.
- 보유 종목이 없고 저장 추천도 없으면 대시보드의 `recommendation`은 `null`, `alerts`는 빈 배열입니다.

분석과 저장 예시:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri 'http://localhost:8080/api/v1/recommendations/analyze/21'

Invoke-RestMethod `
  -Method Get `
  -Uri 'http://localhost:8080/api/v1/recommendations?page=0&size=20'
```

추천 결과가 매수·익절·위험 상태이면 `alerts`에 Windows 전달 대기 알림이 저장됩니다. 보유 종목의 손절·익절 기준 도달과 급등락은 가격 알림으로 저장되며, 권장 최대 비중 초과와 총 미실현 손실 한도 도달은 포트폴리오 알림으로 저장됩니다. 관심 종목 동기화에서 발견한 신규 뉴스·공시는 고유 이벤트 키로 한 번만 알립니다. Ubuntu 운영 환경에서는 `SAGOPALGO_ALERT_ANALYSIS_ENABLED=true`로 설정해 보유 종목을 기본 15분마다 자동 분석합니다. 포트폴리오 알림만 끄려면 `SAGOPALGO_ALERT_PORTFOLIO_EVENTS_ENABLED=false`로 설정합니다.

```powershell
Invoke-RestMethod -Uri 'http://localhost:8080/api/v1/alerts?page=0&size=20'
Invoke-RestMethod -Uri 'http://localhost:8080/api/v1/alerts/pending?limit=20'
Invoke-RestMethod -Method Patch -Uri 'http://localhost:8080/api/v1/alerts/1/sent'
Invoke-RestMethod -Method Patch -Uri 'http://localhost:8080/api/v1/alerts/1/read'
```

## 다음 구현 후보

주문 사전검증 후 `POST /api/v1/orders/approvals/prepare`로 90초짜리 일회용 토큰을 발급하고, `POST /api/v1/orders/approvals/confirm`으로 수동 승인 **기록만** 저장할 수 있습니다. 승인 확인과 제출 가드 `READY` 행 생성은 한 트랜잭션이며, `GET /api/v1/orders/approvals/{approvalId}/submission`에서 상태를 읽을 수 있습니다. `orderSubmitted=false`이며 KB 주문은 전송되지 않습니다. 기존 DB에는 `007_order_approvals.sql` 다음 `008_order_submission_guards.sql`을 적용해야 합니다.

서버 내부의 `OrderSubmissionGuardService.reserveOnce`는 `READY`를 원자적으로 `RESERVED`로 한 번만 바꿉니다. 예약 후 통신 결과가 불명확하면 `UNCERTAIN`으로 기록하며 두 상태 모두 자동 재시도를 허용하지 않습니다. 마이그레이션 전 이미 확인된 승인은 재사용할 수 없는 `LEGACY_REVIEW`로 기록합니다. 현재는 주문 전송자가 이 서비스를 호출하지 않으므로 새 승인 건은 `READY`에 머뭅니다.

KB 공식 매수 `SSAM1802`·매도 `SSAM1801` 지정가 요청 형식과 응답 판정은 `KbLimitOrderContract` 및 단위 테스트로 고정했습니다. 이는 순수 형식 검사기이며 외부 주문 API에 연결되지 않았습니다. HTTP/헤더의 `resultCode=200`만으로 주문 접수로 판단하지 않고 `processFlag`와 실제 주문번호를 함께 확인합니다. 자세한 필드와 후속 안전 작업은 `docs/api-spec.md` 15.4절을 참고하세요.

`GET /api/v1/orders/kb/executions`와 `GET /api/v1/orders/kb/executions/{orderNo}`는 KB `SSQM2341`의 읽기 전용 체결미체결 조회 및 최대 10페이지 주문번호 대조 API입니다. 주문 제출·취소·정정은 호출하지 않습니다. 실제 KB 응답 형태와 계좌 권한은 운영 계좌에서 별도 수동 확인이 필요합니다. 진척도 산정은 `docs/development-progress.md`를 참고하세요.

1. 주문 전송 어댑터가 단일 예약을 사용하도록 연결하고, 불명확 응답의 수동 대조 절차를 완성한 뒤 별도 활성화 설정 아래 수동 승인 기반 실주문 전송
2. 주문 결과·실패·취소·정정 상태 동기화
3. 배포 패키지 자동 업데이트와 운영 상태 진단
