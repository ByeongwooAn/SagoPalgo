# KRX 기간 전체 종목 목록과 관찰 변화 이력

[H01 후속 대조](historical-membership-identity-audit.md)에서 시장마다 1,098일의 전체/보통주 수를 집계하고 별도 KRX 일별매매 9일·KOSIS 월말 35개월을 대조했습니다. 발행회사 식별과 전체 날짜의 독립 총수는 아래 수집 범위와 구분합니다.

최신 결과는 [V7 재상장·대상 시장 편입 대조](remaining-membership-disclosures.md)입니다. 17건 중 재상장 9·대상 시장 편입 7건을 보강해 개별 공시 576/577건·현황 일치 단계 1건을 구분합니다. 폐지일 충돌은 유지하며 아래 수집·후속 기록은 각 작업 당시 결과입니다.

달력 후속: [개장 여부 1,098일 재구성과 시장별 특수 세션](market-calendar-session-coverage.md)에서 독립 가격 날짜 730개를 대조했습니다. 2026-08-17 휴장 문맥을 추가했지만 V7 폐지일 충돌 1건과 종목군 관찰은 변경하지 않았습니다.

최신 결과는 [V4 이름/약명 검증](name-alias-evidence.md)입니다. 이름 관찰 291건을 모두 설명하고 추가 검토 0건을 확인했으며, 편입/제외 현황 일치 단계 514건의 개별 공시와 전체 기준정보 검증은 남습니다. 아래 V1/V2/V3 수치는 각 작업 당시의 기록입니다.

최신 후속: [이름 변경 관찰의 V3 검토](name-change-evidence.md)에서 공시 일치 285건·이전상장 표기 변화 3건·추가 검토 3건을 구분했습니다. 아래 원문 수집·V1/V2 후속 기록은 각 작업 당시의 결과입니다.

후속: [V1 대조 원장](universe-event-reconciliation.md)에 이어 [미해결 57건의 개별 공시 확인과 V2 원장](unresolved-membership-evidence.md)에서 편입·제외·시장 변경 577/577건의 현황/공시 일치를 확인했습니다. 그중 개별 공시 63건이며 나머지 514건·이름 변경 관찰 291건은 추가 검증 대상입니다. 아래 원문 수집·해시·초기 검증 기록은 보존합니다.

기준일: 2026-11-04. [시작일 기준표](krx-baseline-live-validation.md)를 재사용해 **2023-11-01~2026-11-02의 1,098개 날짜·KOSPI/KOSDAQ**를 조회하는 후속입니다. 현재 생존 종목이나 삼성전자 거래 날짜로 과거 시장을 구성하지 않습니다. 원문·수집 영수증·파생 자료는 개인 로컬 `research-artifacts`에 보관하며 Git에는 수집기·가상 테스트·검증 결과 문서만 포함합니다.

## 실제 수집 결과

| 항목 | 결과 |
|---|---:|
| 날짜별 두 시장 응답 확보 | **1,098/1,098일 · 100%** |
| 원문 응답 | 2,196개: 시작일 재사용 2개 + 신규 2,194개 |
| 전체 원문 행 | **3,002,614행**: 여러 날짜에 반복 등장하는 종목 포함 |
| 기간 전체 고유 보통주 ISIN | **2,873개**: 발행회사 수와 구분 |
| 날짜별 보통주 수 | 2,517~2,675개 |
| 영문이 포함된 보통주 단축코드 | 68개 보존 |
| 두 시장이 모두 빈 날짜 | 0일 |
| 한 시장만 빈 날짜 | 0일 |
| 미수집 요청 / 실패·중단 예약 | 0 / 0 |

이는 **요청한 날짜별 API 목록 확보율**입니다. 거래일 1,098일이나 서로 다른 종목 3,002,614개를 뜻하지 않으며, 전체 5-08 완료율도 아닙니다. 기간 중 상장됐다가 폐지된 종목도 원문과 일별 목록에 보존합니다.

파생 목록의 미검토 분류는 **0건**이며, 관찰 변화는 총 **868건**입니다.

| 관찰 종류 | 건수 |
|---|---:|
| 보통주 추가 `ADDED_OBSERVED` | 356 |
| 보통주 제외 `REMOVED_OBSERVED` | 218 |
| 같은 ISIN의 시장 변경 `MARKET_TRANSFER_OBSERVED` | 3 |
| 이름 변경 `NAME_CHANGE_OBSERVED` | 291 |

