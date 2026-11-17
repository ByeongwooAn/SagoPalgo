from datetime import datetime, timezone
from io import BytesIO
from zipfile import ZipFile

import pytest

from app.replay.dataset import canonical, digest
from app.replay.historical_dividend_april import decision_facts, manual_payment, supplemental_field
from app.replay.historical_dividend_month import (
    DND_Q3_ID,
    ESRKS_HISTORY_ID,
    ESRKS_HISTORY_URL,
    HYUNDAI_HISTORY_ID,
    HYUNDAI_HISTORY_URL,
    SKREIT_HISTORY_ID,
    SKREIT_HISTORY_URL,
    hyundai_payment,
    issuer_history_payment,
    load_document,
    prior_field,
    reported_payment,
    skreit_payment,
)
from app.replay.models import ResearchError
from app.replay.historical_dividend_payments import CONFIRMED


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


def test_prior_confirmation_with_combined_audit_keeps_all_source_links():
    sources = [{"sourceUrl": "https://example.com/decision"}, {"sourceUrl": "https://example.com/report"}]
    target = {"status": CONFIRMED, "recordDate": "2024-12-31", "issuerEvidence": {"priorAudit": sources}}
    field = prior_field(target, "recordDate")
    assert field["status"] == "MATCH"
    assert field["issuerValue"] == field["seibroValue"] == "2024-12-31"
    assert field["evidence"] == [source | {"markers": []} for source in sources]


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


@pytest.mark.parametrize("marker", [
    "배당 지급일 2025-09-09에 지급될 예정입니다",
    "배당 지급일 2025-09-09에 지급할 예정입니다",
])
def test_post_payment_filing_does_not_turn_a_schedule_into_an_actual_payment(marker):
    target = {"symbol": "023160", "recordDate": "2025-08-26", "displayedPaymentDate": "2025-09-09"}
    entry = {"value": "2025-09-09", "marker": marker}
    proof = {"receipt": "20251114000708", "reportedOn": "2025-11-14"}
    with pytest.raises(ResearchError, match="APRIL_PAYMENT_EXPRESSION"):
        manual_payment(target, entry, {marker}, proof)


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


@pytest.mark.parametrize(("label", "record_date", "error"), [
    ("배당지급일", "2024-03-31", None),
    ("배당지급예정일", "2024-03-31", "SKREIT_HISTORY_ROUND"),
    ("배당지급일", "2024-06-30", "SKREIT_HISTORY_ROUND"),
])
def test_skreit_history_binds_payment_to_the_dividend_round(tmp_path, label, record_date, error):
    folder = tmp_path / "ir" / SKREIT_HISTORY_ID
    folder.mkdir(parents=True)
    html = (
        f"<table><tr><th>구분</th><th>배당기준일</th><th>{label}</th>"
        "<th>주당배당(원)</th><th>배당총액 (백만원)</th></tr>"
        "<tr><th>정기배당</th><th>특별배당</th><th>합계</th></tr>"
        f"<tr><td>제12기</td><td>{record_date}</td><td>2024-06-28</td>"
        "<td>66</td><td>0</td><td>66</td><td>17,829</td></tr></table>"
    ).encode()
    (folder / "original.html").write_bytes(html)
    receipt = canonical({"url": SKREIT_HISTORY_URL, "startedAt": "2026-11-16T15:00:00+00:00",
                         "capturedAt": "2026-11-16T15:01:00+00:00", "sha256": digest(html)})
    (folder / "receipt.json").write_bytes(receipt)
    target = {"symbol": "395400", "market": "KOSPI", "recordDate": "2024-03-31",
              "displayedPaymentDate": "2024-06-28", "commonCashPerShare": "66"}
    reviewed_at = datetime(2026, 11, 17, tzinfo=timezone.utc)

    if error:
        with pytest.raises(ResearchError, match=error):
            skreit_payment(target, tmp_path, digest(receipt), reviewed_at)
    else:
        result = skreit_payment(target, tmp_path, digest(receipt), reviewed_at)
        assert result["status"] == "MATCH"
        assert result["evidence"][0]["reportedOn"] is None


