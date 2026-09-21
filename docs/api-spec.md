# 사고팔고 API 명세서

이 문서는 Flutter Windows 프로그램, Spring Boot API 서버, 이후 추가될 Python AI 서버가 같은 데이터 계약을 보고 개발하기 위한 API 명세입니다.

## 1. 기본 원칙

- API 서버는 Spring Boot가 담당한다.
- 개인용 Windows 프로그램은 로그인 없이 로컬 사용자 1명으로 실행한다.
- 앱은 모든 개인 투자 데이터 요청을 Spring Boot API로 보낸다.
- 서버는 `SAGOPALGO_PERSONAL_MODE_USER_ID` 값을 현재 로컬 사용자 ID로 사용한다.
- Auth API, JWT, OAuth, refresh token은 현재 구조에서 제거한다.
- 모든 날짜/시간은 서버 내부에서는 UTC로 저장하고, 앱 표시 시 사용자 로컬 시간대로 변환한다.
- 추천 결과는 점수와 추천 사유를 반드시 함께 내려준다.
- 자동 주문은 즉시 구현하지 않고, 추후 사용자 승인과 감사 로그가 준비된 뒤 별도 단계로 구현한다.

## 2. 공통 응답 형식

### 성공 응답

```json
{
  "success": true,
  "data": {},
  "message": "요청이 성공했습니다."
}
```

### 실패 응답

```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "요청값이 올바르지 않습니다."
  }
}
```

### 공통 에러 코드

| 코드 | 의미 | HTTP |
| --- | --- | --- |
| `VALIDATION_ERROR` | 요청값 검증 실패 | 400 |
| `RESOURCE_NOT_FOUND` | 대상 데이터 없음 | 404 |
| `DUPLICATE_RESOURCE` | 이미 존재하는 데이터 | 409 |
| `EXTERNAL_DATA_ERROR` | 주가/뉴스/공시 외부 데이터 오류 | 502 |
| `INTERNAL_ERROR` | 서버 내부 오류 | 500 |

## 3. 개인용 사용자 컨텍스트

모든 사용자별 API는 요청자가 따로 로그인하지 않아도 서버가 로컬 사용자 ID를 사용합니다.

```text
SAGOPALGO_PERSONAL_MODE_ENABLED=true
SAGOPALGO_PERSONAL_MODE_USER_ID=1
SAGOPALGO_PERSONAL_MODE_NICKNAME=개인 사용자
SAGOPALGO_PERSONAL_MODE_EMAIL=local@sagopalgo.local
```

서버 시작 시 `users` 테이블에 해당 로컬 사용자 행이 없으면 자동으로 생성합니다.

## 4. Provider 설정 API

### 4.1 외부 Provider 연동 상태 조회

`GET /api/v1/settings/providers`

민감한 API Key, App Secret, 계좌번호는 응답에 포함하지 않습니다. 이 API는 시장 데이터, 뉴스, 공시 Provider의 역할별 활성화 여부와 안전한 누락 설정 이름만 보여줍니다.

2단계 기준 민감정보 저장 방식은 `.env` 파일입니다. Windows Credential Manager는 자동 주문 단계 전 다시 검토합니다.

응답:

