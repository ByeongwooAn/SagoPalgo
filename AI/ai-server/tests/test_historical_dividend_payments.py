import pytest

from app.replay.historical_dividend_payments import confirm, CONFIRMED, summarize, UNREVIEWED
from app.replay.models import ResearchError


PAYMENT = {"market": "KOSPI", "symbol": "000001", "recordDate": "2024-12-31",
           "displayedPaymentDate": "2025-04-11", "cashAmountPerShare": "1250"}


@pytest.fixture
def report():
    fields = {"issuer": "발행회사", "recordDate": "배당기준일 2024-12-31",
              "actualPaymentDate": "2025년 4월 11일 지급하였습니다", "commonCashPerShare": "보통주 1,250원"}
    return {field: {"source": "filing", "markers": [mark]} for field, mark in fields.items()}


@pytest.mark.parametrize(("filed", "issuer", "changed", "error"), [
    ("2025-04-12", ("KOSPI", "000001"), None, None),
    ("2025-04-11", ("KOSPI", "000001"), None, "DIVIDEND_POST_PAYMENT_REPORT"),
    ("2025-04-12", ("KOSPI", "000002"), None, "DIVIDEND_REPORT_ISSUER"),
    ("2025-04-12", None, ("actualPaymentDate", "2025-04-11 지급 예정"), "DIVIDEND_PAYMENT_COMPLETION_MARKER"),
    ("2025-04-12", None, ("recordDate", "2025-01-01"), "DIVIDEND_DATE_MARKER"),
    ("2025-04-12", None, ("commonCashPerShare", "보통주 1,251원"), "DIVIDEND_AMOUNT_MARKER"),
])
def test_confirmation_requires_issuer_fields_and_post_payment_claim(report, filed, issuer, changed, error):
    if changed:
        field, marker = changed
        report[field]["markers"] = [marker]
    body = " ".join(reference["markers"][0] for reference in report.values())
    proof = {"reportedOn": filed}
    sources = {"filing": (body, proof, issuer)}
    if error:
        with pytest.raises(ResearchError, match=error):
            confirm(PAYMENT, report, sources)
    else:
        assert confirm(PAYMENT, report, sources) == dict.fromkeys(report, proof)


def test_rollup_uses_payment_year_and_preserves_unconfirmed_rows():
    rows = [PAYMENT | {"status": CONFIRMED}, PAYMENT | {"status": UNREVIEWED, "displayedPaymentDate": "2025-06-11"}]
    result = summarize(rows)
    assert len(result["issuerYears"]) == 1
    assert result["issuerYears"][0]["events"] == rows
    assert result["marketYears"] == [{"market": "KOSPI", "paymentYear": "2025", "counts": {CONFIRMED: 1, UNREVIEWED: 1}}]
