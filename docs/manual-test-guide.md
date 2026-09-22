# 사고팔고 실제 기능 테스트 가이드

이 문서는 로컬 개발 환경에서 Spring Boot API와 Flutter 앱을 실제로 연결해 확인하는 절차입니다.

## 1. 자동 검증

백엔드 단위 테스트:

```powershell
cd Back/spring-server
.\gradlew.bat '-Dorg.gradle.project.buildDir=build-codex-status' test --no-daemon
```

Flutter 정적 분석과 테스트:

```powershell
cd Front/app_version
flutter analyze
flutter test --no-pub
```

## 2. 개발 서버 실행

루트 `.env.dev.example`을 `.env.dev`로 복사한 뒤 DB 비밀번호와 개인용 모드 값을 확인합니다. 실제 현재가를 함께 확인하려면 한국투자증권 Open API App Key/Secret도 입력하고 `SAGOPALGO_KIS_ENABLED=true`로 바꿉니다.

```dotenv
SAGOPALGO_PERSONAL_MODE_ENABLED=true
SAGOPALGO_PERSONAL_MODE_USER_ID=1
SAGOPALGO_PERSONAL_MODE_NICKNAME=개인 사용자
SAGOPALGO_PERSONAL_MODE_EMAIL=local@sagopalgo.local

SAGOPALGO_KB_ACCOUNT_ENABLED=false
SAGOPALGO_KB_ORDER_ENABLED=false
SAGOPALGO_KB_APP_KEY=
SAGOPALGO_KB_APP_SECRET=
SAGOPALGO_KB_ACCOUNT_NUMBER=

SAGOPALGO_KIS_ENABLED=true
SAGOPALGO_KIS_BASE_URL=https://openapivts.koreainvestment.com:29443
SAGOPALGO_KIS_APP_KEY=발급받은-app-key
SAGOPALGO_KIS_APP_SECRET=발급받은-app-secret
SAGOPALGO_KIS_PRICE_TR_ID=FHKST01010100

SAGOPALGO_TOSS_MARKET_DATA_ENABLED=false
SAGOPALGO_TOSS_BASE_URL=https://openapi.tossinvest.com
SAGOPALGO_TOSS_APP_KEY=
SAGOPALGO_TOSS_APP_SECRET=

SAGOPALGO_NAVER_NEWS_ENABLED=false
SAGOPALGO_NAVER_NEWS_CLIENT_ID=
SAGOPALGO_NAVER_NEWS_CLIENT_SECRET=

SAGOPALGO_OPEN_DART_ENABLED=false
SAGOPALGO_OPEN_DART_API_KEY=
```

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml --env-file .env.dev up -d --build
docker compose -f docker-compose.yml -f docker-compose.dev.yml --env-file .env.dev ps
```

DB volume을 새로 만들 때 `Back/database/schema.sql`은 `.env.dev`의 `SAGOPALGO_MYSQL_DATABASE` 값에 해당하는 DB 안에 테이블을 생성합니다. 예를 들어 `SAGOPALGO_MYSQL_DATABASE=sagopalgo_dev`이면 Spring API도 `sagopalgo_dev`에 접속하고, 테이블도 같은 DB에 생성되어야 합니다.

기존 DB volume을 유지하는 환경에서는 뉴스·공시 저장 테이블을 한 번 추가합니다. 아래 SQL은 `CREATE TABLE IF NOT EXISTS`라 반복 실행해도 기존 테이블을 지우지 않습니다.

```powershell
Get-Content -Raw Back/database/migrations/002_research_feed_storage.sql | `
  docker compose -f docker-compose.yml -f docker-compose.dev.yml --env-file .env.dev exec -T mysql `
  sh -lc 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"'

Get-Content -Raw Back/database/migrations/003_research_sync_status.sql | `
  docker compose -f docker-compose.yml -f docker-compose.dev.yml --env-file .env.dev exec -T mysql `
  sh -lc 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"'

