# 사고팔고 Flutter 앱

사고팔고 Android 앱 UI 프로젝트입니다. 기획서 색상과 A/B 시안을 기반으로 만든 투자 대시보드에 Google/Naver 소셜 로그인을 연결합니다.

## 현재 구현 상태

- 로그인 전에는 `LoginScreen`이 표시됩니다.
- Google/Naver 버튼만 제공하며 이메일/비밀번호 입력 화면은 없습니다.
- `SAGOPALGO_USE_MOCK_AUTH=true`이면 Mock 로그인으로 UI 흐름을 확인합니다.
- `SAGOPALGO_USE_MOCK_AUTH=false`이면 `SpringAuthRepository`가 실제 Google ID token과 Naver authorization code를 Spring Boot 인증 API로 전달합니다.
- 로그인 성공 후에는 기존 대시보드, 추천, 포트폴리오, 알림 탭으로 진입합니다.
- 홈 상단 로그아웃 버튼을 누르면 인증 세션을 비우고 로그인 화면으로 돌아갑니다.
- `SAGOPALGO_USE_MOCK_INVESTMENT=false`이면 대시보드 스냅샷과 포트폴리오 탭이 Spring API에서 데이터를 불러옵니다.
- 포트폴리오 탭은 `/api/v1/capital`, `/api/v1/holdings`를 별도로 호출해 자본금, 권장 투자금, 보유 종목 손익을 최신화합니다.
- 추천 화면의 관심 등록/알림 설정 버튼은 `SAGOPALGO_USE_MOCK_WATCHLIST=false`일 때 Spring 관심 종목 API로 동작합니다.

## 실제 소셜 SDK 연결 지점

- Google은 Flutter 공식 `google_sign_in` 패키지에서 받은 ID token을 서버의 `/api/v1/auth/google`로 전달합니다.
- Naver는 백엔드가 생성한 authorization URL을 Android 브라우저에 열고, 앱 callback으로 받은 code를 서버의 `/api/v1/auth/naver`로 전달합니다.
- Naver Client ID, Client Secret, Redirect URI는 앱에 포함하지 않고 백엔드 `.env.dev`/`.env.prod`에만 둡니다.

## 백엔드 API 기준

기본 API 주소는 `Front/app_version/.env`의 `SAGOPALGO_API_BASE_URL`에서 읽습니다. 이 값이 없으면 루트 `.env.dev`와 같은 Docker 개발 키를 사용해 `http://{SAGOPALGO_NGINX_SERVER_NAME}:{SAGOPALGO_PROXY_HTTP_PORT}`를 자동으로 만듭니다.

```dotenv
SAGOPALGO_API_PORT=8080
SAGOPALGO_PROXY_HTTP_PORT=8081
SAGOPALGO_NGINX_SERVER_NAME=192.168.0.25
SAGOPALGO_USE_MOCK_AUTH=false
```

Android 에뮬레이터에서 로컬 PC의 Spring Boot 서버에 접근할 때는 `10.0.2.2:8080` 또는 `10.0.2.2:8081`을 사용합니다. 실제 Android 기기에서는 같은 네트워크의 Ubuntu IP, 예를 들어 `192.168.0.25:8081`을 사용합니다.

모바일 앱의 `.env`는 APK에 포함되므로 Naver Client ID/Secret, JWT Secret, DB 비밀번호 같은 서버 설정값은 넣지 않습니다.

## 검증 명령

```powershell
flutter pub get
flutter analyze
flutter test --no-pub
flutter build apk --debug --no-pub
```