```json
{
  "success": true,
  "data": {
    "secretStorageType": "ENV_FILE",
    "secretStorageDescription": ".env 파일과 Docker env-file로 개인용 API Key, App Secret, 계좌번호를 관리합니다.",
    "orderSafetyMode": "주문 기능 기본 OFF",
    "marketDataFallbackOrder": ["KB", "KIS", "TOSS"],
    "marketDataFallbackDescription": "앞 Provider가 비활성·미설정·조회 실패이면 다음 Provider를 시도하고, 모두 실패하면 등록 매수가를 사용합니다.",
    "providers": [
      {
        "code": "KB",
        "displayName": "KB증권",
        "marketDataEnabled": false,
        "accountEnabled": false,
        "orderEnabled": false,
        "newsEnabled": false,
        "disclosureEnabled": false,
        "configured": false,
        "missingRequiredSettings": ["App Key", "App Secret"],
        "roleDescription": "계좌 조회와 추후 주문 기능의 기준 증권사"
      },
      {
        "code": "KIS",
        "displayName": "한국투자증권",
        "marketDataEnabled": false,
        "accountEnabled": false,
        "orderEnabled": false,
        "newsEnabled": false,
        "disclosureEnabled": false,
        "configured": false,
        "missingRequiredSettings": ["App Key", "App Secret"],
        "roleDescription": "국내 주식 시세 조회용 데이터 소스"
      },
      {
        "code": "TOSS",
        "displayName": "토스증권",
        "marketDataEnabled": false,
        "accountEnabled": false,
        "orderEnabled": false,
        "newsEnabled": false,
        "disclosureEnabled": false,
        "configured": false,
        "missingRequiredSettings": ["Base URL", "현재가 API 경로", "App Key", "App Secret"],
        "roleDescription": "분석용 시세/종목 정보 보조 데이터 소스"
      },
      {
        "code": "NAVER_NEWS",
        "displayName": "네이버 뉴스",
        "marketDataEnabled": false,
        "accountEnabled": false,
        "orderEnabled": false,
        "newsEnabled": false,
        "disclosureEnabled": false,
        "configured": false,
        "missingRequiredSettings": ["Client ID", "Client Secret"],
        "roleDescription": "종목명 기준 최신 뉴스 검색 데이터 소스"
      },
      {
        "code": "OPEN_DART",
        "displayName": "OpenDART",
        "marketDataEnabled": false,
        "accountEnabled": false,
        "orderEnabled": false,
        "newsEnabled": false,
        "disclosureEnabled": false,
        "configured": false,
        "missingRequiredSettings": ["API Key"],
        "roleDescription": "종목코드와 DART 고유번호를 연결하는 전자공시 데이터 소스"
      }
    ]
  },
  "message": "외부 Provider 설정이 조회되었습니다."
}
```

## 5. KB증권 계좌 API

KB증권 Open API는 App Key/App Secret으로 `POST /oauth2/token`에서 access token을 발급받고, 이후 Bearer Token으로 계좌/잔고 API를 호출합니다. Base URL 기본값은 `https://developer.kbsec.com:32484`입니다.

KB증권 공식 API 문서 `all_kbstock_excel` 기준으로 보유주식 조회는 `SSQM1801_보유주식 조회`, 호출 path는 `/api/v1/ssqm1801`입니다. 이 path는 공개 API 경로라 예시 파일에 포함할 수 있습니다. App Key, App Secret, 계좌번호 같은 민감정보는 예시 파일에 넣지 않습니다.

공개 API path, 토큰 경로, `inq_clsf`, `mkt_tm_ccd` 기본값은 백엔드 기본 설정으로 관리합니다. `.env`에는 실제 실행 여부와 민감정보만 넣습니다.

```text
SAGOPALGO_KB_ACCOUNT_ENABLED=true
SAGOPALGO_KB_APP_KEY=KB에서 발급받은 App Key
SAGOPALGO_KB_APP_SECRET=KB에서 발급받은 App Secret
SAGOPALGO_KB_ACCOUNT_NUMBER=
```

### 5.1 KB 계좌 목록 조회

`GET /api/v1/kb/accounts`

KB 공식 API 문서 파일 기준으로 별도 계좌 목록 API는 확인되지 않았습니다. `SAGOPALGO_KB_ACCOUNTS_PATH`가 비어 있으면 KB API를 호출하지 않습니다. 이때 `SAGOPALGO_KB_ACCOUNT_NUMBER`가 있으면 로컬 설정 계좌를 마스킹해 반환하고, 계좌번호도 없으면 빈 목록을 반환합니다.

응답:

```json
{
  "success": true,
  "data": {
    "items": [
      {
        "provider": "KB",
        "accountAlias": "primary",
        "maskedAccountNumber": "****7890",
        "accountProductCode": "01",
        "accountName": "KB증권 연결 계좌",
        "accountType": "SECURITIES",
        "currency": "KRW"
      }
    ]
  },
  "message": "KB증권 계좌 목록이 조회되었습니다."
}
```

### 5.2 KB 보유 주식 조회

