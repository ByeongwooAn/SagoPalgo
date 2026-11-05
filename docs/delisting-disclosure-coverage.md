# 5-08 상장폐지 개별 공시·정정 이력 대조와 V6

최신 후속: [V7 재상장·대상 시장 편입 대조](remaining-membership-disclosures.md)에서 남은 17건 중 재상장 9·대상 시장 편입 7건을 보강했습니다. 개별 공시 576/577건·폐지일 충돌 1건이며 아래는 보존한 V6 기록입니다.

기준일: 2026-11-05 · 자료 수집: 2026-11-04. [V5 신규상장 대조](listing-disclosure-coverage.md)의 후속입니다. 기존 514건 목록과 V5 파일 해시를 고정하고 상장폐지 관찰 206건만 추가 검증했습니다. **205건 일치·1건 날짜 충돌**이며, 편입/제외 관련 개별 공시 확인은 **355 → 560/577건·97.1%**, 현황 일치 단계는 **222 → 17건**입니다. 97.1%는 해당 관찰의 개별 공시 확인율이며 전체 5-08 완료율이 아닙니다.

## 결과와 남은 범위

| 구분 | 결과 |
|---|---|
| 이번 상장폐지 대상 | 206건: KOSDAQ 169·KOSPI 37 |
| 개별 공시 일치 | 205건: KOSDAQ `70769` 168·KOSPI `68051` 37 |
| 개별 공시 검토 필요 | 위지윅스튜디오 `299900` 1건, 폐지일 충돌 |
| 정정 이력 | 52개 종목·155개 문서, 기존 본문 52개 재사용·이전 문서 103개 추가 수집 |
| 정리매매 기간 | 검증 205건 중 명시 날짜 135건·날짜 미제공 70건. 실제 거래 체결 확인과 구분 |
| 남은 현황 일치 단계 | 폐지 날짜 충돌 1·재상장 9·대상 시장 이전상장 7 = 17건 |

