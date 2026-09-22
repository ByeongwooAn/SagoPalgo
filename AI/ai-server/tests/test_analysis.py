from datetime import datetime

from app.analysis import analyze
from app.models import CandleInput, InvestmentAnalysisRequest, NewsInput


def request(**changes: object) -> InvestmentAnalysisRequest:
    values: dict[str, object] = {
        "stock_code": "005930",
        "stock_name": "삼성전자",
        "market": "KOSPI",
        "current_price": 75200,
        "buy_price": 70000,
        "profit_rate": 7.43,
        "stop_loss_rate": -5,
        "take_profit_rate": 12,
        "candles": [
            CandleInput(date_time=datetime(2026, 9, 1), close_price=70000, volume=1000),
            CandleInput(date_time=datetime(2026, 9, 22), close_price=75200, volume=1400),
        ],
        "news": [NewsInput(title="AI 반도체 수주 증가", summary="투자 확대")],
        "disclosures": [],
    }
    values.update(changes)
    return InvestmentAnalysisRequest(**values)


def test_positive_price_and_news_create_buy_signal() -> None:
    result = analyze(request())

    assert result.recommendation_type == "BUY"
    assert result.status in {"BUY_STRONG", "BUY_WATCH"}
    assert result.score >= 62
    assert {reason.type for reason in result.reasons} == {
        "RISK",
        "PRICE",
        "NEWS",
        "DISCLOSURE",
    }


def test_stop_loss_has_priority_over_other_signals() -> None:
    result = analyze(request(profit_rate=-4.5))

    assert result.recommendation_type == "SELL"
    assert result.status == "STOP_LOSS_WATCH"
    assert "손절 기준" in result.summary
