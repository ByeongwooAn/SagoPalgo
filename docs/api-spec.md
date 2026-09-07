# 사고팔고 API 명세서

이 문서는 Flutter 앱, Spring Boot API 서버, Python AI 서버가 같은 데이터 계약을 보고 개발하기 위한 1차 API 명세입니다.

## 1. 기본 원칙

- API 서버는 Spring Boot가 담당한다.
- 앱은 모든 사용자 데이터 요청을 Spring Boot API로 보낸다.
- Python AI 서버는 Spring Boot 내부 서버 간 호출 대상으로 둔다.
- Android 앱은 JWT access token을 `Authorization: Bearer {token}` 형식으로 전달한다.
- 모든 날짜/시간은 서버 내부에서는 UTC로 저장하고, 앱 표시 시 사용자 로컬 시간대로 변환한다.
- 추천 결과는 점수와 추천 사유를 반드시 함께 내려준다.
- 주문 자동화는 MVP 범위에서 제외하고, 4단계에서 사용자 승인 기반으로 별도 구현한다.

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
    "code": "AUTH_INVALID_TOKEN",
    "message": "인증 토큰이 유효하지 않습니다."
  }
}
```

### 공통 에러 코드

| 코드 | 의미 | HTTP |
| --- | --- | --- |
| `VALIDATION_ERROR` | 요청값 검증 실패 | 400 |
| `AUTH_INVALID_TOKEN` | 소셜 provider token 또는 JWT 누락/만료 | 401 |
| `AUTH_FORBIDDEN` | 접근 권한 없음 | 403 |
| `RESOURCE_NOT_FOUND` | 대상 데이터 없음 | 404 |
| `DUPLICATE_RESOURCE` | 이미 존재하는 데이터 | 409 |
| `AI_SERVER_ERROR` | AI 서버 호출 실패 | 502 |
| `EXTERNAL_DATA_ERROR` | 주가/뉴스/공시 외부 데이터 오류 | 502 |
| `INTERNAL_ERROR` | 서버 내부 오류 | 500 |

## 3. 인증 API

### 3.1 Google 로그인

`POST /api/v1/auth/google`

Flutter 앱은 Google 로그인 SDK에서 받은 ID token을 서버로 전달합니다. 서버는 Google OpenID Connect 공개키로 ID token 서명과 `aud`, `iss`, `exp` 값을 검증하고, Google `sub` 값을 사용자 고유 식별자로 저장합니다.

```json
{
  "providerToken": "google-id-token"
}
```

응답:

```json
{
  "success": true,
  "data": {
    "accessToken": "jwt-access-token",
    "refreshToken": "jwt-refresh-token",
    "expiresIn": 3600,
    "user": {
      "userId": 1,
      "authProvider": "GOOGLE",
      "email": "user@gmail.com",
      "nickname": "Google User",
      "profileImageUrl": "https://example.com/profile.png"
    }
  },
  "message": "Google 로그인이 완료되었습니다."
}
```

### 3.2 Naver 로그인

`POST /api/v1/auth/naver`

Flutter 앱은 Naver 로그인 SDK에서 받은 access token을 서버로 전달합니다. 서버는 Naver 회원 프로필 조회 API를 호출해 access token을 검증하고, 응답의 `response.id` 값을 사용자 고유 식별자로 저장합니다.

```json
{
  "providerToken": "naver-access-token"
}
```

응답:

```json
{
  "success": true,
  "data": {
    "accessToken": "jwt-access-token",
    "refreshToken": "jwt-refresh-token",
    "expiresIn": 3600,
    "user": {
      "userId": 2,
      "authProvider": "NAVER",
      "email": "user@naver.com",
      "nickname": "네이버사용자",
      "profileImageUrl": "https://example.com/naver-profile.png"
    }
  },
  "message": "Naver 로그인이 완료되었습니다."
}
```

### 3.3 토큰 재발급

`POST /api/v1/auth/refresh`

```json
{
  "refreshToken": "jwt-refresh-token"
}
```

응답:

```json
{
  "success": true,
  "data": {
    "accessToken": "new-jwt-access-token",
    "refreshToken": "new-jwt-refresh-token",
    "expiresIn": 3600,
    "user": {
      "userId": 1,
      "authProvider": "GOOGLE",
      "email": "user@example.com",
      "nickname": "투자초보",
      "profileImageUrl": "https://example.com/profile.png"
    }
  },
  "message": "토큰이 재발급되었습니다."
}
```

재발급에 성공하면 기존 refresh token은 폐기되고 새 refresh token이 발급됩니다.

### 3.4 로그아웃

`POST /api/v1/auth/logout`

인증 필요: 예

응답:

```json
{
  "success": true,
  "data": null,
  "message": "로그아웃되었습니다."
}
```

## 4. 대시보드 API

### 4.1 앱 초기 스냅샷 조회

`GET /api/v1/dashboard/snapshot`

인증 필요: 예

이 API는 현재 Flutter의 `InvestmentSnapshot` 모델과 맞춘 통합 응답입니다. MVP에서는 앱 첫 화면을 빠르게 띄우기 위해 여러 화면의 데이터를 한 번에 내려줍니다.

응답:

```json
{
  "success": true,
  "data": {
    "marketSummary": {
      "availableCapital": 3000000,
      "monthlyReturnRate": 3.8,
      "recommendedPositionRange": "30~60만원",
      "marketTrend": "강세",
      "marketScore": 76,
      "newsSentiment": "긍정",
      "positiveNewsCount": 12,
      "marketBars": [0.42, 0.68, 0.54, 0.82, 0.61, 0.94]
    },
    "recommendation": {
      "recommendationId": 101,
      "stockName": "삼성전자",
      "stockCode": "005930",
      "market": "KOSPI",
      "status": "강한 매수",
      "score": 87,
      "entryPrice": 72000,
      "stopLossRate": -5.0,
      "aiSummary": "시장 강세와 거래량 증가가 동시에 나타나 단기 관심 종목으로 분류됩니다.",
      "reasons": [
        {
          "label": "RSI",
          "description": "과매도 구간에서 반등 신호가 확인되었습니다.",
          "type": "TECHNICAL",
          "score": 20
        }
      ]
    },
    "portfolioSummary": {
      "totalProfit": 128400,
      "profitRate": 4.2,
      "maxAllowedLoss": 60000,
      "riskUsageRate": 0.42
    },
    "holdings": [],
    "alerts": []
  },
  "message": "대시보드 데이터가 조회되었습니다."
}
```

## 5. 자본금 API

### 5.1 자본금 조회

`GET /api/v1/capital`

인증 필요: 예

응답:

```json
{
  "success": true,
  "data": {
    "availableCapital": 3000000,
    "recommendedMinPosition": 300000,
    "recommendedMaxPosition": 600000,
    "riskPerTradeRate": 0.02
  },
  "message": "자본금이 조회되었습니다."
}
```

### 5.2 자본금 수정

`PUT /api/v1/capital`

인증 필요: 예

```json
{
  "availableCapital": 3000000,
  "riskPerTradeRate": 0.02
}
```

응답:

```json
{
  "success": true,
  "data": {
    "availableCapital": 3000000,
    "recommendedMinPosition": 300000,
    "recommendedMaxPosition": 600000,
    "riskPerTradeRate": 0.02
  },
  "message": "자본금이 수정되었습니다."
}
```

## 6. 관심 종목 API

### 6.1 관심 종목 목록 조회

`GET /api/v1/watchlist`

인증 필요: 예

응답:

```json
{
  "success": true,
  "data": [
    {
      "watchlistId": 11,
      "stockCode": "005930",
      "stockName": "삼성전자",
      "market": "KOSPI",
      "alertEnabled": true,
      "createdAt": "2026-09-07T00:00:00Z"
    }
  ],
  "message": "관심 종목 목록이 조회되었습니다."
}
```

### 6.2 관심 종목 추가

`POST /api/v1/watchlist`

인증 필요: 예

```json
{
  "stockCode": "005930",
  "stockName": "삼성전자",
  "market": "KOSPI",
  "alertEnabled": true
}
```

응답:

```json
{
  "success": true,
  "data": {
    "watchlistId": 11
  },
  "message": "관심 종목이 추가되었습니다."
}
```

### 6.3 관심 종목 알림 설정 변경

`PATCH /api/v1/watchlist/{watchlistId}/alert`

인증 필요: 예

```json
{
  "alertEnabled": false
}
```

### 6.4 관심 종목 삭제

`DELETE /api/v1/watchlist/{watchlistId}`

인증 필요: 예

## 7. 추천 API

### 7.1 추천 목록 조회

`GET /api/v1/recommendations?status=BUY_STRONG&page=0&size=20`

인증 필요: 예

응답:

```json
{
  "success": true,
  "data": {
    "items": [
      {
        "recommendationId": 101,
        "stockCode": "005930",
        "stockName": "삼성전자",
        "market": "KOSPI",
        "recommendationType": "BUY",
        "status": "BUY_STRONG",
        "statusLabel": "강한 매수",
        "score": 87,
        "createdAt": "2026-09-07T00:00:00Z"
      }
    ],
    "page": 0,
    "size": 20,
    "totalCount": 1
  },
  "message": "추천 목록이 조회되었습니다."
}
```

### 7.2 추천 상세 조회

`GET /api/v1/recommendations/{recommendationId}`

인증 필요: 예

응답:

```json
{
  "success": true,
  "data": {
    "recommendationId": 101,
    "stockCode": "005930",
    "stockName": "삼성전자",
    "market": "KOSPI",
    "recommendationType": "BUY",
    "status": "BUY_STRONG",
    "statusLabel": "강한 매수",
    "score": 87,
    "entryPrice": 72000,
    "stopLossRate": -5.0,
    "takeProfitRate": 9.0,
    "aiSummary": "시장 강세와 거래량 증가가 동시에 나타나 단기 관심 종목으로 분류됩니다.",
    "reasons": [
      {
        "reasonType": "RSI",
        "label": "RSI",
        "description": "과매도 구간에서 반등 신호가 확인되었습니다.",
        "score": 20
      },
      {
        "reasonType": "MACD",
        "label": "MACD",
        "description": "골든크로스 초기 구간으로 추세 전환 가능성이 있습니다.",
        "score": 20
      },
      {
        "reasonType": "NEWS",
        "label": "뉴스",
        "description": "AI 반도체 수주 관련 긍정 감성이 증가했습니다.",
        "score": 15
      }
    ],
    "createdAt": "2026-09-07T00:00:00Z"
  },
  "message": "추천 상세가 조회되었습니다."
}
```

## 8. 보유 종목 API

### 8.1 보유 종목 목록 조회

`GET /api/v1/holdings`

인증 필요: 예

응답:

```json
{
  "success": true,
  "data": {
    "summary": {
      "totalProfit": 128400,
      "profitRate": 4.2,
      "maxAllowedLoss": 60000,
      "riskUsageRate": 0.42
    },
    "items": [
      {
        "holdingId": 21,
        "stockCode": "005930",
        "stockName": "삼성전자",
        "market": "KOSPI",
        "buyPrice": 69100,
        "quantity": 12,
        "currentPrice": 75319,
        "profitRate": 9.0,
        "stopLossRate": -5.0,
        "takeProfitRate": 9.0,
        "status": "PARTIAL_TAKE_PROFIT",
        "statusLabel": "부분 익절"
      }
    ]
  },
  "message": "보유 종목이 조회되었습니다."
}
```

### 8.2 보유 종목 등록

`POST /api/v1/holdings`

인증 필요: 예

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

인증 필요: 예

### 8.4 보유 종목 삭제

`DELETE /api/v1/holdings/{holdingId}`

인증 필요: 예

## 9. 알림 API

### 9.1 FCM 토큰 등록

`POST /api/v1/devices/fcm-token`

인증 필요: 예

```json
{
  "fcmToken": "firebase-token",
  "deviceType": "ANDROID"
}
```

### 9.2 알림 목록 조회

`GET /api/v1/alerts?page=0&size=20`

인증 필요: 예

응답:

```json
{
  "success": true,
  "data": {
    "items": [
      {
        "alertId": 31,
        "title": "삼성전자 매도 검토",
        "body": "현재 수익률 +9%. 목표 수익 도달로 부분 익절을 추천합니다.",
        "alertType": "SELL",
        "read": false,
        "createdAt": "2026-09-07T00:00:00Z"
      }
    ],
    "page": 0,
    "size": 20,
    "totalCount": 1
  },
  "message": "알림 목록이 조회되었습니다."
}
```

### 9.3 알림 읽음 처리

`PATCH /api/v1/alerts/{alertId}/read`

인증 필요: 예

## 10. AI 서버 연동 API

아래 API는 앱이 직접 호출하지 않고 Spring Boot가 Python AI 서버를 호출할 때 사용하는 내부 계약입니다.

### 10.1 종목 분석 요청

`POST /internal/ai/analyze-stock`

```json
{
  "stockCode": "005930",
  "stockName": "삼성전자",
  "market": "KOSPI",
  "analysisPeriod": "ONE_YEAR"
}
```

응답:

```json
{
  "stockCode": "005930",
  "technicalSignals": {
    "rsi": 29.4,
    "rsiSignal": "OVERSOLD_RECOVERY",
    "macdSignal": "GOLDEN_CROSS",
    "volumeRatio": 2.1,
    "movingAverageSignal": "BREAKOUT_5D"
  },
  "marketSignals": {
    "marketTrend": "BULLISH",
    "marketScore": 76
  },
  "score": 72,
  "reasons": [
    {
      "reasonType": "RSI",
      "description": "RSI 과매도 탈출 신호가 있습니다.",
      "score": 20
    }
  ]
}
```

### 10.2 뉴스 감성 분석 요청

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

응답:

```json
{
  "stockCode": "005930",
  "sentiment": "POSITIVE",
  "sentimentScore": 15,
  "summary": "AI 반도체 수주 증가는 반도체 업종 호재로 판단됩니다."
}
```

## 11. 우선 구현 순서

1. `POST /api/v1/auth/google`
2. `POST /api/v1/auth/naver`
3. `POST /api/v1/auth/refresh`
4. `POST /api/v1/auth/logout`
5. `GET /api/v1/dashboard/snapshot`
6. `GET/PUT /api/v1/capital`
7. `GET/POST/DELETE /api/v1/watchlist`
8. `GET /api/v1/recommendations`
9. `GET /api/v1/recommendations/{recommendationId}`
10. `GET/POST/PUT/DELETE /api/v1/holdings`
11. `POST /api/v1/devices/fcm-token`
12. `GET/PATCH /api/v1/alerts`
