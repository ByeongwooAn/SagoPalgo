# H05 코스피 정지·해제 공지의 적용 주권 대조

2026-11-15 기준. [월별 공지 원장](../../examples/historical-market-action-monthly.jsonl)에서 정지·해제 날짜 또는 시각을 확인한 코스피 공지 **390건**을 당시 상장 주권 및 KRX 일자별 정지 이력에 대조했습니다. 게시일·정지일·해제일의 후보와 본문에 기재된 날짜를 기준으로 연결했습니다. [접수별 대조 기록과 조회 결과](../../examples/historical-kospi-halt-scope.json)

| 일자별 정지 이력 조회 전 원문과 기준일 KRX 목록의 대조 | 접수 |
| --- | ---: |
| 본문이 우선주를 명시하고 해당 우선주 코드·ISIN이 확인됨 | 16 |
| 본문 회사명이 연결되며 해당일 상장 후보가 보통주 1종 | 327 |
| 해당일 상장 후보가 보통주·우선주 등 복수 주권 | 24 |
| 화면 코드로 상장 후보가 확인되나 일부 대상명 또는 날짜 연결이 미확인 | 23 |
| 합계 | 390 |

복수 주권은 당시 종목명과 약명에서 주권 종류 접미사를 분리한 회사명 및 단축코드 앞 다섯 자리의 일치를 확인했습니다. 근거는 해당일 상장 후보의 범위입니다. 본문 회사명이 연결되지 않은 경우 화면 코드로 관찰한 후보와 그 사유를 남겼습니다. 효력일 범위 밖의 2026-11-03 해제일 1건은 별도 상태를 기록했습니다.

## 공개 후속 공지 대조

전자등록 변경 관련 **105건**을 KIND에서 추가 조회했습니다. 후속 변경상장 공지에서 상장일과 정지 해제일이 같은 날짜로 명시되고, 공지의 코드·ISIN이 해제일 KRX 목록과 일치한 **63건**을 원문에 연결했습니다. 이 가운데 변경상장 본문이 보통주 한 종목을 명시한 건이 **58건**, 보통주와 우선주를 함께 명시한 건이 **5건**입니다. 공개 후속 공지의 해제일은 거래소가 공시한 날짜이며, 앞선 정지 공지와의 연결 근거 및 실제 체결 재개 시각은 접수별로 확인 범위가 다릅니다.

