# 5-08 이전상장·합병 폐지와 종목군 식별 목록

기준일: 2026-11-03. [이전 대표 사례와 고정 완료 조건](multi-company-reference-cases.md)의 후속입니다. 이번에는 **이전상장 1사례·합병에 따른 폐지 1사례**를 추가하고, 현재 상장법인 목록과 과거 사례를 연결하는 식별 목록을 만들었습니다. 1차 목표 기간·시장과 7개 완료 조건은 유지합니다.

## 실제 확보 결과

| 자료 | 확보 결과 | 의미 |
|---|---|---|
| KIND KOSPI 상장법인 목록 | 829행 | 수집 당시의 법인 목록. 과거 보통주 종목군이 아님 |
| KIND KOSDAQ 상장법인 목록 | 1,827행 | 수집 당시의 법인 목록. 과거 보통주 종목군이 아님 |
| 현재 목록 합계 | 2,656개 식별 코드 | 서로 다른 시장에서 같은 코드가 중복되면 실패 |
| 과거 사례와 합친 식별 목록 | 2,658개 | 현재 명단에 없는 유진스팩7호·한국스팩11호 2개 보존 |
| 영문자가 포함된 코드 | 69개 | 원문 그대로 보존. 기존 숫자 6자리 시세 처리기의 지원 대상으로 간주하지 않음 |
| 신규 사건 자료 | 공시 3건, 대표 사례 2건 | 시장별 편입/제외 사건 3건 생성 |

