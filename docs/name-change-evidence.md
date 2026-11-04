# 5-08 이름 변경 관찰 291건의 공식 근거와 V3 원장

기준일: 2026-11-04. [V2 원장](unresolved-membership-evidence.md)에 남았던 이름 변경 관찰 291건을 고정 대상으로 삼습니다. 기존 편입·제외·시장 변경 결과, V1/V2 및 원래 관찰 868건을 보존하면서 변경상장 공시와 식별 관계를 추가 대조합니다.

## 결과와 남은 검토

| 항목 | V2 | V3 |
|---|---:|---:|
| 이름 변경 관찰 | 291 | 291 유지 |
| 변경상장 공시와 이름/날짜 일치 | 0 | **285** |
| 이전상장에 따른 보통주 표기 변화 설명 | 0 | **3** |
| 추가 검토 | 291 | **3** |
| 편입·제외·시장 변경의 현황/공시 일치 | 577/577 | **577/577 유지** |
| 그중 개별 공시 확인 | 63 | **63 유지** |

**288/291·99.0%는 이번 이름 관찰의 설명/대조 비율**입니다. 실제 회사 상호변경 288건, 법적 사건 완전성 또는 5-08 전체 완료율이 아닙니다. 공시 285건의 양식별 관찰 연결은 KOSDAQ `70765` 224건·KOSPI `68155` 59건·복합 상장안내 `68151` 2건입니다.

| 남은 종목/관찰일 | 확인 내용과 미확인 사유 | 후속 |
|---|---|---|
| 케이바이오 `038530` / 2026-04-20 | 공시의 이전 정식명 `(주)케이바이오컴퍼니`와 KRX 이전 이름 `케이바이오`의 관계가 현재 검토 규칙에서 확정되지 않음 | 이전 정식명·약명의 별도 공식 연결 |
| 파수 `150900` / 2026-05-08 | 확보한 변경상장 공시는 04-28의 `파수→파수에이아이`이며 05-08 `파수에이아이→파수AI`를 설명하지 못함. 탐색에서 05-04 기타시장안내 제목 확인 | 약명 변경 시장안내 원문·적용일 대조 |
| NH농우바이오 `054050` / 2026-05-11 | 고정 변경상장/상장안내 검색에서 검토한 제목의 근거를 찾지 못함 | 약명·정식명 관련 공식 안내 확인 |

공시가 없다고 단정하지 않으며, 코드나 이름 유사성으로 통과시키지 않습니다. 세 건의 관찰·미확인 사유·후보 버전 및 확보 시점을 그대로 저장했습니다. 전체 법적 이름 변경 이력의 완전성은 별도입니다.

## 고정 범위와 날짜 의미

- 기간: 2023-11-01~2026-11-02, KOSPI/KOSDAQ 보통주 관찰. 고유 종목코드 269개에서 이름 변경 관찰 291건입니다.
- 같은 시장·코드·ISIN에서의 이름 변경 관찰은 288건입니다. 코스닥→코스피 이전과 동시에 이름 뒤에 `보통주`가 붙은 관찰은 3건입니다.
- 거래소의 변경상장일, KRX 목록에서 이름 변경이 관찰된 구간, 자료를 현재 수집한 시각을 분리합니다. 변경상장일을 법적 상호변경 효력일·합병 완료일로 사용하지 않습니다.
- 기존 현황/공시 일치 577/577건 중 개별 공시 63건, 현황 일치 단계 514건의 구분을 유지합니다. 이름 공시 확인 수를 기존 편입·제외 공시 63건에 섞지 않습니다.

## 수집과 식별 검증

`app.replay.name_disclosures`가 V2 파일 SHA-256과 관찰 ID로 계획을 고정합니다. 전체 코드를 지정한 공식 변경상장 검색 → 뷰어 → 문서 경로 → 원문 순으로 수집합니다. 검색 기간은 관찰 직전 날짜의 45일 전부터 관찰 후 날짜까지입니다. 이 기간·제목 밖의 전체 공시 완전성을 주장하지 않습니다.

