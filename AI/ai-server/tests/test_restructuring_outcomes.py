from datetime import date
from xml.etree import ElementTree

import pytest

from app.replay.dataset import canonical, digest
from app.replay.models import ResearchError, utc
from app.replay.restructuring_outcomes import (
    Sources, as_of, consolidated_ratio, correction_start, outcome_index, stamp, typed_date,
)


REVIEW = "2026-11-07T20:50:00+09:00"


@pytest.mark.parametrize("value", ["2024 년 9월 2일", "2024.09.02", "2024-09-02", "20240902"])
def test_dates_preserve_the_same_day_across_provider_formats(value):
    assert stamp(value) == "2024-09-02"


def test_planned_date_detects_machine_and_display_conflict():
    group = ElementTree.fromstring('<TABLE-GROUP><TU AUNIT="SPL_DT" AUNITVALUE="20240902">2024년 9월 3일</TU></TABLE-GROUP>')
    with pytest.raises(ResearchError, match="H04_DATE_DISPLAY_CONFLICT"):
        typed_date(group, "SPL_DT")


def test_correction_links_original_submission_date_without_inferring_publication():
    root = ElementTree.fromstring("<DOCUMENT><BODY><LIBRARY><CORRECTION>"
                                  "<P>정정대상 공시서류의 최초제출일 : 2026년 4월 8일</P>"
                                  "</CORRECTION></LIBRARY></BODY></DOCUMENT>")
    assert correction_start(root) == "2026-04-08"
    assert correction_start(ElementTree.fromstring("<DOCUMENT/>")) is None


def test_after_consolidation_uses_decimal_precision_and_checks_publication():
    assert consolidated_ratio("0.5774514", "0.1154903", 5) == "0.11549028"
    with pytest.raises(ResearchError, match="H04_MERGER_ADJUSTED_RATIO"):
        consolidated_ratio("0.5774514", "0.1154902", 5)


def test_index_preserves_distinct_receipt_dates_and_separates_out_of_scope_types():
    class Archive:
        def listing(self, name, params):
            assert params["pblntf_detail_ty"] == "E003" and "pblntf_ty" not in params
            if name == "e003-K-20261101-01":
                base = {"corp_code": "12345678", "rcept_dt": "20261104", "stock_code": "123456", "corp_name": "sample"}
                return [base | {"rcept_no": "20261103000001", "report_nm": "[기재정정]합병등종료보고서(합병)", "rm": "철"},
                        base | {"rcept_no": "20261104000001", "report_nm": "합병등종료보고서(자산양수도)", "rm": ""}], {
                            "sha256": "1" * 64, "capturedAt": REVIEW}
            return [], {}

    candidates, counts = outcome_index(Archive())
    assert counts == {"KOSDAQ": 2}
    [row] = candidates.values()
    assert row["receiptDate"] == "2026-11-04" and row["receiptIdDatePrefix"] == "2026-11-03"
    assert row["correctionLabel"] and row["withdrawalFlag"] and row["receiptAfterEffectScope"]
    assert row["legalEffectiveDate"] is None


def test_general_e_class_response_cannot_be_published_as_completion_index():
    class IncorrectFilter:
        def listing(self, name, params):
            return [{"rcept_no": "20231101000001", "report_nm": "주주총회소집공고"}], {}

    with pytest.raises(ResearchError, match="H04_INDEX_FILTER_OR_DUPLICATE"):
        outcome_index(IncorrectFilter())


def test_changed_capture_bytes_fail_before_extracting_fields(tmp_path):
    folder = tmp_path / "captures" / "sample"
    folder.mkdir(parents=True)
    receipt = canonical({"schemaVersion": "SAGOPALGO_H04_CAPTURE_V1", "status": "CAPTURED", "endpoint": "document",
                         "parameters": {"rcept_no": "20240801000001"}, "startedAt": REVIEW, "capturedAt": REVIEW,
                         "sha256": digest(b"original")})
    (folder / "receipt.json").write_bytes(receipt)
    (folder / "raw.bin").write_bytes(b"modified")
    sources = Sources(tmp_path, {"sample": digest(receipt)}, utc(REVIEW))
    with pytest.raises(ResearchError, match="H04_RAW_HASH"):
        sources.read("sample", "document")


def test_report_cannot_be_replayed_at_historical_effective_date():
    case = {"legalEffectiveDate": date(2024, 9, 2).isoformat()}
    report = {"knownAt": REVIEW, "cases": [case], "candidateFilings": [{"receiptDate": "2024-09-02"}]}
    assert as_of(report, "2024-09-02T23:59:59+09:00") == {"auditVisible": False, "cases": [], "candidateFilings": []}
    assert not as_of(report, "2026-11-07T20:49:59.999999+09:00")["auditVisible"]
    assert as_of(report, "2026-11-07T11:50:00Z")["cases"] == [case]
