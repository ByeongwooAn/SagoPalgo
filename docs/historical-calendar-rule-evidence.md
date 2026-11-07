# H02 시장별 휴장·표준 결제 규정 대조

2023-11-01~2026-11-02의 KRX KOSPI·KOSDAQ 보통주를 대상으로, 기존 시장 업무규정 15개 판본의 제5조와 확보한 청산결제 업무규정 2개 판본을 연결했습니다. [기존 달력 플래그 감사](historical-calendar-flag-audit.md)에서 분리한 KIS 원장 플래그에는 이 규칙을 대입하지 않습니다.

| 적용 범위 | 근거 | 해석 |
|---|---|---|
| 시장별 거래 일정 | KOSPI 8·KOSDAQ 7개 업무규정의 제5조와 기존 KRX 연도별 휴장 목록 | 조문에서 휴장 사유를 확인해 각 날짜에 유효한 판본을 연결 |
| 2025-03-03까지 통상 결제 | KOSPI 제7조, KOSDAQ 제7조의2 | 보통거래는 체결일 포함 3번째 날, 휴장일 제외 |
| 2025-03-04부터 통상 결제 | 증권시장 청산결제 업무규정 제2287호·제2418호 제2·3·6조 | KOSPI·KOSDAQ 적용 범위와 통상 결제 계산 확인. 제2418호 헤더 시행일은 2026-04-27 |
| 증권사 영업일·거래일 응답 플래그 | 기존 KIS 24일 관측 | 시장과 공급자 필드의 직접 대응 근거 대기 |

KRX 공개 본문 조회는 양식 1회와 bookid `210018187`, `210185757`의 과거 판본 지정 POST 2회로 마쳤습니다. 응답 본문의 제목·개정 차수·시행일·조문별 판본 ID와 해시를 검증했습니다. 예외 상황의 청산 처리와 결제일 변경 가능성은 보고서에 남습니다. [KRX 법무포털](https://rule.krx.co.kr/out/index.do) · [KRX 증권시장 청산결제 설명](https://open.krx.co.kr/contents/OPN/02/02020104/OPN02020104.jsp)

| 결과 | KOSPI·KOSDAQ 각각 |
|---|---:|
| 유효한 판본을 붙인 날짜 | 1,098일 |
| 시장 휴장 및 통상 결제일 계산 제외 | 368일 |
| 시장 개장 일정·후보 | 730일 |
| 범위 안에서 계산 가능한 표준 결제일 후보 | 728일 |
| 범위 끝 이후 자료가 필요한 후보 | 2일 |

거래 일정 9일은 개별 공지도 확인됐습니다. 나머지 일반 개장일은 규정과 휴장 목록으로 계산한 후보입니다. T+2 후보는 해당일에 체결된 **통상 보통거래**를 가정하고 뒤의 두 결제 가능일을 셉니다. 거래일과 후보 사이에 충돌이나 미확인 날짜가 들어가면 계산을 보류합니다. 실제 거래·결제 이행, 계좌 입금, 예탁결제원의 날짜별 업무 결과는 별도 근거가 필요합니다.

| 검증한 체결 날짜 | 통상 결제일 후보 | 경계 |
|---|---|---|
| 2023-12-28 | 2024-01-03 | 연말 휴장·주말·신정 제외 |
| 2025-02-28 | 2025-03-05 | 삼일절 대체휴일·2025-03-04 제정 판본 경계 |
| 2026-04-24 | 2026-04-28 | 주말·2026-04-27 개정 판본 경계 |

양쪽 시장에서 동일한 날짜를 확인했습니다. 판본의 시행일은 규정을 적용할 날짜이며, 보고서를 사용할 수 있는 시점은 관련 원문을 실제 확보한 시각 중 가장 늦은 값입니다. 후보가 참조한 경계 판본 ID를 보존하고, 그 시각 직전 조회에서는 값을 숨깁니다.

## 실행과 증거

`AI/ai-server`에서 실행합니다. [고정 입력 해시](examples/calendar-rule-evidence.json)는 기존 플래그 보고서·규정 V2·새 청산결제 본문을 묶습니다. 원문과 날짜별 산출물은 Git 제외 연구 폴더에 보관합니다.

```powershell
$job = 'research-artifacts/calendar-rule-evidence-20261107'
$h02 = @(
  '--manifest', '../../docs/examples/calendar-rule-evidence.json',
  '--calendar', 'research-artifacts/calendar-flag-audit-20261107/report.json',
  '--rule-report', 'research-artifacts/kosdaq-rule-effective-20261105/report-v2.json',
  '--rules-cache', 'research-artifacts/session-rules-20261105/sources-reviewed',
  '--effective-cache', 'research-artifacts/kosdaq-rule-effective-20261105/sources',
  '--clearing-cache', $job, '--output', "$job/report.json"
)
.\.venv\Scripts\python.exe -m app.replay.calendar_rule_evidence build @h02
.\.venv\Scripts\python.exe -m app.replay.calendar_rule_evidence audit @h02
.\.venv\Scripts\python.exe -m app.replay.calendar_rule_evidence as-of @h02 --market KOSDAQ --date 2025-02-28 --at 2026-11-07T16:00:00+09:00
```

연결을 차단한 상태에서 동일 보고서를 재생성하고 원본 48개 파일의 SHA-256 보존, 세 경계의 양 시장 후보 및 가용 시점 직전/경계를 검증했습니다. 새 공개 HTTP는 3회입니다. 보고서에는 실제 주문이나 계좌 결제 판단에 사용할 수 있다는 판정을 부여하지 않습니다.

신규 5건을 포함한 관련 검증 84건과 AI 서버 전체 1,339건이 통과했습니다. 격리 Java/MySQL 내보내기 표본을 포함했으며 실패·오류·제외는 0건입니다.

다음은 KSD의 날짜별 결제 예외와 증권사 영업일·거래일 플래그의 시장별 정의를 확보하는 작업입니다. 이 근거를 기존 후보와 대조해야 H02의 나머지 필드를 확정할 수 있습니다. [남은 실행 단위](remaining-development-units.md)
