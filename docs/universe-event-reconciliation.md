# 5-08 전체 종목군 관찰과 KIND 근거 대조

기준일: 2026-11-04. [전체 기간 KRX 목록](krx-universe-history.md)의 관찰 **868건을 모두 대조 원장에 등록**하고, 공식 KIND 신규상장·상장폐지 현황 및 개별 공시와 연결하는 후속입니다. 고정 완료 조건의 **① 과거 종목군**을 검증하며 **⑤ 정정/시점·⑥ 사건 경계·⑦ 감사**도 보강합니다.

## 수집 범위와 근거 등급

기간은 2023-11-01~2026-11-02, 시장은 KOSPI/KOSDAQ입니다. KIND 공식 화면의 조회 파라미터와 EXCEL 조회에서 사용하는 3,000행 한도를 확인한 뒤, 시장별 신규상장/폐지 현황을 **4회 POST**로 확보했습니다. 페이지 번호·총 페이지·총 행 수·시장·날짜·중복·원문 해시를 검증하며 1페이지에 모두 담기지 않으면 완료로 받아들이지 않습니다.

| 공식 현황 | KOSPI | KOSDAQ | 합계 |
|---|---:|---:|---:|
| 신규상장기업현황 | 30 | 289 | 319 |
| 상장폐지현황 | 40 | 181 | 221 |
| 합계 | 70 | 470 | **540** |

