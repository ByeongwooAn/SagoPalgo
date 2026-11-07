from hashlib import sha256
import json

import pytest

from app.replay.action_listing_inventory import listing_page
from app.replay.corporate_action_event_audit import add_candidate, body_fields, membership
from app.replay.models import ResearchError
from app.replay.restructuring_event_audit import kind_anchor, party_signature


def test_membership_keeps_date_market_and_name_collision(tmp_path):
    days = tmp_path / "days"
    days.mkdir()
    issuer = {"classification": "COMMON_SHARE", "market": "KOSPI", "symbol": "000001",
              "isin": "KR0000000001", "name": "알파보통주", "sourceRowSha256": "one"}
    sources = [{"market": market, "status": "OBSERVED", "sha256": market} for market in ("KOSPI", "KOSDAQ")]
    day_files = []
    for day, issues in (("2025-01-02", [issuer]), ("2025-01-06", [issuer, issuer | {"symbol": "000002"}])):
        raw = json.dumps({"date": day, "status": "OBSERVED", "issues": issues, "sources": sources}).encode()
        (days / f"{day}.json").write_bytes(raw)
        day_files.append({"date": day, "status": "OBSERVED", "sha256": sha256(raw).hexdigest()})
    history = {"dayFiles": day_files, "startDate": "2025-01-01", "endDate": "2025-01-06"}
    filings = [{"listedMinuteKst": f"2025-01-{day} 10:00", "market": market, "issuerDisplayName": "㈜ Alpha",
                "receipt": str(i)} for i, (day, market) in enumerate((
                    ("01", "KOSPI"), ("02", "KOSPI"), ("02", "KOSDAQ"), ("04", "KOSPI"), ("06", "KOSPI"),
                    ("07", "KOSPI")))]
    aliases = {("KOSPI", code, issuer["isin"]): (issuer["name"], "Alpha") for code in ("000001", "000002")}
    rows = {row["receipt"]: row for row in membership(filings, tmp_path / "report.json", history,
                                                     lambda day, sources: aliases)}
    assert [rows[str(i)]["membership"]["status"] for i in range(6)] == [
        "NO_PRIOR_OBSERVATION", "SAME_DATE_NAME_MATCH", "NO_SAME_MARKET_NAME_MATCH",
        "PRIOR_DATE_NAME_CANDIDATE", "AMBIGUOUS_NAME_MATCH", "OUTSIDE_SNAPSHOT_DATES",
    ]
    assert rows["3"]["membership"]["observationDate"] == "2025-01-02"
    assert all(not row["instrumentIdentityConfirmed"] for row in rows.values())


def test_route_overlap_keeps_both_proofs_and_rejects_conflict():
    rows = {}
    row = {"market": "KOSPI", "receipt": "1", "title": "권리락"}
    add_candidate(rows, row, "title/rights", "first")
    add_candidate(rows, row, "category/rights", "second")
    assert rows["KOSPI", "1"]["routes"] == {"title/rights": ["first"], "category/rights": ["second"]}
    with pytest.raises(ResearchError, match="CROSS_ROUTE_ROW_CONFLICT"):
        add_candidate(rows, row | {"title": "배당락"}, "category/rights", "third")


def test_notice_requires_common_security_and_preserves_date_only_reopening():
    notice = "1.대상종목 (주)알파 보통주 2.해제사유 점검완료 3.해제일시 2025-01-06 - 4.근거규정"
    assert body_fields("KOSDAQ", "REOPENING", "70799.htm", notice, "알파", "000001") == {
        "appliedDate": "2025-01-06", "noticeTimeKst": None, "actualFirstTradeAt": None,
    }
    assert body_fields("KOSDAQ", "REOPENING", "70799.htm", notice.replace("보통주", "우선주"), "알파", "000001") is None
    ex_rights = "1. 회사명 알파 2. 주식 보통주식 3,000 3. 사유 권리락(유상증자) 4. 적용일 2025-01-06"
    assert body_fields("KOSPI", "RIGHTS", "99301.htm", ex_rights, "알파", "000001")["referencePriceKrw"] == 3000


def test_stock_listing_preserves_signed_count_without_legal_date():
    raw = """<div class="info type-00">전체 1 건 : 1 /1</div><table>
      <tr onclick="fnDetailView('20250105000001')"><td><img alt="유가증권" />알파</td>
      <td>2025-01-06</td><td>변경상장</td><td>-1,500</td><td>500</td><td>주식소각</td></tr></table>""".encode()
    total, pages, rows = listing_page(raw, "KOSPI", "3", "2025-01-01", "2025-01-31", 1)
    assert (total, pages, rows[0]["signedShareChange"], rows[0]["listingDate"]) == (1, 1, -1500, "2025-01-06")
    with pytest.raises(ResearchError, match="STOCK_LISTING_ROW"):
        listing_page(raw, "KOSDAQ", "3", "2025-01-01", "2025-01-31", 1)


def test_h04_party_roles_and_viewer_identity_stay_independent():
    left = [["구분", "알파㈜(존속회사)", "(주)베타(소멸회사)"]]
    right = [["구분", "㈜베타(소멸회사)", "주식회사 알파(존속회사)"]]
    assert party_signature(left) == party_signature(right)
    assert party_signature(left) != party_signature([["구분", "알파(존속회사)", "감마(소멸회사)"]])
    assert party_signature(left + [["구분", "알파(존속회사)", "감마(소멸회사)"]]) is None
    versions = [{"document": "a", "correctionMarked": False}, {"document": "b", "correctionMarked": True}]
    assert kind_anchor({"selectedDocument": "b", "viewerVersions": versions}) == "a"
    assert kind_anchor({"selectedDocument": "c", "viewerVersions": versions}) is None
