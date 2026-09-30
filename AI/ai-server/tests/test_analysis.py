from datetime import datetime

import pytest
from pydantic import ValidationError

from app.analysis import analyze
from app.models import CandleInput, DisclosureInput, InvestmentAnalysisRequest, NewsInput


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


def test_watchlist_analysis_uses_no_holding_profit_or_sell_signal() -> None:
    result = analyze(request(
        analysis_type="WATCHLIST",
        buy_price=None,
        profit_rate=None,
        stop_loss_rate=None,
        take_profit_rate=None,
    ))

    assert result.status in {"BUY_STRONG", "BUY_WATCH", "RISK", "HOLD"}
    assert result.status not in {"TAKE_PROFIT", "STOP_LOSS_WATCH"}
    assert "관심 종목 점수" in result.summary
    assert all("현재 수익률" not in reason.description for reason in result.reasons)


def test_watchlist_negative_signals_mean_avoid_entry_not_sell() -> None:
    result = analyze(request(
        analysis_type="WATCHLIST",
        buy_price=None,
        profit_rate=None,
        stop_loss_rate=None,
        take_profit_rate=None,
        candles=[],
        news=[NewsInput(title="적자 감소 위험 소송 제재 리콜", summary="하락 손실")],
        disclosures=[DisclosureInput(report_name="소송 횡령 부도 상장폐지")],
    ))

    assert result.status == "RISK"
    assert result.recommendation_type == "HOLD"
    assert "신규 진입을 보류" in result.summary


def test_holding_analysis_still_requires_risk_fields() -> None:
    with pytest.raises(ValidationError):
        request(profit_rate=None)