| 양식/근거 | 확인 내용 | 식별 방법 |
|---|---|---|
| `70765` KOSDAQ 변경상장(상호변경) | 변경 전 상호·변경 후 정식명/명시된 한글 약명·상장일 | 뷰어 전체 코드 + 양쪽 KRX 원문 코드/ISIN/보통주 + 변경 전후 이름 |
| `68155` KOSPI 변경상장(상호변경) | 변경 전후 상장종목명·변경상장일·보통주 표준/단축코드 | 본문 ISIN/전체 코드 + 뷰어 코드 + 양쪽 KRX 원문 이름 |
| `68151` KOSPI 복합 상장안내 | `◎`로 구분된 상호변경 구간의 이름·변경상장일 | 해당 구간의 ISIN/전체 코드와 양쪽 이름. 다른 구간의 날짜·행사와 분리 |
| 기존 이전상장 공시 | KOSDAQ 제외/KOSPI 편입 및 `보통주` 접미사 변화 | 정확히 같은 관찰 구간·코드·ISIN·변경 전후 이름의 기존 공시 대조 행 |

회사 표기 `(주)`·`㈜`·`주식회사`와 공백만 정규화합니다. 영문 약자·한글 발음을 임의 변환하지 않습니다. 코스피의 `보통주` 접미사는 본문 ISIN이 확인되고 KRX 원문의 주식 종류가 보통주일 때만 별도로 대조합니다.

일반 변경상장 제목이 없으면 같은 기간·전체 코드로 상장안내를 제한 조회합니다. `008970`의 액면병합/상호변경, `267270`의 합병/상호변경 안내에서 이름 변경 구간만 사용했습니다. 다른 구간의 액면병합 비율·합병 완료·실제 가격 조정은 검증 완료로 올리지 않습니다.

공시 정식명과 KRX 이름이 다르면 **공시에 명시된 약명**이 일치하는 경우에만 연결하고 연결 근거를 보존합니다. 예를 들어 `347700`의 공시 정식명 `(주)스피어코퍼레이션`, 약명 `스피어`, KRX 이름 `스피어`를 각각 저장합니다. 단순 유사도나 이름 추정으로 승인하지 않습니다.

3건의 이전상장 표기 변화는 별도 분류 `MARKET_TRANSFER_COMMON_SHARE_LABEL`입니다. 이를 실제 회사 상호변경 3건으로 계산하지 않습니다. SPAC 등의 이름 변경 공시도 합병의 법적 완료·교환 비율을 확정하는 자료로 확대하지 않습니다.

## 정정과 공개 시점

검색에서 확인한 후보와 원본/정정 버전을 모두 보존합니다. 뷰어의 문서 이력 중 수집하지 않은 버전이 있거나 같은 날짜에 문서를 하나로 식별할 수 없으면 검토 대상으로 남깁니다. 여러 변경상장 공시가 검색되면 동일한 문서 이력의 한 사건만 현재 관찰과 연결되는지 검사합니다.

정정 쌍은 **변경 전후 정식명·변경상장일·제공된 코드/ISIN**이 같은지 검사합니다. 약명·영문명·발행일 등 다른 내용은 원문과 버전별 파싱 결과로 보존하며, 전체 정정 내용의 법적 해석 완료로 계산하지 않습니다. 예를 들어 `229640`은 발행일 정정, `139050`은 변경 후 한글 약명 정정이며 정식명·변경상장일 대조와 구분합니다.

`knownAt`은 수집된 검색/뷰어/원문과 양쪽 KRX 문맥의 확보 시각 중 가장 늦은 시각입니다. 미확인 사유도 같은 시점 제약을 적용합니다. 과거 접수일만으로 당시 사용할 수 있었던 정보를 추정하지 않습니다.

## 실제 수집·검증 결과

- [x] 291개 관찰 모두 분류: 이름 공시 285·이전상장 표기 3·추가 검토 3
- [x] 정정 이력 3쌍의 원본/정정 보존과 정식명·변경상장일 대조
- [x] 변경 전후 실제 목록 **582/582개 경계 일치**
- [x] 기존 관찰 868개·편입/제외 관련 577행과 V1/V2 보존
- [x] 기존 **3,669개**, 신규 수집/원장 관련 **1,168개** 파일 해시 유지
- [x] 통신 차단 재감사·완성 캐시 재사용의 추가 요청 **0회**, 확보 전 시점에 새 사실/미확인 사유 노출 0건
- [x] 전체 AI 서버 **609건 통과**: 기존 553 + 신규 56, 실패/오류/건너뛰기 0건. Java 내보내기 fixture 포함, 기존 Starlette/AnyIO 경고 1건
- [ ] 이름 추가 검토 3건, 현황 일치 단계 514건의 개별 공시 및 나머지 고정 완료 조건

