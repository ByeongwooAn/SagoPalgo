"""All tape fixtures here are synthetic; observed-config tests exercise declarations only."""
import json

import pytest
from pydantic import ValidationError

from app.replay.__main__ import main
from app.replay.dataset import canonical, digest
from app.replay.models import ResearchError
from app.replay.ticks import ExecutionClaim, TickAuditConfig, audit_ticks, audit_tick_files
from app.replay.daily_reference import compare_daily_rows


def config(**changes):
    value = dict(schemaVersion="SAGOPALGO_TICK_AUDIT_V1", sourceId="test-kis", provider="KIS_KRX_PUBLIC",
                 market="KOSPI", stockCode="005930", startAt="2025-11-03T00:00:00Z",
                 endAt="2025-11-03T00:02:00Z", provenance="SYNTHETIC", rights="PERMITTED",
                 evidence="SYNTHETIC test only; not a live provider capture", regularSessionCodes=["R"], maxQuoteAgeMs=1000)
    value.update(changes)
    return TickAuditConfig.model_validate(value)


def row(kind="TRADE", at="2025-11-03T00:00:01Z", received="2025-11-03T00:00:02Z", **changes):
    trade = kind == "TRADE"
    value = dict(stockCode="005930", type=kind, marketTime=at, receivedAt=received,
                 price="100" if trade else None, volume="2" if trade else None,
                 cumulativeVolume="2" if trade else None,
                 asks=[] if trade else [dict(price=str(101+i), quantity="5") for i in range(10)],
                 bids=[] if trade else [dict(price=str(99-i), quantity="6") for i in range(10)],
                 session="R", dateBasis="PROVIDER_DATE" if trade else "RECEIVE_DATE_INFERRED")
    value.update(changes)
    identity = f'TRADE|005930|2025-11-03|{int(value["cumulativeVolume"])}' if trade else "QUOTE|synthetic"
    value["eventId"] = digest(identity.encode())
    raw = canonical(value).decode()
    return dict(eventId=value["eventId"], stockCode="005930", type=kind, marketAt=at,
                receivedAt=received, payloadJson=raw, contentHash=digest(raw.encode()))


def export(*rows):
    return dict(schemaVersion="SAGOPALGO_STORED_EXPORT_V1", stockCode="005930", **{"from":"2025-11-03T00:00:00Z",
                "to":"2025-11-03T00:02:00Z"}, exportedAt="2025-11-03T00:05:00Z", readOnly=True,
                usableForTrading=False, consistency="REPEATABLE_READ", streamCoverage="OBSERVED_ONLY",
                researchScope="ALL_VERSIONS_OBSERVED_BEFORE_TO", streamEvents=list(rows), researchVersions=[])


def claim(**changes):
    v = dict(claimId="c1", referenceTradeId=row()["eventId"], side="BUY", decisionAt="2025-11-03T00:00:00Z",
             filledAt="2025-11-03T00:00:01Z", price="100", quantity="1")
    v.update(changes)
    return ExecutionClaim.model_validate(v)


def modify(event, **changes):
    p = json.loads(event["payloadJson"])
    p.update(changes)
    event["payloadJson"] = canonical(p).decode()
    event["contentHash"] = digest(event["payloadJson"].encode())


def test_empty_sample_does_not_pass_as_complete():
    records, report = audit_ticks(canonical(export()), config(), [claim()])
    assert records == [] and report["status"] == "NO_TICK_SAMPLE"
    assert report["comparisonCounts"] == {"NOT_ASSESSABLE": 1}
    assert not report["usableForTrading"] and not report["usableForStrategyValidation"]


def test_fields_preserved_without_invented_sequence_or_commit():
    records, report = audit_ticks(canonical(export(row(), row("QUOTE"))), config(), [])
    assert len(records) == 2 and report["counts"] == {"TRADE": 1, "QUOTE": 1}
    for r in records:
        assert r["knownAt"] == "2025-11-03T00:05:00+00:00" and r["exchangeSequence"] is None
        assert len(r["rawSha256"]) == 64
    quote = next(x for x in records if x["type"] == "QUOTE")
    assert quote["price"] is None and quote["volume"] is None and len(quote["asks"]) == 10
    assert "UNCONFIRMED_BUSINESS_DATE" in quote["flags"]


@pytest.mark.parametrize("change", [dict(price=None), dict(volume=None), dict(volume=2), dict(price="NaN"),
    dict(volume="-1"), dict(cumulativeVolume="1"), dict(price="0"), dict(accountNumber="private"), dict(asks=[dict(price="1", quantity="1")])])
def test_malformed_or_private_trade_rejected(change):
    event = row()
    modify(event, **change)
    with pytest.raises(ValidationError): audit_ticks(canonical(export(event)), config(), [])


@pytest.mark.parametrize("change,code", [
    (dict(eventId="f"*64), "STORED_EVENT_INVALID"),
    (dict(marketTime="2025-11-03T00:00:02Z"), "STORED_EVENT_TIME_MISMATCH"),
    (dict(receivedAt="2025-11-03T00:06:00Z"), "STORED_EVENT_TIME_MISMATCH"),
    (dict(cumulativeVolume="3"), "STORED_TRADE_ID_MISMATCH")])
