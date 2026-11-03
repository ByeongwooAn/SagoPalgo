# SagoPalgo AI Analysis Server

과거 자료 연구용 오프라인 도구는 [R5 데이터셋·시점 재현 문서](../../docs/historical-data-replay.md)를 따릅니다. `python -m app.replay --help`로 버전 데이터셋·시점 조회·명시적 주문안의 비용 추정·시간 구간 분리를 실행합니다. 기존 분석 API와 분리되어 있으며 실제 계좌·자동 주문·학습 모델을 활성화하지 않습니다. [가상 예제](examples/replay)는 실측 시세/성과가 아닙니다.

가격 추세, 뉴스 핵심어, 공시 사건 유형과 보유 종목의 손익·매입 원금 비중 신호를 조합해 설명 가능한 투자 참고 점수를 만드는 로컬 FastAPI 서비스입니다. `analysisType=WATCHLIST`에서는 보유 손익·비중 신호를 사용하지 않습니다. 외부 생성형 AI나 유료 API를 호출하지 않으며 주문을 실행하지 않습니다.

## 로컬 실행

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

상태 확인:

```powershell
Invoke-RestMethod -Uri 'http://localhost:8000/health'
```

테스트:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Spring Boot는 `POST /internal/ai/analyze-investment`를 호출합니다. 모델 버전 `WEIGHTED_SIGNAL_V1`과 추천 유형, 상태, 0~100 점수, 요약, 개별 점수 근거를 반환합니다.

관심 종목 분석은 `analysisType=WATCHLIST`와 실제 현재가를 보내고, 매수가·수익률·손절·익절 필드는 생략하거나 `null`로 둡니다. 기본 `HOLDING` 분석은 해당 보유 손익 필드를 모두 요구합니다. 관심 종목의 낮은 점수는 보유 주식 매도가 아니라 신규 진입 보류로 해석합니다.

보유 종목 요청의 선택적 `portfolioWeightRate`, `capitalWeightRate`, `maxCapitalWeightRate`는 Spring이 동일 종목의 여러 보유 건을 합산한 **매입 원금 기준**으로 계산합니다. 자본금 미설정 시 한도 판정은 하지 않습니다. 설정 자본금 대비 원금 비중이 권장 한도를 넘으면 신규 매수만 보류하며, 손절·익절 신호는 우선합니다. 실계좌 평가 비중이나 주문 가능 금액을 뜻하지 않습니다.
