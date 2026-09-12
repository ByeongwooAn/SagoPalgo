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
SAGOPALGO_TOSS_APP_KEY=
SAGOPALGO_TOSS_APP_SECRET=
```

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml --env-file .env.dev up -d --build
docker compose -f docker-compose.yml -f docker-compose.dev.yml --env-file .env.dev ps
```

DB volume을 새로 만들 때 `Back/database/schema.sql`은 `.env.dev`의 `SAGOPALGO_MYSQL_DATABASE` 값에 해당하는 DB 안에 테이블을 생성합니다. 예를 들어 `SAGOPALGO_MYSQL_DATABASE=sagopalgo_dev`이면 Spring API도 `sagopalgo_dev`에 접속하고, 테이블도 같은 DB에 생성되어야 합니다.

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

응답에는 `secretStorageType=ENV_FILE`, `orderSafetyMode=주문 기능 기본 OFF`, KB/KIS/Toss의 역할, 활성화 여부, 필수 설정값 입력 여부만 표시되어야 합니다. API Key, App Secret, 계좌번호 원문은 응답에 포함되면 안 됩니다.

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
SAGOPALGO_APP_LOCK_PIN=
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
8. 추천 탭에서 `관심 등록`을 누른 뒤 성공 메시지가 나오는지 확인합니다.
9. 추천 탭에서 `알림 설정`을 눌러 관심 종목 알림이 켜지는지 확인합니다.
10. 포트폴리오 탭에서 자본금 기준 카드와 보유 종목 손익이 한국투자증권 현재가 기준으로 동기화되는지 확인합니다.
11. 설정 탭에서 민감정보 저장 방식이 `ENV_FILE`로 표시되는지 확인합니다.
12. 설정 탭에서 주문 상태가 `주문 기능 기본 OFF`로 표시되는지 확인합니다.
13. 설정 탭에서 KB증권, 한국투자증권, 토스증권 연동 상태가 표시되는지 확인합니다.
14. 서버를 잠시 내린 뒤 포트폴리오 탭의 재시도 배너가 보이는지 확인합니다.

앱 잠금 확인이 필요하면 `Front/app_version/.env`에 `SAGOPALGO_APP_LOCK_PIN=1234`처럼 값을 넣고 다시 실행합니다. 시작 시 PIN 잠금 화면이 표시되고, 같은 값을 입력하면 홈 화면에 진입해야 합니다.

Windows 릴리즈 빌드 확인:

```powershell
flutter build windows
```

빌드 성공 후 `build\windows\x64\runner\Release\SagoPalgo.exe`를 실행합니다. 같은 폴더의 `flutter_windows.dll`과 `data/` 폴더가 함께 있어야 합니다.

## 5. 현재 MVP 제약

- 현재가는 한국투자증권 Open API 설정이 켜진 KOSPI/KOSDAQ/KONEX 종목이면 실제 현재가로 반환합니다.
- KIS 설정이 꺼져 있거나 아직 지원하지 않는 해외 시장 종목이면 임의 샘플 가격을 만들지 않고 사용자가 등록한 매수가를 기준값으로 반환합니다.
- 추천은 실제 보유 종목이 있을 때만 `DashboardRecommendationEngine`의 규칙 기반 MVP 로직으로 생성합니다. Python AI 서버가 연결되면 같은 응답 계약으로 대체합니다.
- 추천 목록/상세 API와 Windows 알림 API는 아직 구현 전이며, 현재 앱은 대시보드 스냅샷의 대표 추천과 알림 데이터를 사용합니다.