Get-Content -Raw Back/database/migrations/004_event_alerts.sql | `
  docker compose -f docker-compose.yml -f docker-compose.dev.yml --env-file .env.dev exec -T mysql `
  sh -lc 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"'
```

자동 수집을 확인할 때만 `.env.dev`에서 아래 값을 켭니다. 기본값은 외부 API 쿼터 보호를 위해 `false`입니다.

```dotenv
SAGOPALGO_RESEARCH_SYNC_ENABLED=true
SAGOPALGO_RESEARCH_SYNC_CRON=0 0/30 * * * *
SAGOPALGO_RESEARCH_SYNC_ZONE=Asia/Seoul
```

API 서버 상태:

```powershell
Invoke-WebRequest -Uri http://localhost:8081/health -UseBasicParsing
docker compose -f docker-compose.yml -f docker-compose.dev.yml --env-file .env.dev logs --tail=100 spring-api
```

## 3. API 직접 테스트

개인용 모드에서는 JWT 없이 대시보드, 자본금, 보유 종목, 관심 종목 API를 호출할 수 있습니다. 서버는 `SAGOPALGO_PERSONAL_MODE_USER_ID`에 지정된 로컬 사용자 ID를 현재 사용자로 사용합니다.

증권사 설정 조회:

```powershell
Invoke-RestMethod `
  -Method Get `
  -Uri http://localhost:8081/api/v1/settings/providers
```

응답에는 `secretStorageType=ENV_FILE`, `orderSafetyMode=주문 기능 기본 OFF`, `marketDataFallbackOrder=[KB,KIS,TOSS]`, KB/KIS/Toss/Naver News/OpenDART의 역할과 누락 설정 이름만 표시되어야 합니다. API Key, App Secret, 계좌번호 원문은 응답에 포함되면 안 됩니다.

Toss 시세·종목 정보 확인:

```powershell
Invoke-RestMethod `
  -Method Get `
  -Uri 'http://localhost:8081/api/v1/market/stocks/005930?market=KOSPI'

Invoke-RestMethod `
  -Method Get `
  -Uri 'http://localhost:8081/api/v1/market/candles?stockCode=005930&market=KOSPI&interval=DAILY&count=20'
```

1. 토스증권에서 발급한 Client ID와 Client Secret을 각각 `SAGOPALGO_TOSS_APP_KEY`, `SAGOPALGO_TOSS_APP_SECRET`에 넣고 `SAGOPALGO_TOSS_MARKET_DATA_ENABLED=true`로 바꿉니다.
2. Provider 설정 응답에서 Toss가 `enabled=true`, `configured=true`인지 확인합니다.
3. KB와 KIS 시세를 끈 상태에서 보유 종목 현재가의 Provider가 `TOSS`인지 확인합니다.
4. 종목 정보 응답의 `stockName`, `market`, `status`, `currency`가 실제 종목과 일치하는지 확인합니다.
5. 일봉 응답 Provider가 `TOSS`이고 캔들이 오래된 날짜부터 정렬되는지 확인합니다.
6. Toss만 켠 상태에서 주봉·월봉은 일봉을 임의 합성하지 않고 사용 가능한 Provider가 없다는 오류를 반환하는지 확인합니다.

뉴스·공시 Provider를 켠 환경에서는 외부 동기화와 로컬 조회를 차례로 확인합니다.

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri 'http://localhost:8081/api/v1/research/feed/sync?stockCode=005930&stockName=삼성전자'

Invoke-RestMethod `
  -Method Get `
  -Uri 'http://localhost:8081/api/v1/research/feed?stockCode=005930&stockName=삼성전자'

Invoke-RestMethod `
  -Method Get `
  -Uri 'http://localhost:8081/api/v1/research/sync/status?stockCode=005930'
```

