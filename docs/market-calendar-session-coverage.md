# 5-08 전체 기간 개장 여부 재구성과 시장별 특수 세션 확대

기준일: 2026-11-05. [V7 개별 공시 대조](remaining-membership-disclosures.md)의 다음 작업입니다. **2023-11-01~2026-11-02, KOSPI·KOSDAQ**을 대상으로 KRX 공식 연도별 휴장일과 시장 규칙을 연결했습니다. 기존 관측 28일에 머물렀던 달력 검사를 전체 **1,098일의 개장 여부 재구성**으로 확대하고, 양 시장 각각 **6일의 특수 거래시간**을 원문에서 확인했습니다.

## 결과와 근거 수준

| 항목 | 이전 | 이번 결과 |
|---|---:|---|
| 개장 여부 대조 날짜 | 기존 관측 28일 | 재구성 1,098일, 별도 누락 날짜 0 |
| 개장일 | 기존 확인 20일 | 재구성 730일 |
| 휴장일 | 일부만 확인 | 주말 314일 + 연도별 휴장일 54일 = 368일 |
| KOSPI 특수 세션 | 2일 | 6일 |
| KOSDAQ 특수 세션 | 기존 대표 사례 1일 | 6일 |
| 삼성전자 일봉과 날짜 대조 | 확인된 개장일만 대조 | 730/730개 일치, 개장일 가격 누락·휴장일 가격 0 |
| KOSPI 가격 날짜의 세션 미확보 | 728일 | 724일 |

