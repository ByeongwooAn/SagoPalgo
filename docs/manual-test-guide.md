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

루트 `.env.dev.example`을 `.env.dev`로 복사한 뒤 DB 비밀번호, JWT secret, Google/Naver OAuth 값을 개발용 값으로 채웁니다.

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml --env-file .env.dev up -d --build
docker compose -f docker-compose.yml -f docker-compose.dev.yml --env-file .env.dev ps
```

API 서버 상태:

```powershell
Invoke-WebRequest -Uri http://localhost:8081/health -UseBasicParsing
docker compose -f docker-compose.yml -f docker-compose.dev.yml --env-file .env.dev logs --tail=100 spring-api
```

## 3. API 직접 테스트

인증 API는 실제 Google ID token 또는 Naver authorization code가 필요합니다. 앱 로그인을 먼저 완료한 뒤 access token을 복사해서 아래 요청에 사용합니다.

자본금 수정:

```powershell
$token = "복사한-access-token"
Invoke-RestMethod `
  -Method Put `
  -Uri http://localhost:8081/api/v1/capital `
  -Headers @{ Authorization = "Bearer $token" } `
  -ContentType "application/json" `
  -Body '{"availableCapital":3000000,"riskPerTradeRate":0.02}'
```

보유 종목 등록:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8081/api/v1/holdings `
  -Headers @{ Authorization = "Bearer $token" } `
  -ContentType "application/json" `
  -Body '{"stockCode":"005930","stockName":"삼성전자","market":"KOSPI","buyPrice":69100,"quantity":12,"buyDate":"2026-09-12","stopLossRate":-5.0,"takeProfitRate":9.0}'
```

포트폴리오 조회:

```powershell
Invoke-RestMethod `
  -Method Get `
  -Uri http://localhost:8081/api/v1/holdings `
  -Headers @{ Authorization = "Bearer $token" }
```

대시보드 스냅샷 조회:

```powershell
Invoke-RestMethod `
  -Method Get `
  -Uri http://localhost:8081/api/v1/dashboard/snapshot `
  -Headers @{ Authorization = "Bearer $token" }
```

관심 종목 조회:

```powershell
Invoke-RestMethod `
  -Method Get `
  -Uri http://localhost:8081/api/v1/watchlist `
  -Headers @{ Authorization = "Bearer $token" }
```

## 4. Flutter 앱 실제 연결 테스트

`Front/app_version/.env.example`을 `Front/app_version/.env`로 복사하고 개발 서버 주소와 Mock 플래그를 맞춥니다.

Android 에뮬레이터에서 Docker Nginx로 붙는 예:

```dotenv
SAGOPALGO_API_BASE_URL=http://10.0.2.2:8081
SAGOPALGO_USE_MOCK_AUTH=false
SAGOPALGO_USE_MOCK_INVESTMENT=false
SAGOPALGO_USE_MOCK_WATCHLIST=false
SAGOPALGO_GOOGLE_SERVER_CLIENT_ID=your-dev-google-oauth-client-id.apps.googleusercontent.com
```

같은 네트워크의 실제 Android 기기에서 붙는 예:

```dotenv
SAGOPALGO_API_BASE_URL=http://192.168.0.25:8081
SAGOPALGO_USE_MOCK_AUTH=false
SAGOPALGO_USE_MOCK_INVESTMENT=false
SAGOPALGO_USE_MOCK_WATCHLIST=false
```

실행:

```powershell
cd Front/app_version
flutter pub get
flutter run
```

앱에서 확인할 흐름:

1. Google 또는 Naver 로그인으로 홈 화면에 진입합니다.
2. 대시보드에서 투자 가능 자본금, 대표 추천, 추천 근거 라벨이 표시되는지 확인합니다.
3. 추천 탭에서 `관심 등록`을 누른 뒤 성공 메시지가 나오는지 확인합니다.
4. 추천 탭에서 `알림 설정`을 눌러 관심 종목 알림이 켜지는지 확인합니다.
5. 포트폴리오 탭에서 자본금 기준 카드와 보유 종목 손익이 API 값으로 동기화되는지 확인합니다.
6. 서버를 잠시 내린 뒤 포트폴리오 탭의 재시도 배너가 보이는지 확인합니다.

## 5. 현재 MVP 제약

- 현재가는 `MarketPriceService`의 샘플 가격으로 계산합니다. 실제 시세 API가 연결되면 이 서비스를 교체합니다.
- 추천은 `DashboardRecommendationEngine`의 규칙 기반 MVP 로직입니다. Python AI 서버가 연결되면 같은 응답 계약으로 대체합니다.
- 추천 목록/상세 API와 FCM 알림 API는 명세만 있으며, 현재 앱은 대시보드 스냅샷의 대표 추천과 알림 데이터를 사용합니다.