동기화 응답의 `data.providers`에서 각 Provider가 `SUCCESS`, `FAILED`, `DISABLED` 중 하나로 표시되는지 확인합니다. 한 Provider만 실패할 때도 HTTP 200 응답으로 다른 Provider 결과가 저장되어야 합니다. 같은 동기화를 두 번 실행한 뒤 GET 결과의 뉴스와 공시 건수가 중복 증가하지 않고, `provider=LOCAL_DB`, `dataType=CACHE`로 표시되는지 확인합니다. 상태 조회에서는 `triggerType`, `status`, `lastAttemptedAt`, 뉴스·공시 건수가 마지막 실행 결과와 일치해야 합니다.

KB 계좌 연동 확인:

```powershell
Invoke-WebRequest -Uri http://localhost:8081/api/v1/kb/accounts -UseBasicParsing
Invoke-WebRequest -Uri http://localhost:8081/api/v1/kb/accounts/primary/holdings -UseBasicParsing
Invoke-WebRequest -Uri http://localhost:8081/api/v1/kb/accounts/primary/balances/settlement -UseBasicParsing
Invoke-WebRequest -Uri http://localhost:8081/api/v1/kb/accounts/primary/balances/execution -UseBasicParsing
```

실제 KB 국내주식 조회를 확인하려면 KB증권 Open API 포털에서 App Key/App Secret을 발급받은 뒤 `SAGOPALGO_KB_ACCOUNT_ENABLED=true`로 바꿉니다. KB 공식 API 문서 파일 기준 보유주식 조회는 `SSQM1801_보유주식 조회`, 결제기준 잔고 현황은 `SSQM2932_잔고현황조회(결제기준)`, 체결기준 잔고 현황은 `SSQM2952_잔고현황조회(체결기준)`입니다. 공개 path와 기본 요청값은 백엔드 기본 설정으로 관리하므로 `.env.dev`에 넣지 않아도 됩니다.

KB access token 발급 실패를 확인할 때는 Compose 파일과 서비스명을 정확히 지정합니다. 개발용 컨테이너의 서비스명은 `spring-api`입니다.

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml --env-file .env.dev ps
docker compose -f docker-compose.yml -f docker-compose.dev.yml --env-file .env.dev exec spring-api sh -lc 'echo ACCOUNT=$SAGOPALGO_KB_ACCOUNT_ENABLED; echo APP_KEY_LEN=${#SAGOPALGO_KB_APP_KEY}; echo APP_SECRET_LEN=${#SAGOPALGO_KB_APP_SECRET}'
docker compose -f docker-compose.yml -f docker-compose.dev.yml --env-file .env.dev logs --tail=100 spring-api
```

KB 응답에 `processCode=E021`, `processMessage=앱키로 앱정보 추출 중 오류가 발생했습니다.`가 나오면 서버 연결은 성공했지만 KB가 전달받은 App Key로 앱 정보를 찾지 못한 상태입니다. `.env.dev`의 App Key/App Secret이 KB Open API B2C 포털에서 발급받은 값인지, 앞뒤 공백이나 잘못된 앱의 키가 섞이지 않았는지, 앱 사용 승인 상태인지 확인합니다.

자본금 수정:

```powershell
Invoke-RestMethod `
  -Method Put `
  -Uri http://localhost:8081/api/v1/capital `
  -ContentType "application/json" `
  -Body '{"availableCapital":3000000,"riskPerTradeRate":0.02}'
```

보유 종목 등록:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8081/api/v1/holdings `
  -ContentType "application/json" `
  -Body '{"stockCode":"005930","stockName":"삼성전자","market":"KOSPI","buyPrice":69100,"quantity":12,"buyDate":"2026-09-12","stopLossRate":-5.0,"takeProfitRate":9.0}'
```

포트폴리오 조회:

```powershell
Invoke-RestMethod `
  -Method Get `
  -Uri http://localhost:8081/api/v1/holdings