`GET /api/v1/kb/accounts/primary/holdings`

KB Open API `SSQM1801_보유주식 조회`를 호출해 종목별 종목번호, 종목명, 주문가능수량, 일반수량을 내부 표준 모델로 정규화합니다. 공식 문서의 필수 입력값은 `inq_clsf`, `mkt_tm_ccd`입니다. 문서상 평균단가/현재가/평가금액이 응답에 없는 경우 해당 금액 필드는 0으로 내려갑니다.

응답:

```json
{
  "success": true,
  "data": {
    "summary": {
      "totalPurchaseAmount": 1100000,
      "totalValuationAmount": 1130000,
      "totalProfitAmount": 30000,
      "profitRate": 2.73
    },
    "items": [
      {
        "stockCode": "005930",
        "stockName": "삼성전자",
        "market": "KRX",
        "quantity": 10,
        "averageBuyPrice": 70000,
        "currentPrice": 77000,
        "purchaseAmount": 700000,
        "valuationAmount": 770000,
        "profitAmount": 70000,
        "profitRate": 10,
        "weightRate": 68.14
      }
    ]
  },
  "message": "KB증권 보유 주식이 조회되었습니다."
}
```

### 5.3 KB 잔고 현황 조회(결제기준)

`GET /api/v1/kb/accounts/primary/balances/settlement`

KB Open API `SSQM2932_잔고현황조회(결제기준)`을 호출합니다. 백엔드는 공식 문서 기준 path `/api/v1/ssqm2932`와 기본 입력값 `inq_clsf=1`, `excg_mktpr_ccd=A`를 사용합니다.

요약 응답에는 예수금, 출금가능금액, 주문가능현금, 매입금액합계, 평가금액합계, 손익금액합계, 수익률합계 등을 정규화합니다. `Record1` 상세는 종목코드, 종목명, 잔고수량, 주문가능수량, 현재가, 매입평균가, 손익금액, 평가금액, 수익률, 평가비중 등을 포함합니다.

### 5.4 KB 잔고 현황 조회(체결기준)

`GET /api/v1/kb/accounts/primary/balances/execution`

KB Open API `SSQM2952_잔고현황조회(체결기준)`을 호출합니다. 백엔드는 공식 문서 기준 path `/api/v1/ssqm2952`와 기본 입력값 `excg_mktpr_ccd=A`를 사용합니다.

요약 응답에는 순자산평가금액, 유가순평가금액, 매입금액합계, 평가금액합계, 평가손익합계, 평가수익률합계 등을 정규화합니다. `Record1` 상세는 보유수량, 주문가능수량, 미결제매도수량, 미결제매수수량, 정산수량, 현재가, 매입평균가, 평가금액, 평가손익, 평가수익률 등을 포함합니다.

## 6. 대시보드 API

### 6.0 시장 데이터 Provider

보유 종목 현재가 계산은 `MarketDataProvider` 내부 표준 모델을 사용합니다. Provider 응답은 `StockQuote`로 정규화하며, 현재가, 전일대비, 등락률, 거래량, 시가, 고가, 저가, 전일종가를 같은 필드로 다룹니다. 캔들 데이터는 `StockCandle` 모델을 기준으로 확장할 수 있게 인터페이스를 열어 두었습니다.

Provider 우선순위는 KB증권, 한국투자증권, Toss 순서입니다. KB증권 시세는 공식 문서 `IVU10140_현재가`, path `/api/v1/ivu10140`, 요청값 `excg_clsf=0`, `shrt_cd=종목코드`를 기본값으로 사용합니다. Toss는 공식 시세 path가 확정되기 전까지 기본값이 비어 있어 자동 비활성 상태입니다.

외부 Provider가 일시적으로 실패하면 다음 Provider를 시도합니다. 모든 Provider가 실패하거나 지원 Provider가 없으면 보유 종목 화면의 계산은 등록 매수가를 fallback 현재가로 사용합니다.

### 6.1 앱 초기 스냅샷 조회

`GET /api/v1/dashboard/snapshot`