실제 수집은 **1,164/1,600회**입니다. 일반 검색 288회 + 상장안내 검색 3회 + 뷰어/경로/본문 각 291회이며, 실제 요청 시작 간격 최솟값은 **1.000065초**입니다. 본문 291개는 정정본과 다른 후보를 포함하며, 확인된 이름 변경 사건 291개라는 뜻이 아닙니다. 규격 탐색 성공 32회·연결 실패 시도 1회는 별도 기록입니다. KRX 인증 API·KB·KIS·DART 추가 호출은 없습니다.

실제 보고서는 `facts.json`, `reconciled-v3.json`, `boundaries.json`, `validation.json`입니다.

| 보고서 | SHA-256 |
|---|---|
| 보존한 V2 | `f7c7ce453bbe21069ece28edf1d2f891f765e76988445773e190d1020dc1dad2` |
| 신규 V3 | `3a1fea673e3d3e0600560b1984a440e21d570e89c51694ff10d81b8b0ca414ee` |
| 이름 사실/미확인 보고서 | `26ec8b14d19377cf4a6e3edf4e3cd9f75ce23acb21c052ca0a0f52883331c882` |

실제 출처 예: [스피어 변경상장](https://kind.krx.co.kr/external/2025/04/09/000668/20250409001735/70765.htm), [동양철관 복합 상장안내](https://kind.krx.co.kr/external/2025/09/11/000116/20250911000288/68151.htm), [HD현대건설기계 복합 상장안내](https://kind.krx.co.kr/external/2026/01/21/000125/20260121000220/68151.htm). 원문 URL·SHA-256·뷰어·검색 영수증을 각 사실에 함께 저장했습니다.

## 실행과 예산

실행 위치는 `AI/ai-server`입니다. 최대 1,600회는 비용이 아닌 HTTP 요청 횟수 상한이며, 요청 시작 간격은 최소 1초입니다. 한 단계의 최대 시도는 3회, 실패/중단 예약은 명시적 `--retry-failed`로만 재시도합니다. 성공 캐시는 다시 받지 않으며 모든 재시도 기록을 보존합니다.

```powershell
.\.venv\Scripts\python.exe -m app.replay.name_disclosures plan `
  --job research-artifacts/name-change-20261104/job `
  --parent research-artifacts/unresolved-membership-20261104/reconciled-v2.json --max-requests 1600
.\.venv\Scripts\python.exe -m app.replay.name_disclosures collect `
  --job research-artifacts/name-change-20261104/job --max-new-requests 1600
.\.venv\Scripts\python.exe -m app.replay.name_disclosures audit `
  --job research-artifacts/name-change-20261104/job

$nameArguments = @(
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
  '--facts-output', 'research-artifacts/name-change-20261104/facts.json',
  '--output', 'research-artifacts/name-change-20261104/reconciled-v3.json'
)
.\.venv\Scripts\python.exe -m app.replay.name_reconciliation build @nameArguments
.\.venv\Scripts\python.exe -m app.replay.name_reconciliation audit @nameArguments
.\.venv\Scripts\python.exe -m app.replay.name_reconciliation as-of @nameArguments `
  --at 2025-04-14T09:00:00+09:00 --symbol 347700
```

`build/audit/as-of`는 기존 KRX 원문·파생·V1/V2와 새 수집 계획/원문을 재감사합니다. 저장한 결과가 재계산과 다르면 덮어쓰지 않고 거절합니다. 실제 원문·영수증·보고서는 Git 제외 경로 `AI/ai-server/research-artifacts/name-change-20261104`에 저장합니다.

이번 작업은 5-08의 **① 과거 종목군 검증과 ⑤ 정정/시점·⑥ 경계·⑦ 감사 보강**입니다. 전체 법적 사건·독립 총수·개별 공시·달력/세션·기업행사·과거 공개 시점·실제 가격 검증이 남아 5-08은 진행 중입니다. 5번 **7/18·39%**, 1~5번 합계 **26/48·54%**를 유지합니다. 학습·주문·배포·DB·EXE 변경은 없습니다.