```

응답의 `items[].currentPrice`가 등록한 `buyPrice`가 아니라 한국투자증권 현재가로 내려오는지 확인합니다. KIS 설정이 켜져 있는데 키가 비어 있거나 API 호출에 실패하면 서버는 `EXTERNAL_DATA_ERROR`를 반환합니다.

대시보드 스냅샷 조회:

```powershell
Invoke-RestMethod `
  -Method Get `
  -Uri http://localhost:8081/api/v1/dashboard/snapshot
```

관심 종목 조회:

```powershell
Invoke-RestMethod `
  -Method Get `
  -Uri http://localhost:8081/api/v1/watchlist
```

## 4. Flutter 앱 실제 연결 테스트

`Front/app_version/.env.example`을 `Front/app_version/.env`로 복사하고 개발 서버 주소를 맞춥니다.

Windows 로컬 프로그램에서 Docker Nginx로 붙는 예:

```dotenv
SAGOPALGO_API_BASE_URL=http://localhost:8081
```

실행:

```powershell
cd Front/app_version
flutter pub get
flutter run -d windows
```

앱에서 확인할 흐름:

1. 로그인 화면 없이 바로 홈 화면에 진입하는지 확인합니다.
2. DB에 자본금이 없으면 자본금이 0원으로 표시되는지 확인합니다.
3. DB에 보유 종목이 없으면 추천 탭에 `추천 데이터 없음`이 표시되는지 확인합니다.
4. 포트폴리오 탭 상단의 자본금 수정 버튼을 눌러 투자 가능 자본금과 1회 리스크 비율을 저장합니다.
5. 포트폴리오 탭 상단의 추가 버튼을 눌러 보유 종목을 등록합니다.
6. 등록된 보유 종목의 메뉴에서 수정과 삭제가 실제로 반영되는지 확인합니다.
7. 대시보드에서 투자 가능 자본금과 실제 보유 종목 기반 대표 추천이 표시되는지 확인합니다.
8. 추천 탭에서 저장 추천 이력과 총 건수가 표시되는지 확인합니다.
9. 추천 이력 항목을 선택해 점수, 손절·익절 기준, 분석 근거, 저장 시각이 상세 화면에 표시되는지 확인합니다.
10. `분석` 또는 상세 화면의 `이 종목 다시 분석`을 눌러 새 추천이 저장되고 최신 추천과 이력이 갱신되는지 확인합니다.
11. 추천 탭에서 `관심 등록`을 누른 뒤 성공 메시지가 나오는지 확인합니다.
12. 추천 탭에서 `알림 켜기`를 눌러 관심 종목 알림이 켜지는지 확인합니다.
13. 포트폴리오 탭에서 자본금 기준 카드와 보유 종목 손익이 한국투자증권 현재가 기준으로 동기화되는지 확인합니다.
14. 소식 탭에서 보유·추천 종목을 선택하면 저장된 뉴스와 공시가 최신순으로 함께 표시되는지 확인합니다.
15. `전체`, `뉴스`, `공시` 필터가 목록을 올바르게 분리하는지 확인합니다.
16. 동기화 아이콘을 눌렀을 때 Provider 상태와 뉴스·공시 건수가 갱신되고 같은 항목이 중복 증가하지 않는지 확인합니다.
17. 자동 수집 카드에서 활성 여부, 마지막 수동·자동 실행 시각, 성공/부분 성공/실패 상태가 표시되는지 확인합니다.
18. 뉴스·공시 행의 원문 아이콘을 눌렀을 때 Windows 기본 브라우저로 링크가 열리는지 확인합니다.
19. 설정 탭에서 Ubuntu 서버 비밀값 저장 방식이 `ENV_FILE`로 표시되는지 확인합니다.
20. `Windows 앱 잠금`에서 PIN을 등록하면 상태가 `보호됨`으로 바뀌는지 확인합니다.
21. 앱을 재실행해 잠금 화면이 나타나는지 확인한 뒤 PIN을 변경하거나 삭제했을 때 다음 실행에 반영되는지 확인합니다.
22. 설정 탭에서 주문 상태가 `주문 기능 기본 OFF`로 표시되는지 확인합니다.
23. 설정 탭에서 KB증권, 한국투자증권, 토스증권, 네이버 뉴스, OpenDART 연동 상태가 표시되는지 확인합니다.
24. 시세 fallback이 `KB증권 → 한국투자증권 → 토스증권 → 등록 매수가` 순서로 표시되는지 확인합니다.
25. 비활성 Provider는 `꺼짐`, 활성화됐지만 설정이 빠진 Provider는 `설정 필요`, 활성화되고 설정이 완료된 Provider는 `사용 가능`으로 표시되는지 확인합니다.
26. 미설정 Provider 카드에 실제 비밀값 대신 `누락: App Key · App Secret`처럼 설정 이름만 표시되는지 확인합니다.
27. 포트폴리오의 보유 종목에서 차트 버튼을 눌러 종목 상세 화면으로 이동하는지 확인합니다.
28. 일봉, 주봉, 월봉을 차례로 선택했을 때 캔들과 OHLCV 수치가 갱신되는지 확인합니다.
29. 차트 상단에 실제 응답 Provider가 `KB 데이터` 또는 `KIS 데이터`로 표시되는지 확인합니다.
30. 캔들을 마우스로 가리키거나 클릭했을 때 선택 날짜의 종가, 등락률, OHLCV가 표시되는지 확인합니다.
31. 서버를 잠시 내린 뒤 포트폴리오, 차트, 소식 탭의 재시도 화면이 보이는지 확인합니다.

캔들 Provider 실데이터 확인:

```powershell
Invoke-RestMethod `
  -Method Get `
  -Uri 'http://localhost:8080/api/v1/market/candles?stockCode=005930&market=KOSPI&interval=DAILY&count=20'
