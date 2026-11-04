# 5-08 미해결 57건의 개별 공시 확인과 V2 원장

최신 후속: [이름/약명 관찰 검토와 V4 원장](name-alias-evidence.md)에서 이름 관찰 291건을 변경상장 이름 근거 286건·약명 안내 2건·이전상장 표기 3건으로 설명하고 추가 검토 0건을 확인했습니다. 아래 수치와 체크리스트는 보존한 V2 작업 당시의 기록입니다. 편입/제외 공시 63건·현황 일치 단계 514건·정정표 일자 차이 1건은 유지합니다.

기준일: 2026-11-04. [V1 대조 원장](universe-event-reconciliation.md)에 남았던 편입·제외 관찰 **57건을 모두 개별 공시로 보강**했습니다. 회사명 검토 13건·외국 발행회사 키 대응 3건·현황 근거 미확보 41건을 고정 대상으로 삼았습니다. 기존 관찰·V1 결과는 유지하고 새 근거와 V2 원장을 별도 저장합니다.

## 진행 결과

| 항목 | 이전 V1 | 현재 V2 |
|---|---:|---:|
| 전체 관찰 | 868 | 868 유지 |
| 편입·제외·시장 변경의 현황 또는 공시 일치 | 520/577 | **577/577 · 100%** |
| 그중 개별 공시 확인 | 6 | **63** |
| 현황 일치 단계·개별 공시 추가 확인 대상 | 514 | **514 유지** |
| 현황/공시로 미확인된 편입·제외·시장 변경 | 57 | **0** |
| 이름 변경 관찰 검토 | 291 | **291 유지** |
| 정정표 기재일과 원공시 접수일의 차이 | 이번 범위에서 미검토 | **1건 별도 보존** |

**577/577은 관찰된 편입·제외·시장 변경에 대한 현황 또는 공시 대조율**입니다. 전체 법적 사건·개별 공시·기업행사 완전성, 학습 가능 여부, 5-08 전체 완료율을 뜻하지 않습니다. 개별 공시 63건과 현황 일치 514건을 구분합니다. 이름 변경 관찰에는 표기 방식 변경도 포함될 수 있습니다.

## 수집과 검증 방식

KIND 공식 상세검색의 종목코드 검색 형식과 공개 뷰어의 원문 경로 조회를 사용했습니다. 각 대상은 관찰 직전 기준일의 45일 전부터 관찰 후 기준일까지 검색합니다. 전 시장·전 기간의 모든 공시를 수집한 결과로 확대하지 않습니다.

1. 고정 V1 원장의 SHA-256과 관찰 ID에서 대상 57건을 생성합니다.
2. 공식 검색 → 전체 종목코드가 표시된 뷰어 → 문서 경로 → 원문 순으로 조회합니다.
3. 검색 총수·페이지·제목·중복 후보, 뷰어의 전체 코드·문서 버전, HTTPS 호스트·원문 경로를 검사합니다. 검색 불명확·정정 검토·통신 실패를 구분합니다.
4. 검토한 양식에서 전체 코드·보통주/KDR 구분·ISIN(제공된 경우)·시장·편입/제외 날짜를 대조합니다.
5. 새 사실을 정확한 관찰 ID에 연결합니다. 이름을 임의로 영문/한글 변환하거나 발행회사 키에 숫자를 붙여 종목코드를 만들지 않습니다.

| 검토 양식 | 의미 | 이번 확인 |
|---|---|---:|
| `70718` | KOSDAQ SPAC 소멸합병 상장의 적용일 | 39건 |
| `70760` | KOSDAQ 상장일 | 7건 |
| `70769` | KOSDAQ 폐지일 | 7건 |
| `68051` | KOSPI 폐지일 | 3건 |
| `68152` | KOSPI 신규상장 텍스트의 상장일·표준코드 | 1건 |
| 합계 | 개별 관찰의 거래소 날짜 | **57건** |

SPAC 소멸합병 상장의 적용일을 최초 IPO일·합병 법적 완료일·교환 비율로 바꾸지 않습니다. KDR 3건은 기존 KRX 원문의 증권 종류 `주식예탁증권`, 주식 종류 `보통주`, 전체 코드·ISIN과 함께 검증했습니다. KDR 문맥의 확보 시각이 더 늦으면 그 시각 이후에만 근거를 사용할 수 있습니다.

## 정정 공시 2건

`473000`, `473950`은 검색 결과에 원공시와 정정공시가 함께 있어 기본 수집 단계에서 확정을 보류했습니다. 별도 계획으로 두 버전의 뷰어·경로·원문을 모두 받았습니다.

- 정정 뷰어가 원본/정정 문서를 같은 이력으로 제공하는지 확인합니다. 검토하지 않은 다른 버전이 있으면 자동 승인하지 않습니다.
- 두 버전의 전체 코드·ISIN·시장·주식 종류·상장일이 같은지 비교합니다.
- 실제 본문 변경은 두 건 모두 `8.업종`이었고, 정정표의 변경 항목도 업종이었습니다. 다른 본문 필드가 바뀌면 별도 검토로 남기는 제한된 규칙입니다.
- **473000은 정정표의 관련 서류 제출일이 2024-05-03, 원공시 접수일은 2024-05-02입니다.** 날짜를 동일시하지 않고 차이 1건을 보존했습니다. 제출일 표기의 해석과 전체 정정 계보 완전성은 후속입니다. 확인된 상장일은 두 버전에서 같았습니다.

정정 전 원문을 덮어쓰지 않으며, 확인된 거래소 날짜와 정정표 메타데이터 차이를 별도 필드로 기록합니다. `supplementCorrectionHeaderDateIssues=1`이고 전체 법적 효과 확인 플래그는 false입니다.