def test_identity_and_time_mismatch(change, code):
    event = row()
    modify(event, **change)
    with pytest.raises(ResearchError, match=code): audit_ticks(canonical(export(event)), config(), [])


def test_hash_tamper_and_duplicate_id_rejected_not_double_counted():
    event = row()
    event["contentHash"] = "0"*64
    with pytest.raises(ResearchError, match="HASH_MISMATCH"): audit_ticks(canonical(export(event)), config(), [])
    with pytest.raises(ValidationError): audit_ticks(canonical(export(row(), row())), config(), [])


def test_gap_regression_and_late_arrival_do_not_invent_ticks():
    later = row(at="2025-11-03T00:00:03Z", received="2025-11-03T00:00:03Z", cumulativeVolume="8")
    earlier = row(received="2025-11-03T00:00:04Z")
    records, report = audit_ticks(canonical(export(later, earlier)), config(), [])
    assert len(records) == 2 and report["issues"]["POSSIBLE_TRADE_GAP"] == 1
    assert report["issues"]["OUT_OF_ORDER_RECEIPT"] == 1
    later = row(at="2025-11-03T00:00:03Z", received="2025-11-03T00:00:03Z", cumulativeVolume="1", volume="1")
    assert audit_ticks(canonical(export(row(), later)), config(), [])[1]["issues"]["CUMULATIVE_VOLUME_REGRESSION"] == 1


def test_zero_volume_is_preserved_and_excluded_from_reference_match():
    event = row(volume="0")
    records, report = audit_ticks(canonical(export(event)), config(provenance="OBSERVED"), [claim()])
    assert records[0]["volume"] == "0"
    assert report["comparisons"][0]["reasons"] == ["ZERO_VOLUME_TRADE"]


def test_empty_legacy_quote_preserved_as_incomplete_without_zero_trade_numbers():
    q = row("QUOTE", asks=[], bids=[])
    records, report = audit_ticks(canonical(export(q)), config(), [])
    assert report["issues"]["INCOMPLETE_BOOK_LEVELS"] == 1
    assert records[0]["price"] is None and records[0]["asks"] == []


@pytest.mark.parametrize("changes,expected,reason", [({}, "MATCH", None),
    ({"price":"99"}, "MISMATCH", "TRADE_PRICE_MISMATCH"),
    ({"quantity":"3"}, "MISMATCH", "QUANTITY_EXCEEDS_OBSERVED_PRINT"),
    ({"filledAt":"2025-11-03T00:00:02Z"}, "MISMATCH", "TRADE_TIME_MISMATCH"),
    ({"referenceTradeId":"f"*64}, "NOT_ASSESSABLE", "REFERENCE_TRADE_MISSING")])
def test_tape_reference_comparison_never_claims_account_fill(changes, expected, reason):
    # OBSERVED is a caller declaration; these remain synthetic unit-test bytes.
    report = audit_ticks(canonical(export(row())), config(provenance="OBSERVED"), [claim(**changes)])[1]
    c = report["comparisons"][0]
    assert c["marketReferenceStatus"] == expected and c["accountFillStatus"] == "NOT_PROVEN"
    if reason: assert reason in c["reasons"]


def test_synthetic_and_unconfirmed_rights_are_not_actual_evidence():
    r = audit_ticks(canonical(export(row())), config(rights="UNCONFIRMED"), [claim()])[1]
    assert r["comparisonCounts"] == {"NOT_ASSESSABLE":1}
    assert r["comparisons"][0]["reasons"] == ["RIGHTS_UNCONFIRMED", "SYNTHETIC_REFERENCE"]


def test_future_quote_and_late_receipt_cannot_enter_decision():
    for at, received in [("2025-11-03T00:00:01Z", "2025-11-03T00:00:01Z"),
                         ("2025-11-03T00:00:00Z", "2025-11-03T00:00:01Z")]:
        q = row("QUOTE", at=at, received=received)
        c = audit_ticks(canonical(export(row(), q)), config(), [claim()])[1]["comparisons"][0]
        assert c["quoteEventId"] is None and "NO_PRIOR_QUOTE" in c["quoteReasons"]


def test_quote_exact_boundary_date_and_historical_availability_remain_unconfirmed():
    q = row("QUOTE", at="2025-11-03T00:00:00Z", received="2025-11-03T00:00:00Z")
    c = audit_ticks(canonical(export(row(), q)), config(), [claim()])[1]["comparisons"][0]
    assert c["quoteEventId"] == q["eventId"] and c["quoteStatus"] == "NOT_ASSESSABLE"
    assert {"UNCONFIRMED_BUSINESS_DATE", "HISTORICAL_AVAILABILITY_UNCONFIRMED"} <= set(c["quoteReasons"])


