"""Offline audit of independently scoped calendar claims and capture-time boundaries."""
import json

import pytest

from app.replay import calendar_flag_audit as audit, calendar_fetch, market_calendar_evidence as market
from app.replay import krx_calendar_sources as years
from app.replay.dataset import canonical, digest
from app.replay.models import ResearchError
from test_krx_calendar_sources import Client
from test_market_calendar_evidence import AT, newyear, newyear_source, receipt, rules


KIS_KNOWN = "2026-11-03T06:00:00Z"


@pytest.fixture
def inputs(tmp_path):
    sources = [market.Source(sourceId=name.lower() + "-rule", role=name + "_RULE",
                             url=market.RULES[name + "_RULE"], markets=[name]) for name in audit.MARKETS]
    sources.append(newyear_source("KOSPI"))
    scope = tmp_path / "scope.json"
    scope.write_bytes(canonical({
        "schemaVersion": "SAGOPALGO_MARKET_CALENDAR_SCOPE_V1",
        "startDate": "2023-11-01", "endDate": "2024-01-02",
        "sources": [value.model_dump(mode="json") for value in sources],
    }))
    cache = tmp_path / "market-cache"
    for source in sources:
        raw = rules(source.markets[0]) if source.role in market.RULES else newyear()
        market.seed_capture(cache, source.url, raw, receipt(source, raw))
    market.capture(scope, cache, 0)
    year_job = tmp_path / "years"
    years.prepare(year_job, "2023-11-01", "2024-01-02", 4, source_kind="SYNTHETIC")
    years.collect(year_job, Client(), 4, sleep=lambda _: None)
    baseline = tmp_path / "baseline.json"
    baseline.write_bytes(canonical(market.build(scope, cache, year_job)))

    kis = tmp_path / "kis-page"
    kis.mkdir()
    raw = canonical({"rt_cd": "0", "output": [
        {"bass_dt": "20231104", "bzdy_yn": "N", "tr_day_yn": "Y", "opnd_yn": "N", "sttl_day_yn": "N"},
        {"bass_dt": "20231105", "bzdy_yn": "N", "tr_day_yn": "Y", "opnd_yn": "Y", "sttl_day_yn": "N"},
        {"bass_dt": "20240103", "bzdy_yn": "Y", "tr_day_yn": "Y", "opnd_yn": "Y", "sttl_day_yn": "Y"},
    ]})
    (kis / "body.json").write_bytes(raw)
    pack = calendar_fetch.calendar_reference(raw, KIS_KNOWN, "M")
    reference = canonical(pack.model_dump(mode="json"))
    (kis / "reference.json").write_bytes(reference)
    (kis / "receipt.json").write_bytes(canonical({
        "schemaVersion": "SAGOPALGO_CALENDAR_RECEIPT_V1", "status": "COMPLETE",
        "basisDate": "2023-11-04", "capturedAt": KIS_KNOWN, "continuation": "M",
        "autoPagination": False, "dailyLimit": 1, "hasMore": True,
        "bodySha256": digest(raw), "referenceSha256": digest(reference), "keyFingerprint": "private-test-marker",
    }))
    return scope, cache, year_job, baseline, kis


def fields(report, market_name, date):
    return next(row["fields"] for row in report["marketReports"][market_name]["rows"] if row["businessDate"] == date)


def test_dated_notice_is_scoped_and_never_fills_other_flags(inputs):
    report = audit.build(*inputs)
    kospi = fields(report, "KOSPI", "2023-12-29")
    kosdaq = fields(report, "KOSDAQ", "2023-12-29")
    assert kospi["openDay"]["status"] == kospi["settlementDay"]["status"] == "EXPLICIT_SCHEDULE"
    assert kospi["openDay"]["value"] is kospi["settlementDay"]["value"] is False
    assert kospi["businessDay"]["value"] is kospi["tradingDay"]["value"] is None
    assert kosdaq["openDay"]["status"] == "RECONSTRUCTED"
    assert kosdaq["settlementDay"] == {"status": "UNKNOWN", "value": None, "claims": []}
    assert fields(report, "KOSPI", "2024-01-02")["openDay"]["status"] == "EXPLICIT_SCHEDULE"
    assert fields(report, "KOSDAQ", "2024-01-02")["openDay"]["status"] == "RECONSTRUCTED"
    assert report["allCalendarFlagsComplete"] is False
    assert report["usableForTrading"] is report["usableForTraining"] is False


