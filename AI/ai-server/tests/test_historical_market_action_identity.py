from app.replay.dataset import canonical
from app.replay.historical_market_action_identity import resolve, targets


KNOWN = "2026-11-04T07:00:00+00:00"
TARGET = {
    "receipt": "20250102000001", "market": "KOSDAQ", "viewerSymbol": "123450",
    "publishedIssuer": "주식회사 옛이름", "kindDisplayName": "새이름",
    "publicationDate": "2025-01-02", "referenceDate": "2025-01-03",
    "actionEvidence": [{"observedAt": KNOWN}],
}


def issue(stamp, name, isin="KR0000000001", symbol="123450"):
    return {"market": "KOSDAQ", "symbol": symbol, "isin": isin, "basisDate": stamp,
            "name": name, "abbreviatedName": name, "knownAt": KNOWN}


def test_publication_match_can_bridge_a_name_change_only_for_same_instrument():
    original = issue("2025-01-02", "옛이름")
    renamed = issue("2025-01-03", "새이름")

    def snapshot(stamp, _market):
        return {"123450": original if stamp == "2025-01-02" else renamed}

    result = resolve(TARGET, snapshot, {}, [])
    assert result["identityBasis"] == "ISSUER_NAME_MATCH_AT_PUBLICATION_SAME_INSTRUMENT_ON_REFERENCE_DATE"
    assert result["historicalIsin"] == original["isin"]
    assert result["publicationObservation"]["basisDate"] == TARGET["publicationDate"]

    renamed["isin"] = "KR0000000002"
    result = resolve(TARGET, snapshot, {}, [])
    assert result["status"] == "HISTORICAL_NAME_AND_IDENTIFIER_LINK_UNRESOLVED"
    assert result["historicalIsin"] is None


def test_names_conflicting_with_another_common_share_are_not_promoted():
    reference = issue("2025-01-03", "새이름")
    conflicting = issue("2025-01-03", "옛이름", "KR0000000002", "987650")

    def snapshot(_stamp, _market):
        return {"123450": reference, "987650": conflicting}

    result = resolve(TARGET, snapshot, {}, [])
    assert result["status"] == "HISTORICAL_NAME_CONFLICTS_WITH_OTHER_SYMBOL"
    assert result["historicalSymbol"] is None


def test_outside_scope_does_not_read_or_carry_an_earlier_snapshot():
    def snapshot(_stamp, _market):
        raise AssertionError("snapshot outside scope")

    result = resolve(TARGET | {"referenceDate": "2026-11-03"}, snapshot, {}, [])
    assert result["status"] == "OUTSIDE_H05_EFFECTIVE_SCOPE"
    assert result["historicalIsin"] is None


def test_reviewed_versions_keep_separate_document_and_publication_date_basis():
    proof = [{"observedAt": KNOWN}]
    row = {
        "receipt": "20250102000001", "market": "KOSDAQ", "listIssuer": "새이름",
        "listedMinuteKst": "2025-01-02 09:10", "evidence": proof,
        "versions": [
            {"document": doc, "label": f"주권매매거래정지 (2025.01.{stamp})", "evidence": proof,
             "review": {"identityReason": "HISTORICAL_BODY_NAME_DIFFERS_FROM_VIEWER",
                        "publishedIssuer": "옛이름", "viewerSymbol": "123450"}}
            for doc, stamp in (("20250102000011", "02"), ("20250103000012", "03"))
        ],
    }

    result = list(targets(canonical(row)))
    assert [target["document"] for target in result] == ["20250102000011", "20250103000012"]
    assert [target["referenceDate"] for target in result] == ["2025-01-02", "2025-01-03"]
    assert all(target["referenceBasis"] == "NOTICE_PUBLICATION_DATE_ONLY" for target in result)
    assert all(target["appliedDate"] is None for target in result)
