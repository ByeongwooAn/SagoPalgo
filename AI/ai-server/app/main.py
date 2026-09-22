from fastapi import FastAPI

from .analysis import analyze
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