def test_provider_comparison_keeps_flags_and_market_scope_separate(inputs):
    report = audit.build(*inputs)
    provider = report["providerObservations"]
    assert provider["openComparisonCounts"] == {"MATCH": 1, "DISAGREE": 1, "OUTSIDE_SCOPE": 1}
    assert provider["tradingAndOpenFlagsDiffer"] == 1
    assert provider["hasMore"] and not provider["appliedToMarketFlags"]
    assert provider["rows"][0]["tradingDay"] is True and provider["rows"][0]["openDay"] is False
    for market_name in audit.MARKETS:
        weekend = fields(report, market_name, "2023-11-05")
        assert weekend["openDay"]["status"] == "RECONSTRUCTED" and weekend["openDay"]["value"] is False
        assert weekend["settlementDay"]["status"] == "UNKNOWN"
    assert b"private-test-marker" not in canonical(report)


def test_as_of_blocks_reconstruction_notice_and_provider_until_their_own_capture_times(inputs):
    report = audit.build(*inputs)
    past = audit.as_of(report, "KOSPI", "2023-11-04", "2023-11-04T23:59:59+09:00")
    assert not past["marketEvidence"] and past["providerObservation"] is None
    assert all(flag["status"] == "UNKNOWN" for flag in past["fields"].values())
    provider = audit.as_of(report, "KOSPI", "2023-11-04", KIS_KNOWN)
    assert provider["providerObservation"]["tradingDay"] is True
    assert provider["providerObservation"]["openComparison"] is None
    assert provider["fields"]["openDay"]["status"] == "UNKNOWN"
    before = audit.as_of(report, "KOSPI", "2023-12-29", "2026-11-05T11:59:59.999999Z")
    at = audit.as_of(report, "KOSPI", "2023-12-29", AT)
    assert before["fields"]["settlementDay"]["status"] == "UNKNOWN"
    assert at["fields"]["settlementDay"]["status"] == "EXPLICIT_SCHEDULE"


def test_conflicting_scoped_values_are_unknown_until_a_resolution_exists():
    evidence = {"a": {"kind": "DATED_MARKET_NOTICE", "knownAt": KIS_KNOWN},
                "b": {"kind": "DATED_MARKET_NOTICE", "knownAt": AT}}
    claims = [{"sourceId": "a", "value": False}, {"sourceId": "b", "value": True}]
    assert audit.resolve(claims, evidence, audit.utc(KIS_KNOWN))["value"] is False
    conflict = audit.resolve(claims, evidence)
    assert conflict["status"] == "CONFLICT" and conflict["value"] is None and conflict["claims"] == claims


@pytest.mark.parametrize(("index", "relative", "diagnostic"), [
    (3, "", "CALENDAR_FLAG_BASELINE_MISMATCH"),
    (4, "body.json", "CALENDAR_CACHE_TAMPERED"),
    (4, "reference.json", "CALENDAR_CACHE_TAMPERED"),
])
def test_rejects_tampered_baseline_or_provider_cache(inputs, index, relative, diagnostic):
    path = inputs[index] / relative if relative else inputs[index]
    path.write_bytes(b"{}")
    with pytest.raises(ResearchError, match=diagnostic):
        audit.build(*inputs)


def test_cli_writes_new_report_reaudits_and_preserves_inputs(inputs, tmp_path, capsys):
    output = tmp_path / "report.json"
    args = []
    for name, value in zip(("scope", "cache", "year-job", "baseline", "kis-cache-page"), inputs, strict=True):
        args.extend(("--" + name, str(value)))
    args.extend(("--output", str(output)))
    existing = {path: digest(path.read_bytes()) for path in tmp_path.rglob("*") if path.is_file()}
    assert audit.main(["build", *args]) == 0
    original = output.read_bytes()
    assert audit.main(["build", *args]) == 2
    assert audit.main(["audit", *args]) == 0
    capsys.readouterr()
    assert audit.main(["as-of", *args, "--market", "KOSPI", "--date", "2023-12-29", "--at", AT]) == 0
    assert json.loads(capsys.readouterr().out)["fields"]["settlementDay"]["value"] is False
    assert output.read_bytes() == original
    assert {path: digest(path.read_bytes()) for path in existing} == existing
    output.write_bytes(b"{}")
    assert audit.main(["audit", *args]) == 2
    assert json.loads(capsys.readouterr().out)["diagnostic"] == "CALENDAR_FLAG_REPORT_MISMATCH"
