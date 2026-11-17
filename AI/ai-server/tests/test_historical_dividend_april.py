from datetime import datetime, timezone

import pytest

from app.replay.dataset import canonical, digest
from app.replay.historical_dividend_april import decision_facts, manual_payment, supplemental_field
from app.replay.historical_dividend_month import SKREIT_HISTORY_ID, SKREIT_HISTORY_URL, reported_payment, skreit_payment
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