KRX [공식 휴장일 화면](https://open.krx.co.kr/contents/MKD/01/0110/01100305/MKD01100305.jsp)의 연도 선택·KRX 구분·공개 조회 절차를 확인해 2023~2026년 목록을 확보했습니다. 전체 연도 원문에는 각각 15·18·19·17행, 합계 69행이 있습니다. 이 중 고정 기간 안의 휴장일은 54일입니다. [유가증권시장 규칙](https://regulation.krx.co.kr/contents/RGL/03/03010100/RGL03010100T1.jsp)과 [코스닥시장 규칙](https://regulation.krx.co.kr/contents/RGL/03/03020401/RGL03020401.jsp)을 검토해 주말과 결합합니다.

`ANNUAL_HOLIDAY`, `WEEKEND_RULE`, `WEEKDAY_OPEN_RECONSTRUCTION`을 구분합니다. 이는 연도별 현재 제공 목록과 검토한 규칙을 이용한 재구성이며, 매일의 별도 거래소 개장 플래그 원문을 받은 것으로 표시하지 않습니다. 과거에 그 목록을 언제 이용할 수 있었는지도 입증하지 않습니다. 모든 자료는 실제 확보 시각을 지식 시각으로 보존합니다.

기존 KIS 달력은 프로젝트의 하루 1회 정책을 유지해 추가 호출하지 않았습니다. 비어 있는 종목군 응답이나 가격 부재를 휴장 근거로 사용하지 않습니다. 새 달력을 먼저 만든 뒤 기존 KIS 일봉과 독립적으로 대조했습니다.

## 명시된 특수 세션과 일반 시간 후보

다음 6개 날짜를 **KOSPI·KOSDAQ 각각** 확인했습니다. 시각은 한국 시각이며 NXT·시간외·호가접수·경쟁대량매매 종료 시각을 정규장에 섞지 않습니다.

| 적용일 | 사유 | 정규장 | 출처 |
|---|---|---|---|
| 2023-11-16 | 수능일 | 10:00~16:30 | [미래에셋 공지](https://securities.miraeasset.com/bbs/board/message/view.do?categoryId=66&messageId=2312542) |
| 2024-01-02 | 연초 개장일 | 10:00~15:30 | [KRX 유가증권](https://kind.krx.co.kr/external/2023/12/14/000173/20231213000752/99303.htm), [KRX 코스닥](https://kind.krx.co.kr/external/2023/12/14/000189/20231214000422/70780.htm) |
| 2024-11-14 | 수능일 | 10:00~16:30 | [유안타 공지](https://www.myasset.com/myasset/customer/notice/CU_0201000_P2.cmd?SEQ=202411061044540000000004&gubun=norNotice) |
| 2025-01-02 | 연초 개장일 | 10:00~15:30 | [기존 KB 원문 재사용](https://www.kbsec.com/go.able?idt=20241226&linkcd=s060901010000&seq=10007903) |
| 2025-11-13 | 수능일 | 10:00~16:30 | [유안타 공지](https://www.myasset.com/myasset/customer/notice/CU_0201000_P2.cmd?SEQ=202511100903560000000004&gubun=norNotice) |
| 2026-01-02 | 연초 개장일 | 10:00~15:30 | [기존 KB 원문 재사용](https://www.kbsec.com/go.able?idt=20251222&linkcd=s060901010000&seq=10009341) |

연초 KRX 공시는 근거 규정과 검토한 양식으로 시장을 식별하고 연도·적용일·휴장일·정규장 시각을 검증합니다. 증권사 수능 공지는 적용 시장·시행 날짜·변경 전후 정규시장 행을 검증하며, 괄호의 경쟁대량매매 종료 시각을 별도로 처리합니다. 날짜·시장·본문 행이 모호하면 실패합니다.

현행 KRX 일반 정규장 09:00~15:30도 원문에서 확인했습니다. 다만 현행 안내문만으로 3년 전체에 동일 규칙이 계속 적용됐다고 확정하지 않습니다. **시장별 724일, 합계 1,448개의 일반 시간은 검토 후보**로 저장하고 `ReferencePack.sessions`에 넣지 않았습니다. 기간별 규정 효력·임시 변경의 전체 대조가 다음 작업입니다. 이 때문에 `allHistoricalSessionsComplete=false`를 유지합니다.

## 달력 플래그와 과거 시점

새 재구성 팩은 개장 여부를 제공하며 영업일·공급자 거래일·결제일을 일괄 생성하지 않습니다. 기존 KIS·KB의 명시된 플래그와 병합한 KOSPI 대조에서 영업일/거래일 미확인 각 **1,074일**, 결제일 미확인 **1,072일**이 남습니다. 기존 원문·부분 플래그는 그대로 보존합니다.

새 팩의 `coverage`는 빈 목록입니다. 개장 여부 재구성이 전 기간 달력의 모든 플래그나 모든 세션의 COMPLETE 선언으로 바뀌지 않습니다. 기존 검사 결과는 계속 `REFERENCE_GAPS`이며 `usableForTraining`, `usableForStrategyValidation`, `usableForTrading`은 false입니다.

달력은 필요한 연도 목록·시장 규칙을 모두 확보한 이후에만 조회하고, 각 특수 세션은 해당 원문의 실제 확보 시각 이후에만 조회합니다. 오래된 KB 캡처는 원래 확보 시각과 해시를 재사용합니다. URL 날짜·등록일을 과거 최초 공개 시각으로 소급하지 않습니다. 현재 규칙에서 만든 후보는 시점 조회에도 확정 세션으로 노출하지 않습니다.

## 위지윅스튜디오 날짜 충돌의 달력 문맥

V7의 개별 공시 확인 **576/577건·폐지일 충돌 1건**은 유지합니다. 새 `membership-context.json`은 다음 사실을 별도로 연결합니다.

| 날짜 | 재구성된 개장 여부 | 의미 |
|---|---|---|
| 2026-08-14 | 개장 | 개별 공시에 적힌 폐지일 |
| 2026-08-15~16 | 휴장 | 주말 |
| 2026-08-17 | 휴장 | KRX 목록에 명시된 광복절 대체휴일. 기존 종목군에는 종목이 남아 있던 날짜 |
| 2026-08-18 | 개장 | 다음 재구성 개장일이며 기존 관찰의 제외일 |

휴장일이 사이에 있다는 사실은 확인했지만, 공시 폐지일과 종목군 변경일의 기준 차이를 설명하는 공식 근거는 추가로 필요합니다. `causalExplanationConfirmed=false`, `exchangeDelistingDateOverridden=false`로 기록하고 V7의 날짜·검토 상태·관찰 868개를 수정하지 않습니다. 휴장일만으로 충돌을 해결 처리하지 않습니다.

## 실행·예산·재감사

구현은 `app.replay.krx_calendar_sources`와 `app.replay.market_calendar_evidence`, 검토한 출처 목록은 [market-calendar-sources.json](examples/market-calendar-sources.json)입니다. 공개 HTTP만 사용하며 계좌·KRX 인증 API·KIS·OpenDART 호출은 없습니다. 규칙/공지 확보와 오프라인 변환을 분리했습니다.

- 연도 목록: 새 요청 **6/16회**, 이미 확보한 2026년 조회 2회분을 불변 seed로 재사용
- 규칙/특수 공지: 새 GET **6/6회**, 기존 캡처 3건 재사용
- 규격/경로 탐색: **17회**. 위 seed의 최초 조회가 포함되므로 다시 더하지 않음
- 이번 CLI 공개 HTTP 합계 **29회**, 웹 검색은 별도. 두 수집 경로 모두 신규 요청 시작 간격 최소 1초
- 공개 화면용 일회성 조회 코드와 응답을 연결해 해시를 검사하며 사용자 인증키·토큰을 사용하지 않음
- 성공 캐시 재사용 시 새 요청 0회. 실패/중단 예약은 자동 재시도하지 않고 그대로 보존. 일회성 조회 코드가 만료된 실패는 새 계획으로 다시 확보해야 함

실측 최소 시작 간격은 연도 조회 **1.000572초**, 원문 GET **1.000978초**입니다. 원문·파생·V1~V7·기존 가격을 네트워크 차단 상태에서 재감사했으며 기존 파일 **7,332개**·신규 원문/계획/보고서 **67개**의 해시를 보존했습니다.

`.gitattributes`는 새 출처 목록의 LF를 고정해 Windows 체크아웃에서도 실제 바이트 해시가 유지되도록 합니다. 기존 사례 설정과 계획 해시는 변경하지 않습니다.

실행 위치는 `AI/ai-server`입니다. 최초 plan은 새 폴더에서 한 번 실행합니다. 새 환경에서 seed 없이 시작하면 연도별 2회씩 총 8회가 필요합니다.

```powershell
.\.venv\Scripts\python.exe -m app.replay.krx_calendar_sources plan `
  --job research-artifacts/calendar-sessions/years --start 2023-11-01 --end 2026-11-02 --max-requests 16
.\.venv\Scripts\python.exe -m app.replay.krx_calendar_sources collect `
  --job research-artifacts/calendar-sessions/years --max-new-requests 16
.\.venv\Scripts\python.exe -m app.replay.krx_calendar_sources audit --job research-artifacts/calendar-sessions/years

# 빈 캐시의 원문 출처 9건. 완료 후에는 0으로 캐시만 재감사할 수 있습니다.
.\.venv\Scripts\python.exe -m app.replay.market_calendar_evidence capture `
  --scope ../../docs/examples/market-calendar-sources.json --cache research-artifacts/calendar-sessions/sources --max-new-requests 9
$calendarArgs = @(
  '--scope', '../../docs/examples/market-calendar-sources.json',
  '--cache', 'research-artifacts/calendar-sessions/sources',
  '--year-job', 'research-artifacts/calendar-sessions/years',
  '--output', 'research-artifacts/calendar-sessions/report.json'
)
.\.venv\Scripts\python.exe -m app.replay.market_calendar_evidence build @calendarArgs
.\.venv\Scripts\python.exe -m app.replay.market_calendar_evidence audit @calendarArgs
.\.venv\Scripts\python.exe -m app.replay.market_calendar_evidence as-of @calendarArgs `
  --market KOSPI --at 2024-11-14T16:30:00+09:00
```

위 과거 시점 예제에서는 이번에 확보한 특수 공시가 보이지 않습니다. 실제 자료는 Git 제외 경로 `AI/ai-server/research-artifacts/calendar-sessions-20261105`의 `years/`, `sources/`, `discovery/`, `report.json`, 시장별 참조 팩, `price-reference-check.json`, `membership-context.json`, `validation.json`에 보관합니다. 코드·출처 목록·검증 결과 요약만 PR에 포함합니다.

| 산출물 | SHA-256 |
|---|---|
| 보존한 V7 | `99ed9386ee14991816a7e9907fcec8b214c714f52a4af470a49b262fe4d0bdbc` |
| 검토 출처 목록 | `8f81601d68bfb3bdb0c8f2fc96b000a67486a81303044e6b6b62a91e00b40d10` |
| 달력·세션 보고서 | `8803fae3e2bfd85c323693f51a3daba1ed5b9d90df0d99bbeb63fd5f89b23849` |
| 가격 날짜 대조 | `7d0b3cdb0bd9f647fad1c29c3e0df5360762d0616b91551181bd46be3ecf7d46` |
| 폐지일 달력 문맥 | `6d863dadc8fdcd527e9ce15a6b7174301d3df5d9afa6b18e851fdc05bad7178c` |

## 체크리스트

- [x] 공식 연도별 휴장일 4개 연도·시장 규칙 2건의 원문 연결
- [x] 두 시장의 전 기간 1,098일 개장 여부 재구성, 독립 일봉 730개 날짜 대조
- [x] 시장별 연초/수능 특수 세션 6일씩, 합계 12개 시장·날짜 확인
- [x] 일반 시간 후보 1,448개를 확정 세션에서 제외
- [x] 폐지일 충돌에 휴장일 문맥을 연결하고 V7·관찰·검토 상태 보존
- [x] 네트워크 차단 재감사·성공 캐시 재사용·확보 전 조회 제외
- [x] 전체 AI 서버 **877건 통과**: 기존 834 + 신규 43, 실패/오류/건너뛰기 0. Java 내보내기 fixture 포함, 기존 Starlette/AnyIO 경고 1건 유지
- [ ] 기간별 일반 정규장 규정·전체 임시 변경의 효력 범위 검증
- [ ] 미확인 영업일/거래일/결제일·과거 최초 공개 시점·남은 폐지일 근거 확인
- [ ] 전체 종목군/법적 사건/독립 총수·기업행사·가격/체결 재현 등 나머지 고정 조건

이번 작업은 5-08의 ② 거래일 달력·③ 세션과 ⑤ 시점·⑥ 대조·⑦ 감사를 보강했습니다. **5-08 진행 중·5번 7/18·39%, 1~5번 26/48·54%**를 유지합니다. 운영 배포·학습·실주문·DB·EXE 변경은 없습니다.
