# 삼성전자·SK하이닉스 장 마감 모델 추론 연결

2026-11-18 기준 [1차 학습 프로토타입 3단계](learning-prototype.md#실행-순서와-완료-기준)입니다. 앱에서 삼성전자(005930) 또는 SK하이닉스(000660)의 보유·관심 종목 **분석**을 요청하면 추천 상세와 이력에 장 마감 모델 신호가 표시됩니다. 모델의 예측 대상은 다음 KRX 개장일에 종가가 시가보다 높을 확률입니다. [2단계에서 고정한 종목별 모델과 임곗값](daily-learning-evaluation.md)을 사용합니다.

## 신호 생성과 만료

1. KST 기준 가장 최근 정규장이 끝난 거래일을 기준일로 정합니다. 모델은 기준일을 포함한 KRX 개장일 21개의 KIS `J` 원주가 OHLCV를 사용합니다. 기간별 시세의 `FID_ORG_ADJ_PRC=1`을 지정하고, 종목·연속 거래일·중복·OHLC·양수 거래량과 공급자 변경·분할 표시를 검사합니다. [KIS 기간별 시세 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/inquire_daily_itemchartprice/inquire_daily_itemchartprice.py)
2. KRX 시간외 거래 종료 20:00 이후 15분을 더 기다린 뒤, `inquire-daily-price`의 KRX 원주가(`FID_ORG_ADJ_PRC=0`)에서 같은 기준일의 OHLCV가 일치할 때 추론합니다. 다음 개장일 정규장이 진행 중이면 직전 거래일의 확정 창을 사용합니다. 새 기준일 일봉이 지연되거나 양쪽 조회의 값이 다르면 해당 종목의 신호를 보류합니다. 20:15는 프로토타입이 선택한 확인 시각입니다. KIS의 실제 당일 일봉 가용 시각은 실환경 확인에서 기록합니다. [KRX 정규장·시간외 및 수능일 공지](https://kind.krx.co.kr/external/2026/11/05/000141/20261105000216/99303.htm) · [KIS 일자별 시세 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/inquire_daily_price/inquire_daily_price.py)
3. Python은 학습 코드와 같은 특징 계산을 사용하고, 종목별 모델 파일의 SHA-256이 고정값과 일치할 때만 저장된 표준화·가중치·절편을 적용합니다. 확률이 종목별 임곗값 이상이면 `매수 관찰`, 미만이면 `관망`입니다. 앱은 모델 버전, 기준 거래일, 확률과 임곗값, 절댓값이 큰 특징별 기여 최대 두 개, 평가·만료 시각을 표시합니다. 만료는 다음 KRX 개장일 정규장 종료입니다. 11월 19일에는 16:30을 사용합니다. 달력은 [2026년 KRX 공식 휴장일 대조](../historical-data/sessions/market-calendar-session-coverage.md)와 임시 거래시간 공지에 근거합니다. 입력 창 또는 다음 개장일이 이 달력 범위를 벗어나면 보류합니다.

신호는 기존 추천 API의 `evidence.dailySignal`에 저장·전달합니다. 보유 위험 판단과 알림은 기존 종합 추천 결과를 사용합니다. 모델용 시세 조회는 두 종목의 수동 분석에서 실행합니다. [추천 API](../contracts/api-spec.md#11-추천-api)

## 오프라인 확률 대조

종목별 독립 평가 142일의 KIS 원주가를 Python 추론 HTTP 요청에 재생했습니다. 기준일·목표일·모델 SHA-256·임곗값이 일치했고 **284건 모두 매수 관찰·관망 판정이 같았습니다.** 공통 마지막 기준일은 2026-10-30, 목표일은 2026-11-02입니다. 확률은 0~1 단위이며, 최대 차이는 평가 142일의 두 계산 값 간 절대 오차입니다.

| 종목 | 기준일 10월 30일 API 확률 | 같은 날 오프라인 확률 | 142일 최대 차이 | 기준일 판정 |
|---|---:|---:|---:|---|
| 삼성전자 | 0.297169952678617 | 0.297169952678617 | 5.55 × 10⁻¹⁷ | 관망 (52.50% 미만) |
| SK하이닉스 | 0.486263157159366 | 0.486263157159366 | 1.11 × 10⁻¹⁶ | 관망 (50.00% 미만) |

```powershell
# AI/ai-server 폴더에서 고정 산출물로 대조합니다.
$env:SAGOPALGO_VERIFY_FROZEN_DAILY = '1'
.\.venv\Scripts\python.exe -m pytest -q -s tests/test_daily_inference.py
```

## 로컬 운영 확인

Docker Compose는 기존 `AI/ai-server/research-artifacts/daily-learning-v1/`를 Python 컨테이너에 읽기 전용으로 연결합니다. 해당 폴더에 2단계의 원본 `005930-model.json`과 `000660-model.json`이 있어야 합니다. 자료와 모델은 로컬에 보관합니다. 모델 경로가 비거나 파일이 변하면 해당 종목이 보류됩니다. Python을 직접 실행할 때는 `AI/ai-server`를 작업 디렉터리로 사용하거나 `SAGOPALGO_DAILY_MODEL_DIR`로 기존 모델 폴더를 지정합니다.

11월 22일 마지막 휴장 관찰 종료 및 관찰 보고서 생성 후, 새 서버·앱으로 두 종목의 실제 KIS 일봉을 같은 날짜의 오프라인 계산과 대조합니다. 장 마감 직후와 20:15 이후의 양쪽 시세 가용성, 앱 추천 상세·이력에 저장된 확률과 만료 표시를 확인합니다. 3단계의 실환경 확인을 마친 뒤 4단계 수동 모의매매에 착수합니다. [관찰 일정과 종료 기준](../market-data/kis-session-observation-20261117.md)
