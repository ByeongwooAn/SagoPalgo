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

응답의 `secretStorageType=ENV_FILE`은 Ubuntu 백엔드의 Provider 비밀값 저장 방식을 뜻합니다. Windows 앱 잠금 PIN은 Credential Manager에 별도로 저장하며 API 응답에 포함하지 않습니다.

응답:

```json
{
  "success": true,
  "data": {
    "secretStorageType": "ENV_FILE",
    "secretStorageDescription": ".env 파일과 Docker env-file로 개인용 API Key, App Secret, 계좌번호를 관리합니다.",
    "orderSafetyMode": "주문 기능 OFF · 사전검증만 지원",
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

보유 종목 현재가 계산은 `MarketDataProvider` 내부 표준 모델을 사용합니다. Provider 응답은 `StockQuote`로 정규화하며, 현재가, 전일대비, 등락률, 거래량, 시가, 고가, 저가, 전일종가를 같은 필드로 다룹니다. 기간별 시세는 `StockCandle`로 정규화해 일·주·월봉 OHLCV를 같은 계약으로 제공합니다.

현재가 Provider 우선순위는 KB증권, 한국투자증권, Toss 순서입니다. KB증권 시세는 공식 문서 `IVU10140_현재가`, path `/api/v1/ivu10140`, 요청값 `excg_clsf=0`, `shrt_cd=종목코드`를 기본값으로 사용합니다.

Toss는 공식 Open API의 OAuth2 Client Credentials 토큰과 `GET /api/v1/prices?symbols=종목코드`를 사용합니다. 국내 주식과 미국 주식을 지원하며 현재가 응답에 없는 등락률·거래량·시가·고가·저가·전일종가는 임의로 계산하지 않고 0으로 둡니다.

외부 Provider가 일시적으로 실패하면 다음 Provider를 시도합니다. 모든 Provider가 실패하거나 지원 Provider가 없으면 보유 종목 화면의 계산은 등록 매수가를 fallback 현재가로 사용합니다.

#### 6.0.1 국내주식 캔들 조회

`GET /api/v1/market/candles?stockCode=005930&market=KOSPI&interval=DAILY&count=60`

- `market`: `KOSPI`, `KOSDAQ`을 지원합니다. KIS fallback은 `KONEX`도 조회할 수 있습니다.
- `interval`: `DAILY`, `WEEKLY`, `MONTHLY` 중 하나입니다.
- `count`: 1~100이며 기본값은 60입니다.
- 조회 순서는 KB증권 `IVS11560_통합차트`, 한국투자증권 `FHKST03010100`, Toss `GET /api/v1/candles`입니다.
- Toss는 공식적으로 `1m`, `1d`만 제공하므로 현재 앱 API에서는 `DAILY` fallback에만 참여합니다. `WEEKLY`, `MONTHLY`는 KB/KIS를 사용하며 Toss 일봉을 임의 집계하지 않습니다.
- 응답 캔들은 차트에서 바로 사용할 수 있도록 오래된 시점부터 최신 시점 순으로 정렬합니다.
- 캔들은 등록 매수가로 대체하지 않습니다. 모든 Provider가 실패하거나 빈 결과를 반환하면 `EXTERNAL_DATA_ERROR`입니다.
- Flutter 포트폴리오의 보유 종목별 차트 버튼에서 일·주·월봉을 전환할 수 있으며, 화면에 실제 응답 Provider를 함께 표시합니다.

응답:

```json
{
  "success": true,
  "data": {
    "provider": "KB",
    "stockCode": "005930",
    "market": "KOSPI",
    "interval": "DAILY",
    "count": 2,
    "candles": [
      {
        "provider": "KB",
        "stockCode": "005930",
        "market": "KOSPI",
        "dateTime": "2026-09-21T00:00:00",
        "interval": "DAILY",
        "openPrice": 74800,
        "highPrice": 75300,
        "lowPrice": 74700,
        "closePrice": 75200,
        "volume": 1122334
      }
    ]
  },
  "message": "종목 캔들 시세가 조회되었습니다."
}
```

#### 6.0.2 종목 기본 정보 조회

`GET /api/v1/market/stocks/{stockCode}?market=KOSPI`

Toss 공식 `GET /api/v1/stocks?symbols=종목코드` 응답을 사용합니다. 응답에는 Provider, 종목명, 영문명, 시장, 종목 유형, 보통주 여부, 상장 상태, 통화, 상장·상장폐지일, 발행주식수, NXT 지원 여부, 거래정지 여부가 포함됩니다.

### 6.1 앱 초기 스냅샷 조회

`GET /api/v1/dashboard/snapshot`

이 API는 현재 Flutter의 `InvestmentSnapshot` 모델과 맞춘 통합 응답입니다. MVP에서는 앱 첫 화면을 빠르게 띄우기 위해 여러 화면의 데이터를 한 번에 내려줍니다.

현재 구현은 `CapitalService`, `HoldingService`, 저장된 최신 추천을 조합합니다. 저장 추천이 아직 없거나 현재 보유하지 않은 종목의 결과이면 `DashboardRecommendationEngine`이 규칙 기반 추천을 대신 반환합니다. 보유 종목의 `currentPrice`는 시장 데이터 Provider 우선순위와 fallback 정책에 따라 계산됩니다. 실제 보유 종목이 없으면 과거 추천 이력이 있어도 `recommendation`은 `null`, `alerts`는 빈 배열입니다.

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

각 항목은 기본 관심 종목 정보와 함께 `provider`, `currentPrice`, `changeRate`를 반환합니다. 시세 Provider 우선순위는 KB, KIS, Toss이며 모든 Provider가 비활성 또는 실패 상태이면 `provider=FALLBACK`, `currentPrice=0`, `changeRate=0`으로 반환합니다. 이 시세 정보는 Windows 미니 위젯의 관심 종목 목록에 사용합니다.

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

응답의 `summary.maxAllowedLoss`는 투자 가능 자본금과 1회 리스크 비율을 곱한 최대 허용 손실입니다. `summary.riskUsageRate`는 현재 총 미실현 손실의 절댓값을 최대 허용 손실로 나눈 비율이며, 수익 중이거나 최대 허용 손실이 0원이면 `0`입니다. 허용 손실을 넘긴 경우 `1`보다 클 수 있습니다.

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

### 10.3 뉴스·공시 동기화 상태 조회

`GET /api/v1/research/sync/status?stockCode=005930`

자동 동기화 활성 여부와 선택 종목의 마지막 수동·자동 동기화 결과를 반환합니다. `item`은 아직 실행 이력이 없으면 생략됩니다.

```json
{
  "success": true,
  "data": {
    "enabled": true,
    "cron": "0 0/30 * * * *",
    "zone": "Asia/Seoul",
    "item": {
      "stockCode": "005930",
      "stockName": "삼성전자",
      "triggerType": "SCHEDULED",
      "status": "PARTIAL",
      "newsCount": 10,
      "disclosureCount": 3,
      "providerSuccessCount": 1,
      "providerFailureCount": 1,
      "providerDisabledCount": 0,
      "message": "Provider 성공 1 · 실패 1 · 비활성 0",
      "lastAttemptedAt": "2026-09-22T00:00:00Z",
      "lastSucceededAt": "2026-09-22T00:00:00Z"
    }
  }
}
```

상태는 `SUCCESS`, `PARTIAL`, `FAILED`, `SKIPPED` 중 하나입니다. 자동 동기화는 등록된 관심 종목을 순회하며 한 종목이 실패해도 다음 종목을 계속 처리합니다.

## 11. 추천 API

추천 분석은 로컬 사용자의 보유 종목을 기준으로 최근 일봉, 저장 뉴스, 저장 공시, 손익·손절·익절 기준을 Python 분석 서버에 전달합니다. 분석 결과는 추천 본문, 점수 근거, 요청·응답 원문 스냅샷으로 나누어 저장합니다. Python 서버가 비활성 또는 일시 실패 상태이면 기존 규칙 엔진 결과를 같은 형식으로 저장합니다.

### 11.1 보유 종목 분석 및 추천 저장

`POST /api/v1/recommendations/analyze/{holdingId}`

응답의 `status`는 `BUY_STRONG`, `BUY_WATCH`, `HOLD`, `TAKE_PROFIT`, `STOP_LOSS_WATCH`, `RISK` 중 하나이며 `statusLabel`은 Flutter에 표시할 한글 상태입니다.

### 11.2 추천 목록 조회

`GET /api/v1/recommendations?status=BUY_STRONG&page=0&size=20`

`status`는 선택값이고 `page`는 0 이상, `size`는 1~100입니다. 목록 응답은 `items`, `page`, `size`, `total`을 포함합니다.

### 11.3 추천 상세 조회

`GET /api/v1/recommendations/{recommendationId}`

상세 응답에는 추천 점수에 반영된 `reasons`가 포함됩니다.

## 12. 알림 API

추천 상태가 `BUY_STRONG`, `BUY_WATCH`, `TAKE_PROFIT`, `STOP_LOSS_WATCH`, `RISK`이면 추천 알림이 생성됩니다. `HOLD`는 알림을 만들지 않습니다. 별도로 보유 종목이 손절·익절 기준에 도달하거나 당일 등락률이 기본 ±5%를 넘으면 가격 이벤트 알림을 만들고, 관심 종목 동기화에서 최근 뉴스와 공시가 발견되면 각각 뉴스·공시 알림을 만듭니다.

보유 종목 자동 평가가 끝나면 포트폴리오 리스크도 한 번 평가합니다. 종목 평가금액이 투자 가능 자본금의 권장 최대 비중 20%를 넘으면 `PORTFOLIO_POSITION_OVERWEIGHT`, 실제 시세로 계산한 총 미실현 손실이 `availableCapital * riskPerTradeRate` 이상이면 `PORTFOLIO_TOTAL_LOSS` 알림을 만듭니다. `FALLBACK` 시세는 매수가 기준의 과다 비중 검사에는 사용할 수 있지만 총 손실 계산에서는 제외합니다.

관심 종목에서 알림을 끈 종목은 추천·가격·종목별 포트폴리오 알림 대상에서 제외됩니다. 같은 가격·포트폴리오 이벤트는 기본 60분 쿨다운 동안 다시 만들지 않으며, 뉴스는 원문 링크, 공시는 DART 접수번호에서 만든 고유 키로 정확히 한 번만 저장합니다. 실제 시세가 아닌 `FALLBACK` 응답으로는 가격 이벤트를 만들지 않습니다.

### 12.1 알림 목록 조회

`GET /api/v1/alerts?unreadOnly=false&page=0&size=20`

응답은 `items`, `page`, `size`, `total`을 포함합니다. 각 항목에는 `alertId`, `recommendationId`, `type`, `eventType`, `stockCode`, `title`, `body`, `read`, `sentAt`, `createdAt`, `timeLabel`이 포함됩니다. `type`은 화면 분류(`BUY`, `SELL`, `RISK`, `PRICE`, `NEWS`, `DISCLOSURE`, `PORTFOLIO`)이고, `eventType`은 `PRICE_STOP_LOSS`, `PRICE_TAKE_PROFIT`, `PRICE_SURGE`, `PRICE_DROP`, `NEWS`, `DISCLOSURE`, `PORTFOLIO_POSITION_OVERWEIGHT`, `PORTFOLIO_TOTAL_LOSS`처럼 실제 발생 조건을 나타냅니다.

### 12.2 알림 읽음 처리

`PATCH /api/v1/alerts/{alertId}/read`

### 12.3 Windows 전달 대기 알림 조회

`GET /api/v1/alerts/pending?limit=20`

`sentAt`이 아직 없는 알림을 오래된 순서로 반환합니다. Flutter Windows 앱은 기본 30초 간격으로 이 API를 조회하고 Windows Runner 네이티브 알림 표시가 성공한 항목만 전달 완료 처리합니다.

### 12.4 Windows 전달 완료 처리

`PATCH /api/v1/alerts/{alertId}/sent`

호출에 성공하면 `sentAt`이 최초 전달 시각으로 기록됩니다. 같은 요청을 다시 보내도 최초 시각을 유지합니다.

## 13. AI 서버 연동 API

아래 API는 앱이 직접 호출하지 않고 Spring Boot가 Python AI 서버를 호출할 때 사용하는 내부 계약입니다.

현재 Python 서버는 외부 유료 모델에 의존하지 않는 `WEIGHTED_SIGNAL_V1` 분석기를 사용합니다. 가격 추세, 보유 손익과 리스크 기준, 뉴스 핵심어, 공시 사건 유형을 점수로 조합하며 각 근거를 응답합니다.

### 13.1 통합 투자 분석 요청

`POST /internal/ai/analyze-investment`

```json
{
  "stockCode": "005930",
  "stockName": "삼성전자",
  "market": "KOSPI",
  "currentPrice": 75200,
  "buyPrice": 70000,
  "profitRate": 7.43,
  "stopLossRate": -5,
  "takeProfitRate": 12,
  "candles": [
    {
      "dateTime": "2026-09-22T00:00:00",
      "closePrice": 75200,
      "volume": 1122334
    }
  ],
  "news": [
    {
      "title": "AI 반도체 수주 증가",
      "summary": "투자 확대"
    }
  ],
  "disclosures": [
    {
      "reportName": "공급계약 체결"
    }
  ]
}
```

응답:

```json
{
  "modelVersion": "WEIGHTED_SIGNAL_V1",
  "recommendationType": "BUY",
  "status": "BUY_WATCH",
  "score": 67,
  "summary": "삼성전자 종합 점수는 67점입니다. 긍정 신호가 우세하지만 추가 확인이 필요합니다.",
  "reasons": [
    {
      "label": "가격 추세",
      "description": "분석 구간 종가는 +7.43% 상승했습니다.",
      "type": "PRICE",
      "score": 11
    }
  ]
}
```

## 14. 모의매매 API

모의매매는 실제 KB 주문 API를 호출하지 않고 `trade_records.execution_mode=PAPER` 원장에만 기록합니다. 초기 자본은 개인 사용자의 `user_capital.available_capital`을 사용하며, 매수와 매도 체결가는 서버가 조회한 실제 현재가만 허용합니다. 모든 Provider가 실패한 `FALLBACK` 시세로는 체결하지 않습니다.

### 14.1 모의매매 현황 조회

`GET /api/v1/paper-trading`

응답은 `summary`, `positions`, `trades`를 포함합니다. `summary`에는 초기 자본, 현금, 포지션 평가액, 총자산, 실현·평가·총손익, 수익률, 완료 매도 횟수, 승률, 최대 단일 손실, 회전율이 포함됩니다. 포지션 현재가를 조회할 수 없을 때는 평균 매수가로 평가하되 Provider를 `FALLBACK`으로 표시합니다.

### 14.2 AI 신호 모의매수

`POST /api/v1/paper-trading/recommendations/{recommendationId}/buy`

```json
{
  "quantity": 10
}
```

현재 사용자에게 저장된 `BUY` 추천만 사용할 수 있습니다. 서버가 실제 현재가를 다시 조회하고 모의 현금 잔액을 검증한 뒤 가상 매수 원장을 저장합니다.

### 14.3 모의 포지션 매도

`POST /api/v1/paper-trading/sell`

```json
{
  "stockCode": "005930",
  "market": "KOSPI",
  "quantity": 4
}
```

현재 모의 보유 수량까지만 매도할 수 있습니다. 평균 원가법으로 매도 수량의 실현손익을 계산하고 원장에 저장합니다.

## 15. 주문 사전검증 API

주문 사전검증은 사용자가 입력한 지정가 주문안을 최신 시세와 KB 계좌 자원에 대조하고 결과를 감사 로그로 저장합니다. 이 단계에는 실제 주문 제출 API가 없으며 응답의 `canSubmit`은 항상 `false`입니다.

### 15.1 주문안 사전검증

`POST /api/v1/orders/precheck`

```json
{
  "stockCode": "005930",
  "stockName": "삼성전자",
  "market": "KOSPI",
  "side": "SELL",
  "limitPrice": 76000,
  "quantity": 4
}
```

검증 항목은 KB 주문 스위치, KB 계좌 연결, 국내주식 지원 시장, 1회 최대 주문금액, 실제 현재가 확인, 지정가 이탈률, 매수 주문가능현금 또는 매도 주문가능수량입니다. 기본 한도는 1회 100만원, 현재가 대비 지정가 이탈률 5%이며 환경 변수로 낮추거나 조정할 수 있습니다.

응답의 `eligible`은 모든 안전 조건 통과 여부이며 `checks`에는 각 조건의 코드, 라벨, 통과 여부, 설명이 포함됩니다. 결과는 `order_prechecks`에 저장되지만 KB 주문 API는 호출하지 않습니다.

### 15.2 최근 사전검증 감사 로그

`GET /api/v1/orders/prechecks?limit=20`

`limit`은 1~100입니다. 최근 검증 결과를 최신순으로 반환하며 계좌번호나 API Key 같은 민감정보는 저장하거나 반환하지 않습니다.

## 16. 다음 구현 순서

Flutter 추천 이력 목록·상세 화면과 보유 종목 수동 재분석 액션까지 연결되었습니다.

Windows 앱 잠금 PIN의 Credential Manager 저장과 기존 `.env` 값 자동 이전까지 연결되었습니다.

Windows 항상 위 미니 위젯과 시스템 트레이 메뉴까지 연결되었습니다.

AI 신호 기반 모의매매와 수익률·승률·최대 손실·회전율 지표까지 연결되었습니다.

주문 가능 금액·수량과 안전 한도를 검사하는 주문 사전검증 및 감사 로그까지 연결되었습니다. 실제 주문 전송은 아직 구현하지 않았습니다.

1. 일회용 확인 토큰과 수동 승인 기반 KB 주문 실행
2. 주문 결과·실패·취소·정정 상태 동기화
3. 배포 패키지 자동 업데이트와 운영 상태 진단
