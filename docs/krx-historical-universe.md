# KRX 과거 기준일 종목군 수집과 승인 대기

**후속 완료:** 사용자의 승인/키 등록 후 [2023-11-01 실제 기준표 2,634행·보통주 2,517개와 교차 검증](krx-baseline-live-validation.md)을 확보했습니다. 아래는 승인 전 준비 작업의 기록이며, 승인 대기·0건·미완료 체크 상태는 당시 결과를 보존합니다. 최신 실행 결과와 V2 분류는 후속 문서를 따릅니다.

기준일: 2026-11-04. [기존 종목군 식별 목록](historical-universe-seed.md)의 후속으로 **2023-11-01 KOSPI·KOSDAQ 종목기본정보를 직접 받는 수집기**를 구현했습니다. 사용자가 KRX 인증키·API 이용 신청 전 상태임을 확인했습니다. 현재 실제 과거 목록은 **0건**, 두 시장 모두 미수집이며 기준표 확보 완료로 계산하지 않습니다.

## 공식 경로와 확인 범위

KRX 공식 [유가증권 종목기본정보](https://openapi.krx.co.kr/contents/OPP/USES/service/OPPUSES002_S2.cmd?BO_ID=PiwgMdTwmsenXhmqqxuj)와 [코스닥 종목기본정보](https://openapi.krx.co.kr/contents/OPP/USES/service/OPPUSES002_S2.cmd?BO_ID=CifLHplnUFMgpHIMMPXs)는 2010-01-04부터 자료를 제공한다고 안내합니다. 유가증권 개발 명세서와 두 시장의 공식 샘플 UI에서 `basDd` 기준일자 인자, API 이름과 12개 응답 필드를 확인했습니다. 표준/단축코드·종목명·상장일·시장·증권구분·주식종류 등이 포함됩니다.

운영 요청은 `https://data-dbg.krx.co.kr/svc/apis/sto/` 아래 `stk_isu_base_info`/`ksq_isu_base_info`에 `basDd=20231101`을 전달합니다. 인증값은 `AUTH_KEY` 헤더에만 넣습니다. 승인된 사용자 키로 운영 응답을 받은 검증은 아직 수행하지 않았습니다.

공식 샘플 전용 경로에서 각 시장 10행, 총 20행을 받아 같은 파서로 필드와 분류를 확인했습니다. 샘플의 기준 인자는 공식 예제의 2020-04-14이며 `OFFICIAL_SAMPLE`로만 기록했습니다. 실제 기준표에 넣거나 사용자 운영 키로 받은 자료로 승격하지 않습니다. 공개 Data Marketplace의 전종목 기본정보 화면도 연결한 브라우저에서 로그인/회원가입을 요구해 실제 목록을 내려받지 못했습니다.

## 사용자가 준비할 항목

KRX의 [공식 이용 절차](https://openapi.krx.co.kr/contents/OPP/INFO/OPPINFO003.jsp)에 따라 다음을 진행해야 합니다.

1. KRX Data Marketplace 회원가입/로그인 후 OPEN API 인증키를 신청하고 승인을 받습니다.
2. **유가증권 종목기본정보**, **코스닥 종목기본정보** 두 서비스를 각각 활용 신청하고 승인을 받습니다. 인증키 승인만으로 두 서비스 이용 승인까지 확인된 것으로 간주하지 않습니다.
3. 승인 후 프로젝트 루트 `.env`에 아래 두 값을 로컬로 설정합니다. 키는 채팅·Git·PR에 넣지 않습니다.

```dotenv
SAGOPALGO_KRX_OPEN_API_ENABLED=true
SAGOPALGO_KRX_AUTH_KEY=<승인된 인증키>
```

`.env.example`에는 기본 OFF와 빈 키만 추가했습니다. 새 CLI만 이 설정을 읽으며 `--env-file ../../.env`로 루트 파일을 명시하거나 프로세스 환경변수를 사용합니다. 다른 환경변수는 읽어 전파하지 않습니다. 프로세스에 이미 설정한 값이 파일보다 우선합니다. 실제 `.env`에 키를 생성하거나 사용자 계정의 인증키/이용 신청을 대신 제출하지 않았습니다.

## 구현한 동작

- `plan`: 기준일·두 시장·운영/가상 출처·**최대 요청 2회**를 해시로 고정합니다. 다른 기존 작업을 덮어쓰지 않습니다.
- `status`: 키 값 없이 등록 여부·활성 여부·시장별 확보 건수·사용 예산을 확인합니다. 서비스 승인은 실제 요청 전까지 미확인으로 표시합니다.
- `collect`: 활성 설정/키를 검사한 뒤 시장별 GET 1회를 예약합니다. 키가 없거나 OFF면 예약·운영 요청을 하지 않습니다. 첫 시장을 이미 저장한 정상 부분 작업은 두 번째 시장부터 진행합니다.
- `audit`: 원문·계획·영수증·파생 보고서와 중복 종목을 오프라인으로 검사합니다. 오류/중단 예약의 자동 재시도는 없습니다. 문제를 해결한 뒤 새 작업 경로로 명시적으로 시작하고 이전 기록을 보존합니다.
- `check`: 감사한 기존 공시와 두 시장의 기준일 응답을 대조합니다. 실제 응답이 없는 시장은 `PENDING_SOURCE`로 표시하며 종목이 없다는 검증에 통과한 것으로 계산하지 않습니다.

사용자 키는 URL·파일·출력에 기록하지 않습니다. 전송 실패/권한 거부는 고정 진단 코드로 반환하고 키가 응답에 그대로 반사되면 저장하지 않습니다. 리다이렉트·응답 크기·행 수를 제한하고 중복 JSON 키/NaN·열 변경·잘못된 코드/시장·미래 상장일·시장 간 동일 코드/ISIN 중복을 차단합니다. 안전하게 받은 원문이 분류/날짜 검증에서 실패해도 원문과 해시를 보존하고 해당 작업을 중단합니다.

## 분류와 대조 기준

종목코드는 영문 포함 6자와 선행 0을 보존합니다. 기존 숫자 6자리 시세 처리기의 지원 여부는 별도 필드로 표시합니다. `SECUGRP_NM`과 `KIND_STKCERT_TP_NM`을 함께 검사해 검토한 주권 유형의 보통주를 분류합니다. 우선주 등은 제외 사유를 남기며 알 수 없는 분류는 `UNREVIEWED_CLASSIFICATION`으로 보존합니다. 리츠/외국주권/예탁증권 등 공식 샘플에서 확인한 주권 유형도 종류 값을 보존합니다. 거래량이나 가격 필드로 종목을 제외하지 않습니다.

상장일이 기준일 이후인 응답은 현재 목록 또는 다른 기준일 자료가 섞였을 가능성으로 보고 실패합니다. 기준일은 요청 인자에서 온 값이므로 `dateBasis=REQUEST_BAS_DD`로 표시합니다. 과거 공개 시각은 만들어내지 않고 현재 수집 시각을 `knownAt`으로 유지합니다.

2023-11-01 기준으로 준비한 대조 항목은 다음 5개입니다.

| 종목 | 대조할 내용 | 현재 결과 |
|---|---|---|
| M83 | 2024년 신규상장이므로 2023-11-01 KOSDAQ 목록에 없어야 함 | 자료 대기 |
| 유진스팩7호 | 원문 상장일 이후·2024년 폐지일 이전이므로 KOSDAQ 목록에 있어야 함 | 자료 대기 |
| 엘앤에프 | 2024년 이전상장 전이므로 KOSDAQ에 있어야 함 | 자료 대기 |
| 엘앤에프 | 같은 기준일 KOSPI 목록에는 없어야 함 | 자료 대기 |
| 한국스팩11호 | 원문 상장일 이후·2024년 합병 사유 폐지일 이전이므로 KOSDAQ 목록에 있어야 함 | 자료 대기 |

이 검사는 나중에 확보한 공시로 공급자의 과거 응답을 **사후 대조**하는 검사입니다. 공시를 2023년 전략 입력으로 사용할 수 있다는 의미가 아닙니다. 일부 사례 일치만으로 전체 종목 수나 거래정지 종목의 포함을 증명하지 않으며 `independentTotalVerified=false`, `tradingHaltCoverageVerified=false`를 유지합니다. 실제 수집 후 독립 총수·정지 종목 대조와 기간 전체 이력 연결이 남습니다.

## 실행 방법

`AI/ai-server`에서 실행합니다. 이번에 다음 작업 경로를 이미 생성했습니다.

```powershell
# 준비된 작업 상태 확인: 운영 호출 없음
.\.venv\Scripts\python.exe -m app.replay.krx_universe status --job research-artifacts/krx-universe-20231101-20261104/job --env-file ../../.env

# 인증키 및 두 서비스 승인·로컬 설정 후 실행
.\.venv\Scripts\python.exe -m app.replay.krx_universe collect --job research-artifacts/krx-universe-20231101-20261104/job --env-file ../../.env

# 수집 결과의 오프라인 감사
.\.venv\Scripts\python.exe -m app.replay.krx_universe audit --job research-artifacts/krx-universe-20231101-20261104/job
```

새 작업은 `plan --date 2023-11-01 --output <새 경로>`로 생성합니다. `.env.example`의 OFF를 실제 승인 없이 켜서 호출하지 않습니다. 승인 전 준비 상태에서 대조 결과는 `comparison-pending.json`에 저장했습니다. 실제 수집 후에는 새 출력 경로로 실행합니다.

```powershell
.\.venv\Scripts\python.exe -m app.replay.krx_universe check `
  --job research-artifacts/krx-universe-20231101-20261104/job `
  --case-cache research-artifacts/kind-case-cache `
  --case-scope ../../docs/examples/kind-reference-cases.json `
  --case-report research-artifacts/kind-cases-20261103/report.json `
  --event-scope ../../docs/examples/universe-events.json `
  --event-report research-artifacts/universe-events-20261103/report.json `
  --output research-artifacts/krx-universe-20231101-20261104/comparison-collected.json
```

`maxRequests=2`는 이 작업 폴더의 **운영 요청 예산**입니다. 현재 사용 0회/남은 2회이며 인증키 없는 실패 점검은 소비하지 않았습니다. 공식 샘플 경로 2회는 별도 규격 점검이며 운영 예산 사용이나 실제 과거 목록 확보로 계산하지 않습니다. 승인/네트워크 오류로 실제 운영 요청을 보냈다면 그 예약은 소비된 것으로 남습니다. 계정 전체의 다른 프로그램 호출 한도를 관리하는 예산은 아닙니다.

## 완료와 남은 작업

- [x] 공식 개발 명세·요청 인자·응답 필드 확인
- [x] 두 시장 각 10행 공식 샘플 파싱 검증, 샘플 출처 유지
- [x] 기준일 수집·감사·부분 재개·분류·공시 대조 CLI와 설정 예시 구현
- [x] 인증키 없음/OFF에서 운영 요청·예약 0회 확인
- [x] 실제 기준일 계획과 5개 대조 항목 생성, 모두 자료 대기로 기록
- [x] 전체 AI 서버 **423건 통과, 실패/오류/건너뛰기 0건**(기존 392 + 신규 31). Java 저장 내보내기 fixture 포함, 기존 Starlette/AnyIO 경고 1건 유지
- [x] 추가 통신을 금지한 로컬 점검과 기존 가격/DART 파일 55개 해시 보존 확인
- [ ] 사용자 KRX 인증키 및 두 API 활용 신청·승인·로컬 설정
- [ ] 두 시장의 실제 2023-11-01 목록 수집과 보통주 분류 대조
- [ ] 5개 공시 대조·독립 총수·거래정지 종목 포함 여부 검증
- [ ] 시작 시점 기준표를 기간 전체 상장/폐지/이전상장 이력과 연결

수집기 구현과 실제 기준표 확보를 구분합니다. **현재 실제 과거 기준표 0건, 5-08 진행 중, 고정 완료율 7/18·39% 유지**입니다. 실제 원문·샘플·명세서·계획·대조 파일은 Git에서 제외한 `research-artifacts/`에 보관합니다. 학습·실주문·운영 배포·마이그레이션·EXE 변경은 없습니다.
