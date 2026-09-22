from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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
    buy_price: float = Field(gt=0)
    profit_rate: float
    stop_loss_rate: float
    take_profit_rate: float
    candles: list[CandleInput] = Field(default_factory=list)
    news: list[NewsInput] = Field(default_factory=list)
    disclosures: list[DisclosureInput] = Field(default_factory=list)


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
