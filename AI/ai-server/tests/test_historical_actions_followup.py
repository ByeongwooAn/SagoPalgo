import pytest

from app.replay.historical_actions_followup import issuer_payment, restructuring_review
from app.replay.models import ResearchError


def test_payment_evidence_requires_post_payment_body_and_one_exact_ksd_row():
    case = {"source": "report", "market": "KOSDAQ", "symbol": "179290", "recordDate": "2025-12-31",
            "paymentDate": "2026-04-20", "amount": "120", "markers": ["2026.04.20 지급하였습니다"]}
    bodies = {"report": {"sourceUrl": "https://kind.krx.co.kr/external/2026/04/21/a/b/71500.htm",
                         "body": "2026.04.20 지급하였습니다", "proof": {}}}
    row = {"market": "KOSDAQ", "symbol": "179290", "recordDate": "2025-12-31", "displayedPaymentDate": "2026-04-20",
           "cashAmountPerShare": "120.00", "status": "DISPLAYED_DATE_AGREES", "sourceRowSha256": "1" * 64, "evidence": {}}
    assert issuer_payment(case, bodies, [row], [])["status"] == "ISSUER_REPORTED_PAYMENT_MATCH"
    with pytest.raises(ResearchError, match="ISSUER_PAYMENT_KSD_MATCH"):
        issuer_payment(case, bodies, [row, row], [])
    with pytest.raises(ResearchError, match="ISSUER_PAYMENT_FIELDS"):
        issuer_payment(case | {"markers": []}, bodies, [row], [])
    bodies["report"]["sourceUrl"] = bodies["report"]["sourceUrl"].replace("/04/21/", "/04/19/")
    with pytest.raises(ResearchError, match="PAYMENT_REPORT_DATE"):
        issuer_payment(case, bodies, [row], [])


def test_issuer_reported_registration_does_not_assert_registry_or_legal_effect():
    parent = {"newlyAuditedE003Filings": [{"receipt": "original", "schedule": [
        {"role": "REFERENCE_DATE", "dates": ["2025-04-01"]}]}]}
    case = {"case": "MERGER", "referenceDate": "2025-04-01", "e003Receipts": ["original"],
            "fields": {"issuerReportedRegistrationDate": "2025-04-02"},
            "markersByField": {"issuerReportedRegistrationDate": {"report": ["합병(해산) 등기일 2025-04-02"]}}}
    bodies = {"report": {"body": "합병(해산) 등기일 2025-04-02", "proof": {"bodySha256": "2" * 64}}}
    result = restructuring_review(case, bodies, parent)
    assert result["reportedFields"] == case["fields"]
    assert result["registryExtractVerified"] is False and result["legalEffectiveDate"] is None
    with pytest.raises(ResearchError, match="RESTRUCTURING_REFERENCE_DATE"):
        restructuring_review(case | {"referenceDate": "2025-04-02"}, bodies, parent)
