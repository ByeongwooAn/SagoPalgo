# 5-08 개별 공시 보강 목록 514건과 신규상장 1차 대조

최신 후속: [V7 재상장·대상 시장 편입 대조](remaining-membership-disclosures.md)에서 개별 공시 576/577건·폐지일 충돌 1건으로 보강했습니다. V6의 폐지 대조와 원래 514건 목록을 보존하며 아래는 V5 기록입니다.

기준일: 2026-11-04. [V4 원장](name-alias-evidence.md)에서 현황 일치 단계에 있던 편입·제외 관찰 514건을 고정하고, 그중 신규상장 현황 292건을 개별 공시와 대조합니다. 원래 관찰 868건과 V1~V4는 보존하며 새 근거를 V5에 추가합니다.

## 고정 목록과 단계

1차 결과: **신규상장 292/292건 검증, 추가 검토 0건**입니다. KOSDAQ `70760` 272건·KOSPI `68152` 20건을 연결했습니다. 편입/제외 관련 개별 공시 확인은 **63 → 355/577건(61.5%)**, 현황 일치 단계는 **514 → 222건**입니다. 61.5%는 해당 577개 관찰의 개별 공시 확인율이며 5-08 전체 완료율이 아닙니다. 이름 관찰 291건의 기존 설명/대조 결과는 유지합니다.

| 분류 | 전체 대상 | 이번 단계 |
|---|---:|---|
| 신규상장 현황 | 292 | 코스닥 272·코스피 20건 수집·대조 |
| 재상장 | 9 | 후속 |
| 대상 시장으로의 이전상장 | 7 | 후속. 범위 밖 시장의 반대편 이력을 임의 생성하지 않음 |
| 상장폐지 | 206 | 후속 |
| 합계 | **514** | 신규상장 외 후속 **222** |

V4의 파일 SHA-256·관찰 ID·전체 코드·ISIN·시장·관찰 구간·현황 날짜/참조 ID를 고정합니다. 전 종목/기간의 모든 법적 사건 수를 독립적으로 확인한 목록은 아닙니다. 기존 검증 사실에서 같은 관찰 유형·전체 코드·ISIN·시장·거래소 날짜의 근거 재사용 가능 여부를 확인했으며 **0건**입니다. 이는 원시 캐시 전체에 관련 문서가 없다는 단정이 아닙니다.

## 검증 규칙

1. 전체 코드를 지정한 공식 검색 → 뷰어 → 문서 경로 → 원문으로 조회합니다. 검색은 관찰 직전 날짜의 45일 전부터 관찰 후 날짜까지입니다.
2. 신규상장 공시를 우선하고 기준가격 안내는 해당 우선 공시가 없을 때만 후보로 삼습니다. 관련 없는 공시·불완전 페이지·후보 중복은 검토 대상으로 남깁니다.
3. 뷰어의 전체 코드와 문서 버전, 공식 HTTPS 호스트·원문 경로·접수번호/문서번호를 검사합니다.
4. 검토 양식에서 전체 코드·제공된 ISIN·시장·보통주/KDR·거래소 적용일을 확인하고 **현황 날짜와도 정확히 일치**해야 개별 공시 확인으로 올립니다.
5. 정정 이력은 원본과 정정본을 보존하고 모든 뷰어 버전을 수집했는지 대조합니다. 코드·ISIN·시장·주식 종류·거래소 날짜가 달라지거나 일부 버전이 검토되지 않으면 이전 문서만 선택해 승인하지 않습니다.

KOSDAQ `70760`과 KOSPI `68152` 신규상장 양식을 사용합니다. 코스피의 제목/상장종목명·공백·보통주 수 표기 및 검토한 부동산투자회사 주석 변형을 지원하되 코드·ISIN·보통주·날짜 검사는 유지합니다. 기존 V1~V4를 생성하는 파서를 변경해 이전 결과를 덮어쓰지 않습니다.

