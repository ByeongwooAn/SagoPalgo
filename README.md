# SagoPalgo

SagoPalgo는 개인용 Windows 투자 프로그램입니다. 최종 목표는 KB증권 실계좌를 기준으로 실시간 시장 데이터·뉴스·공시·수급을 분석하고, 검증된 AI·전략이 운용 한도 안에서 종목·금액·매매 시점을 판단하는 단기 자동매매 시스템입니다.
현재는 계좌 조회·규칙 기반 분석·알림·모의매매·제한된 승인형 주문을 구현한 상태이며, 실시간 수집·학습 모델·자동매매는 단계적으로 개발합니다.

최근에는 [H04 합병·분할 종료보고서 전수 대조](docs/historical-data/corporate-actions/historical-restructuring-census.md)에서 기존 후보 351건과 별도 발행실적보고서 68건의 본문을 대조했습니다. [현재 개발 진척도](docs/project/numbered-work-progress.md#현재-개발-진척도)는 **27/46 · 59%**입니다. [프로젝트·AI 작업 단위별 진척도](docs/project/project-and-ai-progress.md)에서 구현과 검증 범위를, [보류 작업](docs/project/deferred-work.md)에서 재개 조건과 진척을 확인할 수 있습니다.

## 삼성전자·SK하이닉스 1차 학습 프로토타입

삼성전자(005930)와 SK하이닉스(000660)에 **L2 로지스틱 회귀를 한 종목당 하나씩** 적용합니다. 장 마감까지 확정된 가격·거래량 특징 7개로 다음 개장일에 종가가 시가보다 높을 확률을 추정합니다. 가중치 7개와 절편으로 계산해 한 종목의 제한된 학습 표본에서 먼저 검증하기 쉽고, 날짜별로 어떤 특징이 점수를 높이거나 낮췄는지 확인할 수 있습니다. [로지스틱 회귀의 원리·계산 예시·다른 모델과의 비교](docs/project/logistic-regression-baseline.md)

두 종목의 원주가 일봉을 각각 730건 확보·감사하고 공통 학습 424일·검증 141일·최종 평가 142일을 고정했습니다. **다음은 종목별 로컬 모델 학습과 독립 평가**입니다. 가격 모델의 앱·모의매매 검증을 마친 뒤 수급·공시·뉴스의 추가 효과를 비교합니다. [고정 학습·평가 구간](docs/project/hynix-daily-training-input.md#공통-날짜-확정) · [단계별 계획](docs/project/learning-prototype.md#실행-순서와-완료-기준)

## 프로젝트 방향

- 공개 앱스토어 출시나 상용 SaaS 운영이 아닌 개인용 Windows 프로그램을 우선합니다.
- 실제 계좌 조회, 주문, 체결 등 금융 업무는 KB증권 Open API만 사용합니다.
- KIS와 Toss Open API는 계좌/주문 연동 없이 읽기 전용 시장 데이터 Provider로 사용합니다.
- 같은 현재가를 여러 증권사에서 매번 합치지 않고, 기본 Provider와 fallback Provider를 분리합니다.
- 실시간 수집·시장 전체 탐색·과거 데이터 학습·AI 자금 배분을 개발하고, 재현 검증·실시간 모의·제한 실거래 검증을 거쳐 자동매매를 도입합니다.
- 국내 대상 시장의 온주 단타를 현재 개발 범위로 삼습니다. 소수점 상품과 추가 시장은 [보류 작업](docs/project/deferred-work.md)에서 관리합니다.

향후 개발 기준은 [실시간 AI 단기 자동매매 로드맵](docs/project/realtime-trading-roadmap.md)입니다. [목표 아키텍처](docs/architecture/target-system-architecture.md), [현재 배포 구조](docs/architecture/docker-architecture.md), [개발 진척도](docs/project/development-progress.md)를 구분해 확인하세요. [기존 설계·구현 이력](docs/architecture/personal-windows-investment-assistant.md)은 보존합니다.

아래 과거 데이터 검증 문단의 진척률은 각 검증 당시의 범위를 기준으로 합니다. 과거 데이터 후속은 [KRX 기간 전체 종목 목록·관찰 변화 수집](docs/historical-data/universe/krx-universe-history.md)입니다. 날짜별 원문·호출 예산·중단 재개·사건 경계 대조를 관리합니다. 종목 목록 확보와 거래일/거래정지·기업행사·학습 가능 여부는 구분합니다.

최신 후속은 [장중 거래중단·단일가와 재현 엔진 연결](docs/historical-data/replay/intraday-session-replay.md)입니다. CB 17쌍·프로그램 호가 정지 100개를 시장/날짜 100개·제한 구간 134개로 연결하고 주문 판단/체결 분봉에 적용합니다. 부분·늦은 근거는 체결을 보류하며 일반 후보 1,448개를 확정하지 않습니다. [Windows 파일 게시 복구](docs/operations/windows-file-publication.md)에서 일시 잠금의 제한 재시도·영구 실패 보존을 추가해 기존 1,062건과 신규 17건, 전체 **1,079건을 0실패로 확인**했습니다. 5-08 진행 중·5번 39%·1~5번 54% 유지입니다.

직전 후속은 [추가 공지 양식·발표 경계·정정과 세션 판단](docs/historical-data/sessions/session-coverage-boundary-review.md)입니다. 추가 검색 170개·176페이지·고유 본문 235개를 검토해 CB 발동/해제 18쌍을 연결했습니다. 목표 기간 안 17개 시장/날짜에 장중 중단이 확인됐으며 일반 후보 1,448개는 날짜별 근거·사유와 함께 확정 보류로 기록했습니다. 전체 회귀 1,018건 통과, 5-08 진행 중·5번 39%·1~5번 54% 유지입니다.

직전 후속은 [임시 거래시간 변경 공지 목록·본문 검토](docs/historical-data/sessions/session-exception-notice-inventory.md)입니다. 16개 검색·40페이지의 공시 2,622건과 본문 75개를 확보해 8개 구간의 선택 범위를 검토했습니다. 기존 특수 세션 12개 시장/날짜를 재확인하고 범위 밖 2개는 분리했습니다. 추가 양식·발표 경계·전체 정정 계보는 남아 일반 후보 1,448개는 승격하지 않습니다. 전체 회귀 984건 통과, 5-08 진행 중·5번 39%·1~5번 54%를 유지합니다.

직전 후속은 [코스닥 과거 전문·위임 시행일과 규정 V2](docs/historical-data/sessions/kosdaq-rule-effective-evidence.md)입니다. 제2280호의 올바른 전문과 시행세칙 제2304호 부칙에 따른 2025-03-04 시행일을 확인해 규정 15/15개의 연결을 보강했습니다. 임시 변경은 두 시장·4개 연도의 8구간으로 검토 계획을 생성했으며 일반 후보 1,448개는 실제 세션에 넣지 않습니다. 전체 회귀 948건 통과, 5-08 진행 중·5번 39%·1~5번 54%를 유지합니다.

규정 V1 후속은 [과거 일반 정규장 규정 판본 검증](docs/historical-data/sessions/historical-ordinary-session-rules.md)입니다. 15개 판본 중 14개 본문이 일치하며 KOSPI 8개 판본·7구간의 명목 시간을 확인했습니다. 코스닥 제53차 요청에 제52차 본문이 반환된 1건과 임시 변경의 전체 대조가 남아 일반 후보를 확정 세션에 넣지 않습니다. 전체 AI 서버 911건 통과, 5-08 진행 중·5번 7/18·39%·1~5번 26/48·54%를 유지합니다.

직전 후속은 [전체 기간 개장 여부 재구성·특수 세션 확대](docs/historical-data/sessions/market-calendar-session-coverage.md)입니다. KRX 근거로 두 시장의 1,098일을 개장 730·주말 314·기타 휴장 54일로 재구성하고 시장별 6일의 특수 세션을 확인했습니다. 일반 시간 후보와 미확인 달력 플래그는 남겨 전체 5-08 진행 중을 유지합니다. V7의 개별 공시 576/577건·폐지일 충돌 1건과 원래 관찰은 보존합니다.

## 개인 사용 및 책임 고지

본 프로젝트는 개인 학습 및 개인 투자 분석 보조용 오픈소스입니다.
본 프로젝트는 투자 권유, 투자자문, 수익 보장 서비스를 제공하지 않습니다.
사용자는 각 증권사 Open API 약관과 관련 법령을 직접 확인한 뒤 본인 책임하에 사용해야 합니다.
API Key, 계좌정보, 토큰 등 민감정보를 저장소에 커밋하지 마세요.

## 목표 기능

- KB증권 계좌 조회, 보유 주식 조회, 평가손익 분석
- 국내 대상 시장 주식의 현재가, 캔들, 거래량, 시장 지표 조회
- 뉴스와 공시 기반 종목별 AI 분석
- 관심종목, 보유종목, 리스크 신호 알림
- 항상 화면 위에 띄울 수 있는 미니 위젯 모드
- 실시간 시세·호가·분봉과 제공 주기에 맞는 투자자별 수급·뉴스·공시 갱신
- 시장 전체 유망 후보 탐색, 다년간 데이터 학습과 비용 포함 전략 검증
- AI 목표 비중·실잔고·미체결 예약을 반영한 분산 투자와 검증된 자동 주문
- 일·주·월·연 실계좌 수익·포트폴리오 차트

현재 완료 범위와 검증은 [개발 로드맵](docs/project/realtime-trading-roadmap.md)을 따릅니다. 기존 구현과 보류한 확장 항목은 [개발 진척도](docs/project/development-progress.md)와 [보류 작업](docs/project/deferred-work.md)에서 확인할 수 있습니다.

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

위 이미지는 현재 배포 구조입니다. 신규 데이터 수집·학습·자동 주문의 연결은 [목표 시스템 구조도](docs/architecture/target-system-architecture.md)에서 확인할 수 있습니다.

## 백엔드 실행

루트 `.env.example`을 `.env`로 복사한 뒤 비밀번호와 Provider 설정을 입력합니다. 새 설치라면 이름이 같은 DB 볼륨을 한 번 생성합니다. 기존 설치는 새 볼륨을 만들지 말고 [기존 설치 전환 절차](docs/architecture/docker-architecture.md#3-실행과-기존-설치-전환)를 먼저 확인하세요.

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

**위 복사·볼륨 생성 명령은 새 설치에서만 사용합니다.** 기존 Ubuntu 배포는 먼저 실제 볼륨 이름을 확인하고 DB 백업을 확보한 뒤 기존 설정값을 루트 `.env`로 옮겨야 합니다. KB 점검 이력의 `014` 마이그레이션 절차도 [Docker 구조 문서](docs/architecture/docker-architecture.md#기존-ubuntu-db의-kb-점검-이력-테이블)에 있습니다. `down -v`로 기존 DB를 지우지 마세요.

## 환경 변수

- 루트 `.env`: 단일 Docker Compose 구성이 읽는 비밀값과 접속 설정입니다.
- 루트 `.env.example`: Git에 올리는 단일 서버 설정 예시입니다.
- `Back/spring-server/.env`: Docker 없이 Spring Boot를 직접 실행할 때 쓰는 값입니다.
- `Front/app_version/.env`: Flutter 앱의 공개 설정값입니다.
- 실제 `.env` 파일은 Git에 올리지 않고 예시 파일만 추적합니다.

Windows 앱 잠금 PIN은 Credential Manager에 저장합니다. Ubuntu 백엔드가 사용하는 API Key, access token, 계좌번호는 서버의 루트 `.env`로 관리하며 저장소에 커밋하지 않습니다. 인증서와 로컬 DB 백업 역시 저장소 밖에서 별도로 보호합니다.

## 참고 문서

- [주제별 문서 목차](docs/README.md)
- [최신 개발 로드맵: 실시간 AI 단기 자동매매](docs/project/realtime-trading-roadmap.md)
- [목표 시스템 아키텍처와 구조도](docs/architecture/target-system-architecture.md)
- [R0 API 지원·계약 매트릭스](docs/contracts/trading-api-contract-matrix.md)
- [KB 문의 관련 계약 보류·재개 조건](docs/contracts/kb-contract-blockers.md)
- [단기·중기·최종 목표와 초기 운용·측정 초안](docs/project/initial-trading-policy.md)
- [개발 진척도: 신규 단계와 기존 구현 이력](docs/project/development-progress.md)
- [개인용 Windows 투자 어시스턴트 기존 설계·구현 이력](docs/architecture/personal-windows-investment-assistant.md)
- [API 명세](docs/contracts/api-spec.md)
- [데이터베이스 스키마](docs/contracts/database-schema.md)
- [Docker 구조](docs/architecture/docker-architecture.md)
- [실제 기능 테스트 가이드](docs/operations/manual-test-guide.md)