@pytest.mark.parametrize(("basis", "suffix", "is_actual"), [
    ("2024.07.09", "배당금 지급", True),
    ("2024.07.09", "배당금 지급 예정", False),
    ("2024.07.08", "배당금 지급", False),
])
def test_disclosure_progress_payment_requires_same_round_and_completed_action(basis, suffix, is_actual):
    marker = f"{basis} 배당기준일 설정3) 2024.07.30 {suffix}"
    target = {"symbol": "000480", "recordDate": "2024-07-09", "displayedPaymentDate": "2024-07-30"}
    entry = {"marker": marker, "value": "2024-07-30"}
    proof = {"receipt": "20240814003732", "reportedOn": "2024-08-14"}
    if is_actual:
        assert manual_payment(target, entry, {marker}, proof)["status"] == "MATCH"
    else:
        with pytest.raises(ResearchError, match="APRIL_PAYMENT_EXPRESSION"):
            manual_payment(target, entry, {marker}, proof)


def test_dnd_ir_timeline_uses_dividend_date_and_same_round_amount():
    marker = ("`24.10.28 `24.11.25 `24.12.10 `24.12.19 이사회 개최 이사회 개최 "
              "정기주주총회 개최 제9기 배당 재무제표 승인 DPS 139원")
    target = {"symbol": "377190", "recordDate": "2024-09-30", "displayedPaymentDate": "2024-12-19",
              "commonCashPerShare": "139"}
    proof = {"receipt": DND_Q3_ID, "reportedOn": "2024-12-26"}
    entry = {"marker": marker, "value": "2024-12-19"}

    assert manual_payment(target, entry, {marker}, proof)["status"] == "MATCH"
    with pytest.raises(ResearchError, match="APRIL_PAYMENT_EXPRESSION"):
        manual_payment(target, entry | {"value": "2024-12-10"}, {marker}, proof)
    with pytest.raises(ResearchError, match="APRIL_PAYMENT_EXPRESSION"):
        manual_payment(target | {"commonCashPerShare": "138"}, entry, {marker}, proof)


def test_conflicting_reported_dates_are_preserved_without_selecting_a_payment():
    target = {"symbol": "214370", "recordDate": "2024-06-30", "displayedPaymentDate": "2024-07-19"}
    entries = [
        {"receipt": "20240814002146", "value": "2024-07-19", "marker": "2024년 7월 19일에 지급되었습니다"},
        {"receipt": "20250317000927", "value": "2024-07-18", "marker": "2024년 7월 18일에 지급되었습니다"},
    ]
    reports = {
        "20240814002146": {"receipt": "20240814002146", "reportedOn": "2024-08-14"},
        "20250317000927": {"receipt": "20250317000927", "reportedOn": "2025-03-17"},
    }
    markers = {entry["receipt"]: {entry["marker"]} for entry in entries}

    result = reported_payment(target, entries, reports, markers, "후속 보고서 간 실제 지급일 상충")

    assert result["status"] == "UNVERIFIED"
    assert "issuerValue" not in result
    assert [proof["reportedPaymentDate"] for proof in result["evidence"]] == ["2024-07-19", "2024-07-18"]


@pytest.mark.parametrize(("basis", "completion", "error"), [
    ("2024년 6월 30일", "지급되었습니다", None),
    ("2023년 6월 30일", "지급되었습니다", "APRIL_PAYMENT_MARKER"),
    ("2024년 6월 30일", "지급 예정입니다", "APRIL_PAYMENT_MARKER"),
])
def test_payment_without_year_requires_the_same_record_date_and_completion(basis, completion, error):
    target = {"symbol": "002960", "recordDate": "2024-06-30", "displayedPaymentDate": "2024-08-16"}
    marker = f"{basis}로 종료하는 당반기 중간배당금은 8월 18일에 {completion}"
    entry = {"value": "2024-08-18", "marker": marker, "dateContext": "RECORD_YEAR"}
    proof = {"receipt": "20241114000720", "reportedOn": "2024-11-14"}
    if error:
        with pytest.raises(ResearchError, match=error):
            manual_payment(target, entry, {marker}, proof)
    else:
        assert manual_payment(target, entry, {marker}, proof)["status"] == "DIFFERS"


def test_attachment_correction_without_body_is_retained_as_unreadable(tmp_path):
    receipt = "20250321001370"
    folder = tmp_path / "documents" / receipt
    folder.mkdir(parents=True)
    archive = BytesIO()
    with ZipFile(archive, "w") as zipped:
        zipped.writestr(f"{receipt}_00760.xml", "<ATTACHMENT/>")
    raw = archive.getvalue()
    (folder / "original.zip").write_bytes(raw)
    proof = canonical({
        "receiptNumber": receipt, "source": "OpenDART document.xml", "status": "CAPTURED",
        "startedAt": "2026-11-17T01:00:00+00:00", "capturedAt": "2026-11-17T01:01:00+00:00",
        "sha256": digest(raw),
    })
    (folder / "receipt.json").write_bytes(proof)
    at = datetime(2026, 11, 17, 2, tzinfo=timezone.utc)
    item = {"report_nm": "[첨부정정]사업보고서 (2024.10)", "rcept_dt": "20250322"}

    body, evidence = load_document(tmp_path, receipt, digest(proof), item, at)
    assert body is None
    assert evidence["status"] == "ATTACHMENT_ONLY"
    assert evidence["reportedOn"] == "2025-03-22"
    assert evidence["archiveSha256"] == digest(raw)
    with pytest.raises(ResearchError, match="APRIL_DART_DOCUMENT_LAYOUT"):
        load_document(tmp_path, receipt, digest(proof), {"report_nm": "사업보고서 (2024.10)"}, at)


