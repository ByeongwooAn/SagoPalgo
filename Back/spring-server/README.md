# 사고팔고 Spring Boot API 서버

이 폴더는 사고팔고 개인용 Windows 프로그램의 로컬 백엔드입니다. 로그인이나 다중 사용자 가입 흐름 없이 로컬 사용자 한 명을 기준으로 계좌, 보유 종목, 관심 종목, 시장 데이터, 뉴스와 공시를 조회합니다.

## 실행 전 준비

1. MySQL에서 `Back/database/schema.sql`을 실행해 데이터베이스와 기본 테이블을 생성합니다.
2. `.env.example`을 참고해 `Back/spring-server/.env`에 DB 접속 정보와 사용할 Provider 설정을 입력합니다.
3. 실제 데이터를 조회할 Provider만 `*_ENABLED=true`로 켭니다. 키가 없거나 사용하지 않는 Provider는 `false`로 둡니다.
4. 서버 시작 시 `.env`가 자동으로 로드되며, OS 환경 변수가 `.env`보다 우선합니다.
5. 아래 명령으로 전체 테스트를 실행합니다.

```powershell
.\gradlew.bat '-Dorg.gradle.project.buildDir=build-codex' test --no-daemon
```

## 개인용 사용자 구조

- `SAGOPALGO_PERSONAL_MODE_ENABLED=true`이면 모든 사용자별 API를 JWT 없이 호출합니다.
- 서버는 `SAGOPALGO_PERSONAL_MODE_USER_ID`의 로컬 사용자를 현재 사용자로 사용합니다.
- 시작 시 사용자 행이 없으면 `LOCAL/personal-owner` 사용자를 준비합니다.
- `users.user_id` 관계는 보유 종목, 관심 종목, 분석 결과를 같은 로컬 소유자 데이터로 묶기 위해 유지합니다.
- Google/Naver 로그인, JWT 재발급, 로그아웃 API는 현재 코드에 없습니다.
- 앱 접근 보호는 선택형 앱 잠금 PIN을 사용하며, 주문 기능은 기본적으로 꺼져 있습니다.

## 현재 구현된 API

| 기능 | 메서드 | 경로 |
| --- | --- | --- |
| Provider 설정 상태 | GET | `/api/v1/settings/providers` |
| KB 계좌 목록 | GET | `/api/v1/kb/accounts` |
| KB 보유 주식 | GET | `/api/v1/kb/accounts/primary/holdings` |
| KB 결제기준 잔고 | GET | `/api/v1/kb/accounts/primary/balances/settlement` |
| KB 체결기준 잔고 | GET | `/api/v1/kb/accounts/primary/balances/execution` |
| 저장된 종목 뉴스·공시 조회 | GET | `/api/v1/research/feed` |
| 종목 뉴스·공시 외부 동기화 | POST | `/api/v1/research/feed/sync` |
| 대시보드 스냅샷 | GET | `/api/v1/dashboard/snapshot` |
| 자본금 조회·수정 | GET, PUT | `/api/v1/capital` |
| 관심 종목 목록·등록 | GET, POST | `/api/v1/watchlist` |
| 관심 종목 알림 설정 | PATCH | `/api/v1/watchlist/{watchlistId}/alert` |
| 관심 종목 삭제 | DELETE | `/api/v1/watchlist/{watchlistId}` |
| 보유 종목 목록·등록 | GET, POST | `/api/v1/holdings` |
| 보유 종목 수정·삭제 | PUT, DELETE | `/api/v1/holdings/{holdingId}` |

## 시장 데이터 Provider

- 현재가 조회 순서는 `KB → KIS → Toss`입니다.
- Provider가 비활성, 미지원, 미설정 또는 일시 실패 상태이면 다음 Provider를 시도합니다.
- 모든 Provider를 사용할 수 없으면 임의 가격을 만들지 않고 사용자가 등록한 매수가를 사용합니다.
- `/api/v1/settings/providers`는 활성화 여부, 누락된 설정 이름, fallback 순서를 반환하지만 실제 키와 계좌번호는 노출하지 않습니다.
- Toss는 공식 시세 API 경로가 확정되기 전까지 기본 URL과 경로가 비어 있어 자동으로 사용되지 않습니다.

## 뉴스·공시 Provider

네이버 뉴스 검색 API와 OpenDART 공시검색 API는 서로 독립적으로 동작합니다. `POST /sync`에서 한쪽 조회가 실패해도 다른 쪽 결과를 저장하고 Provider별 `SUCCESS`, `FAILED`, `DISABLED` 상태를 반환합니다. 일반 `GET`은 외부 API를 다시 호출하지 않고 로컬 DB만 조회합니다.

- 네이버 뉴스 검색: [공식 개발가이드](https://developers.naver.com/docs/serviceapi/search/news/news.md)
- OpenDART 공시검색: [공식 개발가이드](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019001)

```dotenv
SAGOPALGO_NAVER_NEWS_ENABLED=true
SAGOPALGO_NAVER_NEWS_CLIENT_ID=발급받은-client-id
SAGOPALGO_NAVER_NEWS_CLIENT_SECRET=발급받은-client-secret

SAGOPALGO_OPEN_DART_ENABLED=true
SAGOPALGO_OPEN_DART_API_KEY=발급받은-api-key
```

외부 동기화 후 저장 결과 조회 예시:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri 'http://localhost:8080/api/v1/research/feed/sync?stockCode=005930&stockName=삼성전자&fromDate=2026-08-01&toDate=2026-09-21'

Invoke-RestMethod `
  -Method Get `
  -Uri 'http://localhost:8080/api/v1/research/feed?stockCode=005930&stockName=삼성전자&fromDate=2026-08-01&toDate=2026-09-21'
```

- 뉴스 제목과 요약은 검색 강조 HTML을 제거해 저장 가능한 일반 문자열로 정규화합니다.
- OpenDART 고유번호 파일을 애플리케이션 메모리에 캐시하고 종목코드로 회사 고유번호를 자동 해석합니다.
- 공시 링크는 DART 원문 조회 주소로 구성합니다.
- 뉴스는 Provider, 종목코드, 원문 URL 기반 키로, 공시는 Provider와 접수번호로 중복을 제거합니다.
- 같은 데이터를 다시 동기화하면 새 행을 만들지 않고 저장값과 마지막 수집 시각을 갱신합니다.
- 날짜를 생략하면 종료일은 오늘, 시작일은 기본 30일 전입니다.

기존 MySQL 데이터 볼륨에는 [`Back/database/migrations/002_research_feed_storage.sql`](../database/migrations/002_research_feed_storage.sql)을 한 번 적용해야 합니다. 새 데이터 볼륨은 `Back/database/schema.sql`에서 두 저장 테이블을 함께 생성합니다.

## 추천 기준

- `DashboardRecommendationEngine`은 실제 보유 종목이 있을 때 수익률, 손절 기준, 익절 기준으로 `보유 유지`, `부분 익절 검토`, `손절 감시` 중 하나를 반환합니다.
- 보유 종목이 없으면 대시보드의 `recommendation`은 `null`, `alerts`는 빈 배열입니다.
- Python AI 서버가 연결되면 추천 서비스 경계를 실제 분석 클라이언트로 교체하되 `/api/v1/dashboard/snapshot` 계약은 유지합니다.

## 다음 구현 후보

1. 뉴스·공시 타임라인 Flutter 화면
2. 관심 종목 뉴스·공시 주기 동기화
3. 뉴스·공시·가격 흐름을 사용하는 AI 분석 엔진
4. Windows 로컬 알림
5. Windows Credential Manager 기반 민감정보 보호