공식 조회 화면: [신규상장기업현황](https://kind.krx.co.kr/listinvstg/listingcompany.do?method=searchListingTypeMain), [상장폐지현황](https://kind.krx.co.kr/investwarn/delcompany.do?method=searchDelCompanyMain).

정식 수집은 현황 4회 + 추가 개별 공시 4회 = **8회**이며, 요청 형식/원문 경로를 확인한 로컬 탐색 스크립트의 13회는 별도입니다. 웹 검색은 이 수집 예산에 포함하지 않습니다. KRX Open API 인증키·KB·KIS·DART 추가 호출은 없습니다. 여기의 예산은 금액이 아닌 공개 HTTP 요청 횟수입니다.

## 실제 대조 결과

| 항목 | 결과 |
|---|---:|
| 원장에 등록한 전체 관찰 | **868/868건** |
| 편입·제외·시장 변경 관찰 | 577건 |
| 공식 현황 또는 개별 공시와 일치 | **520/577건 · 90.1%** |
| 그중 개별 공시로 거래소 날짜 확인 | **6건** |
| 현황 일치 단계·개별 공시 추가 확인 대상 | 514건 |
| 현황에서 연결 근거 미확보 | 41건 |
| 회사명 식별 관계 확인 필요 | 13건 |
| 외국 발행회사 키 대응 확인 필요 | 3건 |
| 별도 이름 변경 관찰 확인 필요 | 291건 |
| 현황/공시 대조의 미해결 관찰 합계 | **348건**: 편입/제외/시장 변경 57 + 이름 변경 291 |

**90.1%는 편입·제외·시장 변경 577건에 대한 이번 현황/공시 대조율**입니다. 5-08 전체 완료율 또는 법적 사건 공시 완전성 비율이 아닙니다. 개별 공시로 확인된 6건을 제외한 **571건은 개별 공시 검증이 남습니다.** 이름 변경 291건은 KRX 이름 필드의 관찰이며, 표기 방식 변경도 포함될 수 있어 법인 상호변경 291건으로 확정하지 않습니다.

대조 원장은 공시 확인 6·현황 일치 514·식별 관계 검토 13·발행회사 키 대응 3·현황 근거 미확보 41·이름 변경 검토 291로 모든 관찰을 보존합니다. 같은 날짜 코드 앞부분을 공유하는 보통주 때문에 생긴 실제 식별 모호성은 0건이며, 이를 승인하지 않는 합성 시험은 별도로 통과했습니다. 연결되지 않은 KIND 현황 행 17개도 검토 목록으로 보존합니다.

신규상장 현황은 SPAC 합병을 통한 신규/이전상장 등을 제외한다고 안내합니다. 현황의 회사 수를 KRX 보통주 수와 동일시하지 않습니다. KIND와 KRX Open API는 같은 공급자이므로 `sameProviderCrossCheck=true`, `independentTotalVerified=false`입니다.

원장의 근거 등급을 구분합니다.

- `DISCLOSURE_MATCH`: 감사한 개별 공시의 전체 종목코드·시장·날짜가 관찰 구간과 일치. 해당 거래소 편입/제외 날짜만 별도 확인합니다.
- `STATUS_LIST_MATCH`: 공식 현황과 날짜·시장·회사명이 일치하고, 기존 KRX 원문에서 종목코드·ISIN의 식별 관계를 확인했습니다. 개별 법적 사건 공시의 검증은 후속입니다.
- `STATUS_IDENTITY_REVIEW`: 날짜와 식별자 후보는 있으나 회사명이 다르거나 식별 관계가 모호합니다.
- `ISSUER_KEY_MAPPING_REQUIRED`: 회사명·시장·날짜 후보는 있지만 KIND 발행회사 키와 종목코드의 대응을 추가 확인해야 합니다.
- `NO_STATUS_EVIDENCE`: 현재 확보한 현황에서 연결 근거를 찾지 못했습니다. SPAC 합병 제외 등의 영향일 수 있으며, 실제 이유를 확정하지 않습니다.
- `NAME_CHANGE_NEEDS_DISCLOSURE`: 이름 변경 관찰은 유지하되 공시로 변경일을 확인해야 합니다.

날짜·사건 유형·여러 근거가 충돌하면 별도 `*_CONFLICT`로 남깁니다. 개별 공시가 없다는 사실이나 현황 조회의 제외 범위를 신규상장/폐지 부재의 증거로 바꾸지 않습니다.

## 발행회사 식별과 원본 보존

KIND 현황의 발행회사 키는 **5자리이며 전체 종목코드나 ISIN이 아닙니다.** 국내 종목은 코드 앞부분과 대응하는 후보가 많지만, 외국 회사에는 `CYM16`·`JPN07`처럼 별도 키가 있습니다. 마지막 자리를 임의로 붙이거나 이름만으로 종목을 확정하지 않습니다.

기존 KRX 원문의 전체 코드·ISIN·정식 이름·약칭을 읽고, 해당 ISIN의 이름 변경 전후 관계를 추적합니다. 같은 관찰 날짜·시장의 보통주 여러 개가 동일한 코드 앞부분을 공유하면 현황만으로 승인하지 않습니다. 이름 정규화는 공백과 맨 앞/뒤의 회사 법인 표기만 처리합니다. 영문/한글 회사명이나 SPAC 약칭을 추측 변환하지 않습니다.

원장의 `observationId`는 기존 관찰의 정규 JSON SHA-256입니다. 원래의 868개 관찰·`effectiveDate=null`·`legalEventConfirmed=false`는 보존하며, 확인된 거래소 날짜와 근거는 원장의 별도 필드에 기록합니다. 합병 법적 완료일·교환 비율·거래 가능 상태를 추정하지 않습니다.

모든 연결은 사후 검증입니다. `knownAt`은 원문·별칭·공식 현황·공시를 실제 확보한 시각 중 가장 늦은 시각입니다. 과거 전략 조회에는 그때 아직 확보하지 않은 증거가 노출되지 않습니다. `as-of`도 입력 자료와 저장 원장 전체를 재감사한 뒤 반환합니다.

## 이전시장 개별 공시 보강

기존 엘앤에프 외에 포스코DX·파라다이스의 제외/편입 원문 **4개를 추가 수집**했습니다. 기존 범위 파일과 보고서는 보존하고 [확장 사례 설정](examples/universe-events-reconciled.json)과 별도 보고서를 사용합니다.

| 종목 | 이전 날짜 | 제외/편입 개별 공시 |
|---|---|---|
| 포스코DX `022100` | 2024-01-02 | [KOSDAQ 제외](https://kind.krx.co.kr/external/2023/12/26/000858/20231226002823/70769.htm) · [KOSPI 편입](https://kind.krx.co.kr/external/2023/12/28/000568/20231228001215/99343.htm) |
| 엘앤에프 `066970` | 2024-01-29 | [KOSDAQ 제외](https://kind.krx.co.kr/external/2024/01/24/000603/20240124001736/70769.htm) · [KOSPI 편입](https://kind.krx.co.kr/external/2024/01/26/000543/20240126001612/99343.htm) |
| 파라다이스 `034230` | 2024-06-24 | [KOSDAQ 제외](https://kind.krx.co.kr/external/2024/06/19/000841/20240619001773/70769.htm) · [KOSPI 편입](https://kind.krx.co.kr/external/2024/06/21/000334/20240621000865/99343.htm) |

각 건은 같은 전체 종목코드의 보통주를 확인하고 두 공시의 제외일·편입 적용일을 대조합니다. KOSDAQ 제외를 시장 전체 상장폐지로 처리하지 않습니다.

개별 공시 일치 6건은 M83 신규상장·유진스팩7호 폐지·한국스팩11호 합병 사유 폐지·위 이전시장 3건입니다. 이전시장 전날/당일의 두 시장을 각각 대조하는 경계 검사는 기존 10항목에서 18항목으로 확장합니다. 합병 사유 폐지 날짜 확인을 합병의 법적 완료일이나 교환 비율 확인으로 확대하지 않습니다.

## 검증과 체크리스트

- [x] 전체 관찰 868건을 해시 ID와 함께 보존하고 누락 없이 원장 생성
- [x] 두 시장 현황 540행·추가 공시 4개 원문과 수신 영수증 확보
- [x] 현황/공시 일치 520건과 미해결 348건을 사유별로 구분
- [x] 이전시장 관찰 3건 모두 개별 공시 연결, 확장 경계 **18/18 통과**
- [x] 통신 차단 상태에서 기존 KRX 원문·1,098일 파생·별칭·공시·현황·원장을 재계산해 일치 확인
- [x] 입력/원장 관련 **3,332개 파일**, 기존 가격/DART 등을 포함한 **72개 파일** 해시 유지. 원래 868개 관찰 해시 유지
- [x] 완성 현황 캐시 재사용과 감사에서 추가 요청 **0회**, 과거 수신 전 조회에서 현재 근거 노출 **0건**
- [x] 전체 AI 서버 **502건 통과**, 실패/오류/건너뛰기 0건: 기존 468 + 신규 34. Java 내보내기 fixture 포함, 기존 Starlette/AnyIO 경고 1건 유지
- [ ] 미해결 편입/제외/시장 변경 57건과 이름 변경 관찰 291건의 추가 근거·식별 검토
- [ ] 현황 일치 단계 514건의 개별 공시 검증, 전체 기준정보 완전성 확인

원장 SHA-256은 `bca0e76902c07228552b01d7935737aa64459210f7d8bf95e66f70e47875cb9a`입니다. 입력 일별 보고서 `538fade82d255f0dfa1f00f9e3b0174cd36c13a292a9ff7f748a792a1bfba239`와 원래 변화 이력 `78c59ce1b23dd44421d0d83c0677771d39b98b0912fd19be5efe3651005cdbb9`는 유지했습니다.

로컬 결과는 아래 경로의 `status/plan.json`, `status/journal.json`, `status/raw/*.html`, `events.json`, `reconciled.json`, `expanded-boundaries.json`, `validation.json`입니다. `unusedStatusReferences`에도 연결되지 않은 현황 17행을 보존합니다.

## 재현 명령

`AI/ai-server`에서 실행합니다. 실제 원문·영수증·원장은 Git 제외 로컬 경로에 보관하며, 키나 계좌 API를 사용하지 않습니다.

```powershell
# 최초 현황 계획과 수집: 계획 전체 최대 4회, 실행 예산 별도 지정
.\.venv\Scripts\python.exe -m app.replay.kind_membership_status plan `
  --job research-artifacts/universe-reconciliation-20261104/status
.\.venv\Scripts\python.exe -m app.replay.kind_membership_status capture `
  --job research-artifacts/universe-reconciliation-20261104/status --max-new-requests 4

# 이미 받은 4개 현황 감사: 추가 요청 없음
.\.venv\Scripts\python.exe -m app.replay.kind_membership_status audit `
  --job research-artifacts/universe-reconciliation-20261104/status

# 추가 원문을 확보한 이후 확장 사건 보고서 생성
.\.venv\Scripts\python.exe -m app.replay.universe_events build `
  --scope ../../docs/examples/universe-events-reconciled.json `
  --cache research-artifacts/kind-case-cache `
  --report research-artifacts/universe-reconciliation-20261104/events.json

# 다음 공통 인자를 build/audit/as-of에서 사용
$ledgerArguments = @(
  '--history-job', 'research-artifacts/krx-history-20231101-20261102-20261104/job',
  '--history-derived', 'research-artifacts/krx-history-20231101-20261102-20261104/derived',
  '--status-job', 'research-artifacts/universe-reconciliation-20261104/status',
  '--cases', '../../docs/examples/kind-reference-cases.json',
  '--case-report', 'research-artifacts/kind-cases-20261103/report.json',
  '--events', '../../docs/examples/universe-events-reconciled.json',
  '--event-report', 'research-artifacts/universe-reconciliation-20261104/events.json',
  '--cache', 'research-artifacts/kind-case-cache',
  '--output', 'research-artifacts/universe-reconciliation-20261104/reconciled.json'
)
.\.venv\Scripts\python.exe -m app.replay.universe_reconciliation build @ledgerArguments
.\.venv\Scripts\python.exe -m app.replay.universe_reconciliation audit @ledgerArguments
.\.venv\Scripts\python.exe -m app.replay.universe_reconciliation as-of @ledgerArguments `
  --at 2024-01-02T09:00:00+09:00 --symbol 022100
```

현황 수집은 완료 소스부터 재사용하고, 실패/중단 예약은 자동 재시도하지 않습니다. 실패 원문을 보존한 채 별도 검토합니다. 원장 생성/감사는 기존 KRX 원문·모든 일별 파생·관찰 이력을 먼저 재계산해 검증합니다. 기존 결과와 다른 보고서가 같은 경로에 있으면 덮어쓰지 않고 거부합니다. 새로운 근거나 정책을 적용할 때는 별도 결과 경로를 사용합니다.

## 5-08에서 남은 범위

전체 법적 사건·발행회사 관계·독립 총수, 거래일/세션, 기업행사/정정/공개 시점, 실제 가격 경계 검증은 계속 남습니다. `marketUniverseComplete`, `allLegalEffectsConfirmed`, `usableForTraining`, `usableForTrading`는 false입니다. 5번은 **7/18·39%**, 1~5번 고정 체크리스트 합계는 **26/48·54%**를 유지합니다. 위 현황 대조율은 5-08 전체 완료율이 아닙니다.