```

1. KB 시세가 활성화되어 있으면 `data.provider`가 `KB`인지 확인합니다.
2. KB 시세를 끄고 KIS를 활성화하면 `data.provider`가 `KIS`로 전환되는지 확인합니다.
3. `data.candles`가 날짜 오름차순이며 각 항목에 시가·고가·저가·종가·거래량이 있는지 확인합니다.
4. 두 Provider를 모두 끄면 임의 캔들 대신 HTTP 502와 `EXTERNAL_DATA_ERROR`가 반환되는지 확인합니다.

AI 분석과 추천 저장 확인:

```powershell
Invoke-RestMethod -Uri 'http://localhost:8000/health'

Invoke-RestMethod `
  -Method Post `
  -Uri 'http://localhost:8080/api/v1/recommendations/analyze/21'

Invoke-RestMethod `
  -Method Get `
  -Uri 'http://localhost:8080/api/v1/recommendations?page=0&size=20'
```

1. 분석 응답에 `status`, `statusLabel`, `score`, `reasons`가 표시되는지 확인합니다.
2. 같은 추천 ID로 `recommendations`, `recommendation_reasons`, `analysis_snapshots`가 저장되는지 확인합니다.
3. AI 서버를 중지하거나 `SAGOPALGO_AI_ENABLED=false`로 바꾼 뒤에도 규칙 fallback 추천이 저장되는지 확인합니다.
4. 대시보드 새로고침 시 가장 최근에 저장한 추천이 대표 추천으로 표시되는지 확인합니다.
5. Flutter 추천 탭에서 목록을 추가 조회할 수 있고, 항목 선택 시 같은 추천 ID의 상세가 표시되는지 확인합니다.
6. 보유 종목 수동 재분석 후 새 추천이 이력 최상단에 나타나는지 확인합니다.

Windows 알림 흐름 확인:

```powershell
Invoke-RestMethod -Uri 'http://localhost:8080/api/v1/alerts?page=0&size=20'
Invoke-RestMethod -Uri 'http://localhost:8080/api/v1/alerts/pending?limit=20'
```

1. `BUY_WATCH`, `BUY_STRONG`, `TAKE_PROFIT`, `STOP_LOSS_WATCH`, `RISK` 추천을 생성하면 알림이 저장되는지 확인합니다.
2. 같은 종목과 알림 유형을 60분 안에 다시 분석하면 중복 알림이 생기지 않는지 확인합니다.
3. Flutter Windows 앱을 실행한 뒤 30초 안에 Windows 알림 센터에 제목과 분석 요약이 표시되는지 확인합니다.
4. 표시된 항목의 `sentAt`이 기록되고 `/pending`에서는 제외되는지 확인합니다.
5. 알림 탭에서 항목을 선택하면 `read=true`로 바뀌는지 확인합니다.
6. 관심 종목 알림을 끈 뒤 새 추천을 만들어도 해당 종목 알림이 생기지 않는지 확인합니다.
7. 실제 현재가가 손절·익절 기준에 도달하면 `eventType`이 `PRICE_STOP_LOSS` 또는 `PRICE_TAKE_PROFIT`인 알림이 생성되는지 확인합니다.
8. 당일 등락률이 `SAGOPALGO_ALERT_VOLATILITY_THRESHOLD_RATE` 이상 또는 이하이면 `PRICE_SURGE` 또는 `PRICE_DROP`이 생성되고, 같은 이벤트는 쿨다운 동안 다시 생기지 않는지 확인합니다.
9. `FALLBACK` 시세에서는 가격 알림이 생성되지 않는지 확인합니다.
10. 관심 종목 뉴스·공시 동기화 후 `NEWS`, `DISCLOSURE` 알림이 생성되고 같은 데이터를 재동기화해도 중복 생성되지 않는지 확인합니다.

새 앱 잠금 PIN은 설정 탭에서 등록합니다. 기존 설치에 `SAGOPALGO_APP_LOCK_PIN=1234`가 있으면 첫 실행 때 `SagoPalgo/AppLockPin` 대상으로 Windows Credential Manager에 자동 이전됩니다. 이전 확인 후 Flutter `.env`의 PIN은 비웁니다. PIN 원문은 화면, 로그, 백엔드 API에 표시되면 안 됩니다.

Windows 릴리즈 빌드 확인:

```powershell
flutter build windows --release
```

빌드 성공 후 `build\windows\x64\runner\Release\SagoPalgo.exe`를 실행합니다. 같은 폴더의 `flutter_windows.dll`과 `data/` 폴더가 함께 있어야 합니다.

## 5. 현재 MVP 제약

- 현재가는 KB/KIS 시세 설정이 켜진 KOSPI/KOSDAQ/KONEX 종목이면 실제 현재가로 반환합니다.
- 일·주·월봉은 KB/KIS 실데이터 조회 API와 Flutter 보유 종목 상세 차트에 연결되어 있으며, 응답 Provider를 화면에 표시합니다.
- KIS 설정이 꺼져 있거나 아직 지원하지 않는 해외 시장 종목이면 임의 샘플 가격을 만들지 않고 사용자가 등록한 매수가를 기준값으로 반환합니다.
- 추천 분석은 Python 서버에서 가격·뉴스·공시·보유 손익을 종합하고 결과와 근거를 저장합니다. 서버 장애 시 규칙 기반 추천으로 대체합니다.
- 추천 분석 실행, 이력 페이지, 상세 조회, Flutter 수동 재분석 흐름이 연결되어 있습니다.
- Ubuntu 백엔드의 추천 신호와 가격·뉴스·공시 전용 알림 저장, 알림 API, Flutter 폴링, Windows 네이티브 알림이 연결되어 있습니다. 앱이 완전히 종료된 동안에는 Windows 토스트를 즉시 표시하지 않지만 백엔드는 알림을 저장하고 다음 앱 실행 때 전달합니다.
- 뉴스와 공시는 외부 동기화, 로컬 저장, 중복 제거, 기간 조회, Flutter 타임라인, 주기 동기화까지 구현됐습니다.
