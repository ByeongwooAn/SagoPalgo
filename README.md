# SagoPalgo

SagoPalgo는 개인용 Windows 투자 프로그램입니다. 최종 목표는 KB증권 실계좌를 기준으로 실시간 시장 데이터·뉴스·공시·수급을 분석하고, 검증된 AI·전략이 운용 한도 안에서 종목·금액·매매 시점을 판단하는 단기 자동매매 시스템입니다.
현재는 계좌 조회·규칙 기반 분석·알림·모의매매·제한된 승인형 주문을 구현한 상태이며, 실시간 수집·학습 모델·자동매매는 단계적으로 개발합니다.

## 프로젝트 방향

- 공개 앱스토어 출시나 상용 SaaS 운영이 아닌 개인용 Windows 프로그램을 우선합니다.
- 실제 계좌 조회, 주문, 체결 등 금융 업무는 KB증권 Open API만 사용합니다.
- KIS와 Toss Open API는 계좌/주문 연동 없이 읽기 전용 시장 데이터 Provider로 사용합니다.
- 같은 현재가를 여러 증권사에서 매번 합치지 않고, 기본 Provider와 fallback Provider를 분리합니다.
- 실시간 수집·시장 전체 탐색·과거 데이터 학습·AI 자금 배분을 개발하고, 재현 검증·실시간 모의·제한 실거래 검증을 거쳐 자동매매를 도입합니다.
- 온주 단타와 소수점 거래는 실제 체결 방식에 맞춰 전략·주문 경로를 구분합니다.

향후 개발 기준은 [실시간 AI 단기 자동매매 로드맵](docs/realtime-trading-roadmap.md)입니다. [목표 아키텍처](docs/target-system-architecture.md), [현재 배포 구조](docs/docker-architecture.md), [개발 진척도](docs/development-progress.md)를 구분해 확인하세요. [기존 설계·구현 이력](docs/personal-windows-investment-assistant.md)은 보존합니다.

과거 데이터 후속은 [KRX 기간 전체 종목 목록·관찰 변화 수집](docs/krx-universe-history.md)입니다. 날짜별 원문·호출 예산·중단 재개·사건 경계 대조를 관리합니다. 종목 목록 확보와 거래일/거래정지·기업행사·학습 가능 여부는 구분합니다.

## 개인 사용 및 책임 고지

본 프로젝트는 개인 학습 및 개인 투자 분석 보조용 오픈소스입니다.
본 프로젝트는 투자 권유, 투자자문, 수익 보장 서비스를 제공하지 않습니다.
사용자는 각 증권사 Open API 약관과 관련 법령을 직접 확인한 뒤 본인 책임하에 사용해야 합니다.
API Key, 계좌정보, 토큰 등 민감정보를 저장소에 커밋하지 마세요.

## 목표 기능

- KB증권 계좌 조회, 보유 주식 조회, 평가손익 분석
- 국내/해외 주식 현재가, 캔들, 거래량, 시장 지표 조회
- 뉴스와 공시 기반 종목별 AI 분석
- 관심종목, 보유종목, 리스크 신호 알림
- 항상 화면 위에 띄울 수 있는 미니 위젯 모드
- 실시간 시세·호가·분봉과 제공 주기에 맞는 투자자별 수급·뉴스·공시 갱신
- 시장 전체 유망 후보 탐색, 다년간 데이터 학습과 비용 포함 전략 검증
- AI 목표 비중·실잔고·미체결 예약을 반영한 분산 투자와 검증된 자동 주문
- 체결 조건에 맞는 소수점 거래, 일·주·월·연 실계좌 수익·포트폴리오 차트

위 목록은 목표 범위입니다. 기존 구현의 완료 표시는 새 목표 전체의 완료를 뜻하지 않습니다.

## 현재 기술 구조

```text
Front/app_version      Flutter 앱. Windows 데스크톱 실행 파일을 우선 대상으로 전환합니다.
Back/spring-server     Spring Boot API 서버. 초기에는 기존 API와 데이터 구조를 활용합니다.
AI/ai-server           가격·뉴스·공시·보유 손익을 조합하는 로컬 Python 분석 서버입니다.
docs                   설계, API, 수동 테스트, 로드맵 문서를 관리합니다.
docker                 Docker/Nginx 템플릿과 실행 보조 파일을 관리합니다.
```

Flutter 앱은 Windows PC에서 실행하고 Spring Boot, Python AI, MySQL, Nginx는 Ubuntu 컴퓨터의 Docker Compose에서 실행합니다. Ubuntu 백엔드는 앱이 꺼져 있어도 보유 종목을 주기적으로 분석해 알림을 저장하고, Windows 앱은 다시 연결될 때 미전달 알림을 운영체제 알림 센터에 표시합니다.

![Ubuntu 백엔드와 Windows 앱 시스템 구조](docs/images/system-architecture-ubuntu.png)