시장 변경 3건은 코드 `022100`의 2024-01-01→01-02, `066970`의 2024-01-28→01-29, `034230`의 2024-06-23→06-24 목록 사이에서 관찰됐습니다. 모두 KOSDAQ→KOSPI이며 같은 ISIN을 유지합니다. 이 중 기존 공식 공시와 대조한 이전상장은 엘앤에프 `066970`입니다. 나머지 두 건은 공식 공시 추가 대조 대상으로 남깁니다. 모든 관찰의 `effectiveDate=null`, `legalEventConfirmed=false`를 유지합니다.

## 실제 감사 결과

- 고정한 4개 사건의 전날/당일 **10/10 통과**, 불일치·자료 대기 0건: M83 신규상장 2항목, 유진스팩7호 폐지 2항목, 엘앤에프 양 시장 이전 4항목, 한국스팩11호 합병 사유 폐지 2항목.
- 전체 원문/계획/영수증 **2,198개 파일**, 일별 파생 목록 **1,098개**, 변화 이력과 보고서를 네트워크 차단 상태에서 재계산해 일치 확인. 기존 가격/DART 55개를 포함한 **72개 파일 해시 유지**, 기존 V1/V2 기준표 유지.
- 완성 캐시 재사용·감사·공시 대조의 신규 요청 **0회**. 과거 2023-11-01 시각 조회에는 현재 수집 자료가 보이지 않으며, 실제 수신 이후 조회에는 시작일 보통주 2,517개가 보임.
- 로컬 일일 원장은 이전 4회 + 신규 2,194회 = **2,198/8,000회**. 전체 계획은 **2,194/2,400회**, 날짜/시장별 실패·잔여 예약 0건. 실제 요청 시작 간격 최솟값 **0.551131초**로 0.5초 기준 충족.
- 전체 AI 서버 **468건 통과, 실패/오류/건너뛰기 0건**: 기존 442 + 신규 26. Java 저장 내보내기 fixture 포함. 기존 Starlette/AnyIO 경고 1건 유지.

주요 로컬 결과는 `job/plan.json`, `job/journal.json`, `derived/report.json`, `derived/changes.jsonl`, `derived/days/*.json`, `event-checks.json`, `validation.json`입니다. 모두 아래 명령의 Git 제외 경로 아래에 있습니다.

| 재현 식별자 | SHA-256 |
|---|---|
| 계획 ID | `ae6fd34d700e191b0856ab48c124e896f4cb9b076a836466c66c832ffa29c650` |
| 파생 보고서 | `538fade82d255f0dfa1f00f9e3b0174cd36c13a292a9ff7f748a792a1bfba239` |
| 변화 JSONL | `78c59ce1b23dd44421d0d83c0677771d39b98b0912fd19be5efe3651005cdbb9` |

## 수집과 예산

