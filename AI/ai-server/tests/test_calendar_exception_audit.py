"""Exercise notice identity, field separation, and time-bounded comparison."""
import json

import pytest

from app.replay import calendar_exception_audit as audit
from app.replay.calendar_rule_evidence import value
from app.replay.dataset import canonical, digest
from app.replay.models import ResearchError, utc


FIRST = "2026-11-07T05:00:00Z"
LATER = "2026-11-07T06:00:00Z"


def test_late_dated_notice_does_not_change_an_earlier_view():
    evidence = {"first": {"knownAt": FIRST}, "later": {"knownAt": LATER}}
    candidate = value("T_PLUS_TWO_CANDIDATE", "2025-01-02", FIRST, ["rule"])
    claims = [audit.claim("first", "2025-01-02"), audit.claim("later", "2025-01-03")]

    assert audit.comparison(candidate, claims, evidence, utc(FIRST))["status"] == "CONFIRMED"
    result = audit.comparison(candidate, claims, evidence, utc(LATER))
    assert result["status"] == "CONFLICT"
    assert result["value"] is None
    assert result["claims"] == claims


def test_single_dated_claim_against_a_rule_is_a_conflict_and_no_notice_is_unknown():
    candidate = value("RULE_EXCLUDED", False, FIRST, ["rule"])
    evidence = {"notice": {"knownAt": LATER}}
    assert audit.comparison(candidate, [], evidence)["status"] == "UNKNOWN"
    result = audit.comparison(candidate, [audit.claim("notice", True)], evidence)
    assert result["status"] == "CONFLICT"
    assert result["value"] is None


def test_confirmed_settlement_requires_the_rule_candidate_to_be_available():
    candidate = value("STANDARD_DAY_CANDIDATE", True, LATER)
    claims = [audit.claim("notice", True)]
    evidence = {"notice": {"knownAt": FIRST}}
    result = audit.comparison(candidate, claims, evidence, utc(FIRST))
    assert result["status"] == "UNKNOWN"
    assert result["candidate"]["value"] is None
    assert result["claims"] == claims
    assert audit.comparison(candidate, claims, evidence, utc(LATER))["value"] is True


def test_krx_market_notice_only_yields_trading_closures():
    raw = ("<html><title>:: 71985_코스닥시장 휴장안내</title><body>코스닥시장 휴장안내 "
           "1. 휴장일자 2026년 6월 3일(수), 2026년 7월 17일(금) 2. 휴장사유 지방선거일, 제헌절 "
           "3. 대상시장 전체 코스닥시장 4. 근거규정 코스닥시장 업무규정 제5조</body></html>").encode()
    receipt = {"url": audit.KIND + "/external/2026/05/20/000121/20260520000184/71985.htm",
               "bodySha256": digest(raw), "capturedAt": FIRST}
    evidence, dates = audit.krx_notice({"test": (receipt, raw)}, "test", "KOSDAQ")
    assert dates == ["2026-06-03", "2026-07-17"]
    assert evidence["knownAt"] == FIRST
    with pytest.raises(ResearchError, match="CALENDAR_EXCEPTION_KRX_IDENTITY"):
        audit.krx_notice({"test": (receipt, raw)}, "test", "KOSPI")


def guide_capture():
    properties = [{"bodyType": "req_b", "propertyCd": field, "description": ""}
                  for field in ("BASS_DT", "CTX_AREA_NK", "CTX_AREA_FK")]
    properties += [{"bodyType": "res_b", "propertyCd": field, "description": ""}
                   for field in ("bass_dt", "wday_dvsn_cd", "rt_cd", "msg_cd", "msg1", "output")]
    properties += [{"bodyType": "res_b", "propertyCd": code, "description": marker}
                   for code, (_, _, marker) in audit.KIS_FIELDS.items()]
    properties.extend([
        {"bodyType": "req_h", "propertyCd": "tr_id", "description": "CTCA0903R"},
        {"bodyType": "res_h", "propertyCd": "tr_cont", "description": "다음조회 불가"},
    ])
    guide = {"apiPropertys": properties, "accessUrl": audit.KIS_PATH, "httpMethod": "GET",
             "name": "국내휴장일조회[국내주식-040]", "apiSummary": "opnd_yn"}
    return {"url": audit.KIS_GUIDE, "capturedAt": FIRST, "bodySha256": "synthetic"}, guide


def test_kis_guide_pins_ledger_meanings_and_does_not_assume_market_coverage():
    receipt, guide = guide_capture()
    result = audit.kis_guide({"kis-guide": (receipt, canonical(guide))})
    assert result["fields"]["tr_day_yn"]["meaning"] == "SECURITIES_SERVICES_DAY"
    assert result["orderCalendarField"] == "opnd_yn"
    assert result["perMarketApplicability"] == "UNKNOWN"
    assert result["continuationDocumentedSupported"] is False

    guide["apiPropertys"].append({"bodyType": "req_b", "propertyCd": "MARKET", "description": ""})
    with pytest.raises(ResearchError, match="CALENDAR_EXCEPTION_KIS_GUIDE_SCOPE"):
        audit.kis_guide({"kis-guide": (receipt, canonical(guide))})


def test_as_of_keeps_provider_values_separate_even_when_visible():
    stamp = "2023-11-04"
    candidate = value("RULE_HOLIDAY", False, FIRST)
    row = {"businessDate": stamp, **{field: audit.comparison(candidate, [], {}) for field in audit.FIELDS}}
    sample = {"rows": [{"businessDate": stamp, "businessDay": False, "tradingDay": True,
                        "openDay": False, "settlementDay": False}],
              "scope": "DOMESTIC_NO_EXPLICIT_MARKET", "bodySha256": "synthetic", "knownAt": FIRST}
    report = {"startDate": stamp, "endDate": stamp, "markets": {"KOSDAQ": {"rows": [row]}}, "evidence": {},
              "provider": {"comparisonKnownAt": LATER, "sample": sample}}
    assert audit.as_of(report, "KOSDAQ", stamp, FIRST)["kisObservation"] is None
    view = audit.as_of(report, "KOSDAQ", stamp, LATER)
    assert view["kisObservation"]["tradingDay"] is True
    assert view["krxTradingSchedule"]["status"] == "UNKNOWN"
    assert view["krxTradingSchedule"]["value"] is None


def test_capture_rejects_modified_body_and_receipt(tmp_path):
    folder = tmp_path / "source"
    folder.mkdir()
    body = folder / "body"
    body.write_bytes(b"original")
    receipt = folder / "receipt.json"
    record = {"status": "COMPLETE", "bodySha256": digest(body.read_bytes()), "startedAt": FIRST, "capturedAt": LATER}
    receipt.write_bytes(canonical(record))
    pin = digest(receipt.read_bytes())
    assert audit.read_capture(tmp_path, "source", pin)[1] == b"original"
    body.write_bytes(b"modified")
    with pytest.raises(ResearchError, match="CALENDAR_EXCEPTION_CAPTURE_MISMATCH"):
        audit.read_capture(tmp_path, "source", pin)
    record["bodySha256"] = digest(body.read_bytes())
    receipt.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ResearchError, match="CALENDAR_EXCEPTION_CAPTURE_MISMATCH"):
        audit.read_capture(tmp_path, "source", pin)
