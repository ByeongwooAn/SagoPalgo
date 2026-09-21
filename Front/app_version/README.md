# SagoPalgo Flutter Windows

이 폴더는 SagoPalgo 개인용 Windows 투자 어시스턴트의 Flutter 클라이언트입니다. 앱스토어 출시용 모바일 앱이 아니라, 내 PC에서 실행하는 데스크톱 대시보드와 위젯 모드를 우선합니다.

## 현재 구현 상태

- 앱 실행 시 Google/Naver 로그인 화면 없이 바로 개인용 홈 화면으로 진입합니다.
- `SAGOPALGO_APP_LOCK_PIN`이 설정되어 있으면 시작 시 로컬 PIN 잠금 화면을 표시합니다.
- 로컬 프로필은 `개인 사용자 · 개인 모드`로 표시됩니다.
- 대시보드 스냅샷과 포트폴리오 탭은 Spring API에서 실제 사용자 데이터를 불러옵니다.
- 개인용 백엔드 모드가 켜져 있으면 API 요청에 JWT Authorization 헤더를 보내지 않습니다.
- 포트폴리오 탭은 `/api/v1/capital`, `/api/v1/holdings`를 별도로 호출해 자본금, 권장 투자금, 보유 종목 손익을 최신화합니다.
- 포트폴리오 탭에서 자본금 수정, 보유 종목 추가, 보유 종목 수정, 보유 종목 삭제를 바로 실행할 수 있습니다.
- 추천 화면의 관심 등록/알림 설정 버튼은 Spring 관심 종목 API로 동작합니다.
- 소식 탭은 보유·추천 종목의 저장된 뉴스와 공시를 시간순으로 표시합니다.
- 소식 탭에서 종목 선택, 뉴스·공시 필터, 외부 Provider 수동 동기화, 원문 열기를 사용할 수 있습니다.

## 백엔드 API 기준

기본 API 주소는 `Front/app_version/.env`의 `SAGOPALGO_API_BASE_URL`에서 읽습니다. 이 값이 없으면 루트 `.env.dev`와 같은 Docker 개발 키를 사용해 `http://{SAGOPALGO_NGINX_SERVER_NAME}:{SAGOPALGO_PROXY_HTTP_PORT}`를 자동으로 만듭니다.

```dotenv
SAGOPALGO_API_BASE_URL=http://localhost:8081
SAGOPALGO_API_PORT=8080
SAGOPALGO_PROXY_HTTP_PORT=8081
SAGOPALGO_NGINX_SERVER_NAME=localhost
SAGOPALGO_APP_LOCK_PIN=
```

API Key, 계좌번호, access token 같은 민감정보는 Flutter asset `.env`에 넣지 않습니다. 이후 단계에서 Windows Credential Manager 또는 앱 잠금 기반 로컬 보안 저장소로 옮깁니다.

## Windows 실행

```powershell
flutter config --enable-windows-desktop
flutter pub get
flutter run -d windows
```

## Windows 빌드

```powershell
flutter build windows --release
```

빌드 산출물은 아래 폴더에 생성됩니다.

```text
build\windows\x64\runner\Release\SagoPalgo.exe
```

Flutter Windows 앱은 `SagoPalgo.exe`만 따로 복사해서 실행하는 구조가 아닙니다. 같은 폴더의 `flutter_windows.dll`과 `data/` 폴더가 함께 있어야 실행됩니다.

## 검증 명령

```powershell
flutter pub get
flutter analyze
flutter test --no-pub
flutter build windows --release
```
