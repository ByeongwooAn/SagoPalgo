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

`weightRate`는 응답에 평가금액이 있을 때 조회된 보유주식 평가금액 합계를 분모로 서버가 계산한 값입니다. 현금과 계좌 순자산은 포함하지 않습니다. 평가합계가 0이면 앱은 비중을 산정 불가로 표시합니다.

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

상세 항목의 `valuationWeightRate`는 KB `val_sgrvt_p2` 응답값이며 필드가 없으면 `null`로 둡니다. Flutter 설정의 `계좌 잔고 상세`에서는 이 결제기준 잔고 항목을 우선 표시하고, `보유 주식` 모드와 출처를 구분합니다. 값이 없으면 0%로 추정하지 않습니다. 실계좌 앱과의 대조가 끝나기 전에는 이 값을 AI 매수 판단이나 실주문 안전 조건에 사용하지 않습니다.

요약의 `totalDataCount`는 KB `tl_data_cnt` 원문을 보존합니다. Flutter는 이를 0 이상의 정수로 해석할 수 있을 때만 현재 응답에서 표시된 잔고 항목 수와 비교합니다. 다르면 `건수 확인 필요`, 해석할 수 없으면 `KB 보고 건수 미제공`으로 표시합니다. 숫자가 같아도 페이지 누락이 없거나 실계좌 잔고와 일치한다고 보증하지 않습니다. 이 진단은 읽기 전용이며 자동 페이지 조회나 AI·주문 판단을 추가하지 않습니다.

### 5.4 KB 잔고 현황 조회(체결기준)

`GET /api/v1/kb/accounts/primary/balances/execution`

KB Open API `SSQM2952_잔고현황조회(체결기준)`을 호출합니다. 백엔드는 공식 문서 기준 path `/api/v1/ssqm2952`와 기본 입력값 `excg_mktpr_ccd=A`를 사용합니다.

요약 응답에는 순자산평가금액, 유가순평가금액, 매입금액합계, 평가금액합계, 평가손익합계, 평가수익률합계 등을 정규화합니다. `Record1` 상세는 보유수량, 주문가능수량, 미결제매도수량, 미결제매수수량, 정산수량, 현재가, 매입평균가, 평가금액, 평가손익, 평가수익률 등을 포함합니다.

### 5.5 읽기 전용 KB 계좌 관찰

`GET /api/v1/kb/accounts/primary/snapshot?orderDate=YYYYMMDD`

보유·결제기준 잔고·체결기준 잔고·지정일 주문을 구간별로 관찰합니다. 공식 숫자 필드를 십진 문자열로 보존하고 `status/completeness/issues`, 서버 수신 구간·조회 범위를 반환합니다. 빈 결과와 누락/잘림·부분 실패를 구분하며 `atomic=false`, `usableForTrading=false`입니다. 기존 화면용 계좌 API와 별도이고 자동 동기화·저장·주문/가드 변경은 없습니다.

`orderDate` 생략 시 한국 날짜이며 잘못된 날짜는 외부 조회 전 400입니다. 관찰 응답의 HTTP 200/공통 `success=true`만으로 각 구간의 성공을 판단하지 않습니다. 응답은 `Cache-Control: no-store`입니다. 상세 필드·페이지 상한·정밀도·검증 범위는 [계좌 관찰 계약](account-snapshot-contract.md)을 따릅니다.

### 5.6 계좌 관찰 저장·이력

- POST `/api/v1/kb/accounts/primary/observations`: `{requestId: UUID, orderDate: YYYYMMDD}`로 서버 관찰과 저장을 명시적으로 요청합니다. 두 필드는 필수이며 같은 사용자/ID는 한 번만 관찰합니다.
- GET `/api/v1/kb/accounts/primary/observations?limit=20&beforeId=...`: 현재 사용자·연결의 최근 요약과 `nextBeforeId`를 반환합니다. limit 1~100, keyset 내림차순입니다.
- GET `/api/v1/kb/accounts/primary/observations/{requestId}`: 저장 상태와 완료된 관찰을 조회하며 KB를 재호출하지 않습니다.

`storageState=PENDING/COMPLETED/FAILED`와 관찰의 `snapshotStatus`를 구분합니다. 동일 ID의 대기/완료/실패는 기존 결과를 반환하고, 다른 날짜/계좌 연결 재사용은 409입니다. 다른 사용자/연결의 상세는 404, 저장소/무결성 오류는 503 `OBSERVATION_STORAGE_UNAVAILABLE`입니다. 정상 응답은 no-store·`readOnly=true`이고 관찰 본문은 계속 `atomic=false`, `usableForTrading=false`입니다. 기존 `/snapshot`은 자동 저장하지 않습니다. 023 적용·상태/복구·정밀도·검증 범위는 [계좌 관찰 이력 계약](account-observation-history.md)을 따릅니다.

### 5.7 저장된 계좌 관찰 비교

`GET /api/v1/kb/accounts/primary/observations/comparison?beforeRequestId=<UUID>&afterRequestId=<UUID>`

서로 다른 두 요청 ID는 필수입니다. 같은 사용자·현재 연결의 저장 이력만 읽으며 KB 재조회나 DB 쓰기를 실행하지 않습니다. 구간별 동일 범위·성공/완전성·문제 코드·식별자·수신 순서를 검사한 뒤 지원 필드의 변화와 정확한 십진 변화량을 반환합니다. 불완전한 구간은 차단 사유와 빈 차이 목록을 반환합니다. 전체 `status=COMPARED/PARTIAL/BLOCKED`를 확인해야 하며 정상 응답은 no-store·`readOnly=true`·`usableForTrading=false`입니다.

필드/행의 누락을 0·매수·매도·주문 종결로 판단하지 않습니다. 입력 오류는 400, 없는 사용자/연결 기록은 404, 연결 변경은 409, 저장 무결성 오류는 503입니다. 응답·매칭 식별자·차단 사유는 [관찰 비교 계약](account-observation-comparison.md)을 따릅니다. 기존 023 테이블을 사용하며 추가 마이그레이션은 없습니다.

Flutter 보유/설정 탭에서 사용하는 [저장·이력·상세·비교 화면과 요청 복구](account-observation-ui.md)를 연결했습니다. 앱의 복구 요청은 같은 ID의 GET이며 POST를 자동 재전송하지 않습니다.

### 5.8 계좌 관찰 자동 수집 상태·재개

