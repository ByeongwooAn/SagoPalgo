# 사고팔고 Spring Boot API 서버

이 폴더는 사고팔고 개인용 Windows 프로그램의 로컬 백엔드 API 서버입니다. 현재 단계에서는 개인용 로컬 사용자 모드, 자본금, 보유 종목, 관심 종목, 대시보드 스냅샷 API를 구현했습니다.

## 실행 전 준비

1. MySQL에서 `Back/database/schema.sql`을 실행해 `sagopalgo` 데이터베이스와 기본 테이블을 생성합니다.
2. `.env.example`을 참고해 `Back/spring-server/.env`에 DB 접속 정보와 개인용 모드 설정을 입력합니다.
3. 실제 국내 주식 현재가를 확인하려면 한국투자증권 Open API App Key/Secret을 입력하고 `SAGOPALGO_KIS_ENABLED=true`로 켭니다.
4. 서버 시작 시 `.env`가 자동으로 로드되며, 배포 환경에서는 OS 환경 변수가 `.env`보다 우선합니다.
5. 아래 명령으로 테스트를 실행합니다.

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

개인용 모드(`SAGOPALGO_PERSONAL_MODE_ENABLED=true`)에서는 대시보드, 자본금, 보유 종목, 관심 종목 API를 JWT 없이 호출할 수 있습니다. 서버는 `SAGOPALGO_PERSONAL_MODE_USER_ID`에 지정된 로컬 사용자 ID를 현재 사용자로 사용합니다. Auth API는 과거 소셜 로그인 구조와 테스트 호환을 위해 남겨둔 레거시 엔드포인트입니다.

## MVP 추천/시세 기준

- `MarketPriceService`는 한국투자증권 Open API 설정이 켜진 KOSPI/KOSDAQ/KONEX 종목이면 `/oauth2/tokenP`로 access token을 발급받고 국내주식 현재가 시세 API에서 현재가를 조회합니다.
- KIS 설정이 꺼져 있거나 아직 지원하지 않는 해외 시장 종목이면 임의 샘플 가격을 만들지 않고, 사용자가 등록한 매수가를 기준값으로 반환합니다.
- KIS 설정이 켜진 국내 종목에서 토큰 발급 또는 현재가 조회가 실패하면 `EXTERNAL_DATA_ERROR`를 반환해 외부 데이터 오류를 숨기지 않습니다.
- `DashboardRecommendationEngine`은 실제 보유 종목이 있을 때만 수익률, 손절 기준, 익절 기준을 보고 `보유 유지`, `부분 익절 검토`, `손절 감시` 중 하나를 대표 추천으로 반환합니다.
- 보유 종목이 없으면 대시보드 스냅샷의 `recommendation`은 `null`, `alerts`는 빈 배열입니다.
- Python AI 서버가 붙으면 추천 서비스 경계를 실제 AI 분석 클라이언트로 교체하고, `/api/v1/dashboard/snapshot` 응답 계약은 유지하는 방향입니다.

## 개인용 사용자 기준

- 개인용 모드가 켜져 있으면 별도 로그인 없이 로컬 사용자 1명으로 API 요청을 처리합니다.
- 서버 시작 시 로컬 사용자 행이 없으면 `users` 테이블에 `LOCAL/personal-owner` 사용자를 준비합니다.
- 기존 `users.user_id` FK 구조는 보유 종목, 관심 종목, 분석 결과를 로컬 사용자 데이터로 묶기 위해 유지합니다.
- Google/Naver 로그인 API는 현재 앱 화면에서는 사용하지 않습니다.
- 추후 보안은 소셜 로그인 대신 앱 잠금 PIN, Windows Credential Manager, 주문 전 재확인으로 대체합니다.

## 다음 구현 후보

1. KB/KIS/Toss Provider 설정 화면과 로컬 저장소 설계
2. KB증권 Open API 계좌 조회 연동
3. 뉴스/OpenDART Provider 연동
4. AI 분석 엔진 연결
5. 앱 잠금 PIN 또는 Windows Credential Manager 기반 민감정보 보호
