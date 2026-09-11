# SagoPalgo

사고팔고는 Flutter Android 앱, Spring Boot API 서버, MySQL DB, 이후 Python AI 서버로 확장되는 AI 투자 어시스턴트 프로젝트입니다.

## Docker 구조

Docker Compose는 공통 파일과 환경별 override 파일로 나누어 관리합니다.

```text
docker-compose.yml       MySQL, Spring API, Nginx 공통 서비스 정의
docker-compose.dev.yml   개발용 포트 공개와 HTTP Nginx 템플릿
docker-compose.prod.yml  운영용 80/443 공개와 HTTPS Nginx 템플릿
```

Flutter 앱은 Android 에뮬레이터/기기 연결 때문에 Docker 밖에서 실행합니다. 앱은 `.env`의 API 주소로 Docker Compose에서 열린 백엔드에 접근합니다.

## 개발 환경 실행

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml --env-file .env.dev up -d --build
```

개발 환경 상태 확인:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml --env-file .env.dev ps
Invoke-WebRequest -Uri http://localhost:8081/health -UseBasicParsing
docker compose -f docker-compose.yml -f docker-compose.dev.yml --env-file .env.dev logs --tail=100 spring-api
```

직접 API 서버에 접근할 때는 `http://localhost:8080`, Nginx 프록시를 통해 접근할 때는 `http://localhost:8081`을 사용합니다.

API와 Flutter 앱을 실제로 연결해 확인하는 자세한 절차는 [실제 기능 테스트 가이드](docs/manual-test-guide.md)를 참고합니다.

## 운영 환경 실행

운영 서버에서는 `.env.prod`의 비밀번호, JWT secret, OAuth 값, 인증서 경로를 실제 운영 값으로 교체한 뒤 실행합니다.

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

운영 환경 상태 확인:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.prod ps
curl -i https://api.sagopalgo.app/health
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.prod logs --tail=100 reverse-proxy
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.prod logs --tail=100 spring-api
```

운영 환경에서는 Nginx에서 HTTPS를 종료하고 Spring Boot는 Docker 내부 네트워크에서 HTTP로 통신합니다.

## 도메인 기준

사고팔고가 Portal-IT와 별도 서비스라면 새 도메인을 Cloudflare에서 구매하는 것을 권장합니다. 초기 테스트나 내부 개발 단계에서는 기존 Portal-IT 도메인의 서브도메인으로 시작할 수 있습니다.

```text
api.sagopalgo.app
app.sagopalgo.app
www.sagopalgo.app
```

도메인은 `sagopalgo.app`으로 확정했으므로 운영 API 주소는 `https://api.sagopalgo.app`을 기준으로 둡니다.

## 환경 변수

- `.env.dev`: Docker 개발 환경이 읽는 값입니다.
- `.env.prod`: Docker 운영 환경이 읽는 값입니다.
- `.env.dev.example`, `.env.prod.example`: Git에 올리는 예시 파일입니다.
- `Back/spring-server/.env`: Docker 없이 Spring Boot를 직접 실행할 때 쓰는 값입니다.
- `Front/app_version/.env`: Flutter 앱에 포함되는 공개 설정값입니다.
- 실제 `.env*` 파일은 Git에 올리지 않고, `.env*.example`만 추적합니다.
