# 6단계 KRX 수급 수신 증거 누적

삼성전자(`005930`)·SK하이닉스(`000660`)의 개인·기관·외국인 수급을 KIS 일별 API의 KRX 시장(`J`)에서 관측합니다. 거래일별 수신 응답 원문과 시각을 보관해 장 마감 모델 입력 시각인 20:15 KST까지 확보한 값을 재현합니다. [11월 26일 첫 실측](krx-investor-flow-availability-20261126.md#11월-26일-장-마감부터-익일까지-관측) · [KIS 일별 수급 요청 명세](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/investor_trade_by_stock_daily/investor_trade_by_stock_daily.py)

## 수집과 가용 판정

| 작업 | Codex 시작 시각(KST) | 자료 요청 창(KST) | 대상 거래일 |
| --- | --- | --- | --- |
| SagoPalgo KRX 수급 마감 전 관측 | 월~금 20:10 | 20:14:30부터 20:15 마감까지 | 당일 |
| SagoPalgo KRX 수급 익일 대조 | 화~토 08:45 | 08:50부터 08:55까지 | 전날 |

- 저녁 작업은 KIS 국내휴장일 페이지의 해당 날짜 `opnd_yn`을 확인하고 개장일에 조회합니다. 한 날짜의 달력 원본을 기존 로컬 캐시에서 검증하거나 새로 수신해 보존합니다. 토요일 아침 작업은 금요일 장후 관측을 대조합니다. 전날에 기준 시각 안에 수신한 응답이 하나도 없으면 익일 작업을 건너뜁니다. [KIS 국내휴장일 요청 명세](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/chk_holiday/chk_holiday.py)
- 응답을 모두 받은 직후 기록한 KST 시각, 거래일·종목·시장·조회 ID, HTTP 상태 및 원문 SHA-256으로 검증합니다. 개인·기관·외국인의 매수·매도·순매수 수량과 대금, 누적 거래량·대금을 확인합니다. 정상 수신과 필드 검사를 통과한 두 종목이 모두 20:15까지 확보되면 그 날짜를 공통 수급 후보로 집계합니다. 원문은 관측별로 보존하며, 익일 값은 변경 필드를 확인하는 데 사용합니다.
- 실패 응답과 마감 이후 응답에는 가용 자격을 부여하지 않습니다. 같은 창에서 다시 실행하면 아직 유효한 응답이 없는 종목을 조회합니다. 로컬 앱이나 실행 호스트의 중지, 네트워크 승인 지연, KIS 오류로 창을 놓친 날은 공통 표본에서 빠집니다.

## 실행과 확인

Windows에서 `AI/ai-server`를 작업 디렉터리로 사용합니다. CLI는 KIS 실환경의 기존 설정을 읽고, 시장 달력과 수급의 읽기 요청을 수행합니다. 저장 위치는 Git 제외 경로 `research-artifacts/kis-investor-flow-live/<거래일>/`입니다. 각 조회의 `receipt.json`과 `body.json`이 원문 근거이며, `audit.json`에 두 종목의 기준 시각 충족 여부와 익일 변경 필드를 기록합니다.

```powershell
.\.venv\Scripts\python.exe -m app.replay.krx_investor_flow_capture calendar
.\.venv\Scripts\python.exe -m app.replay.krx_investor_flow_capture close
.\.venv\Scripts\python.exe -m app.replay.krx_investor_flow_capture next-day
.\.venv\Scripts\python.exe -m app.replay.krx_investor_flow_capture audit --date 2026-11-27
```

`calendar`는 당일 시장 달력을 확인하고 `audit`은 네트워크 없이 해당 거래일의 수신 원문 해시와 가용 여부를 재검증합니다. `close`와 `next-day`는 표의 시작 시각부터 마감 전까지만 실행할 수 있습니다. 기본 샌드박스에서 KIS 도메인 DNS가 제한되어 네트워크 권한이 필요합니다.

## 2026-11-27 준비 검증

- 11월 26일에 수신한 마감 전 원문과 11월 27일 08:50 익일 원문을 두 종목씩 대조하고, 기존 수신 기록과 해시를 연결해 누적 폴더에 등록했습니다. 새 감사 CLI에서 두 종목 모두 기준 시각을 충족했고 운용에 사용하는 수급·누적 거래 필드의 익일 변경은 0개였습니다.
- KIS 시장 달력에서 11월 27일 개장을 확인했습니다. 두 종목의 11월 26일 행은 11월 27일 10:48 KST에 정상 조회됐고, 파서로 날짜와 필드를 확인했습니다. 이 실행의 사후 조회 응답은 당일 가용 시점 표본에 포함하지 않습니다.
- 로컬 Codex에서 저녁 관측과 익일 대조 작업을 활성화했습니다. 11월 27일 장후와 11월 28일 익일의 예약 실행 결과가 첫 자동 수집 대조 대상입니다.
- 시각 경계, 늦은 수신 제외, 토요일 아침 정정 대조, 휴장·누락 처리, 반복 실행, 원문 해시 손상 검출을 오프라인으로 검증했습니다. 모델에 사용할 날짜는 시간순 학습·검증·독립 평가를 구성할 표본이 확보되면 두 모델에 공통으로 고정합니다. [수급 특징과 평가 기준](learning-prototype.md#투자자별-수급공시뉴스-비교-기준)

## 2026-11-28 첫 예약 실행 대조

| 확인 항목 | 결과 |
| --- | --- |
| 11월 27일 시장 달력 | KIS 저장본에서 개장(`openDay=true`) 확인 |
| 11월 27일 마감 전 수집 | 20:10 KST 예약의 실패 기록이 20:05:29에 남았습니다. CLI는 시작 허용 시각인 20:10 전에 `FLOW_OUTSIDE_CAPTURE_WINDOW`로 종료됐습니다. |
| 11월 28일 익일 대조 | 08:45:33 KST 실행 기록에 `NO_PRIOR_EVIDENCE`가 남았습니다. 전날의 유효한 마감 전 원문이 없어 수급 요청을 건너뛰었습니다. |
| 11월 27일 오프라인 감사 | 삼성전자·SK하이닉스 모두 `close`, `nextDay`, `changedFields`가 `null`이고 `commonByCutoff=false`입니다. 해당 거래일은 공통 수급 후보에서 제외합니다. |

예약 설정의 시작 시각은 20:10 KST로 확인했습니다. 실행이 먼저 시작된 이유는 확인되지 않았습니다. 두 관측 창이 지났으므로 11월 27일 수급을 소급 조회하지 않았습니다. 비교 기준으로 11월 26일분을 재감사해 두 종목의 마감 전·익일 원문 해시와 `commonByCutoff=true`, 종목별 대조 필드 변경 0개를 확인했습니다. 누적 공통 수급 후보는 11월 26일 1일입니다.

6단계의 다음 확인은 이른 시작에도 실제 KST 20:10까지 기다린 뒤 관측을 시작하도록 예약 실행을 보완하고, 다음 개장일의 두 종목에서 마감 전 원문과 익일 대조 결과를 확보하는 것입니다.
