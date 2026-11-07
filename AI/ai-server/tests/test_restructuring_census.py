from io import BytesIO
from xml.etree import ElementTree
from zipfile import ZipFile

import pytest

from app.replay.models import ResearchError
from app.replay.restructuring_census import (
    as_of, correction_groups, coverage, original_xml, schedule_rows, share_terms,
)


def test_same_calendar_date_has_different_registration_and_listing_roles():
    section = ElementTree.fromstring("""
        <SECTION-1><TABLE>
          <TR><TD>합병기일</TD><TD>2024년 9월 1일</TD><TD>2024.09.01</TD></TR>
          <TR><TD>1</TD><TD>합병 등기 접수 예정일(합병효력발생일)</TD><TD>2024-09-02</TD></TR>
          <TR><TD>2024/09/02</TD><TD>합병등기신청일</TD><TD>-</TD></TR>
          <TR><TD>합병등기일</TD><TD>2024-09-02</TD></TR>
          <TR><TD>신주상장예정일</TD><TD>2024-09-27</TD></TR>
        </TABLE></SECTION-1>
    """)
    rows, parties = schedule_rows(section)
    assert [row["role"] for row in rows] == [
        "REFERENCE_DATE", "REGISTRATION_SCHEDULED", "REGISTRATION_APPLICATION",
        "REGISTRATION_LABEL_UNCONFIRMED", "LISTING_SCHEDULED",
    ]
    assert rows[0]["dates"] == ["2024-09-01"] and parties == []
    assert coverage({"schedule": rows}) == "REFERENCE_DATE_IN_SCOPE"


def test_scope_uses_reference_date_and_never_falls_back_to_registration_date():
    result = {"schedule": [{"role": "REGISTRATION_APPLICATION", "dates": ["2023-11-01"]}]}
    assert coverage(result) == "REFERENCE_DATE_UNCONFIRMED"
    result["schedule"].append({"role": "REFERENCE_DATE", "dates": ["2023-10-31"]})
    assert coverage(result) == "REFERENCE_DATE_OUTSIDE_SCOPE"
    result["schedule"].append({"role": "REFERENCE_DATE", "dates": ["2024-01-01"]})
    assert coverage(result) == "MULTIPLE_REFERENCE_DATES_REVIEW"


def test_no_new_shares_and_exchange_ratio_are_separate_claims():
    terms = share_terms("분할합병비율(1 : 5.1593850)에 따라 교부금을 지급하며 신주를 발행하지 않는 무증자합병입니다.")
    assert terms["explicitNoNewShares"]
    assert terms["statedRatios"] == [{"label": "분할합병", "left": "1", "right": "5.1593850"}]
    assert terms["statedNewCommonShareCounts"] == []


def test_correction_same_issuer_and_original_day_stays_ambiguous():
    base = {"corpCode": "12345678", "category": "DIVISION", "receiptDate": "2024-05-03",
            "receiptIdDatePrefix": "2024-05-02", "correctionLabel": False, "bodyCorrectionSection": False}
    records = [base | {"receipt": n} for n in ("20240502000001", "20240502000002")]
    records.append(base | {"receipt": "20241029000184", "correctionLabel": True, "bodyCorrectionSection": True,
                           "originalSubmissionDateInCorrection": "2024-05-02"})
    [linked] = correction_groups(records)
    assert linked["possibleOriginalReceipts"] == ["20240502000001", "20240502000002"]
    assert linked["status"] == "AMBIGUOUS"
    assert not linked["directParentProven"]


def document_zip(text):
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("20250101000001.xml", text.encode())
    return output.getvalue()


def test_narrow_literal_repairs_keep_provenance_and_cannot_admit_doctype():
    body = "<DOCUMENT><BODY>정관 <개정 2019.03.22.> <회사이름(주)></BODY></DOCUMENT>"
    root, proof = original_xml(document_zip(body), "20250101000001")
    assert root.find("BODY").text == "정관 <개정 2019.03.22.> <회사이름(주)>"
    assert proof["escapedLiteralAngleTokens"] == 2
    assert proof["bodySha256"] != proof["normalizedXmlSha256"]
    with pytest.raises(ResearchError, match="FACT_XML_DECLARATION_FORBIDDEN"):
        original_xml(document_zip("<!DOCTYPE DOCUMENT>" + body), "20250101000001")


def test_historical_report_is_hidden_before_local_review():
    report = {"knownAt": "2026-11-08T01:00:00+09:00", "newlyAuditedE003Filings": ["20231102000042"]}
    assert as_of(report, "2026-11-08T00:59:59+09:00") is None
    assert as_of(report, "2026-11-07T16:00:00Z") == report
