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

## 4. 증권사 설정 API

### 4.1 증권사 연동 상태 조회

`GET /api/v1/settings/providers`

민감한 API Key, App Secret, 계좌번호는 응답에 포함하지 않습니다. 이 API는 어떤 증권사를 어떤 역할로 사용할지와 필요한 값이 설정되어 있는지만 보여줍니다.

응답:

```json
{
  "success": true,
  "data": {
    "providers": [
      {
        "code": "KB",
        "displayName": "KB증권",
        "marketDataEnabled": false,
        "accountEnabled": false,
        "orderEnabled": false,
        "configured": false,
        "roleDescription": "계좌 조회와 추후 주문 기능의 기준 증권사"
      },
      {
        "code": "KIS",
        "displayName": "한국투자증권",
        "marketDataEnabled": false,
        "accountEnabled": false,
        "orderEnabled": false,
        "configured": false,
        "roleDescription": "국내 주식 시세 조회용 데이터 소스"
      },
      {
        "code": "TOSS",
        "displayName": "토스증권",
        "marketDataEnabled": false,
        "accountEnabled": false,
        "orderEnabled": false,
        "configured": false,
        "roleDescription": "분석용 시세/종목 정보 보조 데이터 소스"
      }
    ]
  },
  "message": "증권사 연동 설정이 조회되었습니다."
}
```

## 5. 대시보드 API

### 5.1 앱 초기 스냅샷 조회

`GET /api/v1/dashboard/snapshot`

이 API는 현재 Flutter의 `InvestmentSnapshot` 모델과 맞춘 통합 응답입니다. MVP에서는 앱 첫 화면을 빠르게 띄우기 위해 여러 화면의 데이터를 한 번에 내려줍니다.

현재 구현은 `CapitalService`, `HoldingService`, `DashboardRecommendationEngine`을 조합합니다. 보유 종목의 `currentPrice`는 KIS 설정이 켜진 국내 주식이면 한국투자증권 Open API 현재가를 사용합니다. 별도 추천 목록 API가 붙기 전까지 대표 추천은 대시보드 스냅샷 안에서 반환합니다. 실제 보유 종목이 없으면 `recommendation`은 `null`, `alerts`는 빈 배열입니다.

## 6. 자본금 API

### 6.1 자본금 조회

`GET /api/v1/capital`

### 6.2 자본금 수정

`PUT /api/v1/capital`

```json
{
  "availableCapital": 3000000,
  "riskPerTradeRate": 0.02
}
```

## 7. 관심 종목 API

### 7.1 관심 종목 목록 조회

`GET /api/v1/watchlist`

### 7.2 관심 종목 추가

`POST /api/v1/watchlist`

```json
{
  "stockCode": "005930",
  "stockName": "삼성전자",
  "market": "KOSPI",
  "alertEnabled": true
}
```

### 7.3 관심 종목 알림 설정 변경

`PATCH /api/v1/watchlist/{watchlistId}/alert`

```json
{
  "alertEnabled": false
}
```

### 7.4 관심 종목 삭제

`DELETE /api/v1/watchlist/{watchlistId}`

## 8. 보유 종목 API

### 8.1 보유 종목 목록 조회

`GET /api/v1/holdings`

KOSPI/KOSDAQ/KONEX 종목이고 `SAGOPALGO_KIS_ENABLED=true`이면 `currentPrice`와 `profitRate`는 한국투자증권 현재가 기준으로 계산됩니다. KIS 설정이 꺼져 있거나 미지원 시장이면 임의 샘플 가격을 만들지 않고 등록 매수가를 기준값으로 사용합니다. KIS 설정이 켜진 국내 종목 조회 중 토큰 발급 또는 현재가 조회가 실패하면 `EXTERNAL_DATA_ERROR`가 반환됩니다.

### 8.2 보유 종목 등록

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

### 8.3 보유 종목 수정

`PUT /api/v1/holdings/{holdingId}`

### 8.4 보유 종목 삭제

`DELETE /api/v1/holdings/{holdingId}`

## 9. 추천 API

이 절의 추천 목록/상세 API는 다음 구현 단계의 명세입니다. 현재 앱에서 실제로 사용하는 대표 추천은 `GET /api/v1/dashboard/snapshot`의 `recommendation` 필드로 제공됩니다.

### 9.1 추천 목록 조회

`GET /api/v1/recommendations?status=BUY_STRONG&page=0&size=20`

### 9.2 추천 상세 조회

`GET /api/v1/recommendations/{recommendationId}`

## 10. 알림 API

이 절의 알림 API는 다음 구현 단계의 명세입니다. 현재 앱 알림 탭의 데이터는 `GET /api/v1/dashboard/snapshot`의 `alerts` 필드로 제공됩니다.

### 10.1 알림 목록 조회

`GET /api/v1/alerts?page=0&size=20`

### 10.2 알림 읽음 처리

`PATCH /api/v1/alerts/{alertId}/read`

## 11. AI 서버 연동 API

아래 API는 앱이 직접 호출하지 않고 Spring Boot가 Python AI 서버를 호출할 때 사용하는 내부 계약입니다.

현재 구현에서는 Python AI 서버가 아직 붙지 않았으므로 `DashboardRecommendationEngine`이 실제 보유 종목 수익률, 손절 기준, 익절 기준을 조합해 설명 가능한 MVP 추천을 생성합니다. 실제 보유 종목이 없으면 임의 추천을 생성하지 않습니다.

### 11.1 종목 분석 요청

`POST /internal/ai/analyze-stock`

```json
{
  "stockCode": "005930",
  "stockName": "삼성전자",
  "market": "KOSPI",
  "analysisPeriod": "ONE_YEAR"
}
```

### 11.2 뉴스 감성 분석 요청

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

## 12. 다음 구현 순서

1. `GET /api/v1/settings/providers`
2. KB증권 계좌 조회 연동 설정과 응답 모델
3. KIS 국내/해외 시세 조회 확장
4. Toss 분석용 시세/종목 정보 연동
5. AI 분석 서버와 추천 결과 저장
6. Windows 로컬 알림
7. 자동 주문 설계와 수동 승인 기반 주문 실행