- **BYC**는 2024-04-17 해제 공지에 보통주 `001460`과 1우선주 `001465`가 명시돼 있습니다. [KIND 변경상장](https://kind.krx.co.kr/external/2024/04/16/000079/20240416000168/68155.htm)
- **남양유업**은 2024-11-20 해제 공지에 보통주 `003920`과 1우선주 `003925`가 명시돼 있습니다. [KIND 변경상장](https://kind.krx.co.kr/external/2024/11/15/000107/20241115000180/68155.htm)
- **한화1우선주**는 KIND 화면에 대표 보통주 코드 `000880`이 표시되지만 원문 대상은 `000885`입니다. 별도 상장폐지 공지에 해당 우선주 코드, 2025-07-01 상장폐지 예고 시작, 2025-07-04 정리매매 시작이 기재돼 있습니다. [KIND 상장폐지 공지](https://kind.krx.co.kr/external/2025/06/30/001081/20250630002033/68051.htm)
- **서울식품공업1우선주**는 2026-07-14 관리종목 지정의 대상입니다. 정지 공지의 우선주명은 당일 KRX 목록의 `004415`에 연결되며, 별도 관리종목 공지는 지정 범위를 명시합니다. [KIND 관리종목 지정](https://kind.krx.co.kr/external/2026/07/13/000587/20260713001306/68052.htm)

## 인증 세션의 종목별 정지 이력

KRX 20011 화면에 로그인해 **254종목의 코드·ISIN·일자 조합 638개**를 종목별 258개 기간으로 묶어 조회했습니다. **222종목의 원본 CSV 225개**에서 **547개 조합**을 확인했습니다. 나머지 **91개 조합**은 32종목에 걸친 33개 기간에서 종목 검색 결과가 비어 `STOCK_FINDER_NO_RESULT`로 기록했습니다. [KRX 개별종목 정지 이력](https://data.krx.co.kr/contents/MDC/STAT/issue/MDCSTAT213.jsp)

| 코드·ISIN·일자별 결과 | 조합 |
| --- | ---: |
| `Y` · 해당일에 정지 이력 있음 | 334 |
| `N` · 해당일에 정지 이력 없음 | 213 |
| 종목 검색 결과 없음 | 91 |
| 합계 | 638 |

390개 접수 모두에 조회 응답 또는 미반환 사유를 연결했습니다. 329건은 조회 대상 조합에 모두 응답이 있었고, 3건은 일부 조합에만 응답이 있었으며, 58건은 조회 대상 조합이 모두 미반환이었습니다. 결과의 `dailyQueryEvidence`에는 547개 응답과 원본 CSV·행의 SHA-256을 기록했습니다. `dailyQueryNeeds`에는 91개 미반환과 사유를 기록했습니다. 두 목록에서 접수번호와 정지일·해제일·변경상장 해제일 중 해당하는 항목을 확인할 수 있습니다. [접수별 대조 기록과 조회 결과](../../examples/historical-kospi-halt-scope.json)

정지일 응답을 얻은 312건은 모두 해당일에 `Y`가 확인됐습니다. 해제일에 `Y`가 확인된 51건 중 48건은 공지의 정지일과 해제일이 같았고, 2건은 정지일이 생략됐습니다. 나머지 1건은 참엔지니어링 `009310`입니다. 자본감소 공지의 해제일인 2026-03-12부터 상장적격성 실질심사 사유로 별도 정지한다는 공지가 있어 같은 `Y` 응답을 두 접수에 연결했습니다. [자본감소 정지·해제 공지](https://kind.krx.co.kr/external/2026/03/11/001380/20260311003341/99808.htm) · [별도 정지 공지](https://kind.krx.co.kr/external/2026/03/11/002719/20260311006014/68054.htm)

변경상장 해제일을 대조한 63건 중 62건은 하나 이상의 해당 코드에서 `N`을 확인했습니다. 1건은 전부 미반환이었으며, `N`을 확인한 62건 중 1건은 다른 대상 코드가 미반환이었습니다. 실제 정지·해제 적용 시각과 해제 뒤 첫 체결을 확인하려면 종목별 상태 전환 기록이나 틱 원본이 필요합니다. [KRX 일자별 결과의 필드와 이전 대조](historical-market-action-kospi-halt-records.md)

## 20011 미반환 91개 조합의 KIND 원문 대조

기존 32종목·91개 조합에 연결된 61개 접수의 원문을 재검증했습니다. 2023-11-16부터 2026-11-15까지 KIND 대표 종목코드 31개로 정지·해제, 변경상장, 상장폐지 목록 93개를 조회했습니다. 별도 관련 접수 89개에서 원문과 정정본을 확인했고, 상장폐지 공시의 주권 표에서 32종목의 단축코드를 확인했습니다. [미반환 전수 결과](../../examples/historical-kospi-halt-missing.json) · [KIND 공시 상세검색](https://kind.krx.co.kr/disclosure/details.do?method=searchDetailsMain)

**89개 조합**에 공지의 종목 범위와 적용일을 연결했고, **2개 조합**에는 미확정 사유를 기록했습니다. 91개 조합에 정지·해제·변경상장 해제 근거를 연결한 참조는 총 96건입니다. 같은 날 정지와 해제가 공지된 경우 두 근거를 한 조합에 기록했습니다.

| 접수별 판정 근거 | 참조 |
| --- | ---: |
| KIND 본문 상호·적용일과 당시 KRX 단일 상장 주권이 일치 | 60 |
| KIND 본문 대상 또는 비고에 해당 우선주 명시 | 25 |
| KIND 상장폐지 공지의 본문 상호·단축코드로 당시 KRX 주권 식별 | 6 |
| KIND 변경상장 원문의 코드·ISIN과 기존 정지 또는 해제 공지를 연결 | 3 |
| 일자는 명시됐으나 해당 우선주 포함 여부 미확정 | 2 |
| 합계 | 96 |

- **진흥기업** `002785`·`002787`은 공지 본문 비고에서 두 우선주의 2026-08-14 정지를 확인했습니다. **서울식품공업1우선주** `004415`는 2026-04-27 정지 공지의 해제 조건과 2026-05-21 변경상장 공지에 명시된 코드·ISIN을 연결했습니다. [진흥기업 정지](https://kind.krx.co.kr/external/2026/08/07/000062/20260807000094/68054.htm) · [서울식품공업 변경상장](https://kind.krx.co.kr/external/2026/05/18/000288/20260518000404/68155.htm)
- **쌍용씨앤이** `003410`과 **한솔피엔에스** `010420`은 KIND 상장폐지 공지에서 정지·해제 공지와 동일한 상호 및 보통주 단축코드를 확인했습니다. ISIN은 적용일 KRX 상장 주권 목록에서 연결했습니다. [쌍용씨앤이 상장폐지](https://kind.krx.co.kr/external/2024/07/02/000332/20240702000854/68051.htm) · [한솔피엔에스 상장폐지](https://kind.krx.co.kr/external/2025/09/18/000039/20250918000091/68051.htm)
- **삼양홀딩스1우선주** `000075` (`KR7000071001`)의 **2025-05-30 정지**와 **2025-06-02 해제**는 미확정입니다. 접수 `20250530000970` 원문은 회사분할 결정에 따른 대상 주권을 회사명으로 표시합니다. 8월 1일 정정 공지와 8월 20일 상장폐지는 같은 우선주의 존속기간 만료에 따른 별도 조치입니다. [5월 정지·해제](https://kind.krx.co.kr/external/2025/05/30/000970/20250530001849/99808.htm) · [8월 정정](https://kind.krx.co.kr/external/2025/08/01/001222/20250801003585/68054.htm) · [상장폐지](https://kind.krx.co.kr/external/2025/08/14/000159/20250814000402/68051.htm)

결과의 `phaseReviews`에 공지상 적용일과 시각, 당시 상장 주권, 접수와 추가 근거를 기록했습니다. `relatedDelistingsBySymbol`에 상장폐지 정정 전후 기재값을 보존했습니다. KIND에서 확인한 내용은 공지상 조치이며, 실제 상태 전환과 첫 체결은 종목별 별도 원장이 필요합니다.

[삼양홀딩스1우선주 상태 전환 자료 조사](historical-samyang-preferred-halt-records.md)에서 코스콤 시장조치내역과 ICE의 KRX 과거 틱 상품을 확인했습니다. 해당 두 날짜의 원본 상태 전환 기록은 공급 범위 확인이 필요합니다.

## 재검증

AI 서버에서 [입력 명세](../../examples/historical-kospi-halt-scope-inputs.json)의 원장·상장 목록·후속 공지·KRX CSV 해시를 확인한 뒤 동일 결과를 계산합니다. `dailySources`에는 원본 경로·해시·코드·ISIN·조회 기간을, `dailyUnavailableRanges`에는 검색 미반환 기간과 관찰일을 기록했습니다. 원본 CSV는 AI 서버의 로컬 `research-artifacts/h05-kospi-halt-share-scope/authenticated-daily`에 보관합니다. 감사 재실행에는 입력 명세가 가리키는 로컬 원본이 필요합니다.

~~~powershell
$haltScopeOptions = @(
  '--manifest', '../../docs/examples/historical-kospi-halt-scope-inputs.json',
  '--ledger', '../../docs/examples/historical-market-action-monthly.jsonl',
  '--artifacts', 'research-artifacts',
  '--job', 'research-artifacts/h05-kospi-halt-share-scope',
  '--output', '../../docs/examples/historical-kospi-halt-scope.json'
)
.\.venv\Scripts\python.exe -m app.replay.historical_kospi_halt_scope audit @haltScopeOptions
~~~

오프라인 감사에서 결과를 바이트 단위로 재현했습니다. 결과 SHA-256은 `72baceb9a598a07d2099ab4c2fb0ca1a40660edbfd2e7c2845538a667f7eb368`입니다. 기존 조회 계획의 638개 조합과 접수 연결이 응답 및 미반환 목록의 합집합과 일치하는지 검사했습니다. AI 서버 전체 회귀는 1,423건 통과이며 격리 Java/MySQL 내보내기 자료가 필요한 검사 1건은 건너뛰었습니다.

미반환 대조는 [입력 명세](../../examples/historical-kospi-halt-missing-inputs.json)의 이전 결과 해시, 월별 원문, KIND 조회·원문 수집 영수증 해시를 검증해 재현합니다. KIND 원본은 AI 서버의 로컬 `research-artifacts/h05-kind-missing-halt-evidence/captures`에 보관합니다.

~~~powershell
.\.venv\Scripts\python.exe -m app.replay.historical_kospi_halt_missing audit `
  --manifest ../../docs/examples/historical-kospi-halt-missing-inputs.json `
  --baseline ../../docs/examples/historical-kospi-halt-scope.json `
  --artifacts research-artifacts `
  --job research-artifacts/h05-kind-missing-halt-evidence `
  --output ../../docs/examples/historical-kospi-halt-missing.json
~~~

미반환 대조 결과를 오프라인에서 바이트 단위로 재현했습니다. SHA-256은 `0a638862a7c8a9b6e14354ab55ab17397489ae4b89c0cd3f21420bf8fcce3314`입니다. AI 서버 전체 회귀 1,427건을 통과했고, 격리 Java/MySQL 내보내기 자료가 필요한 검사 1건은 건너뛰었습니다.
