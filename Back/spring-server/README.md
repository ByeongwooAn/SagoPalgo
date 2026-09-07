# 사고팔고 Spring Boot API 서버

이 폴더는 사고팔고 앱의 백엔드 API 서버입니다. 현재 단계에서는 Google/Naver 소셜 로그인, 토큰 재발급, 로그아웃 API를 구현했습니다.

## 실행 전 준비

1. MySQL에서 `Back/database/schema.sql`을 실행해 `sagopalgo` 데이터베이스와 기본 테이블을 생성합니다.
2. `.env.example`을 참고해 `Back/spring-server/.env`에 DB 접속 정보, JWT secret, 소셜 로그인 설정을 입력합니다.
3. 서버 시작 시 `.env`가 자동으로 로드되며, 배포 환경에서는 OS 환경 변수가 `.env`보다 우선합니다.
4. 아래 명령으로 테스트를 실행합니다.

```powershell
.\gradlew.bat '-Dorg.gradle.project.buildDir=build-codex' test --no-daemon
```

## 현재 구현된 API

| 기능 | 메서드 | 경로 |
| --- | --- | --- |
| Google 로그인 | POST | `/api/v1/auth/google` |
| Naver 로그인 | POST | `/api/v1/auth/naver` |
| 토큰 재발급 | POST | `/api/v1/auth/refresh` |
| 로그아웃 | POST | `/api/v1/auth/logout` |

## 소셜 로그인 토큰 기준

- Google 로그인은 앱에서 받은 ID token을 `providerToken`으로 서버에 전달합니다.
- 서버는 Google OpenID Connect JWKS 공개키로 ID token 서명을 검증하고, `aud`, `iss`, `exp`를 확인합니다.
- Google 사용자는 이메일이 아니라 Google ID token의 `sub` 값으로 식별합니다.
- Naver 로그인은 앱에서 받은 access token을 `providerToken`으로 서버에 전달합니다.
- 서버는 Naver 회원 프로필 조회 API를 호출하고, 응답의 `response.id` 값으로 사용자를 식별합니다.

## 다음 구현 후보

1. 자본금 조회/수정 API 구현
2. 관심 종목 API 구현
3. 인증된 사용자 ID를 공통으로 꺼내는 컨트롤러 헬퍼 정리
4. 통합 테스트용 테스트 DB 구성
5. Flutter 앱 로그인 화면과 API 연동