목록의 1차 출처는 KIND [상장법인목록 화면](https://kind.krx.co.kr/corpgeneral/corpList.do?method=loadInitPage)과 시장별 [KOSPI 내려받기](https://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13&marketType=stockMkt), [KOSDAQ 내려받기](https://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13&marketType=kosdaqMkt)입니다. 각 원문 GET 1회씩, 사건 3건 포함 **이번 신규 수집 총 5회**입니다. 재검증 추가 통신은 0회이며 KB 계좌·KIS·OpenDART API 추가 호출은 없습니다.

현재 목록은 회사·코드 대응을 넓히기 위한 기초입니다. 2023-11-01 시작 시점의 전체 종목군이나 2026-11-02 종가 시점의 명단으로 소급하지 않습니다. 공급자 기준 시각은 없으므로 `providerAsOf=null`, 두 시장 순차 조회이므로 `snapshotAtomic=false`, 독립 총수 대조가 없어 `independentTotalVerified=false`입니다. 각 행은 `reportedListingDate`와 현재 `knownAt`을 분리하고, 해당 날짜에 상장됐다고 과거 편입 사건을 생성하지 않습니다.

## 이전상장: 엘앤에프

- KOSDAQ [상장폐지 공시](https://kind.krx.co.kr/external/2024/01/24/000603/20240124001736/70769.htm)는 066970 보통주·회사명·사유 `유가증권시장 상장`·폐지일 2024-01-29를 명시합니다.
- KOSPI [이전상장 기준가격 안내](https://kind.krx.co.kr/external/2024/01/26/000543/20240126001612/99343.htm)는 같은 코드·보통주식·사유 `이전상장`·적용일 2024-01-29를 명시합니다. 회사명 표기의 차이는 설정에 각각 기록하고 양쪽 코드로 대조합니다.
- 두 근거를 함께 검증한 뒤 01-29에 **KOSDAQ 제외와 KOSPI 편입을 각각 생성**합니다. 시장 전체에서 거래할 수 없어진 종목으로 처리하지 않습니다. 날짜·코드·주식 종류·시장·사유가 충돌하거나 한쪽 원문이 없으면 완성된 이전상장 사건을 만들지 않습니다.
- 사건 `knownAt`은 두 원문 수집 시각 중 늦은 값입니다. 뒤에 확보한 편입 자료를 앞 시점 조회에 노출하지 않습니다. 01-28의 소속 시장은 근거 없이 역산하지 않고 미확인으로 둡니다.

기존 `SAGOPALGO_MARKET_REFERENCE_V1`의 상장 사건에는 시장 필드가 없습니다. 여기에 시장별 두 사건을 넣으면 같은 코드·날짜의 상충이나 시장 전체 폐지로 해석될 수 있어, **별도 `venueEvents` 형식과 조회**를 추가했습니다. 기존 기준정보 모델·보고서 해시는 바꾸지 않았으며 기존 가격 재현기에 이 자료를 자동 투입하지 않습니다.

## 합병에 따른 폐지: 한국제11호스팩

[거래소 폐지 공시](https://kind.krx.co.kr/external/2024/09/25/000422/20240925001236/70769.htm)의 436610 보통주·회사명·사유 `피흡수합병(스팩소멸합병)`·폐지일 2024-09-27을 검증했습니다. 기타란의 흡수합병 상대방 `(주)차이커뮤니케이션`도 설정과 대조합니다.

이 근거로 만드는 것은 **소멸 종목의 KOSDAQ 제외 사건 1건**입니다. 폐지일을 법적 합병 효력일로 바꾸지 않으며 교환 비율·존속회사 코드·실제 신규상장·계좌 수량을 추측하지 않습니다. `legalMergerCompletionConfirmed=false`, `survivorListingConfirmed=false`, `exchangeRatio=null`입니다. 법적 합병 완료·비율·존속회사 주식 연결은 별도 원문 대조가 남습니다.

## 종목군 식별 목록의 처리

`kind_registry`는 검토한 EUC-KR 내려받기 표를 읽고 헤더·시장·날짜·코드·행 길이·중복을 검사합니다. 1956년처럼 목표 기간보다 오래된 상장일과 코드의 선행 0을 보존합니다. 현재 원문의 6자리 영문·숫자 코드는 누락시키지 않고 `numericCodeSupported`로 기존 시세 처리기의 지원 여부를 구분합니다. 기존 가격/주문 모델의 숫자 6자리 제약은 이번에 바꾸지 않았으며 69개 코드의 시세 연결은 남은 확장입니다.

`seed-build`는 현재 목록과 **감사한 기존 5사례·신규 2사례**를 코드로 연결합니다. 출처 보고서 해시와 개별 원문 해시·수집 시각·과거 회사명·시장 관찰을 보존하고 서로 덮어쓰지 않습니다. 현재 목록에 없다는 상태는 `NOT_PRESENT`로만 표시합니다. 목록에 없다는 이유만으로 상장폐지 사유를 만들어내지 않으며, 명시적 과거 원문 근거가 있는 코드도 식별 목록에서 제거하지 않습니다.

현재 법인 목록만으로 보통주 증권 종류·기간별 소속을 확정하지 않습니다. `membershipEventsGeneratedFromCurrentSnapshot=0`, `historicalMembershipComplete=false`, `marketUniverseComplete=false`입니다. `seed-lookup`은 조회 시각 이전에 확보한 관찰만 반환하며 과거 거래 가능 종목군을 반환하는 API가 아닙니다. 시장별 사건 조회도 실제 주문 가능 상태를 확정하지 않습니다.

## 재실행

`AI/ai-server`에서 실행합니다. 새 수집이 필요한 경우에만 예산을 명시합니다. 아래는 모두 이미 확보한 캐시를 사용하며 새 호출 예산 0입니다.

```powershell
.\.venv\Scripts\python.exe -m app.replay.universe_events capture --scope ../../docs/examples/universe-events.json --cache research-artifacts/kind-case-cache --max-new-requests 0
.\.venv\Scripts\python.exe -m app.replay.universe_events build --scope ../../docs/examples/universe-events.json --cache research-artifacts/kind-case-cache --report research-artifacts/universe-events-20261103/report.json
.\.venv\Scripts\python.exe -m app.replay.kind_registry capture --cache research-artifacts/kind-registry-20261103 --max-new-requests 0
.\.venv\Scripts\python.exe -m app.replay.kind_registry build --cache research-artifacts/kind-registry-20261103 --report research-artifacts/universe-events-20261103/registry.json
```

식별 목록 생성·감사는 같은 인자로 `seed-build`/`seed-audit`를 사용합니다.

```powershell
.\.venv\Scripts\python.exe -m app.replay.kind_registry seed-build `
  --cache research-artifacts/kind-registry-20261103 `
  --report research-artifacts/universe-events-20261103/seed-final.json `
  --case-cache research-artifacts/kind-case-cache `
  --case-scope ../../docs/examples/kind-reference-cases.json `
  --case-report research-artifacts/kind-cases-20261103/report.json `
  --event-scope ../../docs/examples/universe-events.json `
  --event-report research-artifacts/universe-events-20261103/report.json
```

`universe_events as-of`는 build와 같은 경로 인자에 `--stock 066970 --at <사건 knownAt 이후 시각> --date 2024-01-29`를 추가하면 KOSDAQ 제외/KOSPI 편입을 반환합니다. 과거 당시 시각으로 조회하면 현재 수집 자료를 제외합니다. `kind_registry seed-lookup`은 seed-audit와 같은 경로 인자에 `--symbol <6자리 코드> --at <조회 시각>`을 추가합니다.

`build/seed-build`는 기존 결과와 다시 계산한 값이 다르면 덮어쓰지 않고 실패합니다. 캐시/범위를 갱신할 때는 별도 경로를 사용합니다. 최초 수집에는 목록 `--max-new-requests 2`, 사건 `--max-new-requests 3`이 필요합니다. 실패한 원문 예약은 자동 재시도하지 않습니다. 실제 목록·본문·보고서는 Git에서 제외한 `research-artifacts/` 아래에 보관하며 Git에는 공개 출처 설정·코드·가상 테스트·문서만 포함합니다.

## 검증과 남은 체크리스트

- [x] 이전상장 두 원문의 날짜·코드·시장 일치와 시장별 사건 2건 검증
- [x] 합병 사유 폐지·존속회사 이름 대조와 제외 사건 1건 검증
- [x] 현재 법인 2,656개와 과거 사례의 2,658개 식별 목록 연결
- [x] 현재 목록에 없는 과거 코드 2개와 영문 포함 코드 69개 보존
- [x] 원문/영수증/보고서 감사·호출 예산·오류 예약·시점 경계 검증
- [x] 전체 AI 서버 **392건 통과, 실패/오류/건너뛰기 0건**(기존 355 + 신규 37), 기존 Starlette/AnyIO 경고 1건 유지. Java 저장 내보내기 fixture 포함
- [x] 실제 자료의 추가 통신 0회 재검증, 기존 가격/DART 작업 파일 55개와 모든 캐시 원문 해시 불변 확인
- [ ] **2023-11-01 시점의 전체 종목군 기준표**와 전 기간 상장/폐지/이전상장 이력 확보·대조
- [ ] 합병 법적 완료일·교환 비율·존속회사 증권 연결과 실제 가격 경계 대조
- [ ] 영문 포함 코드의 시세/재현 연결, 현재 법인 목록의 보통주 증권 분류 검증
- [ ] 전체 거래일 달력/세션·정정 계보·과거 공개 시각·완전성 감사

대표 사례는 기존 5개에서 **7개**로 늘었지만, 기준표가 없으므로 과거 전체 종목군의 확보 건수를 2,658개로 보고하지 않습니다. 달력·세션·일봉 730건·삼성전자 공시 204건의 기존 수집 범위는 유지합니다. **5-08 진행 중, 5번 고정 완료율 7/18·39% 유지**입니다. 다음 우선순위는 시작 시점 종목군 기준표와 기간별 상장/폐지 이력 확보입니다. 학습·실시간 주문·운영 배포·DB·EXE 변경은 없습니다.