위지윅스튜디오의 [개별 공시](https://kind.krx.co.kr/external/2026/08/14/002694/20260814009419/70769.htm)는 상장폐지일을 **2026-08-14**로 기재합니다. 보존한 KRX 폐지 현황 날짜는 **2026-08-18**이며 종목군에도 08-17까지 존재하고 08-18에 제외됩니다. 코드·ISIN·시장만 같다고 날짜를 맞춰 수정하지 않습니다. 이 행은 `STATUS_LIST_MATCH`를 유지하고 `REVIEW_REQUIRED`로 남깁니다. 후속 원문/정정·날짜 기준 확인 전 개별 공시 일치에 포함하지 않습니다.

## 검증 방식

1. V5·원래 목록의 해시, 관찰 ID, 전체 코드·ISIN·시장·보통주, 관찰 전후 구간과 현황 날짜·사유·참조 ID를 고정합니다.
2. 전체 코드를 지정한 공식 검색 → 뷰어 → 문서 경로 → 본문을 보존합니다. 거래소 `상장폐지` 양식만 사용하며 발행회사의 `상장폐지결정`을 대체 근거로 쓰지 않습니다.
3. 최초 검색은 관찰 직전 날짜의 45일 전부터 관찰 후 날짜까지입니다. 원공시가 그보다 오래된 정정 건은 뷰어가 직접 연결한 문서번호·공시 날짜로 별도 계획을 만들고 수집합니다. 이전 접수번호를 추측하지 않습니다.
4. 정정 문서 1~20개의 연결·순서·전체 코드·문서번호·공식 HTTPS 경로·날짜를 검사합니다. 현재 문서는 뷰어 값의 `Y` 표시로 구분하며 HTML의 선택 위치나 같은 날 공시 날짜만으로 결정하지 않습니다.
5. 과거 원문도 전체 코드·제공 ISIN·시장 규정·보통주/KDR 식별이 일치해야 합니다. 과거에 예고된 날짜와 미정 표기는 보존하되 실제 폐지 발생으로 승인하지 않습니다. **현재 문서의 폐지일**이 현황 날짜 및 실제 종목군 제외 구간과 일치해야 V6의 개별 공시 확인으로 올립니다.
6. 정리매매 시작/종료일·원문 행·명시된 매매일 수는 별도로 보존합니다. `-`는 날짜 미제공이며, 실제 거래가 없었다는 확인으로 바꾸지 않습니다. 폐지일을 정리매매 종료일로 사용하지 않습니다.

예: [114120 최종 정정](https://kind.krx.co.kr/external/2024/01/31/000999/20240131002430/70769.htm)은 2023-12-15 원공시와 12-18 정정을 연결합니다. [136510 최종 정정](https://kind.krx.co.kr/external/2024/07/18/000409/20240718001016/70769.htm)은 2024-02-28부터 이어진 5개 문서를 연결합니다. [015540 공시](https://kind.krx.co.kr/external/2023/10/23/000556/20231023001257/68051.htm)의 정리매매 기간도 폐지일과 분리합니다.

정정 대상 52건 중 51건에는 현재 폐지일과 다른 과거 예정일 또는 미정 표기가 있습니다. 이력 문서 53개는 폐지일을 미정으로 기재했습니다. 이 표기를 실제 폐지가 발생했다는 근거로 사용하지 않습니다.

V6는 검증된 205행에 새 근거를 추가하고 날짜 충돌 1행에 검토 사유를 남깁니다. 원래 관찰 868개와 이번 대상 밖 662행, V1~V5 및 이름 관찰 291건의 설명/대조 결과를 보존합니다. 새 사실·검토 사유는 원문과 KRX 문맥을 실제 확보한 시각 이후에만 노출하며, 공시 날짜를 당시 공개 시각으로 추정하지 않습니다. 합병이라는 사유만으로 법적 합병 완료·교환 비율을 확정하지 않습니다.

## 체크리스트와 실행

- [x] 206건의 정확한 대상·부모/목록 해시 고정
- [x] 205건 개별 공시 일치와 날짜 충돌 1건 분리
- [x] 정정 이력 52건·155문서 수집/대조와 기존 52문서 재사용
- [x] 상장폐지 전후 종목 목록 412/412개 경계 일치
- [x] 기존 6,194개 파일·관찰 868개·대상 밖 662행 보존
- [x] 새 원문/계획/보고서 1,037개 해시 보존, 네트워크 차단 전체 재감사·캐시 재사용 추가 요청 0회
- [x] 전체 AI 서버 777건 통과: 기존 719 + 신규 58, 실패/오류/건너뛰기 0. Java 저장 내보내기 fixture 포함, 기존 Starlette/AnyIO 경고 1건 유지
- [ ] 폐지 날짜 충돌 1건 해소, 재상장 9건·대상 시장 이전 7건 개별 공시 대조
- [ ] 전체 법적 사건·발행회사 관계·독립 총수·거래정지/기업행사·달력/세션·과거 공개 시점·실제 가격 검증

실행 위치는 `AI/ai-server`입니다. 예산은 금액이 아닌 **공개 HTTP 요청 상한**입니다. 기본 수집 **825/1,000회**, 별도 정정 문서 수집 **206/400회**, 합계 **1,031회**입니다. 별도 규격 탐색 요청과 KRX 인증 API·KB·KIS·DART 추가 호출은 없습니다. 요청 시작 간격은 각 계획에서 최소 1초입니다. 성공 캐시는 재사용하고, 실패/중단 예약은 명시적 `--retry-failed`로만 재시도하며 단계당 최대 3회와 전체 상한을 지킵니다.

실측 최소 시작 간격은 기본 **1.000063초**, 정정 **1.000058초**입니다. 완료 캐시를 재사용한 검증 중에는 추가 요청이 없었습니다.

```powershell
.\.venv\Scripts\python.exe -m app.replay.delisting_disclosure_coverage plan `
  --job research-artifacts/delisting-coverage-20261104/job `
  --parent research-artifacts/listing-coverage-20261104/reconciled-v5.json `
  --inventory research-artifacts/listing-coverage-20261104/inventory.json --max-requests 1000
.\.venv\Scripts\python.exe -m app.replay.delisting_disclosure_coverage collect `
  --job research-artifacts/delisting-coverage-20261104/job --max-new-requests 1000
.\.venv\Scripts\python.exe -m app.replay.delisting_revision_capture plan `
  --job research-artifacts/delisting-coverage-20261104/revisions `
  --source-job research-artifacts/delisting-coverage-20261104/job --max-requests 400
.\.venv\Scripts\python.exe -m app.replay.delisting_revision_capture collect `
  --job research-artifacts/delisting-coverage-20261104/revisions `
  --source-job research-artifacts/delisting-coverage-20261104/job --max-new-requests 400
```

`plan`은 새 폴더에서 한 번만 실행합니다. 이후 두 수집 모듈의 `audit`으로 계획·원문·요청을 검증합니다. [V5 실행 예제](listing-disclosure-coverage.md)의 `$coverageArguments`에서 `--facts-output`·`--output`을 이번 경로로 바꾸고 다음 인자를 추가합니다.

```powershell
  '--parent-v5', 'research-artifacts/listing-coverage-20261104/reconciled-v5.json',
  '--delisting-job', 'research-artifacts/delisting-coverage-20261104/job',
  '--revision-job', 'research-artifacts/delisting-coverage-20261104/revisions',
  '--facts-output', 'research-artifacts/delisting-coverage-20261104/facts.json',
  '--output', 'research-artifacts/delisting-coverage-20261104/reconciled-v6.json'
```

```powershell
.\.venv\Scripts\python.exe -m app.replay.delisting_coverage_reconciliation build @coverageArguments
.\.venv\Scripts\python.exe -m app.replay.delisting_coverage_reconciliation audit @coverageArguments
.\.venv\Scripts\python.exe -m app.replay.delisting_coverage_reconciliation as-of @coverageArguments `
  --at 2024-02-15T09:00:00+09:00 --symbol 114120
```

`build/audit/as-of`는 KRX 원문/파생과 V1~V5를 재계산하고 부모·목록·기본/정정 계획·원문 해시를 검사합니다. 다른 결과로 기존 보고서를 덮어쓰지 않습니다. 실제 원문·계획·보고서는 Git 제외 경로 `AI/ai-server/research-artifacts/delisting-coverage-20261104`의 `job/`, `revisions/`, `facts.json`, `reconciled-v6.json`, `boundaries.json`, `validation.json`에 보관합니다.

| 보고서 | SHA-256 |
|---|---|
| 보존한 V5 | `1077c9d9c28a2ffa5f7961074d509761b0602356aa9f470724071e896e5a0379` |
| 원래 514건 목록 | `f452566ef88bbd5ddb3cc57909982d82704261ee21d87bd5575768aed0fe75ef` |
| 상장폐지 사실 | `fcdbbe3b8ce1633f8a2ad6a970bec9d95bc8a07b9399a79aff49bac8dd407027` |
| 신규 V6 | `961913e8e972195fc138b026df339886ee033ad06c96f61e152c31c23151b555` |

이번 작업은 고정 완료 조건 ① 과거 종목군·⑤ 정정/시점·⑥ 경계·⑦ 감사를 보강했습니다. **5-08 진행 중, 5번 7/18·39%, 1~5번 26/48·54%**를 유지합니다. 다음은 날짜 충돌 근거 확인과 재상장/대상 시장 이전 개별 공시 대조입니다. 학습·실주문·배포·DB·EXE 변경은 없습니다.
