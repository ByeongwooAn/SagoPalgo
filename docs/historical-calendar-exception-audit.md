# H02 날짜별 결제 일정과 KIS 플래그 대조

2023-11-01~2026-11-02 KOSPI·KOSDAQ 보통주의 [휴장·표준 결제 규정 후보](historical-calendar-rule-evidence.md)를 KRX 날짜별 공지와 KSD 청산결제부 보도자료로 대조했습니다. 날짜별 공지와 규정 후보가 일치하면 `CONFIRMED`, 날짜별 근거끼리 또는 규정 후보와 맞지 않으면 `CONFLICT`, 직접 대조할 근거가 없으면 `UNKNOWN`입니다. 충돌·미확인은 확정값을 비워 두고 규정 후보와 원문 근거를 별도로 표시합니다.

## 시장별 결과

| 대조 항목 | 확정 | 충돌 | 미확인 | 범위 |
|---|---:|---:|---:|---|
| KRX 거래 일정 | 17 | 0 | 1,081 | 기존 9일과 신규 휴장 8일 |
| 결제 일정의 날짜별 포함·제외 | 9 | 0 | 1,089 | 기존 연말 결제 제외 3일과 KSD 결제 예정 6일 |
| 매매일별 결제 예정일 | 6 | 0 | 1,092 | KSD 공지의 6쌍. 그 외 기존 T+2 후보 722일, 매매 일정 없음 368일, 범위 밖 결제 후보 2일 |

표의 건수는 시장당 1,098일 기준이며 두 시장에서 동일합니다. 확정은 **공지된 일정과 규정 계산의 일치**를 뜻합니다. 실제 거래 성립, 결제 이행, 개별 계좌의 잔고 반영은 별도 증거가 필요합니다.