@pytest.mark.parametrize(("header", "amount", "error"), [
    ("배당지급일", "2,000", None),
    ("배당지급예정일", "2,000", "HYUNDAI_HISTORY_ROUND"),
    ("배당지급일", "2,001", "HYUNDAI_HISTORY_PAYMENT"),
])
def test_hyundai_history_uses_exact_round_and_common_share_amount(tmp_path, header, amount, error):
    folder = tmp_path / "ir" / HYUNDAI_HISTORY_ID
    folder.mkdir(parents=True)
    html = (
        f"<table><tr><th>배당기준일</th><th>{header}</th><th>보통주</th>"
        "<th>1우선주</th><th>2우선주</th><th>3우선주</th></tr>"
        f"<tr><td>2024.06.30</td><td>2024.08.13</td><td>{amount}</td>"
        "<td>2,000</td><td>2,000</td><td>2,000</td></tr></table>"
    ).encode()
    (folder / "original.html").write_bytes(html)
    receipt = canonical({"url": HYUNDAI_HISTORY_URL, "startedAt": "2026-11-17T01:00:00+00:00",
                         "capturedAt": "2026-11-17T01:01:00+00:00", "sha256": digest(html)})
    (folder / "receipt.json").write_bytes(receipt)
    target = {"symbol": "005380", "market": "KOSPI", "recordDate": "2024-06-30",
              "displayedPaymentDate": "2024-08-13", "commonCashPerShare": "2000"}
    at = datetime(2026, 11, 17, 2, tzinfo=timezone.utc)

    if error:
        with pytest.raises(ResearchError, match=error):
            hyundai_payment(target, tmp_path, digest(receipt), at)
    else:
        assert hyundai_payment(target, tmp_path, digest(receipt), at)["status"] == "MATCH"


@pytest.mark.parametrize(("record_date", "displayed_payment", "outcome"), [
    ("2024-05-31", "2024-09-06", "MATCH"),
    ("2024-05-31", "2024-09-09", "DIFFERS"),
    ("2024-05-30", "2024-09-06", "ESRKS_HISTORY_ROUND"),
])
def test_esrks_history_uses_record_date_and_disbursement_columns(tmp_path, record_date, displayed_payment, outcome):
    folder = tmp_path / "ir" / ESRKS_HISTORY_ID
    folder.mkdir(parents=True)
    html = (
        "<table><tr><th>연도</th><th>회계연도</th><th>배당락일</th><th>배당기준일</th>"
        "<th>정기 주주총회 소집일</th><th>주당배당금(원)</th><th>배당지급일</th></tr>"
        "<tr><td>2024</td><td>9기</td><td>2024-05-30</td><td>2024-05-31</td>"
        "<td>2024-08-23</td><td>137</td><td>2024-09-06</td></tr></table>"
    ).encode()
    (folder / "original.html").write_bytes(html)
    receipt = canonical({"url": ESRKS_HISTORY_URL, "startedAt": "2026-11-17T01:00:00+00:00",
                         "capturedAt": "2026-11-17T01:01:00+00:00", "sha256": digest(html)})
    (folder / "receipt.json").write_bytes(receipt)
    target = {"symbol": "365550", "market": "KOSPI", "recordDate": record_date,
              "displayedPaymentDate": displayed_payment, "commonCashPerShare": "137"}
    at = datetime(2026, 11, 17, 2, tzinfo=timezone.utc)

    if outcome == "ESRKS_HISTORY_ROUND":
        with pytest.raises(ResearchError, match=outcome):
            issuer_history_payment(target, tmp_path, digest(receipt), at, ESRKS_HISTORY_ID)
    else:
        result = issuer_history_payment(target, tmp_path, digest(receipt), at, ESRKS_HISTORY_ID)
        assert (result["status"], result["issuerValue"], result["seibroValue"]) == (outcome, "2024-09-06", displayed_payment)
