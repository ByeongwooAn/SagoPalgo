# 5-08 개인용 자료 이용 범위·과거 기준정보 검증

기준일: 2026-11-03. 사용자가 본인 투자 목적·외부 AI 시세 전송 없음·타인 데이터/서비스 제공 없음으로 운용 범위를 확정했습니다. [새 공식 FAQ](https://apiportal.koreainvestment.com/community/10000000-0000-0011-0000-000000000002/post/1f422ddb-7a9c-4279-9ecb-21eb750a4b7a)의 개인용 로컬 저장·가공·분석 안내와 함께 개인용 학습/추론 진행 근거로 기록합니다. KIS가 AI 학습을 별도로 명시 승인했다고 표시하지 않습니다.

후속: [실제 KIND 거래시간 공지·시장별 대조](historical-session-evidence.md)를 추가했습니다. 세션은 시장/날짜별로 구분하고 실제 자료 검사에는 `--market`을 지정합니다. 새 공지의 knownAt은 현재 확보 시각이며 과거 공개 시각으로 소급하지 않습니다. 아래 163건과 최초 대조 기록은 당시 결과이고, 최신 전체 검증은 193건입니다.

## 이용 범위와 원본 이력

[local_use.py](../AI/ai-server/app/replay/local_use.py)의 accept-local은 완료된 수집의 원본/파생 해시를 재검사하고 별도 이용 범위 기록을 생성합니다.

- historyPlanId·dailySha256으로 정확한 수집 자료에 연결합니다.
- basis=PERSONAL_ANALYSIS_INTERPRETATION, 목적은 SELF_ASSET_INVESTMENT입니다.
- localStorageOnly=true, externalAiTransfer=false, thirdPartyProvision=false를 검사합니다. 범위를 넓힌 설정이나 providerExplicitAiGrant=true는 이 기록 형식에서 거절합니다.
- 처음 수집했을 때의 request/plan/journal/audit와 trainingRightsConfirmed=false를 소급 수정하지 않습니다. 새 해석·운용 범위·기록 시각은 별도 파일입니다.

이용 범위 수락은 학습 입력 품질 검증을 대신하지 않습니다. 이후 검사기는 localUseAccepted=true와 실제 달력/세션/종목군/기업행사 부족 사유를 분리합니다. 이번에는 외부 AI 연결이나 모델 학습 실행을 추가하지 않았습니다. 범위 선언 검증이며 다른 임의 프로그램의 네트워크 접근을 통제하는 방화벽 기능은 아닙니다.

## 기준정보 팩

[reference.py](../AI/ai-server/app/replay/reference.py)의 SAGOPALGO_MARKET_REFERENCE_V1은 출처·실측/근거 입력/가상 구분·관측 시각과 다음 자료를 받습니다. [가상 예제](../AI/ai-server/examples/replay/reference-pack.json)는 실제 시장 근거가 아닙니다.

| 자료 | 필드/검사 |
|---|---|
| calendar | 날짜와 영업일·거래일·개장일·결제일을 각각 보존. 모르는 날짜를 주말 규칙으로 생성하지 않음 |
| sessions | 날짜별 실제 openAt/closeAt·knownAt·근거. 같은 한국 날짜의 유효 구간만 허용. 기본 09:00을 자동 입력하지 않음 |
| listings | 종목·편입/제외·효력 날짜·당시 확인 가능 시각·근거. 오늘 상장 목록을 과거 전체 종목군으로 대체하지 않음 |
| actions | 분할·배당·합병·권리·정지 등의 효력 날짜·knownAt·근거. 분할 비율은 양의 십진 문자열. 가격을 자동 소급 조정하지 않음 |
| coverage | 자료 종류·기간·시장 전체/특정 종목·완전/부분/미확인과 근거를 명시. 특정 종목 목록을 시장 전체 선언으로 혼합하지 않음 |

동일 날짜/이벤트의 다른 내용은 충돌로 중단합니다. 당시 보이는 종목 상태는 knownAt과 effectiveDate를 함께 확인하며, 같은 효력 날짜의 상충 상태를 임의 선택하지 않습니다. 알려지지 않은 미래 분할·배당은 과거 조회에서 제외합니다. 미리 알려진 향후 사건은 보이되 과거 가격을 조정하지 않습니다.

coverage는 근거를 가진 입력자의 범위 선언입니다. 선언만으로 독립 검증을 완료한 것은 아니며 보고서에 declaredCoverageOnly=true로 표시합니다. 가상 기준정보를 실측 가격에 섞으면 별도 문제로 남깁니다.

## KIS 캘린더 단일 조회

[공식 휴장일 함수](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/chk_holiday/chk_holiday.py)는 원장 서비스 영향을 이유로 가급적 1일 1회 호출을 요청합니다. calendar-fetch는 다음을 지킵니다.

1. 로컬 날짜별 예약 디렉터리·요청 전 영수증을 만들고 인증 후 캘린더 GET 1회만 실행합니다. 공식 HTTPS·CTCA0903R·고정 경로를 사용합니다.
2. 다음 페이지 표시가 있어도 자동 순회하지 않습니다. 같은 날짜/기준일 재실행은 원본/변환 해시를 확인해 캐시를 반환하고 다른 기준일·실패·미해결 예약은 추가 요청을 차단합니다.
3. 원문·조회 기준일·관측 시각·페이지 상태·해시를 보관합니다. 키/토큰/인증 응답은 저장하지 않으며 키 구분에는 해시만 사용합니다.
4. 받은 날짜만 팩으로 변환하고 세션 시각·종목군·기업행사는 만들지 않습니다. 행이 연속으로 보여도 전체 과거 달력의 완전성을 선언하지 않습니다.

이 제한은 해당 캐시를 사용하는 도구의 보호 범위이며 다른 앱/프로세스의 공유 계정 호출까지 통제하지 않습니다. 캐시 경로를 바꿔 우회 호출하거나 실패를 자동 재시도하는 기능은 제공하지 않습니다.

## 실제 대조 결과

기존 730건 원주가 자료에 개인용 범위를 별도 연결했습니다. 원래 수집 시도 25회와 원본 파일은 변경하지 않았습니다. 캘린더는 2023-11-01 기준으로 인증 후 GET 1회만 실행했고, 재실행 시 캐시 반환·추가 네트워크 없음도 확인했습니다.

| 항목 | 결과 |
|---|---|
| 일봉 자료 | 2023-11-01~2026-11-02의 730건 |
| 비교 대상 달력 날짜 | 1,098일 |
| 이번 캘린더 응답 | 2023-11-01~2023-11-24의 24일 |
| 원문 플래그 | 거래일 Y 24일, 개장일 Y 18일. 두 플래그가 다른 날짜 6개는 그대로 보존 |
| 가격 대조 기준 | 공식 함수가 주문 가능일 확인에 안내한 opnd_yn, 보고서 expectedPriceDayBasis=OPEN_DAY |
| 확인된 개장일의 일봉 | 18/18 존재, 이 범위 내 가격/개장일 불일치 0 |
| 제공되지 않은 날짜 | 1,074일을 UNKNOWN으로 유지 |
| 세션·상장군·기업행사 | 미확보/범위 미확인으로 표시. 전체 기준정보 검증 완료로 올리지 않음 |

초기 개발 검사는 tr_day_yn을 기준으로 6건의 후보 불일치를 냈습니다. 실제 응답에서 거래일/개장일 값의 차이를 확인하고 공식 안내에 맞춰 개장일 기준을 명시했습니다. 가격을 생성하거나 공급자의 플래그를 바꿔 해결한 것이 아닙니다. 최초 검사와 최종 보고서는 모두 로컬에 남겼습니다.

산출물은 Git 제외 `AI/ai-server/research-artifacts/kis-daily-live-20261103-130145/personal-local-use.json`, `reference-check-open-days.json`, `AI/ai-server/research-artifacts/kis-calendar-cache/2026-11-03/`에 있습니다. 실제 시세 원문·개인 설정은 PR에 포함하지 않습니다.

## 실행

```powershell
# 작업 디렉터리 AI/ai-server. 실제 자료/근거는 Git 제외 위치에 준비합니다.
.\.venv\Scripts\python.exe -m app.replay.reference_cli accept-local --job research-artifacts/history-job --output research-artifacts/local-use.json
.\.venv\Scripts\python.exe -m app.replay.reference_cli calendar-fetch --basis-date 2023-11-01 --cache research-artifacts/calendar-cache
.\.venv\Scripts\python.exe -m app.replay.reference_cli check --job research-artifacts/history-job --local-use research-artifacts/local-use.json --reference research-artifacts/calendar-cache/2026-11-03/reference.json --output research-artifacts/reference-check.json
```

accept-local/check는 네트워크 없는 파일 검증입니다. calendar-fetch만 기존 환경변수의 개인용 KIS 인증으로 공식 조회를 수행합니다. .env를 자동 로드하거나 수집/주문 스위치를 켜지 않습니다. 출력은 덮어쓰지 않으며 REFERENCE_GAPS는 종료값 1, 입력/저장소/형식 오류는 고정 코드와 2입니다.

검증은 전체 AI 서버 163건 통과(기존 132 + 신규 31), 실패/오류/제외 0입니다. 날짜/시각·미래 사건·분할 비율·충돌·특정 종목/시장 범위·개인용 범위 위반·파일 변조·캐시/실패 예약·페이지 미순회·날짜별 coverage 합집합을 검사했습니다. 기존 Starlette/AnyIO 경고 1건은 유지됩니다. 실제 호출은 자동 테스트와 별개이며 캘린더 조회는 위 1회입니다.

5-07은 확정된 개인용 범위에서 완료, 5번은 **7/18·39%**입니다. 5-08은 형식·시점/범위 검사와 실제 일부 달력 대조까지 진행 중입니다. 실제 과거 달력·특수 거래 세션·상장/폐지 종목군·기업행사 이력을 확보한 후 R5의 시각 있는 BAR/학습 특징으로 연결합니다. 이번에는 데이터셋 시각을 임의 생성하거나 실제 모델 학습·자동매매를 실행하지 않았습니다.