정정 이력 **16쌍**을 보존·대조했습니다. 한라캐스트 `125490` 원공시는 같은 코드·ISIN의 보통주를 0주 행과 실제 수량 행으로 중복 기재했고, 정정본이 0주 행을 삭제했습니다. 이 경우에 한해 **검증된 정정본과 원본의 실제 수량 행·회사명·상장일이 같고 식별자가 모두 일치**하는지 확인해 원본 날짜 근거를 보강합니다. 원본을 수정하지 않고 원문 해시와 중복행/실제행 해시, 연결한 정정 문서를 저장합니다. 다른 코드/ISIN·수량·날짜라면 승인하지 않습니다. 전체 정정 내용의 해석·주식수 이력 검증 완료로 올리지 않습니다.

`신규상장` 현황 분류나 거래소 적용일을 최초 IPO·합병 법적 완료·교환 비율로 바꾸지 않습니다. KDR은 기존 KRX 증권 종류·보통주·코드/ISIN 문맥이 확인된 경우에만 사용합니다. 검토하지 않은 양식/정정·식별/날짜 충돌은 후보 원문 해시와 사유를 남깁니다.

V5는 검증된 1차 대상만 `STATUS_LIST_MATCH → DISCLOSURE_MATCH`로 보강합니다. 검토가 남으면 기존 현황 대조 결과와 개별 공시 검토 상태를 분리하며, 해당 건을 개별 공시 완료 수에서 제외합니다. 새 사실뿐 아니라 미확인 사유도 원문·KRX 문맥·기존 행의 확보 시각 이후에만 조회합니다. 당시 공개 시각을 접수일에서 추정하지 않습니다.

## 실행과 예산

검증 체크리스트:

- [x] 514건 전체 목록·단계 분류·부모/목록 해시 고정
- [x] 신규상장 292/292건의 개별 공시 일치, 추가 검토 0건
- [x] 정정 16쌍과 0주 중복행 삭제 1건의 제한된 원본/정정 대조
- [x] 신규상장 전후 실제 목록 **584/584개 경계 일치**
- [x] 기존 **4,962개**·신규 수집/원장 관련 **1,221개** 파일 해시 유지
- [x] 원래 관찰 **868개**, 이번 대상이 아닌 **576행**, V1~V4 및 이름 관찰 결과 보존
- [x] 네트워크 차단 재감사·완성 캐시 재사용 추가 요청 **0회**, 확보 전 새 사실/미확인 사유 노출 0건
- [x] 전체 AI 서버 **719건 통과**: 기존 666 + 신규 53, 실패/오류/건너뛰기 0건. Java 내보내기 fixture 포함, 기존 Starlette/AnyIO 경고 1건 유지
- [ ] 폐지 206·재상장 9·대상 시장 이전 7건 및 나머지 고정 완료 조건

| 보고서 | SHA-256 |
|---|---|
| 보존한 V4 | `68238aedc19e2d043c2d985fee23320e93f00395aa935eba74b08f093759f318` |
| 514건 목록 | `f452566ef88bbd5ddb3cc57909982d82704261ee21d87bd5575768aed0fe75ef` |
| 신규 V5 | `1077c9d9c28a2ffa5f7961074d509761b0602356aa9f470724071e896e5a0379` |
| 신규상장 사실 | `95f4e058ea39e950183c5150eae81e8daf7826d21bbd5d095ef18ee636bfe756` |