위 이미지는 현재 배포 구조입니다. 신규 데이터 수집·학습·자동 주문의 연결은 [목표 시스템 구조도](docs/target-system-architecture.md)에서 확인할 수 있습니다.

## 백엔드 실행

루트 `.env.example`을 `.env`로 복사한 뒤 비밀번호와 Provider 설정을 입력합니다. 새 설치라면 이름이 같은 DB 볼륨을 한 번 생성합니다. 기존 설치는 새 볼륨을 만들지 말고 [기존 설치 전환 절차](docs/docker-architecture.md#3-실행과-기존-설치-전환)를 먼저 확인하세요.

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker volume create sagopalgo-mysql-data
docker compose --env-file .env config --quiet
docker compose --env-file .env up -d --build
```

백엔드 상태 확인:

```powershell
docker compose --env-file .env ps
Invoke-WebRequest -Uri http://localhost:8081/health -UseBasicParsing
docker compose --env-file .env logs --tail=100 spring-api
```

Docker 호스트에서 Flutter 앱까지 함께 테스트할 때는 앱의 `SAGOPALGO_API_BASE_URL`을 `http://localhost:8080`으로 지정합니다. 다른 Windows PC에서 Ubuntu 서버에 접속할 때만 IP 허용 목록을 설정한 Nginx `:8081` 주소를 사용합니다. 서버의 루트 `.env`를 Flutter asset으로 복사하지 마세요.

Flutter Windows 실행:

Windows `.exe` 빌드를 위해 Visual Studio Installer에서 `Desktop development with C++` 워크로드와 `C++ CMake tools for Windows`, `Windows 10 SDK`가 필요합니다.

```powershell
cd Front/app_version
flutter config --enable-windows-desktop
flutter pub get
flutter run -d windows
```

Windows 릴리즈 빌드:

```powershell
cd Front/app_version
flutter build windows --release
```

Ubuntu에서 Windows 앱이 접속할 때는 `.env`의 `SAGOPALGO_PROXY_BIND_ADDRESS=0.0.0.0`과 `SAGOPALGO_ALLOWED_CLIENT_IP=<Windows PC 사설 IP>`를 설정하고 방화벽도 같은 PC로 제한합니다. 백엔드 실행 명령은 Windows와 동일합니다.

```bash
cp -n .env.example .env
# .env의 비밀번호, Provider 키, 프록시 설정을 수정합니다.
docker volume create sagopalgo-mysql-data
docker compose --env-file .env config --quiet
docker compose --env-file .env up -d --build
docker compose --env-file .env ps
curl http://localhost:8081/health
```

**위 복사·볼륨 생성 명령은 새 설치에서만 사용합니다.** 기존 Ubuntu 배포는 먼저 실제 볼륨 이름을 확인하고 DB 백업을 확보한 뒤 기존 설정값을 루트 `.env`로 옮겨야 합니다. KB 점검 이력의 `014` 마이그레이션 절차도 [Docker 구조 문서](docs/docker-architecture.md#기존-ubuntu-db의-kb-점검-이력-테이블)에 있습니다. `down -v`로 기존 DB를 지우지 마세요.

## 환경 변수

- 루트 `.env`: 단일 Docker Compose 구성이 읽는 비밀값과 접속 설정입니다.
- 루트 `.env.example`: Git에 올리는 단일 서버 설정 예시입니다.
- `Back/spring-server/.env`: Docker 없이 Spring Boot를 직접 실행할 때 쓰는 값입니다.
- `Front/app_version/.env`: Flutter 앱의 공개 설정값입니다.
- 실제 `.env` 파일은 Git에 올리지 않고 예시 파일만 추적합니다.

Windows 앱 잠금 PIN은 Credential Manager에 저장합니다. Ubuntu 백엔드가 사용하는 API Key, access token, 계좌번호는 서버의 루트 `.env`로 관리하며 저장소에 커밋하지 않습니다. 인증서와 로컬 DB 백업 역시 저장소 밖에서 별도로 보호합니다.

## 참고 문서

- [최신 개발 로드맵: 실시간 AI 단기 자동매매](docs/realtime-trading-roadmap.md)
- [목표 시스템 아키텍처와 구조도](docs/target-system-architecture.md)
- [R0 API 지원·계약 매트릭스](docs/trading-api-contract-matrix.md)
- [KB 문의 관련 계약 보류·재개 조건](docs/kb-contract-blockers.md)
- [단기·중기·최종 목표와 초기 운용·측정 초안](docs/initial-trading-policy.md)
- [개발 진척도: 신규 단계와 기존 구현 이력](docs/development-progress.md)
- [개인용 Windows 투자 어시스턴트 기존 설계·구현 이력](docs/personal-windows-investment-assistant.md)
- [API 명세](docs/api-spec.md)
- [데이터베이스 스키마](docs/database-schema.md)
- [Docker 구조](docs/docker-architecture.md)
- [실제 기능 테스트 가이드](docs/manual-test-guide.md)
