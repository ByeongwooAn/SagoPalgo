# 5-07 KIS 과거 원주가 수집·실제 대조

기준일: 2026-11-03. [5번 고정 체크리스트](../../project/numbered-work-progress.md)의 5-07입니다. 수집기·공식 계약·실제 3년 일봉 수집/대조와 후속 [개인용 이용 범위 확정](historical-reference-validation.md)을 완료해 7/18·39%로 반영했습니다. 아래 미확인 서술은 최초 수집 당시 기록이며 새 범위 기록이 이를 소급 수정하지 않습니다.

## 확인한 자료 범위

| 자료 | 공식 근거와 이번 확인 | 상태 |
|---|---|---|
| KIS KRX 일봉 | [공식 함수](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/inquire_daily_itemchartprice/inquire_daily_itemchartprice.py): 호출당 최대 100건, D 일봉, 1 원주가·0 수정주가 | 작은 날짜 구간의 실제 조회·중첩/별도 대조 완료. 전체 종목/최대 과거 보관 기간 확인을 뜻하지 않음 |
| 날짜·가격·기업행사 관련 원문 필드 | [공식 점검 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/inquire_daily_itemchartprice/chk_inquire_daily_itemchartprice.py): 영업일·OHLC·거래량·락/분할/변경 등 | 숫자 문자열·제공 날짜·원문 플래그를 보존. 기업행사 원장으로 해석하지 않음 |
| 과거 분봉 | [공식 함수](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/inquire_time_dailychartprice/inquire_time_dailychartprice.py): 실전 호출당 최대 120건, 서버 보관 범위 내 최대 1년 안내 | 이번 수집기는 일봉만 지원. 이를 다년간 분봉/호가 확보로 계산하지 않음 |
| 개인용 조회 권한 | 기존 활성 KIS 개인 조회 설정과 실제 인증·시세 조회 성공 | 계정의 조회 접근 확인. 장기 보관/AI 학습·재배포 권한을 자동 확정하지 않음 |
| AI 학습·장기 보관 | [고객 약관·개인 분석 FAQ 추가 조사](../../market-data/kis-data-usage-evidence.md): 개인 분석 허용 안내 확인, 학습/보관 조건의 명시 문구는 미확인 | 사용자도 기존 확인 자료 없음. 금지로 단정하지 않고 미확인으로 유지하며 학습은 연결하지 않음 |

공식 예제의 지원 필드·요청 상한과 계정의 공유 호출 예산·자료 활용권은 별개입니다. 이번 설정의 2초 간격/64회 상한은 수집기의 보호 값이며 공급자가 허용한 한도라는 뜻이 아닙니다.

## 구현

[app/replay/history.py](../../../AI/ai-server/app/replay/history.py)는 기존 오프라인 재현 CLI와 별도 실행점입니다.

- `plan`: 날짜·종목·출처·권한 선언·호출 예산을 확인한 뒤 원본 요청과 결정적 계획을 저장합니다. 네트워크를 호출하지 않습니다. 기존 폴더를 덮어쓰지 않습니다.
- `collect`: 공식 운영 HTTPS의 OAuth 인증 POST와 고정된 국내 기간별 시세 GET만 사용합니다. KRX·DAY·원주가를 고정하며 계좌/주문·다른 서버·리다이렉트를 허용하지 않습니다. 인증값은 환경변수에서 받고 토큰은 메모리에만 둡니다.
- `audit`: 원본 응답 해시·요청 계보·가격 관계·중첩/추가 대조와 daily.jsonl을 다시 계산해 확인합니다. 네트워크를 호출하지 않습니다.

한 작업은 최대 약 10년, 한 구간은 8~90달력일입니다. 기본은 60달력일·7일 중첩으로 100건 상한보다 작게 요청합니다. 7일 중첩은 영업일 달력을 대신하지 않습니다. 구간별 미조회/빈 응답과 중첩 값 모순을 구분하고, 최초·중간·최근 제공 날짜를 최대 3번 별도로 조회합니다.

호출 횟수는 인증·실패도 포함합니다. 요청 전에 IN_FLIGHT와 소비 예산을 파일에 flush/fsync하고, 응답은 새 번호의 파일로 보관합니다. 실패하면 완료 구간을 보존하고 재실행은 완료되지 않은 구간·대조만 시도합니다. 이전 실패와 재인증도 누적 예산에 포함합니다. 자동 네트워크 재시도는 없습니다.

동일 작업의 동시 실행은 PID·시작 시각을 가진 배타 잠금으로 막습니다. 프로세스 강제 종료로 잠금이나 IN_FLIGHT가 남으면 자동 삭제/재전송하지 않습니다. 소유 프로세스의 종료·원본/영수증·이미 소비한 예산을 확인한 운영자 복구가 필요합니다. 별도 앱과 공유하는 API 키의 전체 예산을 이 파일만으로 통제하지는 못합니다.

## 산출물과 품질

| 파일 | 내용 |
|---|---|
| request.json / plan.json | 원본 설정·가격 기준·날짜 구간·계획 해시. 인증값 없음 |
| journal.json | 인증/조회/검증 시도, 요청 전 상태, 결과/고정 실패 코드, 원본 파일 해시 |
| response-번호.json | 공개 시세 응답 원본. 인증 응답·키·토큰·HTTP 헤더는 저장하지 않음 |
| daily.jsonl | 중첩 대조 후 날짜별 원주가·수량 문자열·최초 수집 시각·기업행사 관련 원문 플래그 |
| audit.json | 구간/건수·원본/파생 해시·추가 대조·활용권/완전성 상태 |