## 예산·감사·체크리스트

예산은 금액이 아닌 공개 HTTP 요청 횟수입니다. 일반 수집 **222/256회**, 정정 쌍 수집 **12/12회**, 합계 **234회**였습니다. 규격 확인용 탐색 4회는 별도입니다. KRX Open API 인증키·KB·KIS·DART 호출은 추가하지 않았습니다. 실제 요청 시작 간격 최솟값은 **1.000092초**로 1초 기준을 충족했습니다.

실패/중단 예약은 일반 수집에서 명시적 `--retry-failed`를 지정할 때만 새 시도로 복구합니다. 단계당 최대 3회·전체 계획 상한을 유지하고 이전 원문/시도를 보존합니다. 정정 쌍 수집의 실패는 자동 재시도하지 않습니다.

- [x] 57건 전체 조회: 기본 수집의 원문 55건·정정 검토 2건을 구분
- [x] 정정 전/후 원문을 포함해 57건 모두 개별 날짜·식별 근거 확인
- [x] 새 편입/제외 전후 **114/114개 경계 일치**. 기존 대표 경계 18항목은 보존
- [x] 통신 차단 재감사·완성 캐시 재사용의 추가 요청 **0회**
- [x] 기존 **3,419개 파일**, 신규 수집/원장 관련 **240개 파일** 해시 유지
- [x] 원래 관찰 **868개 해시**와 V1 원장 유지, 과거 시점 조회에서 현재 근거 노출 0건
- [x] 전체 AI 서버 **553건 통과**, 실패/오류/건너뛰기 0건: 기존 502 + 신규 51. Java 내보내기 fixture 포함, 기존 Starlette/AnyIO 경고 1건 유지
- [ ] 현황 일치 단계 514건의 개별 공시, 이름 변경 관찰 291건 검증
- [ ] 정정표 일자 차이 1건 해석·전체 정정/철회 계보 및 5-08 나머지 고정 조건 검증

실제 원문·영수증·대상 명세·보고서는 모두 Git 제외 경로 `research-artifacts/unresolved-membership-20261104`에 보관합니다. 주요 결과는 `job/plan.json`, `job/journal.json`, `job/raw/*.bin`, `corrections/`, `facts.json`, `reconciled-v2.json`, `boundaries.json`, `validation.json`입니다.

| 보고서 | SHA-256 |
|---|---|
| 보존한 V1 | `bca0e76902c07228552b01d7935737aa64459210f7d8bf95e66f70e47875cb9a` |
| 신규 V2 | `f7c7ce453bbe21069ece28edf1d2f891f765e76988445773e190d1020dc1dad2` |
| 신규 공시 사실 | `67fd92fcaaa34665f0ac953ebcf4da3b8271837ac769fb4a277aea104c6e3326` |

## 재현 명령

`AI/ai-server`에서 실행합니다. `plan`은 최초 생성 시 새 경로에만 실행하며, 이미 계획이 있으면 생략합니다. 수집이 완료된 경로의 `collect`는 캐시를 재사용합니다.

```powershell
.\.venv\Scripts\python.exe -m app.replay.kind_membership_evidence plan `
  --job research-artifacts/unresolved-membership-20261104/job `
  --parent research-artifacts/universe-reconciliation-20261104/reconciled.json --max-requests 256
.\.venv\Scripts\python.exe -m app.replay.kind_membership_evidence collect `
  --job research-artifacts/unresolved-membership-20261104/job --max-new-requests 256
.\.venv\Scripts\python.exe -m app.replay.kind_membership_evidence audit `
  --job research-artifacts/unresolved-membership-20261104/job

.\.venv\Scripts\python.exe -m app.replay.membership_corrections plan `
  --job research-artifacts/unresolved-membership-20261104/corrections `
  --source-job research-artifacts/unresolved-membership-20261104/job
.\.venv\Scripts\python.exe -m app.replay.membership_corrections collect `
  --job research-artifacts/unresolved-membership-20261104/corrections `
  --source-job research-artifacts/unresolved-membership-20261104/job --max-new-requests 12

$evidenceArguments = @(
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
  '--facts-output', 'research-artifacts/unresolved-membership-20261104/facts.json',
  '--output', 'research-artifacts/unresolved-membership-20261104/reconciled-v2.json'
)
.\.venv\Scripts\python.exe -m app.replay.membership_reconciliation build @evidenceArguments
.\.venv\Scripts\python.exe -m app.replay.membership_reconciliation audit @evidenceArguments
.\.venv\Scripts\python.exe -m app.replay.membership_reconciliation as-of @evidenceArguments `
  --at 2024-05-07T09:00:00+09:00 --symbol 473000
```

`build/audit/as-of`는 기존 KRX 원문·파생·V1 보고서와 새 수집 원문·정정 쌍을 먼저 재계산해 검증합니다. 같은 결과 경로를 다른 내용으로 덮어쓰지 않습니다. `knownAt`은 실제 수신·문맥 확보 시각을 사용하며 과거 공시 날짜에서 공개 시각을 추정하지 않습니다.

이번 작업은 5-08 고정 조건 **① 검증과 ⑤/⑥/⑦ 보강**입니다. 전체 법적 사건/발행회사 관계·독립 총수·거래일/세션·기업행사·정정/공개 시점·실제 가격 검증이 남아 5-08은 진행 중입니다. 5번은 **7/18·39%**, 1~5번 고정 체크리스트 합계는 **26/48·54%**를 유지합니다. 학습·주문·운영 배포·DB·EXE 변경은 없습니다.