신규 휴장 8일은 **2024-04-10, 2024-05-01, 2024-10-01, 2025-01-27, 2025-05-01, 2025-06-03, 2026-06-03, 2026-07-17**입니다. KRX 원문 12개에서 시장, 휴장 일자와 업무규정 제5조를 대조했습니다. 이 공지의 근거는 거래 일정에 적용했습니다. 해당일의 결제 여부는 별도 명시 근거가 없어 미확인으로 남습니다. 2026-08-17도 결제일에 대해 규정상 제외 후보만 유지합니다. [KRX KOSPI 2026년 공지](https://kind.krx.co.kr/external/2026/05/20/000117/20260520000009/99340.htm) · [KRX KOSDAQ 2026년 공지](https://kind.krx.co.kr/external/2026/05/20/000121/20260520000184/71985.htm)

### 예탁결제원 원문의 매매일→결제 예정일

| KSD 보도자료 | 연말 마지막 결제 일정 | 다음 해로 넘어가는 결제 일정 |
|---|---|---|
| [2023년 연말 보도자료 원문](https://www.ksd.or.kr/ko/api/download/attach?atchFileId=19201&fileSn=1&fileStreCours=KR_NOT_000003) | 2023-12-26 → 2023-12-28 | 2023-12-27 → 2024-01-02 |
| [2024년 연말 보도자료 원문](https://www.ksd.or.kr/ko/api/download/attach?atchFileId=19328&fileSn=1&fileStreCours=KR_NOT_000003) | 2024-12-26 → 2024-12-30 | 2024-12-27 → 2025-01-02 |
| [2025년 연말 보도자료 원문](https://www.ksd.or.kr/ko/api/download/attach?atchFileId=19461&fileSn=1&fileStreCours=KR_NOT_000003) | 2025-12-26 → 2025-12-30 | 2025-12-29 → 2026-01-02 |

세 공지는 연말 주식을 대상으로 결제 예정일을 직접 예시했습니다. 일반 T+2가 휴장 경계를 넘을 때의 대조 사례이며, 전체 날짜에 예외가 없다는 결론이나 결제 주기 변경으로 확대하지 않습니다. KSD 공지·보도자료 제목 검색에서 범위 안 추가 결제 예외 원문은 확인하지 못했습니다. [기존 연말 결제 제외 근거](historical-calendar-flag-audit.md)

## KIS 국내휴장일조회 `CTCA0903R`

| 응답 필드 | 공식 명세의 의미 | 저장 표본 Y / N |
|---|---|---:|
| `bzdy_yn` | 금융기관 업무일 | 18 / 6 |
| `tr_day_yn` | 입출금·이체 등을 포함한 증권 업무 가능일 | 24 / 0 |
| `opnd_yn` | 주식시장 개장일. 주문 가능일 확인에 쓰도록 안내 | 18 / 6 |
| `sttl_day_yn` | 주식과 대금을 주고받는 결제일 | 18 / 6 |

공식 명세의 조회 인자와 응답 행에는 시장 식별자가 없습니다. 기존 2023-11-01~11-24 응답의 개장 플래그는 공통 KRX 재구성과 24/24일 일치했습니다. 주말 6일에는 증권 업무일 `Y`와 개장일 `N`이 함께 관측됐습니다. 의미가 다른 두 필드의 관측 차이로 기록하며, 시장 일정의 충돌 건수에는 포함하지 않습니다. KIS 플래그가 KOSPI·KOSDAQ 각각에 어떻게 적용되는지는 미확인입니다. [KIS API 가이드 상세 명세](https://apiportal.koreainvestment.com/api/apis/public/detail?accessUrl=%2Fuapi%2Fdomestic-stock%2Fv1%2Fquotations%2Fchk-holiday)

가이드 상세 명세의 `tr_cont` 설명은 연속조회 불가로 되어 있으나, 저장된 첫 응답 헤더에는 `M`이 있고 공식 예제는 `M`을 받으면 다음 요청을 구성합니다. 문서와 관측의 차이를 기록했고 다음 요청의 성공 여부나 전체 페이지 범위는 확인하지 않았습니다. 기존 1일 1회·자동 페이지 조회 없음 정책을 적용했습니다. 이번 감사에 인증 KIS·KB 호출은 0회입니다. [KIS 공식 조회 예제](https://github.com/koreainvestment/open-trading-api/blob/d8c7f7936793f85dc1e9c364ba5dc66832353f8c/examples_llm/domestic_stock/chk_holiday/chk_holiday.py)

## 보존과 재현

정식 근거는 인증 없는 공개 응답 42개입니다. KIS 가이드 1개, KSD 게시글·첨부 목록·HWP 9개, KRX 직접 원문과 뷰어·문서 경로·본문 32개를 고정했습니다. KSD의 잘못된 메뉴 코드로 반환된 응답 2개와 검색용 조회는 증거 집계에서 분리했습니다. [고정 입력 해시](examples/calendar-exception-audit.json)는 이전 보고서 2개, 성공 응답 영수증 42개, 검토한 HWP 텍스트 3개의 SHA-256을 묶습니다. HWP 텍스트는 저장한 원본의 본문 스트림에서 로컬로 추출했으며, 원본과 함께 Git 제외 경로에 보관합니다.

`AI/ai-server`에서 실행합니다. `build`는 새 출력 파일을 생성하며, 이미 만든 파일은 `audit`으로 검증합니다.

```powershell
$job = 'research-artifacts/calendar-settlement-exceptions-20261107'
$h02 = @(
  '--manifest', '../../docs/examples/calendar-exception-audit.json',
  '--rule-report', 'research-artifacts/calendar-rule-evidence-20261107/report.json',
  '--flag-report', 'research-artifacts/calendar-flag-audit-20261107/report.json',
  '--cache', "$job/sources",
  '--output', "$job/report.json"
)
.\.venv\Scripts\python.exe -m app.replay.calendar_exception_audit build @h02
.\.venv\Scripts\python.exe -m app.replay.calendar_exception_audit audit @h02
.\.venv\Scripts\python.exe -m app.replay.calendar_exception_audit as-of @h02 --market KOSPI --date 2025-12-29 --at 2026-11-07T20:00:00+09:00
```

네트워크를 차단한 재생성 결과가 바이트 단위로 일치했고 입력 파일 97개의 SHA-256을 보존했습니다. KIS 기존 응답을 다시 읽어 24일의 플래그와 헤더를 대조했습니다. 양 시장의 결제 6쌍은 규정 후보와 공지가 모두 확보된 시각부터만 표시합니다. 확보 시각 직전에는 값을 공개하지 않으며, 공지 등록일을 과거 연구 가용 시점으로 소급하지 않습니다. 신규 7건 포함 관련 테스트 99건과 AI 서버 전체 1,346건이 통과했고 실패·오류·제외는 0건입니다.

H02는 KIS 필드의 시장 적용 범위·연속조회 계약과 KSD의 추가 날짜별 결제 예외·실제 운영 근거가 남아 진행 중입니다. 5-08 고정 완료 기준과 프로젝트 집계는 [고정 체크리스트](numbered-work-progress.md)를 따릅니다. [다음 실행 단위](remaining-development-units.md)