- 날짜별 두 시장을 모두 조회합니다. 시작일 원문 2개를 해시 검증 후 복사해 재사용하므로 필요한 **신규 요청은 2,194회**입니다.
- 계획 전체 시도 한도는 2,400회, 날짜/시장 조합별 최대 3회입니다. 실행별 `--max-new-requests`가 별도 상한이며 실패·중단 예약도 시도로 계산합니다. 예산은 금액이나 AI 토큰이 아니라 API 요청 횟수입니다.
- [KRX 공식 이용약관 제8조](https://openapi.krx.co.kr/contents/OPP/INFO/OPPINFO002.jsp)의 키당 일 10,000회보다 낮은 로컬 일 8,000회 한도를 둡니다. 한국 시각 자정 기준, 같은 키의 SHA-256으로 식별한 공유 원장에 요청 전 예약합니다. 키 자체는 파일명/본문에 남기지 않습니다.
- 이 작업 시작 전에 사용한 4회는 `--prior-requests 4`로 처음 생성하는 당일 원장에 반영했습니다. 이후 같은 원장 재개 시 중복 가산하지 않습니다. 다른 프로그램의 호출을 자동으로 관측하는 전사 한도 관리 기능은 아닙니다.
- 호출 시작 간격은 최소 0.5초이며 단일 작업 소유권과 공유 예산 잠금으로 중복 실행을 막습니다. 키/활성화 검증이 실패하면 API 요청을 시작하지 않습니다.

승인 거절·통신 오류·비정상 원문·예산 초과는 중단하며 API를 자동 재시도하지 않습니다. 사용자가 명시한 `--retry-incomplete`에서만 실패/예약 항목을 새 시도로 재조회하고 이전 시도·원문은 보존합니다. 정상 완료된 날짜/시장은 재조회하지 않습니다.

Windows에서 실제 확인한 파일 공유 위반에는 **파일 교체만 최대 8회, 총 대기 2초 미만** 재시도합니다. 원문 요청을 다시 보내는 동작이 아닙니다. 그래도 실패하면 이전 체크포인트를 보존하고 중단합니다. 수집 응답 후 저장하지 못한 예약은 성공으로 간주하지 않습니다.

## 날짜별 상태와 관찰 변화

종목기본정보는 실제 주말에도 행을 반환했습니다. **목록 응답 유무로 거래일·휴장일을 판정하지 않습니다.** 상태는 다음과 같습니다.

| 상태 | 의미 |
|---|---|
| `OBSERVED` | 같은 날짜 두 시장 모두 비어 있지 않은 원문 확보 |
| `EMPTY_RESPONSE` | 두 시장이 정상 형식의 빈 배열을 반환. 휴장 확정 아님 |
| `INCONSISTENT_RESPONSE` | 한 시장만 빈 배열. 두 시장의 일관성 미확인 |
| `UNAVAILABLE` | 한 시장 이상 미수집·실패·중단 예약 |

각 원문은 해시·수신 시각·기준 요청 날짜·시장·행 수에 묶입니다. 기존 V1 파서와 `KRX_COMMON_SHARE_CLASSIFICATION_2`를 재사용하며 처음 확보한 V1/V2 기준표는 변경하지 않습니다. 새로운 증권/주식 종류는 미검토로 남기고 변화 비교를 중단합니다. 같은 날짜의 ISIN/단축코드 중복은 시장을 가로질러 거부합니다.

서로 비교 가능한 두 목록은 ISIN으로 연결합니다. 보통주의 추가·제외·이전시장·코드 변경·이름 변경·분류 변경을 `*_OBSERVED`로 남깁니다. 같은 단축코드를 다른 ISIN이 재사용하면 별개 종목으로 처리합니다. 시장과 이름이 동시에 바뀌면 두 관찰을 모두 기록합니다.

이는 신규상장·상장폐지·합병의 법적 효력을 자동 확정한 결과가 아닙니다. `observedFrom`/`observedTo`는 변화가 보인 두 기준 날짜이며 `effectiveDate=null`, `legalEventConfirmed=false`입니다. 빈 응답이 사이에 있으면 그 날짜들을 명시합니다. 미수집·불일치·미검토를 가로질러 대량 제외/편입을 추정하지 않습니다. 합병 비율·대가나 법적 승계도 ISIN/코드 유사성으로 만들지 않습니다.

## 정보 시점과 감사

`as-of`는 정확히 요청한 날짜의 보통주 목록만 반환합니다. 과거 날짜를 현재 수집한 자료의 `knownAt`은 실제 수신 시각입니다. 과거 기준 날짜만으로 당시 전략에 이미 알려진 정보로 바꾸지 않습니다. 조회 시각보다 늦게 수신한 시장은 제외하고, 빈 응답·미수집 날짜를 이전 목록으로 채우지 않습니다. `completeAtCutoff`는 해당 목록의 수신 여부이며 학습 가능 여부가 아닙니다.

`build`는 원문에서 일별 목록·변화 JSONL·파일별 해시 보고서를 생성합니다. `audit`는 통신 없이 원문과 저장된 행 수, 모든 일별 파생 파일, 변화 파일, 전체 보고서를 다시 계산해 비교하며 파일을 다시 쓰지 않습니다. 시작일 원문도 동일하게 감사합니다. `status`는 체크포인트 메타데이터의 진행 표시이며 전체 원문 감사를 대신하지 않습니다.

`check-events`는 기존 KIND 사례/시장 사건 보고서를 원문 캐시에서 먼저 재감사하고, 신규상장·폐지·이전상장·합병 사유 폐지의 전날/당일 목록을 대조합니다. 전날 또는 당일이 미수집/빈 응답이면 대기로 남기고 불일치도 숨기지 않습니다. 선택한 사건의 대조이며 전체 시장의 모든 법적 사건을 검증했다고 표시하지 않습니다.

## 재현 명령

`AI/ai-server`에서 실행합니다. 아래 작업 경로는 실제 수집용 Git 제외 폴더입니다. `plan`/`build`는 새 경로에만 생성하고 기존 결과를 덮어쓰지 않습니다.

```powershell
# 최초 계획: 이미 받은 시작일 자료 재사용
.\.venv\Scripts\python.exe -m app.replay.krx_universe_history plan `
  --output research-artifacts/krx-history-20231101-20261102-20261104/job `
  --start 2023-11-01 --end 2026-11-02 --max-requests 2400 `
  --seed-job research-artifacts/krx-universe-20231101-20261104/job

# 수집/이어받기: 완료된 조합은 자동 재사용
.\.venv\Scripts\python.exe -m app.replay.krx_universe_history collect `
  --job research-artifacts/krx-history-20231101-20261102-20261104/job `
  --env-file ../../.env --budget-cache research-artifacts/krx-request-budget `
  --max-new-requests 2194 --prior-requests 4

# 추가 요청이 없는 진행 조회
.\.venv\Scripts\python.exe -m app.replay.krx_universe_history status `
  --job research-artifacts/krx-history-20231101-20261102-20261104/job

# 파생 목록/관찰 이력 최초 생성
.\.venv\Scripts\python.exe -m app.replay.krx_universe_history build `
  --job research-artifacts/krx-history-20231101-20261102-20261104/job `
  --output research-artifacts/krx-history-20231101-20261102-20261104/derived

# 재계산 감사: 키/네트워크 없이 재현
.\.venv\Scripts\python.exe -m app.replay.krx_universe_history audit `
  --job research-artifacts/krx-history-20231101-20261102-20261104/job `
  --output research-artifacts/krx-history-20231101-20261102-20261104/derived

# 과거 전략 시각에는 현재 수신한 자료가 보이지 않음
.\.venv\Scripts\python.exe -m app.replay.krx_universe_history as-of `
  --job research-artifacts/krx-history-20231101-20261102-20261104/job `
  --date 2023-11-01 --at 2023-11-01T15:30:00+09:00

# 이미 확보한 공식 공시와 대표 사건 경계 대조
.\.venv\Scripts\python.exe -m app.replay.krx_universe_history check-events `
  --job research-artifacts/krx-history-20231101-20261102-20261104/job `
  --cases ../../docs/examples/kind-reference-cases.json `
  --case-report research-artifacts/kind-cases-20261103/report.json `
  --events ../../docs/examples/universe-events.json `
  --event-report research-artifacts/universe-events-20261103/report.json `
  --cache research-artifacts/kind-case-cache `
  --output research-artifacts/krx-history-20231101-20261102-20261104/event-checks.json
```

명시적 복구는 원문·실패 사유·남은 예산을 확인한 뒤 같은 `collect`에 `--retry-incomplete`를 추가합니다. 이미 완료한 조합은 이 옵션에서도 재요청하지 않습니다. 전체 계획 예산 또는 날짜/시장별 시도 한도를 소진했다면 자동으로 새 계획을 만들지 않습니다.

## 완료 범위와 다음 검증

이번 작업 체크리스트입니다.

- [x] 시작일 자료를 재사용하고 전체 1,098개 날짜·두 시장 원문 확보
- [x] 호출 예산·간격·중단 재개·Windows 파일 교체와 실패 원문 보존 구현/검증
- [x] 일별 보통주 분류·ISIN 관찰 변화 868건 생성, 미검토 0건
- [x] 전체 원문/파생 감사·대표 사건 10/10·과거 정보 시점 차단 검증
- [x] 회귀 468건·기존 자료 72개 해시·추가 통신 없는 캐시 재사용 확인
- [ ] 관찰 변화 전체의 공식 공시/발행회사 관계·독립 총수 대조
- [ ] 전 기간 거래일/세션·거래정지·기업행사/정정/공개 시점·실제 가격 경계 검증

일별 API 목록 수집은 [5-08 고정 완료 조건](multi-company-reference-cases.md)의 과거 종목군 조건을 채우는 단계입니다. 독립 총수·전체 상장/폐지 공시와의 대조, 모든 정지/기업행사·정정 계보, 거래일/세션, 과거 공개 시점 및 가격과의 검증은 별도입니다. 보고서의 `marketUniverseComplete`, `usableForTraining`, `usableForTrading`, `calendarCompletenessConfirmed`, `allLegalEventsConfirmed`는 이 검증들이 남아 있는 동안 false입니다. 5번 고정 체크리스트는 7/18·39%, 1~5번 합계는 26/48·54%를 유지합니다. 전체 프로젝트 공수 기준 완료율은 산정하지 않습니다.
