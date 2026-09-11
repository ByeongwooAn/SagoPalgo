# 사고팔고 Docker 구조

이 문서는 사고팔고를 개인용 Windows 투자 어시스턴트로 실행할 때의 Docker 관리 범위를 정리합니다. 현재 목표는 공개 서비스 배포가 아니라 내 PC에서 안정적으로 백엔드와 DB를 띄우는 것입니다.

## 1. 관리 범위

| 영역 | Docker 관리 여부 | 이유 |
| --- | --- | --- |
| Spring Boot API | 관리 | 로컬 실행 환경과 환경 변수를 고정하기 좋음 |
| MySQL | 관리 | PC에 직접 설치하지 않아도 같은 DB 버전을 사용할 수 있음 |
| Nginx reverse proxy | 선택 관리 | Spring API를 프록시 경유로 확인하거나 나중에 로컬 라우팅을 정리할 때 사용 |
| Flutter Windows 프로그램 | 로컬 실행 | Windows 빌드, 트레이, 창 고정, 위젯형 UI는 Flutter SDK와 Visual Studio 환경에서 직접 실행하는 편이 적합 |
| Python AI 서버 | 추후 관리 | AI 분석 서버를 분리하면 독립 컨테이너로 추가 |
| Redis | 추후 관리 | 알림 큐, 캐시, 스케줄링이 필요할 때 추가 |

## 2. 현재 Compose 서비스

```text
docker-compose.yml
├─ mysql          공통 DB 서비스 정의
├─ spring-api     공통 API 서비스 정의
└─ reverse-proxy  공통 Nginx 서비스 정의

docker-compose.dev.yml
├─ mysql          개발용 DB 포트 공개
├─ spring-api     개발용 API 포트 공개
└─ reverse-proxy  개발용 HTTP 프록시 공개

docker-compose.prod.yml
├─ mysql          DB 포트 비공개
├─ spring-api     API 포트 비공개
└─ reverse-proxy  개인 PC 고정 실행용 HTTP 프록시 공개
```

`mysql`은 `Back/database/schema.sql`을 컨테이너 최초 생성 시 자동 실행합니다. 이미 MySQL volume이 만들어진 뒤에는 init SQL이 다시 실행되지 않으므로, 스키마를 다시 만들려면 volume을 삭제하고 다시 생성해야 합니다.

`spring-api`는 Compose가 `--env-file`로 받은 `.env.dev` 또는 `.env.prod` 값을 컨테이너 환경 변수로 주입합니다. 컨테이너 내부에서는 DB 주소가 `mysql:3306`입니다.

`reverse-proxy`는 Nginx가 `spring-api:8080`으로 요청을 넘깁니다.

## 3. 실행 명령어

개발 중에는 MySQL, Spring API, Nginx HTTP 포트를 모두 호스트에 공개합니다.

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml --env-file .env.dev up -d --build
docker compose -f docker-compose.yml -f docker-compose.dev.yml --env-file .env.dev ps
Invoke-WebRequest -Uri http://localhost:8081/health -UseBasicParsing
```

개인 PC에서 백엔드 포트를 직접 열지 않고 프록시만 쓰고 싶다면 `docker-compose.prod.yml` 예시를 사용할 수 있습니다. 파일명은 기존 호환을 위해 유지하지만, 현재 의미는 공개 운영 배포가 아니라 로컬 고정 실행입니다.

```powershell
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.prod up -d --build
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.prod ps
Invoke-WebRequest -Uri http://localhost:8081/health -UseBasicParsing
```

## 4. 네트워크 기준

개인용 로컬 실행에서는 도메인, HTTPS, OAuth callback이 필요하지 않습니다.

| 용도 | URL | 설명 |
| --- | --- | --- |
| 직접 API 접근 | `http://localhost:8080` | 빠른 로컬 개발용 |
| HTTP 프록시 | `http://localhost:8081` | Nginx 경유 확인용 |
| Flutter Windows 기본 API | `http://localhost:8080` 또는 `http://localhost:8081` | 실행 방식에 맞춰 `Front/app_version/.env`에서 선택 |

인터넷에 공개되는 서버로 운영하지 않는 한 TLS 인증서와 운영 도메인은 필수 조건이 아닙니다. 다만 나중에 외부 접속, 원격 PC 접근, 모바일 재전환을 다시 고려하면 그때 HTTPS와 도메인 설계를 별도 문서로 되살립니다.

## 5. 민감정보 기준

- `.env`, `.env.dev`, `.env.prod`, `Back/spring-server/.env`는 저장소에 커밋하지 않는다.
- KB/KIS/Toss API Key, App Secret, 계좌번호는 예시 파일에는 빈 값 또는 placeholder만 둔다.
- 현재 백엔드는 로그인/JWT/OAuth를 사용하지 않는다.
- Spring API는 개인용 로컬 사용자 ID를 기준으로 보유 종목, 관심 종목, 자본금 데이터를 묶는다.

## 6. 다음 확장

1. Python AI 서버가 생기면 `ai-server` 서비스를 추가한다.
2. Spring Boot에서 AI 서버를 `http://ai-server:{port}`로 호출하도록 환경 변수를 추가한다.
3. 알림 큐나 캐시가 필요해지면 `redis` 서비스를 추가한다.
4. 자동 주문 기능을 붙이기 전에는 Docker 설정보다 주문 승인 흐름, 로그, 실패 복구 정책을 먼저 설계한다.