공급자의 실패 응답을 빈 성공으로 바꾸지 않습니다. 종목 불일치·날짜 이탈·중복 날짜·잘못된 수치/OHLC·중첩 모순·추가 대조 실패는 중단합니다. 빈 공급자 패딩과 날짜가 있지만 가격/거래량이 모두 0인 기록은 구분하며 후자는 NON_TRADING_OR_UNKNOWN으로 보존합니다.

날짜는 `businessDate`·DATE 정밀도이고, 거래소/통화/주기는 KRX/KRW/DAY입니다. 확인되지 않은 과거 장 시작/종료·공개 시각·종목 편입·기업행사를 만들지 않습니다. 따라서 곧바로 R5의 시각 있는 BAR 또는 분봉 전략에 넣지 않습니다. 5-08의 실제 달력·기업행사/종목군과 시점 기준을 확인한 뒤 연결해야 합니다.

`COLLECTED`는 계획한 요청 구간과 선택 날짜 재조회가 끝났다는 뜻입니다. `marketCoverage=UNVERIFIED_NO_CALENDAR`, `usableForTraining=false`, `usableForTrading=false`를 유지합니다. queryRightsConfirmed는 실행자의 개인 조회 범위 선언이며 인증 성공과 별도로 학습 권한의 근거를 만들지 않습니다.

## 실제 읽기 수집 기록

실행일은 2026-11-03입니다. 기존 활성화된 KIS 개인용 설정으로 삼성전자 005930의 **2023-11-01~2026-11-02 원주가 일봉**만 수집했습니다. 새 DB 적용·배포·실시간 수집 설정·실제 계좌/주문·모델 학습은 실행하지 않았습니다.

| 검사 | 결과 |
|---|---|
| 실제 일봉 | 730건, 최초/최근 제공 날짜가 요청 경계와 일치 |
| 날짜 구간 | 21/21 완료, 빈 구간 0 |
| 중첩 비교 | 89건 일치 |
| 별도 재조회 | 최초·중간·최근 3/3 일치 |
| 전체 호출 | 인증 1 + 구간 21 + 대조 3 = 25회, 상한 64회 |
| 무결성 | 전체 원본 해시·정규화 파생 자료 재검사 통과 |
| 활용 범위 | 조회 접근 확인, 학습/장기 보관 권한 미확인 |

대조는 같은 공급자의 별도 요청이며 독립 공급자 검증이나 거래소 전체 영업일·휴장/정지·과거 상장군 검증이 아닙니다. 실제 가격·키·토큰·개인 설정은 Git/PR에 올리지 않습니다. 원본·실행/대조 자료는 Git 제외 로컬 `AI/ai-server/research-artifacts/kis-daily-live-20261103-130145/job/`에 보관했습니다. 공개 문서에는 기간·집계만 기록합니다.

## 사용법

```powershell
# 작업 디렉터리 AI/ai-server. 기본 예제는 오프라인 계획용입니다.
.\.venv\Scripts\python.exe -m app.replay.history plan --config examples/replay/history-request.json --output research-artifacts/history-job

# 실제 실행에는 근거를 확인한 PROVIDER_HISTORICAL 설정과 환경변수가 필요합니다.
# SAGOPALGO_KIS_APP_KEY, SAGOPALGO_KIS_APP_SECRET: 명령행 인수나 Git 파일에 넣지 않습니다.
.\.venv\Scripts\python.exe -m app.replay.history collect --job research-artifacts/history-job
.\.venv\Scripts\python.exe -m app.replay.history audit --job research-artifacts/history-job
```

예제는 SYNTHETIC·조회 권한 false라 collect를 허용하지 않습니다. 실제 설정·인증값은 Git 제외 위치/환경에서 별도 준비합니다. 코드가 프로젝트 .env를 자동 읽거나 스케줄러를 켜지 않습니다. 실패/형식 오류는 원문 없는 고정 코드·종료값 2, 불완전 수집은 1입니다.

자동 테스트는 가상 전송기로만 실행합니다. 전체 AI 서버 검증 132건 통과(기존 102 + 신규 30)이며 기존 Starlette/AnyIO 경고 1건은 유지됩니다. 원본 Java/MySQL 교차 파일을 지정하지 않은 일반 실행에서는 기존 교차 검사 1건만 별도 제외합니다. 실제 KIS 조회는 위의 독립 수집 기록입니다.

## 5-07 세부 체크

- [x] 공식 요청 계약·가격 기준·일/분봉 범위 조사
- [x] 호출 예산·원본/실패 보존·재개·해시/데이터 대조 구현
- [x] 실제 다년간 1종목 일봉 수집·중첩/선택 날짜 대조
- [x] 공식 개인 저장/가공/분석 FAQ와 사용자 확정 범위에 근거한 개인용 진행 기준 확정 — 별도의 명시적 AI 허가를 받았다고 표시하지 않음

마지막 조건을 확인할 때 원래 수집 기록의 ‘당시 미확인’ 상태를 소급 수정하지 않고 별도 확인 근거·시각을 연결합니다. 실제 시장 전체 자료·기업행사·달력·독립 모델 평가·단타 전략 검증은 계속 후속입니다.

사용자의 추가 조사 요청에 따라 공식 고객 약관 제5조③·제14조와 개인 분석 FAQ를 확인했습니다. 상세 출처·검색 범위·고객 기록 보존 조항의 주체 구분·발송하지 않은 문의 초안은 [활용권 조사](../../market-data/kis-data-usage-evidence.md)에 정리했습니다.