Flutter의 [자동 수집 상태/재개 패널](account-observation-ui.md#6-자동-수집-상태와-재개)에서 아래 API를 사용합니다. 화면 진입·재조회는 GET이며 재개 POST를 자동 반복하지 않습니다.

- GET `/api/v1/kb/accounts/primary/observations/collection`: 현재 로컬 사용자·연결의 수집 설정과 `NOT_STARTED/IDLE/ACTIVE/PAUSED/UNCONFIGURED`, 실행/직전 요청·종료 상태·고정 사유·DB UTC 시각을 읽습니다. 상태 조회는 예약·KB 조회를 실행하지 않습니다.
- POST `/api/v1/kb/accounts/primary/observations/collection/resume`: `{lastRequestId: UUID}`로 현재 PAUSED의 저장된 종료 결과를 확인하고 IDLE로 바꿉니다. 즉시 KB 조회나 설정 ON은 하지 않고 현재 시각+간격 이후 새 주기를 허용합니다. ACTIVE/PENDING은 해제하지 않습니다.

정상 응답은 no-store·증권사 `readOnly=true`·`usableForTrading=false`입니다. 수집 기본 OFF·기본 간격 900초, DB 실행 소유권·불명확 결과 보존과 024 적용 조건은 [자동 수집 계약](account-observation-collection.md)을 따릅니다. 수집 저장소 오류는 503 `OBSERVATION_COLLECTION_STORAGE_UNAVAILABLE`, 잘못된 입력은 400, 상태/연결 충돌은 409입니다.

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

#### 6.0.3 실시간 시세와 연구 변경 조회

`GET /api/v1/market/realtime?stockCode=005930`, `GET /api/v1/market/realtime/events?stockCode=005930`(SSE), `GET /api/v1/research/changes?stockCode=005930&afterId=0&limit=100`은 [실시간 데이터 수집 계약](realtime-data-pipeline.md)을 따릅니다. KIS 공개 KRX 시세와 저장된 연구 버전이며 계좌 관찰/주문 상태와 분리합니다. 신규 기능은 기본 OFF이고 025/026 적용·배포·권한/예산 확인 후 사용합니다. 스냅샷은 항상 usableForTrading=false이며, 분봉은 OBSERVED_ONLY입니다.

#### 6.0.4 연구 데이터셋용 저장 자료 내보내기

`GET /api/v1/research/dataset-export?stockCode=005930&from=2025-11-03T00:00:00Z&to=2025-11-03T00:02:00Z`는 [내보내기 계약](stored-dataset-export.md)을 따릅니다. no-store·읽기 전용 REPEATABLE_READ이며 외부 Provider/계좌/주문을 호출하지 않습니다. 025/026 필요, 종목별 분 단위 최대 24시간·각 종류 10,000행·원문 합계 32MiB 상한입니다. 시세는 시장 시각 구간, 연구 버전은 to 이전의 전체 관측 이력을 반환하고 상한 초과를 부분 성공으로 바꾸지 않습니다.

후속 `GET /api/v1/research/dataset-export/availability`는 같은 쿼리/상한/읽기 전용 계약의 `SAGOPALGO_STORED_EXPORT_V2`입니다. 027 테이블의 선택적 `availability`(해시·clockDomain·커밋/로컬 공개 관측 시각·단조 경과량·품질)를 연결합니다. 기록 없음은 null, `utcSynchronized=false`이며 실제 외부 전략 수신을 의미하지 않습니다. 기존 V1 응답은 유지합니다. [전체 계약·운영 확인](committed-input-availability.md)을 따릅니다.

`GET /api/v1/research/input-delivery?requestId=<요청별 UUID>&stockCode=005930&from=<UTC>&to=<UTC>`는 V2와 같은 읽기 전용/구간/상한 계약의 `SAGOPALGO_INPUT_DELIVERY_V1`입니다. 요청·새 deliveryId·JVM 도메인·수신/발행 단조 시각·V2 원문 JSON 문자열/UTF-8 SHA-256을 반환합니다. no-store, utcSynchronized=false이며 계좌·Provider·모델·주문을 호출하지 않습니다. [Python 수신·오차 범위·차단과 실제 검증](strategy-input-receipts.md)을 따릅니다.

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

보유 종목 분석은 최근 일봉, 저장 뉴스·공시와 보유 손익·손절·익절 기준을 Python 분석 서버에 전달합니다. 관심 종목 분석은 보유 가격·손익률을 만들어 넣지 않고 실제 현재가와 가격·뉴스·공시만 전달합니다. 분석 결과는 추천 본문, 점수 근거, 요청·응답 원문 스냅샷으로 나누어 저장합니다. Python 서버가 비활성 또는 일시 실패 상태이면 보유 종목은 기존 규칙 엔진, 관심 종목은 판단 보류의 중립 결과를 저장합니다.

### 11.1 보유 종목 분석 및 추천 저장

`POST /api/v1/recommendations/analyze/{holdingId}`

응답의 `status`는 `BUY_STRONG`, `BUY_WATCH`, `HOLD`, `TAKE_PROFIT`, `STOP_LOSS_WATCH`, `RISK` 중 하나이며 `statusLabel`은 Flutter에 표시할 한글 상태입니다.

### 11.2 추천 목록 조회

`GET /api/v1/recommendations?status=BUY_STRONG&page=0&size=20`

`status`는 선택값이고 `page`는 0 이상, `size`는 1~100입니다. 목록 응답은 `items`, `page`, `size`, `total`을 포함합니다.

### 11.3 추천 상세 조회

`GET /api/v1/recommendations/{recommendationId}`

상세 응답에는 추천 점수에 반영된 `reasons`가 포함됩니다.

### 11.4 관심 종목 직접 분석

`POST /api/v1/recommendations/analyze/watchlist/{watchlistId}`

서버는 요청 사용자의 관심 종목 ID를 확인하고, KB/KIS/Toss 우선순위로 실제 현재가를 조회합니다. `FALLBACK` 또는 0원 시세에서는 분석을 거절합니다. Python 요청의 `analysisType=WATCHLIST`에서는 `buyPrice`, `profitRate`, `stopLossRate`, `takeProfitRate`가 `null`이며, 비보유 종목에 손절·익절 판정을 적용하지 않습니다. 응답과 추천 이력의 `analysisContext=WATCHLIST`는 보유 종목의 `HOLDING`과 구분됩니다. 관심 종목의 `RISK`는 매도가 아니라 신규 진입 보류(`recommendationType=HOLD`)입니다. AI 서버가 비보유 종목에 `SELL` 또는 손절·익절 상태를 돌려주면 해당 결과를 사용하지 않고 중립 fallback으로 저장합니다. 관심 종목 분석은 종목의 알림 설정과 신호 조건에 따라 알림을 만들며, 현재 등록 상태에 맞으면 홈 대표 분석에도 포함됩니다. 보유/관심 분석 유형은 구분해서 표시합니다. 실제 주문은 전송하지 않습니다.

기존 MySQL에는 AI 서버를 함께 배포한 뒤 `Back/database/migrations/013_watchlist_recommendation_context.sql`을 적용합니다. 기존 추천은 `HOLDING`으로 보존됩니다. 새 볼륨은 `schema.sql`에 포함됩니다.

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

`GET /api/v1/alerts/pending?limit=20&afterAlertId=123`

`sentAt`이 아직 없는 알림을 `alertId` 오름차순으로 반환합니다. `afterAlertId`는 선택적인 배타적 커서이며 생략하면 처음부터 조회합니다. `limit`는 1~50으로 제한되고 음수 커서는 거절합니다. Flutter Windows 앱은 기본 30초 간격으로 최대 5페이지씩 조회하고, 한 건이 실패해도 다음 건을 시도합니다. 5페이지를 모두 사용하면 다음 주기에서 이어받고, 끝에 도달하면 처음으로 돌아가 실패 건을 재시도합니다. Windows 표시 성공 후 서버 완료 기록만 실패하면 앱 실행 중에는 다시 표시하지 않고 기록만 재시도합니다. 앱 종료·재시작 사이에 표시 성공과 기록 실패가 겹치면 중복 표시될 수 있으므로 정확히 한 번 전달을 보장하지 않습니다.

### 12.4 Windows 전달 완료 처리

`PATCH /api/v1/alerts/{alertId}/sent`

호출에 성공하면 `sentAt`이 최초 전달 시각으로 기록됩니다. 같은 요청을 다시 보내도 최초 시각을 유지합니다.

## 13. AI 서버 연동 API

아래 API는 앱이 직접 호출하지 않고 Spring Boot가 Python AI 서버를 호출할 때 사용하는 내부 계약입니다.

현재 Python 서버는 외부 유료 모델에 의존하지 않는 `WEIGHTED_SIGNAL_V1` 분석기를 사용합니다. 가격 추세, 보유 손익과 리스크 기준, 뉴스 핵심어, 공시 사건 유형 및 선택적 매입 원금 비중을 점수로 조합하며 각 근거를 응답합니다.

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

보유 종목 요청에는 선택적으로 `portfolioWeightRate`(등록된 활성 보유 종목 전체 매입 원금 중 동일 종목 비중), `capitalWeightRate`(설정된 투자 가능 자본금 대비 동일 종목 매입 원금 비중), `maxCapitalWeightRate`(설정된 종목당 권장 한도의 자본금 비중)를 보냅니다. 같은 시장·종목코드의 여러 보유 건은 합산합니다. 설정 자본금이 없으면 뒤의 두 필드는 `null`이며 한도 초과 판정도 생략합니다. 이 값은 KB 실계좌의 실시간 평가 비중이 아닙니다. 권장 한도를 초과하면 손절·익절 기준 판정은 유지하면서 신규 `BUY` 신호만 `HOLD/RISK`로 보류합니다. `WATCHLIST` 요청에는 이 비중을 적용하지 않습니다. 세 필드가 없는 이전 요청은 기존 점수 동작을 유지합니다.

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

### 15.3 수동 승인 준비 및 기록 (실주문 미전송)

`POST /api/v1/orders/approvals/prepare`는 15.1과 같은 지정가 주문안을 받아 안전 조건을 **다시** 검사합니다. KOSPI/KOSDAQ 6자리 종목코드, 9자리 이하 정수 원화 지정가, 10자리 이하 정수 주식 수량만 허용합니다. 모든 검사가 통과하면 새 사전검증 ID와 90초짜리 일회용 토큰을 반환합니다. 토큰 원문은 서버 DB에 저장하지 않고 SHA-256 해시만 `order_approvals`에 보존합니다. KB 계좌번호·상품코드·App Key·엔드포인트를 App Secret으로 HMAC 처리한 계좌 지문도 함께 저장하며, 계좌번호와 인증값 원문은 기록하지 않습니다.

사용자가 새 검증 결과와 “실제 주문 미전송” 안내를 확인한 뒤 `POST /api/v1/orders/approvals/confirm`에 `approvalId`, `token`, `acknowledged: true`를 보냅니다. 서버는 사용자·토큰·만료·미사용 상태와 준비 당시 계좌 지문을 원자적으로 검사하고 `ACKNOWLEDGED`로 기록합니다. 재사용하거나 만료된 토큰, 그사이 계좌 설정이 변경된 토큰은 거절합니다. 응답의 `orderSubmitted`는 항상 `false`이며 KB 주문 API를 호출하지 않습니다.

이 단계는 실제 거래 승인/체결이 아닙니다. 기존 DB에는 `Back/database/migrations/007_order_approvals.sql`을 적용해야 합니다.

### 15.4 KB 공식 지정가 주문 계약

[매수주문 `SSAM1802`](https://openapi.kbsec.com/apidoc_b2c#O_5e895db9-9f4c-4c98-aeb1-efc9c57df6f8#G_domestic#A_b5c9ce31-f3f8-4f9c-a4cd-987ce047c39f)과 [매도주문 `SSAM1801`](https://openapi.kbsec.com/apidoc_b2c#O_5e895db9-9f4c-4c98-aeb1-efc9c57df6f8#G_domestic#A_402bb495-8f3d-4de5-99e4-161d378a4f55)의 공식 요청 필드를 확인했습니다. 둘 다 `POST /api/v1/ssam1802` 또는 `/api/v1/ssam1801`에 `dataBody`의 `mkt_tm_clsf=1`(정규장), `is_cd`(종목코드), `ordr_q`(수량), `ordr_uprc`(단가), `ordr_ccd=00`(지정가), `sor_ordr_ccd=K`(KRX)를 사용합니다. 현재 계약 코드는 이 본문을 생성하고 길이·정수 조건을 검증하지만 네트워크 요청은 보내지 않습니다.

응답은 `dataHeader.resultCode=200` **만으로 성공 처리하지 않습니다**. `processFlag=A`와 0이 아닌 `dataBody.ordr_no`가 함께 있을 때만 접수로 분류합니다. 공식 매도 실패 샘플은 `resultCode=200`, `processFlag=B`, `ordr_no=0000000000`입니다. 명시적 실패는 거절, 서로 모순되거나 누락된 필드는 확인 필요(`UNKNOWN`)로 분류하고 자동 재시도하지 않는 것이 다음 구현의 원칙입니다. 이 분류는 체결 완료를 의미하지 않습니다.

[체결미체결 조회 `SSQM2341`](https://openapi.kbsec.com/apidoc_b2c#O_5e895db9-9f4c-4c98-aeb1-efc9c57df6f8#G_domestic#A_66998ea3-85f3-4060-bf6d-f88a163eee35)는 `ccls_clsf`, `ordr_dt`, 선택적 `nxt_key`로 조회하고 `Record1`에 주문번호, 체결·미체결 수량을 반환합니다. 실주문 연결 전에는 운영용 `ipAddr`·`macAddr` 헤더, 응답 불명확 시 이력 대조, 서버 측 중복 제출 차단과 실제 계좌의 수동 검증을 마쳐야 합니다.

수동 전송 연결과 정정/취소·감사·체결 조회 API, 016 배포 절차는 [KB 수동 주문 문서](kb-manual-orders.md)에 정리했습니다. 계약 클래스 자체는 순수 인코딩/분류이고 실제 HTTP 호출은 별도 단일 전송 메서드에서 실행합니다.

후속 017은 `POST /api/v1/orders/manual/{id}/reconciliation/prepare`와 `/confirm`을 추가합니다. UNKNOWN 신규 주문의 전량 체결을 사용자가 확정한 경우에만 해당 신규 제출 차단을 해소합니다. 원래 상태와 가드는 보존하고 GET 수동 주문 응답의 `reconciliation`에 대조 번호·시각·수량·확정 시각을 반환합니다. 이 두 API는 KB 읽기 전용 조회만 수행하며 주문을 전송하지 않습니다. 만료·동시 확인·주문번호 재사용·정정/취소/SENDING 차단 및 마이그레이션은 위 문서에 정리했습니다.

### 15.5 KB 체결미체결 읽기 전용 조회

`GET /api/v1/orders/kb/executions?orderDate=yyyyMMdd&classification=0&nextKey=...`

KB `SSQM2341`을 호출합니다. `orderDate`를 생략하면 한국 시간의 오늘이며, `classification`은 `0` 전체, `1` 체결, `2` 미체결입니다. 응답은 `items`, `nextKey`, 원본 `continuationFlag`를 반환합니다. 다음키는 불투명 값이므로 받은 문자열을 그대로 다음 요청에 전달합니다. 계좌명과 계좌번호는 반환하지 않습니다.

`GET /api/v1/orders/kb/executions/{orderNo}?orderDate=yyyyMMdd`

주문번호 10자리와 일자를 지정해 최대 10페이지를 읽기 전용으로 대조합니다. `matches`는 해당 주문번호의 **원본 조회 행들**이며 여러 행을 하나의 체결 상태로 임의 합산하지 않습니다. `completeScan=false`이면 페이지 제한, 반복된 다음키 또는 해석되지 않은 연속구분 때문에 전체 조회가 완료되지 않은 상태입니다. `matches=[]`만으로 주문 부재나 미접수를 단정하지 말고 `completeScan`을 함께 확인해야 합니다.

항목의 `status`는 주문·체결·미체결 수량이 일치할 때만 `OPEN`, `PARTIAL`, `FILLED`로 표시합니다. 거절 사유가 있거나 수량이 맞지 않으면 `UNKNOWN`으로 남기며 취소·정정 상태는 추정하지 않습니다. 이 API는 주문을 제출하거나 재시도하지 않습니다. [개발 진척도](development-progress.md)에 남은 안전 작업을 기록합니다.

### 15.6 승인별 단일 제출 가드

`POST /api/v1/orders/approvals/confirm`은 일회용 승인 토큰을 소비할 때 같은 DB 트랜잭션으로 `order_submission_guards`에 승인 ID당 하나의 `READY` 행을 생성합니다. 가드 생성에 실패하면 승인 확인도 롤백합니다. 기존 DB에는 `008_order_submission_guards.sql`을 적용해야 합니다.

`GET /api/v1/orders/approvals/{approvalId}/submission`은 개인 사용자의 승인 건에 대한 가드 상태(`READY`, `EXPIRED`, `ACCOUNT_CHANGED`, `RESERVED`, `UNCERTAIN`, `LEGACY_REVIEW`)와 만료·예약·불명확 시각을 반환합니다. 기존 DB의 이미 확인된 승인은 마이그레이션에서 예약할 수 없는 `LEGACY_REVIEW`로 이관합니다. 내부 서비스의 원자적 `READY -> RESERVED` 전환은 성공을 한 번만 허용합니다. 응답이 불명확하면 `RESERVED -> UNCERTAIN`으로 기록할 수 있지만 어느 상태에서도 자동 재전송하지 않습니다. 현재는 주문 전송 어댑터가 연결되지 않았으므로 승인 확인만으로 `RESERVED`가 되거나 KB 주문이 전송되지 않습니다. `UNCERTAIN`은 실주문 성공/실패를 뜻하지 않으며 별도 수동 대조가 필요합니다.

`011_order_submission_expiry.sql`부터 새 가드의 `expiresAt`은 승인 확인 시각 + 90초로 저장됩니다. `READY -> RESERVED` DB 갱신은 `expires_at > now` 조건에서만 성공합니다. 기존 DB의 기한 없는 `READY`는 백엔드를 중지하고 `011`을 적용할 때 `LEGACY_REVIEW`로 전환합니다. 기한이 지난 DB `READY` 행은 상태 조회에서 `EXPIRED`로 표시되지만, 가드 행이나 승인 기록을 삭제하지 않습니다. `EXPIRED`와 `LEGACY_REVIEW`는 재사용할 수 없으며 새 사전검증과 승인 준비가 필요합니다.

`012_order_approval_account_binding.sql`부터 계좌 지문이 승인 준비 시 저장되고, 확인 및 내부 예약의 DB 갱신 조건에서 현재 지문과 대조됩니다. 기존 승인에는 지문을 소급 생성하지 않으며, 지문 없는 `READY`는 `LEGACY_REVIEW`로 이관합니다. 유효 기한 안에 계좌·상품코드·인증값·엔드포인트가 달라지면 조회 상태는 `ACCOUNT_CHANGED`이고 예약은 실패합니다. 새 사전검증과 승인을 진행해야 합니다. 이 상태도 주문 전송 여부를 뜻하지 않습니다.

### 15.7 불명확한 주문의 수동 대조 기록

`POST /api/v1/orders/approvals/{approvalId}/reconciliation-checks`

본문은 `{ "orderDate": "yyyyMMdd", "orderNo": "숫자 10자리" }`입니다. 서버는 승인 가드가 `RESERVED` 또는 `UNCERTAIN`인지 확인하고, 승인 당시 주문안을 가져온 뒤 KB `SSQM2341`을 읽기 전용으로 조회합니다. 주문번호를 이미 알고 있을 때만 사용할 수 있습니다. 응답에는 승인 당시 종목코드·매수/매도·지정가·수량과 KB 조회의 원본 일치 행, 전체 페이지 확인 여부, 조회 요약 상태를 함께 반환합니다. `INCOMPLETE_SCAN`, `NO_MATCH_IN_SCAN`, `MATCHES_REQUIRE_REVIEW`는 **검토 분류**이며 주문 접수·거절·체결 판정이 아닙니다. 종목·수량·가격이 같아 보여도 계좌·주문 방향 등을 자동으로 동일 주문이라고 단정하지 않습니다.

조회 요약은 `order_reconciliation_checks`에 추가 기록하고, `GET /api/v1/orders/approvals/{approvalId}/reconciliation-checks`에서 최근 20건을 조회합니다. 원본 KB 행은 이 테이블에 저장하지 않습니다. 대조 호출은 가드 상태를 변경하거나 주문을 재전송하지 않습니다. 기존 DB에는 `009_order_reconciliation_checks.sql`이 필요합니다. 주문번호가 없는 응답 불명확 사례는 다음 절의 날짜별 조회와 KB 앱·증권사 확인을 함께 사용합니다.

### 15.8 주문번호가 없는 날짜별 수동 대조

`POST /api/v1/orders/approvals/{approvalId}/date-reconciliation-checks`

본문은 `{ "orderDate": "yyyyMMdd" }`입니다. 승인 가드가 `RESERVED` 또는 `UNCERTAIN`일 때 KB `SSQM2341`의 해당 날짜 전체 구분을 최대 10페이지·200행까지 읽고, 승인 당시 종목코드·매수/매도·지정가·수량과 조회 행을 나란히 반환합니다. `completeScan=false`는 페이지 제한, 행 수 제한, 반복된 다음키 또는 해석되지 않은 연속구분을 뜻할 수 있습니다. `itemLimitReached`를 별도로 반환합니다. 종목과 수량이 일치해 보여도 동일 주문으로 자동 판정하지 않으며, 결과가 비어 있어도 주문 미접수나 안전한 재전송을 뜻하지 않습니다.

조회 날짜·행 수·페이지 수·완료 여부만 `order_date_reconciliation_checks`에 기록합니다. `GET /api/v1/orders/approvals/{approvalId}/date-reconciliation-checks`는 최근 20건의 요약을 반환합니다. 원본 KB 행은 저장하지 않습니다. 이 API는 가드 상태를 변경하거나 주문을 전송하지 않습니다. 기존 DB에는 `010_order_date_reconciliation_checks.sql`이 필요합니다. 주문번호 확인과 최종 판단은 KB 앱·증권사 대조를 포함한 수동 절차로 남습니다.

### 15.9 실주문 준비 상태 조회

`GET /api/v1/orders/readiness`는 KB 계좌·사전검증·별도 실주문 스위치, API 키, 계좌번호, HTTPS 엔드포인트, 운영 주문 IP/MAC 형식 및 전송 어댑터 연결 여부를 `checks`로 반환합니다. IP/MAC과 비밀값 원문은 반환하지 않습니다. `SAGOPALGO_KB_LIVE_ORDER_ENABLED`는 기본 `false`이며 `SAGOPALGO_KB_ORDER_IP_ADDRESS`와 `SAGOPALGO_KB_ORDER_MAC_ADDRESS`는 기본 빈 값입니다. 형식 통과는 KB의 운영 승인이나 해당 서버가 실제 주문 발신지라는 증명이 아닙니다. [KB 개발 가이드](https://openapi.kbsec.com/guide_b2c)의 주문 요청 예시에는 `ipAddr`·`macAddr`가 있지만, 실제 사용 값은 계좌·운영 환경에서 검증해야 합니다.

D 묶음에서 전송 어댑터를 연결했습니다. `SUBMISSION_TRANSPORT`는 016·017·019의 여섯 주문 테이블 접근 여부를 확인합니다. 별도로 `OFFICIAL_ORDER_ENDPOINT`와 `ORDER_TOKEN_ENDPOINT`를 검사하며 전체 설정 통과 시에만 `canSubmit=true`입니다. 이 값은 설정 충족이며 주문 권한·실계좌 운영 검증 완료를 뜻하지 않습니다. 기본 실주문 스위치는 계속 OFF이고 기존 계좌 조회 요청의 헤더는 바꾸지 않습니다.

`POST /api/v1/orders/readiness/probe`는 사용자가 Flutter 설정 화면의 "조회 권한 점검"을 누를 때만 실행합니다. 서버는 오늘(한국 시간)의 KB `SSQM2341` 전체 구분 첫 페이지를 **읽기 전용으로 한 번** 조회합니다. 계좌 조회 스위치·인증값·계좌번호·HTTPS 설정이 빠졌다면 KB를 호출하지 않고 `CONFIGURATION_BLOCKED`를 반환합니다. 조회 응답 형식까지 확인되면 `VERIFIED`, 권한·네트워크·응답 오류가 있으면 `UNVERIFIED`입니다. 응답은 `status`, `orderDate`, `checkedAt`, `readOnly=true`, 일반 안내 문구만 포함하며 주문 행·계좌번호·인증값·원본 오류는 포함하지 않습니다. `VERIFIED`는 이 조회 API의 응답 확인일 뿐 주문 제출 권한, 운영 IP/MAC 승인, 실주문 가능 상태를 증명하지 않습니다. 이 진단은 가드나 승인 상태를 변경하지 않습니다.

수동 점검 결과는 로컬 사용자별 `order_read_only_probe_checks`에 `status`, `orderDate`, `checkedAt`만 저장합니다. 기존 DB에는 `Back/database/migrations/014_order_read_only_probe_checks.sql` 적용이 필요합니다. `GET /api/v1/orders/readiness/probe/latest`는 새 KB 호출 없이 해당 사용자의 마지막 결과를 같은 안전한 형식으로 반환하며, 기록이 없으면 `data=null`입니다. Flutter 설정 화면의 마지막 점검 표시는 과거 이력일 뿐 현재 조회 권한이나 주문 가능 상태를 보증하지 않습니다.

`GET /api/v1/orders/readiness/probe/history`는 요청자의 최근 수동 점검 결과를 `checkedAt` 최신순(동시각에는 생성 순서 역순)으로 최대 10건 반환합니다. 기록이 없으면 `data=[]`입니다. 요청 파라미터로 사용자나 건수를 바꿀 수 없으며, 이 조회는 KB API를 호출하거나 주문 준비 상태를 변경하지 않습니다. Flutter에서는 사용자가 `최근 점검 이력`을 펼칠 때만 요청합니다.

수동 점검은 먼저 점검 기록 테이블 접근을 확인합니다. 접근할 수 없으면 KB를 호출하지 않고 `503 PROBE_STORAGE_UNAVAILABLE`을 반환합니다. 마지막 결과·최근 이력 조회나 결과 저장 중 DB 접근이 실패해도 같은 안전한 코드와 일반 안내만 반환합니다. 원인 예외는 서버 로그에만 남기며, 오류 응답에는 SQL·계좌번호·인증값을 넣지 않습니다. 이 코드는 `014` 미적용과 DB 연결 장애를 구분하지 않으므로 서버 로그와 배포 상태를 확인해야 합니다.

## 16. KB 계좌 스냅샷을 앱에 반영

기존 계좌 GET API는 앱 자본금·보유 종목을 변경하지 않습니다. 별도의 명시적 미리보기·적용으로만 반영합니다. 기존 DB는 `015_kb_portfolio_import.sql` 적용 후 새 백엔드를 배포해야 합니다.

### 16.1 반영 미리보기

`GET /api/v1/kb/portfolio-import/preview`

- KB 보유 종목과 결제기준 주문가능 현금(`ordr_psbl_csh`)을 다시 조회합니다.
- `previewToken`, `expiresAt`(5분), `checkedAt`, `currentCapital`, `orderAvailableCash`, `items`, `retainedImportedCount`를 반환합니다.
- `items`는 `stockCode`, `stockName`, `market`, `quantity`, `averageBuyPrice`, `action`, `message`를 갖습니다. `action`은 `CREATE`, `UPDATE`, `SKIP`(수동 등록분 보존), `INVALID`입니다.
- 주문가능 현금이 미제공·잘못된 값·음수이면 `null`이며 0원과 구분합니다. 자본금 기준은 예수금이나 순자산이 아닙니다.
- KB가 상장 시장을 제공하지 않으면 `KRX` 상태를 유지하며 적용 시 실제 KOSPI/KOSDAQ/KONEX 선택을 요구합니다. 매수일은 만들지 않습니다.
- 연결 지문 원문·API Key·계좌번호는 응답에 포함하지 않습니다. 이 조회는 앱 데이터를 저장하지 않습니다.

### 16.2 선택 반영

`POST /api/v1/kb/portfolio-import`

```json
{
  "previewToken": "GET 응답의 확인 토큰",
  "expiresAt": "GET 응답의 만료 시각",
  "importCapital": false,
  "importHoldings": true,
  "markets": {"005930": "KOSPI"},
  "stopLossRate": -5,
  "takeProfitRate": 9
}
```

- 사용자별 잠금·트랜잭션 안에서 KB와 현재 앱 데이터를 재조회하고 토큰을 검증합니다. 만료·사용자/연결 변경·잔고/앱 데이터 변경은 `VALIDATION_ERROR`로 거절하고 다시 확인하게 합니다.
- 클라이언트가 보내는 보유 수량·매수가·자본금 수치는 사용하지 않습니다. 서버가 재조회한 값을 사용합니다.
- `importCapital=true`일 때만 주문가능 현금을 자본금으로 반영합니다. 기존 1회 거래 리스크 비율은 유지합니다.
- 수동 등록 국내 종목과 겹치면 건너뜁니다. 같은 연결의 KB 종목은 한 행을 갱신하고 기존 손절·익절 기준은 유지합니다. 새 종목에만 요청한 기준을 적용합니다.
- 다른 연결의 KB 보유분이 남아 있으면 반영을 막습니다. 응답에 없는 기존 KB 종목은 유지하며 자동 매도/삭제하지 않습니다. 전체 계좌 페이지 동기화가 아닌 수동 스냅샷 반영입니다.
- 응답은 `capitalImported`, `createdCount`, `updatedCount`, `skippedCount`, `importedAt`입니다. 실주문이나 모의 거래를 생성하지 않습니다.

### 16.3 포트폴리오 조회의 시세·원본 정보

설정 Provider 응답에 `accountConfigured`를 추가하여 계좌 조회 필수 설정을 시세 설정과 독립적으로 판정합니다. KB 계좌 조회는 API Key·인증/잔고 API 경로 등을 검사하며 주문용 계좌번호는 별도 주문 준비 조건입니다.

보유 항목에 `priceProvider`, `priceReceivedAt`, `priceFallback`, `source`, `sourceSyncedAt`을 추가합니다. `source`는 `MANUAL` 또는 `KB`이며 KB 반영 시각은 UTC입니다. 계좌 지문은 반환하지 않습니다.

목록과 합계는 같은 현재가를 사용합니다. 대체 매수가는 등록 건별로 적용하고 `priceFallback=true`, `priceReceivedAt=null`로 반환합니다. KB 보유분의 일반 수정은 거절하며, 변경은 KB 가져오기로 수행합니다. 수동 등록/수정에서 같은 국내 종목의 KB 보유분이 있으면 중복 계산을 막기 위해 거절합니다.

## 17. 뉴스·분석·홈·알림·모의매매 연결 (B 묶음)

추가 DB 마이그레이션 없이 기존 015까지의 스키마를 사용합니다. 신규 응답과 화면을 사용하려면 새 백엔드와 Windows 앱을 배포합니다.

### 17.1 관심 종목과 수집·분석

기존 `POST /api/v1/watchlist`에 종목코드·종목명·시장·`alertEnabled`만 보내 직접 등록하는 UI를 추가합니다. 가짜 추천·매수가를 만들어 관심 종목 등록 요청에 사용하지 않습니다. 추천·소식 탭에서 등록할 수 있고 소식 탭의 조회 대상은 보유·관심·최근 대표 분석 종목을 합칩니다.

분석 화면은 선택한 경우 기존 `POST /api/v1/research/feed/sync`를 먼저 호출한 뒤 보유/관심 종목 분석 API를 호출합니다. Provider 부분/전체 실패·비활성은 결과 없음과 구분해 안내합니다. 수집 자체가 실패 응답이면 분석까지 성공했다고 표시하지 않습니다. 기본 조회 기간과 분석 입력 기간은 한국 날짜를 사용합니다.

추천 목록·상세와 대표 분석에 `evidence`를 추가합니다. 기존 `analysis_snapshots.raw_payload`에서 저장 모델과 실제 입력 건수를 읽으며 원문은 응답에 포함하지 않습니다.

```json
{
  "evidence": {
    "modelVersion": "WEIGHTED_SIGNAL_V1",
    "candleCount": 20,
    "newsCount": 2,
    "disclosureCount": 1
  }
}
```

이전/잘못된 원본은 `evidence=null`로 유지합니다. `FALLBACK` 모델은 화면에서 대체 규칙 결과로 표시하며 현재 시세·뉴스의 품질을 보증하는 값으로 쓰지 않습니다. 실제 가격이 없으면 분석을 저장하지 않는 기존 차단 조건은 유지합니다.

### 17.2 홈 요약 응답

`GET /api/v1/dashboard/snapshot`의 `marketSummary`에 다음 정보를 추가합니다.

| 필드 | 의미 |
|---|---|
| `portfolioReturnRate` | 현재 보유분의 평가 수익률. 월간 수익률 아님 |
| `checkedAt` | 이번 화면 응답 조합 시각 |
| `index.status` | `SUCCESS`, `DISABLED`, `FAILED` |
| `index.provider`, `message` | 지수 출처와 조회/설정 안내 |
| `index.value`, `changeRate` | 코스피 지수와 전일 대비율. 미확인 시 null |
| `index.receivedAt` | 외부 지수 응답 수신 시각. 미확인 시 null |
| `index.points` | 날짜/종가(`date`, `close`), 오래된 순서의 최대 20거래일 |
| `news.status`, `label`, `method` | 저장 뉴스의 `SUCCESS`/`EMPTY`/`FAILED`, 표시값·분류 범위 |
| `news.articleCount`, `positiveCount`, `negativeCount` | 중복 제거 후 기사·긍정·부정 건수 |
| `news.latestPublishedAt` | 포함 기사 중 가장 최근 발행 시각. 수집 시각과 다름 |

KIS 지수는 [공식 업종기간별시세 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/inquire_daily_indexchartprice/inquire_daily_indexchartprice.py)의 `U/0001/D`, `FHKUP03500100` 계약으로 조회합니다. 기존 KIS 활성화·인증 설정을 사용하고 성공·실패 모두 1분 캐시합니다. 일봉은 최근 45일 범위에서 유효한 최대 20거래일을 선택하며 날짜·양수 가격을 검사합니다. 미설정·조회 실패에 임의의 지수를 반환하지 않습니다.

기존 `marketBars`는 실제 종가를 구간 내 0.15~1.0 상대 높이로 정규화한 값입니다. 평탄한 구간은 0.5입니다. 절대 지수 축이나 전체 이력 조회로 주장하지 않으며 실제 값·거래일은 `index.points`를 사용합니다. 당일 일봉은 확정 종가가 아닌 진행값일 수 있습니다.

뉴스는 사용자 보유·관심 종목의 최근 7일 저장 기사 최대 200행에서 Provider/링크 중복을 제거합니다. 제목·요약의 공개된 긍정/부정 키워드를 기사당 분류하며 혼합 표현은 중립입니다. 이는 AI 감성 결과·시장 전체 뉴스가 아닙니다. 분류 목록은 [개발 진척도 B 묶음](development-progress.md#b-묶음-구현과-검증-범위-2026-10-31)에 기록합니다.

`monthlyReturnRate`는 이전 앱의 숫자 형식 호환용 평가 수익률 별칭으로 남깁니다. 새 앱은 `portfolioReturnRate`를 읽고 `평가`로 표시합니다. 실제 월간 수익률은 산정하지 않습니다. 기존 `marketScore`는 호환 필드 0으로 유지하고 새 앱은 실제 지수·전일 대비율을 표시합니다.

대표 분석은 현재 활성 보유분 또는 등록 관심 종목과 일치하는 최신 저장 결과를 선택합니다. `recommendationType`, `analysisContext`, `machineStatus`, `createdAt`, `evidence`를 함께 반환합니다. GET에서 새 추천을 생성하지 않습니다. 삭제/매도 완료된 대상의 결과는 대표 분석에서 제외되지만 사용자 추천 이력은 유지됩니다.

### 17.3 알림과 모의매매

관심 종목 수동 분석도 기존 `AlertService`를 거쳐 종목 알림 설정·신호 유형·중복 제한을 검사합니다. 기존 주기 분석 스위치가 켜져 있으면 알림 ON 관심 종목을 추가로 순회합니다. 동일 종목이 보유분에 있으면 관심 분석을 중복 실행하지 않으며 한 종목의 실패가 다음 종목을 막지 않습니다.

앱은 분석/관심 설정 변경 뒤 알림 목록·전달 대기를 갱신합니다. 목록 조회 실패는 기존 목록을 보존하면서 별도 안내하고, 읽음 기록 실패는 읽음으로 확정하지 않습니다. 전달 상태의 정상 표시는 실제 알림 발생·OS 표시의 증명이 아닙니다.

모의 자본금 미설정은 `409 PAPER_CAPITAL_REQUIRED`를 반환합니다. 새 앱은 자본금 설정으로 이동하는 CTA를 표시하며 이전 서버의 동일 안내 문구도 지원합니다. 가상 매수·매도는 사용자 행 잠금으로 자본금 수정과 직렬화합니다. 모의매매는 현재 설정 자본금 기준이므로 설정 변경 시 현금·수익률은 재산정되지만 PAPER 기록은 유지합니다. 실주문을 호출하지 않습니다.

### 17.4 관심 종목 코드 조회와 삭제 화면

`GET /api/v1/market/stocks/{stockCode}/identity`는 시장 입력 없이 국내 6자리 종목코드로 등록용 정보를 조회합니다. 예시 응답의 이름·시장은 예시이며 실제 Provider 응답을 사용합니다.

```json
{
  "provider": "KIS",
  "stockCode": "000660",
  "stockName": "SK하이닉스",
  "market": "KOSPI"
}
```

위 객체는 공통 응답의 `data`입니다. 형식 오류는 `VALIDATION_ERROR`, 미설정·없는/잘못된 종목 응답·시장 판독 불가·외부 호출 실패는 `EXTERNAL_DATA_ERROR`입니다. 코드·Provider·종목명·지원 시장을 검사한 결과만 반환하며 임의 이름이나 KOSPI 기본값을 만들지 않습니다. 저장 POST와 독립적인 읽기 전용 API입니다.

- KIS는 [공식 주식기본조회](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/search_stock_info/search_stock_info.py)의 `search-stock-info`, `CTPF1002R`, `PRDT_TYPE_CD=300`, `PDNO` 계약을 사용합니다. 종목명과 현재 유효한 KOSPI/KOSDAQ 상장 일자를 확인합니다. 시장 판독이 안 되면 [현재가 조회의 명시적 시장명·단축 코드](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/inquire_price/chk_inquire_price.py)를 확인하며, 불명확하면 오류로 남깁니다. 확인된 상장폐지 종목은 자동 조회 결과로 반환하지 않습니다.
- KIS 조회가 불가능하면 설정된 Toss 종목정보를 시도하고 실제 응답의 시장을 사용합니다. 기존 KIS/Toss 활성화·인증 설정을 사용하며 새 DB 테이블이나 환경변수 추가는 없습니다.
- Flutter 등록 시 코드 입력 후 400ms 동안 변경이 없으면 조회합니다. 조회된 이름·시장은 자동 입력되며 코드 변경 시 즉시 초기화하고 이전 응답을 무시합니다. 조회 실패 시 재시도 또는 명시적인 `종목명·시장 직접 입력`을 선택합니다. 기존 `POST /api/v1/watchlist` 계약은 유지하며 확인된 값과 알림 선택을 보냅니다.
- 추천·소식 탭의 `관심 목록 관리`에서 기존 `DELETE /api/v1/watchlist/{watchlistId}`를 호출합니다. 확인 취소는 요청을 보내지 않고, 실패는 행을 유지하며, 완료 전 닫기·중복 요청을 막습니다. 삭제된 관심 행과 그 알림 설정만 제거하고 보유분·뉴스·추천·기존 알림 이력은 보존합니다. 관리 창을 닫을 때 변경이 있으면 루트 데이터를 다시 조회합니다.

### 17.5 NAVER API HUB 뉴스 검색 전환

뉴스 수집은 [NAVER API HUB 공통 규격](https://api.ncloud-docs.com/docs/naver-api-hub-overview)과 [뉴스 검색 규격](https://api.ncloud-docs.com/docs/naver-api-hub-search-news)을 사용합니다. Client ID/Secret 변수명은 유지하고 요청 주소·헤더를 클라우드 방식으로 변경합니다.

| 항목 | 설정 |
|---|---|
| 기본 주소 | `https://naverapihub.apigw.ntruss.com` |
| 뉴스 경로 | `/search/v1/news` |
| 인증 헤더 | `X-NCP-APIGW-API-KEY-ID`, `X-NCP-APIGW-API-KEY` |
| 키 출처 | NAVER API HUB Application 인증 정보의 Client ID/Client Secret |
| 쿼리 | UTF-8 종목명, `display=1~100`, `start=1`, `sort=date`, `format=json` |

`SAGOPALGO_NAVER_NEWS_CLIENT_ID/CLIENT_SECRET`을 새 헤더에 매핑합니다. Spring 기본값과 Compose 전달값에 `SAGOPALGO_NAVER_NEWS_BASE_URL/SEARCH_PATH`를 반영합니다. 기존 `/api/v1/research/feed/sync`와 `NAVER_NEWS` 식별자, 기사 저장·부분 성공 계약은 유지합니다.

실패 메시지는 `stage=NEWS_SEARCH`, `httpStatus`와 `naverCode` 또는 `kind=DNS/TIMEOUT/TLS/CONNECT/NETWORK/CLIENT`를 포함합니다. Gateway의 `error.errorCode`와 검색 API의 `errorCode`를 검사하며 코드 형식이 잘못됐거나 비 JSON 응답이면 `UNAVAILABLE`입니다. 원문 메시지·본문·인증값·URL은 로그와 Provider 상태에 복사하지 않습니다. 정상 빈 배열은 성공 0건으로 유지합니다.

### 17.6 AI 분석 캔들 날짜 전송 계약

Spring → Python `POST /internal/ai/analyze-investment`의 `candles[].dateTime`은 ISO 지역 날짜·시각 문자열입니다. 예: `"2026-09-15T00:00:00"`. 시간·소수초도 보존하며 날짜 배열(`[2026,9,15,0,0]`)이나 임의 타임존 변환을 사용하지 않습니다.

Spring 요청 DTO의 캔들 날짜 필드에 문자열 직렬화를 명시합니다. Python의 기존 `datetime` 검증 계약은 유지하고 배열 입력은 HTTP 422로 거절합니다. AI 호출 실패 시 기존 대체 결과 경로는 유지하며, 서버 로그는 응답의 요청 값/검증 본문 대신 종목코드와 HTTP 상태 또는 예외 유형만 남깁니다. 기존 저장 분석은 자동 재작성하지 않습니다.

## 18. 다음 구현 순서

Flutter 추천 이력 목록·상세 화면, 보유 종목 수동 재분석과 관심 종목 직접 분석 액션까지 연결되었습니다.

Windows 앱 잠금 PIN의 Credential Manager 저장과 기존 `.env` 값 자동 이전까지 연결되었습니다.

Windows 항상 위 미니 위젯과 시스템 트레이 메뉴까지 연결되었습니다.

AI 신호 기반 모의매매와 수익률·승률·최대 손실·회전율 지표까지 연결되었습니다.

주문 사전검증·수동 승인·단일 제출 가드·제한 전송/정정/취소·전량 체결 대조가 연결되었습니다. 실제 계좌 운영 검증과 남은 복구 범위는 별도입니다. 실계좌를 사용하지 않는 주문 시뮬레이터도 추가했습니다.

작업 묶음은 [개발 진척도](development-progress.md#화면-기준-실행-계획)를 기준으로 진행합니다.

1. A/B/C 운영 확인: 새 Windows 앱의 창 크기·배율·초기 동선 및 사용자 선택 종목의 계좌·수집·분석·홈·알림·모의매매 대조. C(9)의 반응형 레이아웃·초기 동선 구현은 완료했으며 API 변경은 없음
2. D(10): 017~020 적용 여부 확인·021 배포 후 SENDING 기록 복구 화면 대조. 다음은 공식 변경 코드·잔량/변경 주문 종결과 추가 변경 보강. UNKNOWN 잔량·변경의 대조 관찰은 구현. 종료 결과 없는 SENDING의 잠금 유지 진단은 구현했으며 종결·해제는 미지원, 별도 승인된 실제 계좌 검증
3. E(11): 운영 검증 후 제한적 자동매매 착수 여부 결정

## 19. 주문 시뮬레이션

`/api/v1/orders/simulations` 아래에 가상 세션 생성/조회, 가정 시세, 승인 준비/확인, 모의 단일 전송과 수동 체결 API를 추가했습니다. [전체 요청·상태·배포·화면 확인](order-simulation.md)을 참고합니다.

가상 세션은 현재 사용자 소유 UUID와 별도 018 JSON 테이블에 저장합니다. 실주문 계약·토큰·검증 계산·단일 제출 코어를 공유하지만 KB 클라이언트·실제 설정·계좌·실주문 가드·기존 PAPER 원장을 참조하지 않습니다. `confirmation="모의 주문 전송"`만 허용하며 실제 전송 확인 문구를 받지 않습니다. 응답에는 `mode="SIMULATION"`, 클라이언트 결과와 가상 증권사 상태, 모의 전송 횟수·예약 제외 현금·가상 보유·이벤트를 구분합니다. 토큰 해시는 노출하지 않습니다.

018 저장소 접근 실패는 `SIMULATION_STORAGE_UNAVAILABLE`(503)입니다. `SAVE_FAILURE` 시나리오는 가상 접수 커밋 후 `SIMULATION_RESULT_FAILURE`(503)를 의도적으로 반환하며 SENDING 기록을 남깁니다. 두 모의 API 오류는 실주문 설정을 켜거나 다른 전송 경로로 재시도하는 근거가 아닙니다.

## 20. SENDING 전송 결과 기록과 복구

[019 스키마·트랜잭션·확인 본문·응답 및 화면 절차](order-dispatch-recovery.md)를 참고합니다. GET `/api/v1/orders/manual/{id}/dispatch`, POST `/api/v1/orders/manual/{id}/dispatch/recover`와 POST `/api/v1/orders/simulations/{sessionId}/commands/{id}/recover`를 추가합니다. 복구 POST 확인 문구는 `저장된 전송 결과 복구`입니다. 신규 주문 POST를 호출하지 않습니다.

실주문 응답은 `commandId,commandStatus,phase,receipt,reservedAt,startedAt,returnedAt,recoveredAt,recoverable,message`이며 receipt는 정규화한 `status,orderNo,resultCode,processCode`입니다. SENDING+RETURNED+유효한 결과+현재 계좌 지문을 모두 확인합니다. ACCEPTED/REJECTED/UNKNOWN을 그대로 적용하며 UNKNOWN은 차단을 유지합니다. RESERVED/DISPATCHING/LEGACY_UNVERIFIED는 시간 경과로 해제하지 않습니다. 정상 완료·동시 복구는 동일 결과의 중복 적용을 막고 복구 감사 기록과 상태 변경을 원자적으로 저장합니다.

시뮬레이터는 STOP_BEFORE_SEND(RESERVED,0회)·JOURNAL_FAILURE(DISPATCHING,1회)를 추가하고 SAVE_FAILURE는 RETURNED 후 최종 상태 저장 실패를 재현합니다. 기존 JSON 필드 누락은 증거 없는 기록으로 취급합니다. 내부 실행 UUID·토큰 해시·계좌 지문·증권사 원문 메시지는 API에 노출하지 않습니다. 복구와 GET은 실주문 스위치 OFF에서도 가능하며 외부 호출이 없습니다.

## 21. 종료 결과 없는 SENDING 읽기 전용 진단

GET/POST `/api/v1/orders/manual/{id}/diagnostics`와 POST `/api/v1/orders/simulations/{sessionId}/commands/{id}/diagnostics`를 추가했습니다. 진단 UUID·숫자 10자리 번호·`acknowledged:true`·`confirmation:"잠금 유지 진단"`을 요구합니다. 실제 요청은 REQUESTED 커밋 이후 읽기 전용 KB 조회를 수행하고 COMPLETED로 관찰을 저장합니다. 같은 ID는 기존 결과만 반환하며 조회를 반복하지 않습니다. 이력 GET은 최근 20건 저장 데이터만 반환합니다.

응답 필드·판정·동시성·응답 유실·020 적용은 [진단 상세 계약](sending-manual-diagnostics.md)을 따릅니다. 020 누락은 DIAGNOSTIC_STORAGE_UNAVAILABLE(503)로 구분하며 기존 주문 준비 조건에는 추가하지 않습니다. 조회 실패 원문·계좌 지문·토큰 해시·전송 실행 UUID는 저장 응답에서 제외합니다. 항목 일치·빈 결과·부분/전량 체결 관찰로 주문 상태나 가드를 바꾸지 않습니다. UNKNOWN 주문 대조 범위도 확장하지 않습니다.

## 22. UNKNOWN 미체결·부분체결·변경 대조 관찰

POST `/api/v1/orders/manual/{id}/reviews/prepare`, `/confirm`와 GET 기본 reviews 경로를 추가했습니다. 준비는 `{orderNo}`와 90초 토큰/관찰 해시, 확인은 `{reviewId,token,acknowledged:true,confirmation:"잠금 유지 대조 저장"}`을 사용합니다. 확인 전 재조회가 달라지면 저장하지 않습니다. 기존 017의 신규 전량 체결 확정과 달리 이 관찰은 UNKNOWN/차단·원주문 가드를 유지합니다. 전체 필드·21번 저장소와 별개인 021 오류/배포 계약은 [대조 관찰 문서](unknown-order-reviews.md)를 따릅니다.

기존 체결 조회 항목에 originalOrderNo/changeCode/correctedQuantity/sorCancelledQuantity를 추가합니다. 선택 수량 누락은 null, 유효하지 않은 수량은 조회 오류입니다. 명시적 응답 주문일이 요청과 다르면 조회를 거절합니다. 구분 원문을 변경 완료로 매핑하지 않습니다. 시뮬레이터에는 같은 command reviews/prepare·confirm 경로와 공개 reviews 이력, TIMEOUT_AFTER_OPEN/TIMEOUT_AFTER_PARTIAL 시나리오를 추가했습니다. 내부 준비/확인 해시는 상태에서 제외합니다.

## 23. 원주문 추가 관찰과 가상 종결

22번 evidence에 선택적 `parentObservation`을 추가합니다. 정정/취소의 알려진 원주문을 별도 조회해 `orderNo,orderTime,price,quantity,filledQuantity,openQuantity,correctedQuantity,sorCancelledQuantity,verification`을 보관합니다. 검증 실패는 원문 없이 결과 코드만 남기며 참조 일치를 완료로 처리하지 않습니다. 부모 관찰도 확인 직전 해시에 포함하고 계좌 변경을 거절합니다. 이전 이력의 누락 필드는 null로 읽습니다. 기존 021 JSON을 사용합니다.

가상 종결은 **시뮬레이터에만** 추가하며 실제 `/orders/manual` 경로에는 대응 API가 없습니다.

| 메서드/경로 | 요청·응답 |
|---|---|
| POST `/api/v1/orders/simulations/{sessionId}/commands/{id}/completion/prepare` | `{orderNo}` → `{mode:"SIMULATION",resolutionId,token,expiresAt,evidence,message}` |
| POST `/api/v1/orders/simulations/{sessionId}/commands/{id}/completion/confirm` | `{resolutionId,token,acknowledged:true,confirmation:"가상 주문 종결 확정"}` → 가상 세션 상태 |
| 기존 GET `/api/v1/orders/simulations/{sessionId}` | 명령에 `resolved`와 검증된 `completion`(미완료 null) 추가 |

가상 evidence는 `source,commandId,kind,outcome,orderNo,parentOrderNo,stockCode,market,side,price,quantity,filledQuantity,openQuantity,parentState,parentFilled,parentOpen`입니다. source는 서버가 SIMULATION으로 생성하며 outcome은 FILLED/AMEND_FILLED/CANCELLED입니다. 공개 completion은 `resolutionId,evidence,confirmedAt,lockMaintained:false,source:"SIMULATION"`만 제공합니다. 토큰/근거 해시·실행 키·내부 준비는 제외합니다.

90초 토큰·근거 재검사·동의·사용자 소유 세션 잠금 아래 감사 기록을 원자적으로 저장합니다. 동일 ID/정확한 토큰의 반복 확인은 저장 결과만 반환합니다. 원본 UNKNOWN과 가상 자원은 변경하지 않고 이 가상 완료만 pending에서 제외하며 다른 미확정 명령은 차단합니다. 이전 JSON에 소유권 근거가 없으면 종결을 허용하지 않습니다. 018 JSON 확장이므로 새 마이그레이션은 없습니다. [종결 규칙·공식 자료 조사와 제한](order-completion-evidence.md)을 따릅니다.

## 24. 동일 수량 지정가 변경과 제한적 증액

기존 실제 주문의 `POST /api/v1/orders/manual/{id}/changes/prepare`와 자식 submit 계약을 유지합니다. 준비 본문 `{kind:"AMEND",price}`의 가격은 기존과 달라야 하며 기존 원주문 수량을 그대로 사용합니다. 당일 전량 미체결 신규 주문·한 차례 변경 제한은 유지합니다. 새 경로/응답 필드/마이그레이션은 없습니다. 시뮬레이터도 기존 commands/prepare·confirm·submit을 사용합니다.

매수 증액은 준비 및 제출 직전의 사전검증에서 BUYING_POWER가 명시적으로 성공하고 `orderAvailableCash >= 새 지정가 × 전체 수량`이어야 합니다. 기존 예약금이나 차액을 합산/대입하지 않습니다. 인하와 동일 수량 매도 정정은 기존 예약 자원의 중복 검사를 제외합니다. 모든 변경은 새 전체 금액 한도·현재가/이탈률·스위치·계좌를 검사하며 일부 수량 변경은 제공하지 않습니다. 상세 정책과 검증은 [지정가 변경](order-price-amendment.md)을 따릅니다.

## 25. 가상 추가 정정·일부 수량·선택 예약금 재사용

시뮬레이터의 기존 commands/prepare에서 `plan.quantity`는 정정/취소할 선택 수량입니다. 정상 접수된 NEW/AMEND의 소유권·현재 잔량·이전 변경 배분을 확인하며 일부 정정은 기존 잔량과 새 가격 주문을 분리하고 일부 취소는 선택 잔량만 제거합니다. 준비 근거가 달라지면 제출을 거절하고 세션 행 잠금으로 동일 예약금의 중복 사용을 막습니다. 실제 KB 전송 정책은 확장하지 않습니다.

세션 GET에 `changePolicy:"OWNED_RESERVATION_V1"`, 명령에 `changeable,removedQuantity,changeBudget`을 추가합니다. changeBudget은 `selectedQuantity,remainingQuantity,reusedCash,newReservedCash,additionalCash,releasedCash,scope`입니다. 가상 추가 필요 현금은 선택 수량의 새/기존 예약액 차이의 양수 부분만 사용합니다. 내부 changeSnapshot·실행 키·토큰 해시는 제외합니다. 부분/추가 정정의 종결 evidence에는 선택적 allocation(`source:"SIMULATION_ALLOCATION",parentQuantity,parentRemoved,allocatedQuantity`)을 추가하며 이전 이력의 누락은 null입니다.

실제 `/orders/manual/{id}/changes/prepare`는 선택적 `quantity,reuseReservation`을 읽습니다. 기존과 다른 수량 또는 reuseReservation=true는 VALIDATION_ERROR(400)로 거절하며 KB 조회/승인/전송을 시작하지 않습니다. 누락·동일 수량/false는 기존 정책을 따릅니다. 시뮬레이터와 실제 API 사이에서 source/모드 플래그를 전달해 조건을 우회하지 않습니다. 새 스키마·마이그레이션 없이 018 JSON을 확장하며 [전체 규칙·공식 근거·배포](order-partial-changes.md)를 따릅니다.

## 26. 전송 시작 전 예약 중단

POST `/api/v1/orders/manual/{id}/dispatch/abort-reservation` 및 `/api/v1/orders/simulations/{sessionId}/commands/{id}/abort-reservation`은 `{acknowledged:true,confirmation:"전송 전 예약 중단"}`을 요구합니다. 전송 시작과 원자적으로 경쟁해 RESERVED만 ABORTED로 전환합니다. 실제 GET dispatch에 `abortable,reservationAbort`, 주문 이력에 선택적 `reservationAbort={source:"LOCAL_BEFORE_DISPATCH",abortedAt}`를 추가합니다. 가상 출처는 `SIMULATION_BEFORE_DISPATCH`이며 서로 대체할 수 없습니다. 실행 키·계좌 지문은 응답에 제외합니다.

원본 SENDING·제출/변경 가드 보존, 검증된 감사 명령만 pending 제외, 중복 감사 한 건, 응답 유실 GET 확인을 적용합니다. DISPATCHING/이전 기록/UNKNOWN은 이 경로로 해제하지 않습니다. 실제 저장소는 022가 필요하며 누락 시 ORDER_STORAGE_UNAVAILABLE로 차단합니다. [전체 검증·배포 계약](reserved-order-abort.md)을 따릅니다.

## 27. 실제 첫 일부 수량 정정·취소

2026-11-02부터 실제 changes/prepare의 quantity를 당일 전량 미체결 NEW의 첫 변경 수량으로 지원합니다. 앞선 24/25절의 실제 동일 수량 제한은 이 후속 범위에서 확장됩니다. 누락은 원수량, 양수 정수이며 원수량 이내여야 하고 reuseReservation=true는 계속 거절합니다. 선택 수량<원수량이면 crct_clsf=1, 같으면 2이며 ordr_q는 선택 수량입니다. 원수량·원주문 변경 가드는 보존하고 추가 변경은 허용하지 않습니다.

매수 증액은 선택 수량의 새 지정가×수량 전체 금액을 별도 주문가능현금으로 검사합니다. 준비·제출의 정확한 일자/번호·전량 미체결 재검사·토큰·동의를 유지합니다. UNKNOWN 부분 변경은 관찰만 가능하며 종결하지 않습니다. 추가 스키마 변경 없이 기존 016~022와 새 백엔드/앱을 사용합니다. [정책·공식 근거·배포 점검](manual-partial-order-changes.md)을 따릅니다.
