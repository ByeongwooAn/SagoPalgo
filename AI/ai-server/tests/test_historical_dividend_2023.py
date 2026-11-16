import pytest

from app.replay.historical_dividend_2023 import assess
from app.replay.models import ResearchError


@pytest.mark.parametrize(("displayed", "status"), [("2023-11-09", "MATCH"), ("2023-11-10", "DIFFERS")])
def test_post_payment_report_preserves_dates_independently(displayed, status):
    marker = "2023년 11월 9일자로 지급되었습니다"
    source = {"annual": ("086790", marker, {"reportedOn": "2023-11-14"})}
    selected = {"value": "2023-11-09", "evidence": [{"source": "annual", "markers": [marker]}]}
    actual = assess("actualPaymentDate", selected, displayed, "086790", source)
    assert (actual["status"], actual["issuerValue"], actual["seibroValue"]) == (status, "2023-11-09", displayed)


@pytest.mark.parametrize(("filed", "marker"), [
    ("2023-11-16", "2023-11-16 지급하였습니다"),
    ("2023-11-17", "2023-11-16 지급 예정"),
])
def test_same_day_and_planned_payment_do_not_confirm_actual_date(filed, marker):
    source = {"filing": ("094280", marker, {"reportedOn": filed})}
    selected = {"value": "2023-11-16", "evidence": [{"source": "filing", "markers": [marker]}]}
    with pytest.raises(ResearchError, match="DIVIDEND_2023_ACTUAL_PAYMENT"):
        assess("actualPaymentDate", selected, "2023-11-16", "094280", source)


def test_fractional_per_share_amount_keeps_exact_precision():
    marker = "주당 200.9698481647 원"
    source = {"declaration": ("334890", marker, {"reportedOn": "2023-11-13"})}
    selected = {"value": "200.9698481647", "evidence": [{"source": "declaration", "markers": [marker]}]}
    amount = assess("commonCashPerShare", selected, "200.9698481647", "334890", source)
    assert amount["status"] == "MATCH"
    assert amount["issuerValue"] == "200.9698481647"


def test_issuer_formula_preserves_difference_from_integer_display():
    markers = ["배당금총액(원) 2,693,177,154", "총배당금/40,400,000주"]
    source = {"declaration": ("417310", " ".join(markers), {"reportedOn": "2023-10-31"})}
    selected = {"value": "66.6628008415", "evidence": [{"source": "declaration", "markers": markers}],
                "calculation": {"totalKrw": "2693177154", "shares": "40400000", "scale": 10, "rounding": "DOWN"}}
    amount = assess("commonCashPerShare", selected, "66", "417310", source)
    assert amount["status"] == "DIFFERS"
    assert amount["calculation"] == selected["calculation"]
