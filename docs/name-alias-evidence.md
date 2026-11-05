# 5-08 남은 이름·약명 3건의 공식 근거와 V4 원장

최신 후속: [V7 재상장·대상 시장 편입 대조](remaining-membership-disclosures.md)까지 편입/제외 관련 개별 공시 576/577건·폐지일 충돌 1건을 구분했습니다. 이름 관찰 결과는 유지하며 아래 수치·다음 작업은 보존한 V4 기록입니다.

기준일: 2026-11-04. [V3 원장](name-change-evidence.md)의 이름 추가 검토 3건을 공식 상호변경안내·시장안내와 대조했습니다. V1/V2/V3와 원래 관찰 868건을 보존하고 V4에 새 근거를 추가합니다.

## 결과와 해석

| 항목 | V3 | V4 |
|---|---:|---:|
| 변경상장 이름 근거 | 285 | **286** |
| 거래소 한글 약명 변경 안내 | 0 | **2** |
| 이전상장에 따른 보통주 표기 변화 | 3 | **3 유지** |
| 이름 관찰의 추가 검토 | 3 | **0** |
| 이름 관찰의 설명/대조 | 288/291 | **291/291** |
| 편입·제외·시장 변경의 현황/공시 일치 | 577/577 | **577/577 유지** |
| 그중 개별 공시 확인/현황 일치 단계 | 63/514 | **63/514 유지** |

관찰된 868건 중 미해결 분류는 0건이지만 **전체 법적 사건·전체 개별 공시·과거 공개 시점의 완전성 또는 5-08 전체 완료**를 뜻하지 않습니다. 이름 291건에는 법적 상호변경과 다른 약명 변경·시장 이전 표기가 포함됩니다. 현황 일치 단계 514건의 개별 공시, 정정표 일자 차이 1건 및 전체 기준정보 검증은 남습니다.

## 세 건의 근거

| 종목/관찰 | 새 공식 근거와 확인 | 사용하는 날짜 |
|---|---|---|
| 케이바이오 `038530` | `70659` 상호변경안내의 이전/이후 한글 정식명을 기존 `70765` 변경상장 공시와 대조. 안내의 `KBIO COMPANY Inc.`/`KBIO LABS Inc.`를 양쪽 KRX 원문의 `KBIO COMPANY`/`KBIO LABS`에 연결 | 기존 변경상장일 **2026-04-20**. 주총일 **03-31**은 별도 보존 |
| 파수 `150900` | `70792` 시장안내의 보통주 한글 약명 `파수에이아이 → 파수AI`가 양쪽 KRX 약명과 일치 | 안내의 상장일 **2026-05-08**. 기존 04-28 변경상장과 구분 |
| NH농우바이오 `054050` | `70792` 시장안내의 `농우바이오 → NH농우바이오`가 양쪽 KRX 약명과 일치. 안내의 종목 정식명이 KRX 이전 전체 이름과 일치하며 이후 전체 이름은 새 약명과 일치 | 안내의 상장일 **2026-05-11** |

