# 사고팔고 Flutter 앱

사고팔고 Android 앱 UI 프로젝트입니다. 현재는 기획서 색상과 A/B 시안을 기반으로 만든 투자 대시보드에 Google/Naver 소셜 로그인 진입 화면을 추가한 상태입니다.

## 현재 구현 상태

- 로그인 전에는 `LoginScreen`이 표시됩니다.
- Google/Naver 버튼만 제공하며 이메일/비밀번호 입력 화면은 없습니다.
- 현재 앱 실행 기본값은 `MockAuthRepository`라 실제 Google/Naver SDK 없이도 UI 흐름을 확인할 수 있습니다.
- 실제 백엔드 연동 시에는 `SpringAuthRepository`와 실제 `SocialTokenProvider` 구현으로 교체합니다.
- 로그인 성공 후에는 기존 대시보드, 추천, 포트폴리오, 알림 탭으로 진입합니다.
- 홈 상단 로그아웃 버튼을 누르면 인증 세션을 비우고 로그인 화면으로 돌아갑니다.

## 실제 소셜 SDK 연결 지점

- Google은 Flutter 공식 `google_sign_in` 패키지에서 받은 ID token을 서버의 `/api/v1/auth/google`로 전달해야 합니다.
- Naver는 공식 Android SDK에서 받은 access token을 서버의 `/api/v1/auth/naver`로 전달해야 합니다.
- 두 토큰 발급 구현은 `lib/services/social_token_provider.dart`의 `SocialTokenProvider`를 구현하는 클래스로 추가합니다.

## 백엔드 API 기준

기본 API 주소는 `Front/app_version/.env`의 `SAGOPALGO_API_BASE_URL`에서 읽습니다.

```dotenv
SAGOPALGO_API_BASE_URL=http://10.0.2.2:8080
SAGOPALGO_USE_MOCK_AUTH=true
```

Android 에뮬레이터에서 로컬 PC의 Spring Boot 서버에 접근할 때는 `10.0.2.2:8080`을 사용합니다. 실제 Android 기기에서는 PC의 같은 네트워크 IP 또는 배포 서버 주소로 바꿔야 합니다.

모바일 앱의 `.env`는 APK에 포함되므로 Naver Client Secret, JWT Secret, DB 비밀번호 같은 민감한 값은 넣지 않습니다. 이런 값은 백엔드 `.env`에서만 관리합니다.

## 검증 명령

```powershell
flutter pub get
flutter analyze
flutter test --no-pub
flutter build apk --debug --no-pub
```
