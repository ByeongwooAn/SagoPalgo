# SagoPalgo AI Analysis Server

가격 추세, 보유 손익, 뉴스 핵심어, 공시 사건 유형을 조합해 설명 가능한 투자 참고 점수를 만드는 로컬 FastAPI 서비스입니다. 외부 생성형 AI나 유료 API를 호출하지 않으며 주문을 실행하지 않습니다.

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