이 API는 현재 Flutter의 `InvestmentSnapshot` 모델과 맞춘 통합 응답입니다. MVP에서는 앱 첫 화면을 빠르게 띄우기 위해 여러 화면의 데이터를 한 번에 내려줍니다.

현재 구현은 `CapitalService`, `HoldingService`, `DashboardRecommendationEngine`을 조합합니다. 보유 종목의 `currentPrice`는 시장 데이터 Provider 우선순위와 fallback 정책에 따라 계산됩니다. 별도 추천 목록 API가 붙기 전까지 대표 추천은 대시보드 스냅샷 안에서 반환합니다. 실제 보유 종목이 없으면 `recommendation`은 `null`, `alerts`는 빈 배열입니다.

## 7. 자본금 API

### 7.1 자본금 조회

`GET /api/v1/capital`

### 7.2 자본금 수정

`PUT /api/v1/capital`

```json
{
  "availableCapital": 3000000,
  "riskPerTradeRate": 0.02
}
```

## 8. 관심 종목 API

### 8.1 관심 종목 목록 조회

`GET /api/v1/watchlist`

### 8.2 관심 종목 추가

`POST /api/v1/watchlist`

```json
{
  "stockCode": "005930",
  "stockName": "삼성전자",
  "market": "KOSPI",
  "alertEnabled": true
}
```

### 8.3 관심 종목 알림 설정 변경

`PATCH /api/v1/watchlist/{watchlistId}/alert`

```json
{
  "alertEnabled": false
}
```

### 8.4 관심 종목 삭제

`DELETE /api/v1/watchlist/{watchlistId}`

## 9. 보유 종목 API

### 9.1 보유 종목 목록 조회

`GET /api/v1/holdings`

KOSPI/KOSDAQ/KONEX 종목이고 시장 데이터 Provider 설정이 켜져 있으면 `currentPrice`와 `profitRate`는 외부 현재가 기준으로 계산됩니다. Provider 우선순위는 KB, KIS, Toss 순서입니다. 설정이 꺼져 있거나 미지원 시장이거나 모든 Provider가 실패하면 임의 샘플 가격을 만들지 않고 등록 매수가를 기준값으로 사용합니다.

### 9.2 보유 종목 등록

`POST /api/v1/holdings`

```json
{
  "stockCode": "005930",
  "stockName": "삼성전자",
  "market": "KOSPI",
  "buyPrice": 69100,
  "quantity": 12,
  "buyDate": "2026-09-07",
  "stopLossRate": -5.0,
  "takeProfitRate": 9.0
}
```

### 9.3 보유 종목 수정

`PUT /api/v1/holdings/{holdingId}`

### 9.4 보유 종목 삭제

`DELETE /api/v1/holdings/{holdingId}`

## 10. 뉴스·공시 API

### 10.1 외부 뉴스·공시 동기화

`POST /api/v1/research/feed/sync?stockCode=005930&stockName=삼성전자&fromDate=2026-08-01&toDate=2026-09-21`

네이버 뉴스와 OpenDART를 독립적으로 호출하고 성공한 결과를 로컬 DB에 upsert한 뒤, 해당 기간에 저장된 통합 피드를 반환합니다. 한쪽이 실패해도 다른 쪽 결과를 저장하며 Provider별 `SUCCESS`, `FAILED`, `DISABLED` 상태를 응답합니다.

`fromDate`와 `toDate`는 선택값입니다. 생략하면 오늘을 종료일로 하고 OpenDART 설정의 기본 조회 기간만큼 이전 날짜를 시작일로 사용합니다.

```json
{
  "success": true,
  "data": {
    "stockCode": "005930",
    "stockName": "삼성전자",
    "fromDate": "2026-08-01",
    "toDate": "2026-09-21",
    "news": [
      {
        "provider": "NAVER_NEWS",
        "stockCode": "005930",
        "title": "삼성전자 반도체 투자 확대",
        "link": "https://news.example/article",
        "summary": "기사 요약",
        "publishedAt": "2026-09-21T01:00:00Z"
      }
    ],
    "disclosures": [
      {
        "provider": "OPEN_DART",
        "stockCode": "005930",
        "corpCode": "00126380",
        "corpName": "삼성전자",
        "reportName": "주요사항보고서",
        "receiptNumber": "20260921000123",
        "submitterName": "삼성전자",
        "receiptDate": "2026-09-21",
        "link": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260921000123"
      }
    ],
    "providers": [
      {"provider": "NAVER_NEWS", "dataType": "NEWS", "status": "SUCCESS", "message": "1건 조회"},
      {"provider": "OPEN_DART", "dataType": "DISCLOSURE", "status": "SUCCESS", "message": "1건 조회"}
    ]
  },
  "message": "종목 뉴스와 공시가 동기화되었습니다."
}
```

