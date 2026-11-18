"""Score the frozen local models without importing the training dependencies."""

from datetime import date
from hashlib import sha256
import json
from math import exp, fsum
from os import environ
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from .daily_features import FEATURE_NAMES, LOOKBACK_SESSIONS, daily_features
from .models import ApiModel

MODEL_VERSION = "daily-l2-logistic-v1"
MODELS = {
    "005930": "b16b81aa4436ea3fa7b955063887ad0f842e78a0461b38a9e78d9a0e9d6618fb",
    "000660": "2dcaaf29b94a556d90a26b3131f496b75a2a482a4a129e46c45de851889bd8a4",
}
Positive = Annotated[int, Field(gt=0, le=10**15)]


class DailyBar(ApiModel):
    business_date: date
    opened: Positive
    high: Positive
    low: Positive
    closed: Positive
    volume: Positive

    @model_validator(mode="after")
    def validate_range(self):
        if not self.low <= min(self.opened, self.closed) <= max(self.opened, self.closed) <= self.high:
            raise ValueError("Invalid daily OHLC range")
        return self


class DailyInferenceRequest(ApiModel):
    stock_code: Literal["005930", "000660"]
    market: Literal["KOSPI"]
    provider: Literal["KIS"]
    price_basis: Literal["RAW"]
    signal_date: date
    bars: list[DailyBar] = Field(min_length=LOOKBACK_SESSIONS + 1, max_length=LOOKBACK_SESSIONS + 1)

    @model_validator(mode="after")
    def validate_dates(self):
        dates = [bar.business_date for bar in self.bars]
        if dates != sorted(set(dates)) or dates[-1] != self.signal_date:
            raise ValueError("Expected ascending unique trading dates through the signal date")
        return self


class DailyInferenceResponse(ApiModel):
    stock_code: str
    signal_date: date
    model_version: str
    model_sha256: str
    probability: float
    threshold: float | None
    contributions: dict[str, float]


class DailyModelUnavailable(Exception):
    pass


def infer_daily(request: DailyInferenceRequest) -> DailyInferenceResponse:
    model_directory = Path(environ.get(
        "SAGOPALGO_DAILY_MODEL_DIR", "research-artifacts/daily-learning-v1"
    ))
    expected_hash = MODELS[request.stock_code]
    try:
        raw = (model_directory / f"{request.stock_code}-model.json").read_bytes()
    except OSError as exc:
        raise DailyModelUnavailable from exc
    if sha256(raw).hexdigest() != expected_hash:
        raise DailyModelUnavailable
    model = json.loads(raw)
    if request.signal_date <= date.fromisoformat(model["trainedOn"]["lastTargetDate"]):
        raise ValueError("Signal date overlaps the training targets")

    contributions = {
        name: (value - center) / scale * weight
        for name, value, center, scale, weight in zip(
            FEATURE_NAMES, daily_features(request.bars), model["means"], model["scales"], model["coefficients"],
            strict=True,
        )
    }
    log_odds = fsum([model["intercept"], *contributions.values()])
    probability = 1 / (1 + exp(-log_odds)) if log_odds >= 0 else exp(log_odds) / (1 + exp(log_odds))
    return DailyInferenceResponse(
        stock_code=request.stock_code,
        signal_date=request.signal_date,
        model_version=MODEL_VERSION,
        model_sha256=expected_hash,
        probability=probability,
        threshold=model["threshold"],
        contributions=contributions,
    )
