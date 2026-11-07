# H02 과거 달력 플래그 근거 감사

후속 작업에서 당시 유효한 업무규정과 새로 확보한 청산결제 업무규정을 연결했습니다. 아래 표는 기존 자료의 시장별 명시 플래그 감사이며, 통상 T+2 계산과 규정상 휴장 결과는 별도 보고서에 있습니다. [시장별 휴장·표준 결제 규정 대조](historical-calendar-rule-evidence.md)

2023-11-01~2026-11-02의 KOSPI·KOSDAQ 달력을 각각 1,098일로 감사했습니다. 시장이 명시된 KRX·KB 등 날짜별 공지, 기존 KRX 연도별 휴장일 재구성, 시장 구분이 없는 KIS 응답을 구분했습니다. 기존 연도 원문과 공지 캡처에서 달력 보고서를 다시 만든 뒤 저장된 기준 보고서와 바이트 단위로 비교합니다.

| 플래그 | KOSPI | KOSDAQ |
|---|---|---|
| 개장일 | 일정 공지 9일, 재구성 1,089일 | 일정 공지 9일, 재구성 1,089일 |
| 결제일 | 명시적 결제 제외 3일, 미확인 1,095일 | 명시적 결제 제외 3일, 미확인 1,095일 |
| 영업일 | 미확인 1,098일 | 미확인 1,098일 |
| 거래일 | 미확인 1,098일 | 미확인 1,098일 |

두 시장에서 같은 범위로 확인된 개장 일정은 연초 3일과 수능 3일, 연말 휴장 3일입니다. **2023-12-29, 2024-12-31, 2025-12-31**은 연말 공지에서 결제 제외가 명시돼 있습니다. **2026-08-17**은 연도별 휴장일에서 개장하지 않는 날로 재구성됐으며, 날짜를 특정한 결제 근거는 미확인입니다. 같은 시장·필드 안의 충돌은 이번 입력에서 0건입니다.

재구성은 연도별 휴장 목록과 검토한 주말 규칙을 결합한 결과입니다. 적용일별 규정 전문, 각 날짜의 시장별 플래그 원문, 개장 실행 자체를 확인할 때는 별도 근거가 필요합니다. 보고서 상태는 `EXPLICIT_SCHEDULE`, `RECONSTRUCTED`, `CONFLICT`, `UNKNOWN`으로 구분하며, 충돌이나 미확인의 값은 `null`입니다. 기존 기준 보고서와 원문이 맞지 않으면 감사를 중단합니다.

## KIS 비교 범위

기존에 확보한 KIS 응답은 2023-11-01~11-24의 24일이고 후속 페이지가 표시된 부분 표본입니다. 표본의 개장 플래그 24일이 공통 KRX 재구성과 일치했습니다. 주말 6일은 원문에 거래일 `Y`, 개장일 `N`이 함께 들어 있어 두 값을 각각 보존했습니다. KIS 예제의 조회 조건과 저장된 응답에서 KOSPI·KOSDAQ을 식별하는 필드를 확인할 수 없어 별도 공급자 관측으로 보고합니다. [KIS 공식 국내휴장일조회 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/chk_holiday/chk_holiday.py)

이전 문서의 코스피 미확인 1,074일·1,072일은 KIS·KB 자료를 함께 놓고 본 비교 수치였습니다. 위 표는 **시장별 출처를 확인한 값만** 집계한 결과입니다. KIS 표본 24일의 확인 범위와 실제 값은 별도 섹션에 남습니다. [기존 개장 재구성 기록](market-calendar-session-coverage.md)

## 과거 시점과 실행

날짜가 명시된 공지는 실제 캡처 시각부터 조회할 수 있습니다. 재구성은 기존 기준 보고서가 사용한 보수적인 확보 시각을, KIS 관측은 해당 응답 확보 시각을 사용합니다. KIS와 KRX의 비교값은 두 근거를 모두 확보한 뒤에 표시합니다. 적용일·공지 등록일만으로 과거 사용 가능 시점을 앞당기지 않습니다.

아래 명령은 Java 서버 없이 `AI/ai-server`의 Python 가상환경에서 실행합니다. 출력 부모 디렉터리는 먼저 만들고, 새 파일로 저장합니다.

```powershell
$job = 'research-artifacts/calendar-sessions-20261105'
$h02 = @(
  '--scope', '../../docs/examples/market-calendar-sources.json',
  '--cache', "$job/sources", '--year-job', "$job/years", '--baseline', "$job/report.json",
  '--kis-cache-page', 'research-artifacts/kis-calendar-cache/2026-11-03',
  '--output', 'research-artifacts/calendar-flag-audit-20261107/report.json'
)
.\.venv\Scripts\python.exe -m app.replay.calendar_flag_audit build @h02
.\.venv\Scripts\python.exe -m app.replay.calendar_flag_audit audit @h02
.\.venv\Scripts\python.exe -m app.replay.calendar_flag_audit as-of @h02 --market KOSPI --date 2023-12-29 --at 2026-11-07T12:00:00+09:00
```

네트워크 연결을 차단한 상태에서 원본 34개 파일의 SHA-256 보존과 보고서 재생성 바이트 일치를 검증했습니다. 세 연말 날짜의 두 시장 결제 근거와 KIS 캡처 직전/경계의 조회도 검증했습니다. 보고서와 검증 파일은 Git 제외 경로에 보관합니다. 훈련·전략 검증·거래에 사용 가능하다는 판정은 차단합니다.

신규 8건을 포함한 관련 검증 67건이 통과했습니다. AI 서버 전체 회귀에서 1,333건이 통과했고 기존 Java/MySQL 변환 테스트 1건은 표본 미지정으로 조건부 제외됐습니다. 이 테스트도 보관한 격리 내보내기 표본을 지정해 별도로 통과했습니다.

다음은 시장·적용일이 명시된 영업일·거래일·결제일 자료의 확보입니다. H02 전체 완료에는 남은 미확인 값과 충돌을 해소해야 합니다. [남은 실행 단위](remaining-development-units.md)
