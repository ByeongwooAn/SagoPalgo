from fastapi import FastAPI, HTTPException

from .analysis import analyze
from .daily_inference import DailyInferenceRequest, DailyInferenceResponse, DailyModelUnavailable, infer_daily
from .models import InvestmentAnalysisRequest, InvestmentAnalysisResponse

app = FastAPI(title="SagoPalgo AI Analysis", version="1.0.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "UP"}


@app.post(
    "/internal/ai/analyze-investment",
    response_model=InvestmentAnalysisResponse,
)
def analyze_investment(
    request: InvestmentAnalysisRequest,
) -> InvestmentAnalysisResponse:
    return analyze(request)


@app.post("/internal/ai/infer-daily", response_model=DailyInferenceResponse)
def infer_daily_model(request: DailyInferenceRequest) -> DailyInferenceResponse:
    try:
        return infer_daily(request)
    except DailyModelUnavailable as exc:
        raise HTTPException(503, "Frozen daily model unavailable") from exc
    except ValueError as exc:
        raise HTTPException(422, "Daily inference input rejected") from exc