def test_same_market_time_quotes_without_exchange_sequence_cannot_pick_hash_order():
    q = row("QUOTE", at="2025-11-03T00:00:00Z", received="2025-11-03T00:00:00Z")
    second = dict(q, eventId=digest(b"second-quote"))
    modify(second, eventId=second["eventId"])
    c = audit_ticks(canonical(export(row(), q, second)), config(), [claim()])[1]["comparisons"][0]
    assert c["quoteEventId"] is None and "AMBIGUOUS_QUOTE_ORDER" in c["quoteReasons"]


def test_stale_quote_and_book_anomalies_reported():
    q = row("QUOTE", at="2025-11-03T00:00:00Z", received="2025-11-03T00:00:00Z")
    p = json.loads(q["payloadJson"])
    p["bids"][0]["price"] = "200"
    modify(q, bids=p["bids"])
    c = audit_ticks(canonical(export(row(), q)), config(), [claim(decisionAt="2025-11-03T00:00:02Z", filledAt="2025-11-03T00:00:03Z")])[1]["comparisons"][0]
    assert "STALE_QUOTE" in c["quoteReasons"] and "LOCKED_OR_CROSSED_BOOK" in c["quoteReasons"]


def test_nanoseconds_ceil_and_clock_anomaly_not_backdated():
    event = row(received="2025-11-03T00:00:02.123456001Z")
    event["receivedAt"] = "2025-11-03T00:00:02.123456Z"
    r = audit_ticks(canonical(export(event)), config(), [])[0][0]
    assert r["receivedAt"].endswith("123457+00:00")
    event = row(received="2025-11-03T00:00:00Z")
    assert "RECEIPT_BEFORE_MARKET_TIME" in audit_ticks(canonical(export(event)), config(), [])[0][0]["flags"]


def test_scope_claim_duplicates_and_half_open_end_rejected():
    with pytest.raises(ResearchError, match="TICK_SCOPE_MISMATCH"):
        audit_ticks(canonical(export()), config(market="KOSDAQ", stockCode="000660"), [])
    with pytest.raises(ResearchError, match="DUPLICATE_CLAIM_ID"):
        audit_ticks(canonical(export()), config(), [claim(), claim()])
    with pytest.raises(ResearchError, match="CLAIM_OUTSIDE_SCOPE"):
        audit_ticks(canonical(export()), config(), [claim(filledAt="2025-11-03T00:02:00Z")])


def test_cli_hashes_raw_preserved_no_network_and_no_overwrite(tmp_path, monkeypatch, capsys):
    import socket
    def blocked(*args, **kwargs): raise AssertionError("network forbidden")
    monkeypatch.setattr(socket.socket, "connect", blocked)
    raw = canonical(export(row(), row("QUOTE")))
    inp, cfg, out = tmp_path/"in.json", tmp_path/"config.json", tmp_path/"output"
    inp.write_bytes(raw)
    cfg.write_bytes(canonical(config().model_dump(mode="json")))
    args = ["audit-ticks", "--input", str(inp), "--config", str(cfg), "--output", str(out)]
    assert main(args) == 0
    report = json.loads((out/"audit.json").read_bytes())
    assert (out/"source-export.json").read_bytes() == raw
    assert all(digest((out/name).read_bytes()) == sha for name, sha in report["files"].items())
    assert main(args) == 2 and "OUTPUT_EXISTS" in capsys.readouterr().err


def test_persistent_publication_failure_preserves_complete_stage(tmp_path, monkeypatch):
    inp, cfg, out = tmp_path/"in.json", tmp_path/"config.json", tmp_path/"output"
    inp.write_bytes(canonical(export(row())))
    cfg.write_bytes(canonical(config().model_dump(mode="json")))
    def fail(*args): raise PermissionError("publication failure")
    monkeypatch.setattr("app.replay.ticks.publish_directory", fail)
    with pytest.raises(PermissionError): audit_tick_files(inp, cfg, out)
    stages = list(tmp_path.glob(".tick-audit-*"))
    assert len(stages) == 1 and (stages[0]/"audit.json").is_file() and not out.exists()


@pytest.mark.parametrize("price,status", [("100.0", "MATCH"), ("101", "MISMATCH"), ("NaN", "NOT_ASSESSABLE"),
    ("-1", "NOT_ASSESSABLE"), (None, "NOT_ASSESSABLE")])
def test_independent_daily_comparison_remains_daily_only(price, status):
    a = dict(stockCode="005930", businessDate="2023-11-01", open="100", high="100", low="100", close="100", volume="2")
    b = dict(ISU_CD="005930", BAS_DD="20231101", TDD_OPNPRC="100", TDD_HGPRC="100", TDD_LWPRC="100", TDD_CLSPRC=price, ACC_TRDVOL="2")
    report = compare_daily_rows([a], [b])
    assert report["comparisons"][0]["status"] == status
    assert report["tickComparisonStatus"] == "NOT_ASSESSABLE"


def test_daily_comparison_missing_scope_is_not_a_match():
    assert compare_daily_rows([], [])["status"] == "NO_COMMON_DAILY_REFERENCE"
