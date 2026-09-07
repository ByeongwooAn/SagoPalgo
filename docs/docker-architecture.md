# 사고팔고 Docker 구조

이 문서는 사고팔고 프로젝트를 Docker로 관리할 때의 권장 구조와 HTTPS 적용 방식을 정리합니다.

## 1. 관리 범위

Docker는 서버 실행 환경을 고정하는 데 사용합니다.

| 영역 | Docker 관리 여부 | 이유 |
| --- | --- | --- |
| Spring Boot API | 관리 | 서버 실행 환경과 환경 변수를 고정하기 좋음 |
| MySQL | 관리 | 로컬 설치 없이 같은 DB 버전을 맞출 수 있음 |
| Nginx reverse proxy | 관리 | HTTPS 종단, 프록시 경로, timeout, 요청 제한을 한곳에서 관리 가능 |
| Flutter Android 앱 | 로컬 실행 | 에뮬레이터, USB 기기, Flutter SDK 연동이 Docker보다 로컬이 편함 |
| Python AI 서버 | 추후 관리 | AI 서버 구현 후 독립 컨테이너로 추가 |
| Redis | 추후 관리 | 캐시/알림 큐/스케줄링이 필요할 때 추가 |

## 2. 현재 Compose 서비스

```text
docker-compose.yml
├─ mysql          공통 DB 서비스 정의
├─ spring-api     공통 API 서비스 정의
└─ reverse-proxy  공통 Nginx 서비스 정의

docker-compose.dev.yml
├─ mysql          개발용 DB 포트 공개
├─ spring-api     개발용 API 포트 공개
└─ reverse-proxy  개발용 HTTP Nginx 템플릿 적용

docker-compose.prod.yml
├─ mysql          외부 포트 비공개
├─ spring-api     외부 포트 비공개
└─ reverse-proxy  운영용 80/443 포트와 HTTPS Nginx 템플릿 적용
```

`mysql`은 `Back/database/schema.sql`을 컨테이너 최초 생성 시 자동 실행합니다. 이미 MySQL volume이 만들어진 뒤에는 init SQL이 다시 실행되지 않으므로, 스키마를 다시 만들려면 volume 삭제가 필요합니다.

`spring-api`는 Compose가 `--env-file`로 받은 `.env.dev` 또는 `.env.prod` 값을 컨테이너 환경 변수로 주입합니다. 컨테이너 내부에서는 DB 주소가 `mysql:3306`입니다.

`reverse-proxy`는 Nginx가 `spring-api:8080`으로 요청을 넘깁니다.

## 3. 실행 명령어

개발 환경은 로컬 디버깅을 위해 MySQL, Spring API, Nginx HTTP 포트를 모두 호스트에 공개합니다.

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml --env-file .env.dev up -d --build
docker compose -f docker-compose.yml -f docker-compose.dev.yml --env-file .env.dev ps
Invoke-WebRequest -Uri http://localhost:8081/health -UseBasicParsing
```

운영 환경은 Nginx의 80/443 포트만 외부에 공개하고, DB와 Spring API는 Docker 내부 네트워크에 둡니다.

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.prod up -d --build
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.prod ps
curl -i https://api.sagopalgo.app/health
```

## 4. HTTPS 전략

운영 환경에서는 HTTPS를 기본으로 사용해야 합니다.

- access token과 refresh token이 네트워크를 지나가므로 HTTPS가 필요합니다.
- Google/Naver 소셜 로그인 이후 앱과 서버가 교환하는 사고팔고 JWT도 HTTPS로 보호해야 합니다.
- 운영에서는 Nginx, Cloudflare, AWS ALB 같은 앞단에서 TLS를 종료하고 Spring Boot는 내부 HTTP로 두는 구성이 일반적입니다.

로컬 개발에서는 인증서 관리 부담을 줄이기 위해 HTTP 경로를 기본으로 엽니다.

| 용도 | URL | 설명 |
| --- | --- | --- |
| 직접 API 접근 | `http://localhost:8080` | 빠른 로컬 개발용 |
| HTTP 프록시 | `http://localhost:8081` | Nginx 경유 확인용 |

Android 에뮬레이터는 로컬 개발 중 `http://10.0.2.2:8080` 또는 `http://10.0.2.2:8081`을 사용합니다. 운영 환경에서는 실제 도메인과 인증서를 붙인 `https://api...` 주소를 사용해야 합니다.

## 5. 도메인 전략

사고팔고는 Portal-IT와 성격이 다른 별도 사용자 서비스이므로, 운영 기준으로는 새 도메인을 Cloudflare에서 구매하는 편이 좋습니다.

| 선택지 | 추천도 | 설명 |
| --- | --- | --- |
| 새 도메인 구매 | 높음 | 브랜딩, OAuth 설정, SSL 인증서, 장애 범위를 Portal-IT와 분리 가능 |
| Portal-IT 도메인의 서브도메인 사용 | 보통 | 비용 없이 빠르게 시작 가능하지만 서비스 경계가 흐려질 수 있음 |
| Portal-IT와 완전히 같은 도메인/경로 사용 | 낮음 | 인증, 쿠키, 라우팅, 운영 장애 범위가 섞일 수 있음 |

도메인은 `sagopalgo.app`으로 확정합니다. 운영 API는 `api.sagopalgo.app`, 서비스/소개 페이지는 `www.sagopalgo.app` 또는 `app.sagopalgo.app`을 기준으로 잡습니다.

## 6. 운영 HTTPS 적용 순서

1. Cloudflare에서 사고팔고 도메인 또는 서브도메인을 준비합니다.
2. DNS A 레코드를 배포 서버 IP로 연결합니다.
3. `.env.prod`의 `SAGOPALGO_NGINX_SERVER_NAME`은 `api.sagopalgo.app`을 기준으로 사용합니다.
4. Let's Encrypt 또는 Cloudflare Origin Certificate 경로를 `.env.prod`의 `SAGOPALGO_NGINX_CERTS_DIR`로 Nginx에 마운트합니다.
5. Flutter `Front/app_version/.env`의 `SAGOPALGO_API_BASE_URL`을 `https://api.sagopalgo.app`으로 둡니다.

## 7. 다음 확장

1. Python AI 서버가 생기면 `ai-server` 서비스를 추가합니다.
2. Spring Boot에서 AI 서버를 `http://ai-server:{port}`로 호출하도록 환경 변수를 추가합니다.
3. 알림 큐나 캐시가 필요해지면 `redis` 서비스를 추가합니다.
4. 운영 배포 시에는 Nginx HTTPS 설정을 실제 도메인 기준으로 분리합니다.
