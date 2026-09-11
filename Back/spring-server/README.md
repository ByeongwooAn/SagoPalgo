# 사고팔고 Spring Boot API 서버

이 폴더는 사고팔고 앱의 백엔드 API 서버입니다. 현재 단계에서는 Google/Naver 소셜 로그인, 토큰 재발급, 로그아웃, 자본금, 보유 종목, 관심 종목, 대시보드 스냅샷 API를 구현했습니다.

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
| Naver 로그인 URL 생성 | GET | `/api/v1/auth/naver/authorization-url` |
| Naver 로그인 | POST | `/api/v1/auth/naver` |
| 토큰 재발급 | POST | `/api/v1/auth/refresh` |
| 로그아웃 | POST | `/api/v1/auth/logout` |
| 대시보드 스냅샷 조회 | GET | `/api/v1/dashboard/snapshot` |
| 자본금 조회 | GET | `/api/v1/capital` |
| 자본금 수정 | PUT | `/api/v1/capital` |
| 관심 종목 목록 조회 | GET | `/api/v1/watchlist` |
| 관심 종목 등록 | POST | `/api/v1/watchlist` |
| 관심 종목 알림 설정 | PATCH | `/api/v1/watchlist/{watchlistId}/alert` |
| 관심 종목 삭제 | DELETE | `/api/v1/watchlist/{watchlistId}` |
| 보유 종목 목록 조회 | GET | `/api/v1/holdings` |
| 보유 종목 등록 | POST | `/api/v1/holdings` |
| 보유 종목 수정 | PUT | `/api/v1/holdings/{holdingId}` |
| 보유 종목 삭제 | DELETE | `/api/v1/holdings/{holdingId}` |

## MVP 추천/시세 기준

- `MarketPriceService`는 외부 시세 API가 붙기 전까지 샘플 종목의 결정적 현재가를 제공합니다.
- `DashboardRecommendationEngine`은 보유 종목의 수익률, 손절 기준, 익절 기준을 보고 `강한 매수`, `보유 유지`, `부분 익절 검토`, `손절 감시` 중 하나를 대표 추천으로 반환합니다.
- Python AI 서버가 붙으면 이 두 서비스 경계를 실제 시세/AI 분석 클라이언트로 교체하고, `/api/v1/dashboard/snapshot` 응답 계약은 유지하는 방향입니다.

## 소셜 로그인 토큰 기준

- Google 로그인은 앱에서 받은 ID token을 `providerToken`으로 서버에 전달합니다.
- 서버는 Google OpenID Connect JWKS 공개키로 ID token 서명을 검증하고, `aud`, `iss`, `exp`를 확인합니다.
- Google 사용자는 이메일이 아니라 Google ID token의 `sub` 값으로 식별합니다.
- Naver 로그인은 앱이 받은 authorization code와 state를 서버에 전달합니다.
- 서버는 `.env.dev`/`.env.prod`의 Naver Client Secret으로 access token을 교환한 뒤 회원 프로필 API를 호출하고, 응답의 `response.id` 값으로 사용자를 식별합니다.

## 다음 구현 후보

1. 실제 Google/Naver SDK callback을 Android 기기에서 검증
2. 실제 시세 API 또는 Python AI 서버 컨테이너 연결
3. 추천 목록/상세 API와 알림 API 구현
4. 통합 테스트용 테스트 DB 구성
5. 인증된 사용자 ID를 공통으로 꺼내는 컨트롤러 헬퍼 정리