실제 출처 예: [에코프로머티 신규상장](https://kind.krx.co.kr/external/2023/11/15/000579/20231115001368/68152.htm), [에이피알 신규상장](https://kind.krx.co.kr/external/2024/02/23/001109/20240223002474/68152.htm), [한라캐스트 정정 신규상장](https://kind.krx.co.kr/external/2025/08/19/000463/20250819001295/70760.htm). 각 사실에 검색·뷰어·경로·본문 해시와 버전을 함께 보존했습니다.

실행 위치는 `AI/ai-server`입니다. 최대 1,400회는 금액이 아닌 공개 HTTP 요청 횟수 상한입니다. 요청 시작 간격은 최소 1초이며 실패/중단 예약은 명시적 `--retry-failed`로만 새 시도를 만들고 단계당 최대 3회·전체 상한을 유지합니다. 성공 캐시는 다시 받지 않습니다.

실제 수집은 **1,216/1,400회**, 검색 292회·뷰어/경로/본문 각 308회입니다. 정정본을 포함한 본문 308개를 보존했으며 최소 요청 시작 간격은 **1.000083초**입니다. KRX 인증 API·KB·KIS·DART 추가 호출과 별도 탐색 요청은 없습니다.

```powershell
.\.venv\Scripts\python.exe -m app.replay.listing_disclosure_coverage plan `
  --job research-artifacts/listing-coverage-20261104/job `
  --parent research-artifacts/name-alias-20261104/reconciled-v4.json `
  --inventory research-artifacts/listing-coverage-20261104/inventory.json --max-requests 1400
.\.venv\Scripts\python.exe -m app.replay.listing_disclosure_coverage collect `
  --job research-artifacts/listing-coverage-20261104/job --max-new-requests 1400
.\.venv\Scripts\python.exe -m app.replay.listing_disclosure_coverage audit `
  --job research-artifacts/listing-coverage-20261104/job

$coverageArguments = @(
  '--history-job', 'research-artifacts/krx-history-20231101-20261102-20261104/job',
  '--history-derived', 'research-artifacts/krx-history-20231101-20261102-20261104/derived',
  '--status-job', 'research-artifacts/universe-reconciliation-20261104/status',
  '--cases', '../../docs/examples/kind-reference-cases.json',
  '--case-report', 'research-artifacts/kind-cases-20261103/report.json',
  '--events', '../../docs/examples/universe-events-reconciled.json',
  '--event-report', 'research-artifacts/universe-reconciliation-20261104/events.json',
  '--cache', 'research-artifacts/kind-case-cache',
  '--parent-report', 'research-artifacts/universe-reconciliation-20261104/reconciled.json',
  '--evidence-job', 'research-artifacts/unresolved-membership-20261104/job',
  '--corrections-job', 'research-artifacts/unresolved-membership-20261104/corrections',
  '--parent-v2', 'research-artifacts/unresolved-membership-20261104/reconciled-v2.json',
  '--name-job', 'research-artifacts/name-change-20261104/job',
  '--parent-v3', 'research-artifacts/name-change-20261104/reconciled-v3.json',
  '--alias-job', 'research-artifacts/name-alias-20261104/job',
  '--alias-cases', '../../docs/examples/name-alias-cases.json',
  '--parent-v4', 'research-artifacts/name-alias-20261104/reconciled-v4.json',
  '--coverage-job', 'research-artifacts/listing-coverage-20261104/job',
  '--inventory', 'research-artifacts/listing-coverage-20261104/inventory.json',
  '--facts-output', 'research-artifacts/listing-coverage-20261104/facts.json',
  '--output', 'research-artifacts/listing-coverage-20261104/reconciled-v5.json'
)
.\.venv\Scripts\python.exe -m app.replay.listing_coverage_reconciliation build @coverageArguments
.\.venv\Scripts\python.exe -m app.replay.listing_coverage_reconciliation audit @coverageArguments
.\.venv\Scripts\python.exe -m app.replay.listing_coverage_reconciliation as-of @coverageArguments `
  --at 2024-02-27T09:00:00+09:00 --symbol 278470
```

`build/audit/as-of`는 기존 KRX 원문·파생·V1~V4와 514건 목록, 새 수집 계획·원문을 재계산합니다. 다른 결과로 기존 파일을 덮어쓰지 않습니다. 실제 자료는 Git 제외 경로 `AI/ai-server/research-artifacts/listing-coverage-20261104`의 `inventory.json`, `job/`, `facts.json`, `reconciled-v5.json`, `boundaries.json`, `validation.json`에 보관합니다.

기존 계획은 `docs/examples/name-alias-cases.json`의 실제 바이트 해시를 고정합니다. Windows 체크아웃의 CRLF 변환으로 의미가 같은 설정도 해시가 달라지는 문제를 확인해 `.gitattributes`에서 이 파일만 LF로 고정했습니다. 기존 계획·보고서 해시는 바꾸지 않았으며 원래 LF 바이트와 일치하는지 확인했습니다.

이번 작업은 5-08 고정 조건 **① 과거 종목군과 ⑤ 정정/시점·⑥ 경계·⑦ 감사**를 보강합니다. 전체 법적 사건/발행회사 관계·독립 총수·달력/세션·기업행사·정정/과거 공개 시점·실제 가격 검증이 남아 **5-08 진행 중, 5번 7/18·39%, 1~5번 26/48·54%**를 유지합니다. 학습·주문·배포·DB·EXE 변경은 없습니다.
