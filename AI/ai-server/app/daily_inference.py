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
US_MODEL_VERSION = "us-daily-l2-logistic-v1"
MODELS = {
    "005930": "b16b81aa4436ea3fa7b955063887ad0f842e78a0461b38a9e78d9a0e9d6618fb",
    "000660": "2dcaaf29b94a556d90a26b3131f496b75a2a482a4a129e46c45de851889bd8a4",
}
US_MODELS = {
    "AAPL": "91fbf5ec715fe9adc4d9a0022d1a7f823d9d2687431a85f4c2296a1d5cd5e5d3",
    "NVDA": "6bd9a01783649d089a27e117c8e94a6c5249f993d9ad81d8a4b27aa8bfa63d53",
}
Positive = Annotated[int, Field(gt=0, le=10**15)]
Price = Annotated[float, Field(gt=0, le=10**15, allow_inf_nan=False)]


class DailyBar(ApiModel):
    business_date: date
    opened: Price
    high: Price
    low: Price
    closed: Price
    volume: Positive

    @model_validator(mode="after")
    def validate_range(self):
        if not self.low <= min(self.opened, self.closed) <= max(self.opened, self.closed) <= self.high:
            raise ValueError("Invalid daily OHLC range")
        return self


class DailyInferenceRequest(ApiModel):
    stock_code: Literal["005930", "000660", "AAPL", "NVDA"]
    market: Literal["KOSPI", "NASDAQ"]
    provider: Literal["KIS"]
    price_basis: Literal["RAW"]
    signal_date: date
    bars: list[DailyBar] = Field(min_length=LOOKBACK_SESSIONS + 1, max_length=LOOKBACK_SESSIONS + 1)

    @model_validator(mode="after")
    def validate_dates(self):
        models = US_MODELS if self.market == "NASDAQ" else MODELS
        if self.stock_code not in models:
            raise ValueError("Stock does not belong to the requested model market")
        if self.market == "KOSPI" and any(
            not price.is_integer() for bar in self.bars
            for price in (bar.opened, bar.high, bar.low, bar.closed)
        ):
            raise ValueError("KRX daily price must be an integer")
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
    if request.market == "NASDAQ":
        model_directory = Path(environ.get(
            "SAGOPALGO_US_DAILY_MODEL_DIR", "research-artifacts/us-daily-learning-v1"
        ))
        expected_hash = US_MODELS[request.stock_code]
        model_version = US_MODEL_VERSION
    else:
        model_directory = Path(environ.get(
            "SAGOPALGO_DAILY_MODEL_DIR", "research-artifacts/daily-learning-v1"
        ))
        expected_hash = MODELS[request.stock_code]
        model_version = MODEL_VERSION
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
        model_version=model_version,
        model_sha256=expected_hash,
        probability=probability,
        threshold=model["threshold"],
        contributions=contributions,
    )