1차 출처: [케이바이오 상호변경안내](https://kind.krx.co.kr/external/2026/03/31/004265/20260327003450/70659.htm), [파수 약명 안내](https://kind.krx.co.kr/external/2026/05/04/000568/20260504001267/70792.htm), [NH농우바이오 약명 안내](https://kind.krx.co.kr/external/2026/05/06/000754/20260506001758/70792.htm). 접수번호와 문서번호 날짜가 다를 수 있어 각각 보존하고 뷰어가 제공한 경로를 검증합니다.

영문명 연결은 명시된 필드에만 적용하며 ASCII 대소문자·공백·끝의 `Inc.` 법인 표기만 정규화합니다. 한글을 영문으로 음역하거나 `컴퍼니`를 임의로 삭제하지 않습니다. 기존 이름 날짜 공시와 새 양언어 안내, 전체 코드가 표시된 두 뷰어, 같은 코드/ISIN의 양쪽 KRX 원문을 함께 사용합니다.

약명은 양쪽 KRX `ISU_ABBRV`와 정확히 대조합니다. KRX 전체 이름도 안내의 정식명 또는 해당 시점 약명과 일치해야 합니다. NH농우바이오의 영문 약명 변경행은 원문대로 보존하지만 이번 한글 관찰 검증으로 영문 약명 변경까지 검증 완료로 표시하지 않습니다.

거래소 적용일과 주주총회일·법적 효력일을 구분합니다. 법적 상호변경 효력일·합병 완료·교환 비율을 새로 확정하지 않습니다. `knownAt`은 새 뷰어/본문·양쪽 KRX 문맥·기존 V3 행의 확보 시각 중 최댓값이며, 그 이전 조회에는 새 사실을 노출하지 않습니다.

## 수집과 검증

[고정 사례 설정](examples/name-alias-cases.json)에 공식 접수번호·관찰 ID·종목코드·검증 방식을 기록했습니다. 계획은 V3와 사례 설정의 SHA-256을 고정하며, **V3에서 미해결인 이름 관찰의 정확한 집합**만 허용합니다. 영수증이 가리킨 뷰어→문서 경로→원문을 수집하며, 미검토 정정 버전·다른 코드/양식이면 확정을 보류합니다.

기존 이름 수집기의 계획 검증·호출 예산·캐시·중단 재개를 재사용합니다. 기본 V3 경로는 같은 정책을 유지하고, 별도의 설정/요청 생성기를 명시할 때만 새 3건 경로를 실행합니다. 성공 캐시는 다시 받지 않으며 실패/예약은 명시적 `--retry-failed`로만 재개하고 단계당 최대 3회·전체 예산을 유지합니다.

실제 수집은 **9/12회**: 뷰어·경로·본문 각 3회, 최소 요청 시작 간격 **1.000456초**입니다. 규격 확인용 탐색 10회는 별도입니다. KRX 인증 API·KB·KIS·DART 추가 호출은 없습니다. 원문·영수증·보고서는 Git 제외 경로 `AI/ai-server/research-artifacts/name-alias-20261104`에 보관합니다.

## 재현 명령

검증 체크리스트:

- [x] 이름 추가 검토 3건 모두 해결, 이전 미확인 내용 보존
- [x] 전체 AI 서버 **666건 통과**: 기존 609 + 신규 57, 실패/오류/건너뛰기 0건. Java 내보내기 fixture 포함, 기존 Starlette/AnyIO 경고 1건 유지
- [x] 새 변경 전후 목록 **6/6개 경계 일치**, 기존 이름 경계 582항목 보존
- [x] 기존 **4,917개**·신규 수집/원장 관련 **13개** 파일 해시 유지
- [x] 원래 관찰 **868개**, 이번 대상이 아닌 **865행**과 편입/제외 관련 **577행** 보존
- [x] 네트워크 차단 재감사·완성 캐시 재사용의 추가 요청 **0회**, 확보 전 새 사실 노출 0건
- [ ] 현황 일치 단계 514건의 개별 공시·정정표 일자 차이·나머지 고정 완료 조건

| 보고서 | SHA-256 |
|---|---|
| 보존한 V3 | `3a1fea673e3d3e0600560b1984a440e21d570e89c51694ff10d81b8b0ca414ee` |
| 신규 V4 | `68238aedc19e2d043c2d985fee23320e93f00395aa935eba74b08f093759f318` |
| 새 근거 보고서 | `a2218b1bfc31300d7da7f5bb71cd2300a4c055a4509d37d3913974412c748559` |

실행 위치는 `AI/ai-server`입니다.

```powershell
.\.venv\Scripts\python.exe -m app.replay.name_alias_evidence plan `
  --job research-artifacts/name-alias-20261104/job `
  --parent research-artifacts/name-change-20261104/reconciled-v3.json `
  --cases ../../docs/examples/name-alias-cases.json --max-requests 12
.\.venv\Scripts\python.exe -m app.replay.name_alias_evidence collect `
  --job research-artifacts/name-alias-20261104/job --max-new-requests 12
.\.venv\Scripts\python.exe -m app.replay.name_alias_evidence audit `
  --job research-artifacts/name-alias-20261104/job

$aliasArguments = @(
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
  '--facts-output', 'research-artifacts/name-alias-20261104/facts.json',
  '--output', 'research-artifacts/name-alias-20261104/reconciled-v4.json'
)
.\.venv\Scripts\python.exe -m app.replay.name_alias_reconciliation build @aliasArguments
.\.venv\Scripts\python.exe -m app.replay.name_alias_reconciliation audit @aliasArguments
.\.venv\Scripts\python.exe -m app.replay.name_alias_reconciliation as-of @aliasArguments `
  --at 2026-05-08T09:00:00+09:00 --symbol 150900
```

`build/audit/as-of`는 기존 KRX 원문/파생·공시·V1/V2/V3를 재계산한 뒤 새 계획과 원문을 검증합니다. 기존 결과를 다른 내용으로 덮어쓰지 않으며 V4에서 해결된 3행의 이전 미확인 내용은 `previousNameReview`로 보존합니다.

이번 작업은 5-08 고정 조건 **① 과거 종목군과 ⑤ 정정/시점·⑥ 경계·⑦ 감사**를 보강했습니다. 다음은 현황 일치 단계 **514건의 개별 공시 확인**입니다. 전체 법적 사건·발행회사 관계·독립 총수·달력/세션·기업행사·정정/과거 공개 시점·실제 가격 검증이 남아 **5-08 진행 중, 5번 7/18·39%, 1~5번 26/48·54%**를 유지합니다. 학습·주문·배포·DB·EXE 변경은 없습니다.
