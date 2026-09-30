from datetime import datetime

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


def to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class CandleInput(ApiModel):
    date_time: datetime
    close_price: float = Field(gt=0)
    volume: float = Field(ge=0)


class NewsInput(ApiModel):
    title: str
    summary: str = ""


class DisclosureInput(ApiModel):
    report_name: str


class InvestmentAnalysisRequest(ApiModel):
    stock_code: str
    stock_name: str
    market: str
    current_price: float = Field(gt=0)
    buy_price: float | None = Field(default=None, gt=0)
    profit_rate: float | None = None
    stop_loss_rate: float | None = None
    take_profit_rate: float | None = None
    analysis_type: Literal["HOLDING", "WATCHLIST"] = "HOLDING"
    portfolio_weight_rate: float | None = Field(default=None, ge=0)
    capital_weight_rate: float | None = Field(default=None, ge=0)
    max_capital_weight_rate: float | None = Field(default=None, ge=0)
    candles: list[CandleInput] = Field(default_factory=list)
    news: list[NewsInput] = Field(default_factory=list)
    disclosures: list[DisclosureInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_holding_risk_fields(self) -> "InvestmentAnalysisRequest":
        if self.analysis_type == "HOLDING" and any(
            value is None
            for value in (
                self.buy_price,
                self.profit_rate,
                self.stop_loss_rate,
                self.take_profit_rate,
            )
        ):
            raise ValueError("보유 종목 분석에는 매수가와 손익·손절·익절 기준이 필요합니다.")
        return self


class AnalysisReason(ApiModel):
    label: str
    description: str
    type: str
    score: int


class InvestmentAnalysisResponse(ApiModel):
    model_version: str
    recommendation_type: str
    status: str
    score: int = Field(ge=0, le=100)
    summary: str
    reasons: list[AnalysisReason]
