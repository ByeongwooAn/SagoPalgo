# SagoPalgo Flutter Windows

이 폴더는 SagoPalgo 개인용 Windows 투자 어시스턴트의 Flutter 클라이언트입니다. 앱스토어 출시용 모바일 앱이 아니라, 내 PC에서 실행하는 데스크톱 대시보드와 위젯 모드를 우선합니다.

## 현재 구현 상태

- 앱 실행 시 Google/Naver 로그인 화면 없이 바로 개인용 홈 화면으로 진입합니다.
- 앱 잠금 PIN은 Windows Credential Manager에 저장하며 설정 탭에서 등록·변경·삭제합니다.
- 기존 `SAGOPALGO_APP_LOCK_PIN` 값은 첫 실행 시 Credential Manager로 자동 이전됩니다.
- 로컬 프로필은 `개인 사용자 · 개인 모드`로 표시됩니다.
- 대시보드 스냅샷과 포트폴리오 탭은 Spring API에서 실제 사용자 데이터를 불러옵니다.
- 개인용 백엔드 모드가 켜져 있으면 API 요청에 JWT Authorization 헤더를 보내지 않습니다.
- 포트폴리오 탭은 `/api/v1/capital`, `/api/v1/holdings`를 별도로 호출해 자본금, 권장 투자금, 보유 종목 손익을 최신화합니다.
- 포트폴리오 탭에서 자본금 수정, 보유 종목 추가, 보유 종목 수정, 보유 종목 삭제를 바로 실행할 수 있습니다.
- 추천 화면에서 저장 이력과 상세 근거를 조회하고 보유 종목을 수동 재분석할 수 있습니다.
- 추천 화면의 관심 등록/알림 설정 버튼은 Spring 관심 종목 API로 동작합니다.
- 소식 탭은 보유·추천 종목의 저장된 뉴스와 공시를 시간순으로 표시합니다.
- 소식 탭에서 종목 선택, 뉴스·공시 필터, 외부 Provider 수동 동기화, 원문 열기를 사용할 수 있습니다.
- 소식 탭에서 자동 수집 활성 여부와 종목별 마지막 동기화 결과를 확인할 수 있습니다.
- Ubuntu 백엔드의 알림 API를 30초마다 조회하고 Windows Runner의 네이티브 알림 영역에 새 투자 신호를 표시합니다.
- 알림 탭은 실제 저장 이력을 표시하며 항목을 선택하면 읽음 처리합니다.

## 백엔드 API 기준

기본 API 주소는 `Front/app_version/.env`의 `SAGOPALGO_API_BASE_URL`에서 읽습니다. 이 값이 없으면 루트 `.env.dev`와 같은 Docker 개발 키를 사용해 `http://{SAGOPALGO_NGINX_SERVER_NAME}:{SAGOPALGO_PROXY_HTTP_PORT}`를 자동으로 만듭니다.

```dotenv
SAGOPALGO_API_BASE_URL=http://ubuntu-server.local:8081
SAGOPALGO_API_PORT=8080
SAGOPALGO_PROXY_HTTP_PORT=8081
SAGOPALGO_NGINX_SERVER_NAME=ubuntu-server.local
```

API Key, 계좌번호, access token 같은 백엔드 민감정보는 Flutter asset `.env`에 넣지 않습니다. 앱 잠금 PIN만 Windows Credential Manager에 보관하고, Ubuntu 백엔드가 사용하는 Provider 키와 계좌번호는 서버의 `.env.prod`에서 관리합니다.

기존 설치의 `.env`에 `SAGOPALGO_APP_LOCK_PIN`이 있으면 첫 실행 때 자동 이전됩니다. 정상 실행을 확인한 뒤 해당 줄을 삭제하거나 값을 비웁니다.

Ubuntu 서버의 IP를 사용할 경우 `SAGOPALGO_API_BASE_URL=http://192.168.x.x:8081`처럼 지정합니다. Windows 방화벽이 아니라 Ubuntu 방화벽에서 Nginx 포트 `8081/tcp`를 같은 사설망에만 허용해야 합니다.

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