뉴스는 `Provider + 종목코드 + 원문 URL`의 SHA-256 키로 중복을 제거합니다. URL이 없으면 제목과 발행시각을 대신 사용합니다. 공시는 `Provider + 접수번호`로 중복을 제거합니다. 같은 항목을 여러 번 동기화해도 새 행을 추가하지 않고 최신 값과 마지막 수집 시각을 갱신합니다.

### 10.2 저장된 종목별 뉴스·공시 조회

`GET /api/v1/research/feed?stockCode=005930&stockName=삼성전자&fromDate=2026-08-01&toDate=2026-09-21`

외부 Provider를 호출하지 않고 로컬 DB에서만 조회합니다. Provider 설정이 꺼져 있거나 외부 API가 일시적으로 실패해도 이전에 동기화한 데이터를 사용할 수 있습니다. 응답의 `providers`에는 `provider=LOCAL_DB`, `status=SUCCESS`, `dataType=CACHE`와 저장 건수가 표시됩니다.

## 11. 추천 API

이 절의 추천 목록/상세 API는 다음 구현 단계의 명세입니다. 현재 앱에서 실제로 사용하는 대표 추천은 `GET /api/v1/dashboard/snapshot`의 `recommendation` 필드로 제공됩니다.

### 11.1 추천 목록 조회

`GET /api/v1/recommendations?status=BUY_STRONG&page=0&size=20`

### 11.2 추천 상세 조회

`GET /api/v1/recommendations/{recommendationId}`

## 12. 알림 API

이 절의 알림 API는 다음 구현 단계의 명세입니다. 현재 앱 알림 탭의 데이터는 `GET /api/v1/dashboard/snapshot`의 `alerts` 필드로 제공됩니다.

### 12.1 알림 목록 조회

`GET /api/v1/alerts?page=0&size=20`

### 12.2 알림 읽음 처리

`PATCH /api/v1/alerts/{alertId}/read`

## 13. AI 서버 연동 API

아래 API는 앱이 직접 호출하지 않고 Spring Boot가 Python AI 서버를 호출할 때 사용하는 내부 계약입니다.

현재 구현에서는 Python AI 서버가 아직 붙지 않았으므로 `DashboardRecommendationEngine`이 실제 보유 종목 수익률, 손절 기준, 익절 기준을 조합해 설명 가능한 MVP 추천을 생성합니다. 실제 보유 종목이 없으면 임의 추천을 생성하지 않습니다.

### 13.1 종목 분석 요청

`POST /internal/ai/analyze-stock`

```json
{
  "stockCode": "005930",
  "stockName": "삼성전자",
  "market": "KOSPI",
  "analysisPeriod": "ONE_YEAR"
}
```

### 13.2 뉴스 감성 분석 요청

`POST /internal/ai/analyze-news`

```json
{
  "stockCode": "005930",
  "stockName": "삼성전자",
  "news": [
    {
      "title": "삼성전자 AI 반도체 수주 증가",
      "url": "https://example.com/news/1",
      "publishedAt": "2026-09-07T00:00:00Z"
    }
  ]
}
```

## 14. 다음 구현 순서

1. 관심 종목 뉴스·공시 주기 동기화
2. 캔들 조회 API를 실제 KB/KIS 차트 TR에 연결
3. Toss 공식 시세/종목 정보 path 확정 후 Provider 상세 매핑
4. AI 분석 서버와 추천 결과 저장
5. Windows 로컬 알림
6. 자동 주문 설계와 수동 승인 기반 주문 실행
