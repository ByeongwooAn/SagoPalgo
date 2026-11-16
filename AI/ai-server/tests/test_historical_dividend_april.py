import pytest

from app.replay.historical_dividend_april import decision_facts, manual_payment, supplemental_field
from app.replay.models import ResearchError


def test_decision_uses_common_amount_and_excludes_correction_comparison():
    body = (
        "<tr><td>1주당 배당금(원)</td><td>보통주식</td><td>60</td><td>100</td></tr>"
        "<tr><td>3. 1주당 배당금(원)</td><td>보통주식</td><td>100</td></tr>"
        "<tr><td>종류주식</td><td>110</td></tr>"
        "<tr><td>6. 배당기준일</td><td>2023-12-31</td></tr>"
        "<tr><td>7. 배당금지급 예정일자</td><td>2024-04-10</td></tr>"
    )
    basis, amount, planned = decision_facts(body)
    assert set(basis) == {"2023-12-31"}
    assert set(amount) == {"100"}
    assert set(planned) == {"2024-04-10"}


@pytest.mark.parametrize("marker", [
    "보통주 배당금 지급일 2024-04-08",
    "2024년 4월 8일에 지급되었습니다",
])
def test_payment_difference_preserves_both_dates(marker):
    target = {"symbol": "009830", "recordDate": "2023-12-31", "displayedPaymentDate": "2024-04-09"}
    result = manual_payment(target, {"value": "2024-04-08", "marker": marker}, {marker},
                            {"receipt": "20240813001506", "reportedOn": "2024-08-13"})
    assert (result["status"], result["issuerValue"], result["seibroValue"]) == (
        "DIFFERS", "2024-04-08", "2024-04-09",
    )


def test_two_distributions_require_the_selected_round_in_the_same_marker():
    target = {"symbol": "015360", "recordDate": "2024-03-31", "displayedPaymentDate": "2024-04-19"}
    marker = "2024년 4월 19일 지급 완료"
    with pytest.raises(ResearchError, match="APRIL_MULTIPLE_DISTRIBUTIONS"):
        manual_payment(target, {"value": "2024-04-19", "marker": marker}, {marker},
                       {"receipt": "20240814004353", "reportedOn": "2024-08-14"})


def test_recalculates_fractional_reit_cash_per_share():
    markers = ["배당금총액(원) 5,594,285,804", "총배당금/77,300,000주"]
    target = {"commonCashPerShare": "72.3710970763"}
    pin = {"value": target["commonCashPerShare"], "markers": markers,
           "calculation": {"totalKrw": "5594285804", "shares": "77300000"}}
    result = supplemental_field("commonCashPerShare", target, pin, {}, set(markers))
    assert result["status"] == "MATCH"
    assert result["calculation"] == pin["calculation"]


@pytest.mark.parametrize("classification", ["지급", "예정"])
def test_retroactive_quarterly_payment_note_discriminates_schedule(classification):
    target = {"symbol": "009240", "recordDate": "2024-03-31", "displayedPaymentDate": "2024-05-17"}
    marker = f"1분기 현금배당('24.5.17 {classification}) : 보통주 750원/주"
    entry = {"marker": marker, "value": "2024-05-17"}
    proof = {"receipt": "20240814004190", "reportedOn": "2024-08-14"}
    if classification == "예정":
        with pytest.raises(ResearchError, match="APRIL_PAYMENT_EXPRESSION"):
            manual_payment(target, entry, {marker}, proof)
    else:
        assert manual_payment(target, entry, {marker}, proof)["status"] == "MATCH"
