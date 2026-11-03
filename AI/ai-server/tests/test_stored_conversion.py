import copy
import json
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.replay.__main__ import main
from app.replay.dataset import build_bundle, canonical, digest, known_at, load_bundle, snapshot
from app.replay.engine import replay
from app.replay.models import ReplayConfig, ResearchError, utc
from app.replay.stored import ConversionConfig, convert, convert_file, precise_time

EXAMPLES = Path(__file__).parents[1] / "examples/replay"


def config(mode="EXPORT_OBSERVED"):
    value = json.loads((EXAMPLES / "conversion.json").read_text(encoding="utf-8"))
    value["availabilityMode"] = mode
    return ConversionConfig.model_validate(value)


def fixture():
    events = []
    for second, received, price, volume, cumulative in [(1, 2, "100", "2", "2"), (20, 70, "102", "3", "5"), (61, 62, "104", "2", "7")]:
        from datetime import timedelta
        at = utc("2025-11-03T00:00:00Z") + timedelta(seconds=second)
        received_at = utc("2025-11-03T00:00:00Z") + timedelta(seconds=received)
        event_id = digest(f"TRADE|005930|2025-11-03|{cumulative}".encode())
        body = {"eventId": event_id, "stockCode": "005930", "type": "TRADE", "marketTime": at.isoformat(),
                "receivedAt": received_at.isoformat(), "price": price, "volume": volume, "cumulativeVolume": cumulative,
                "asks": [], "bids": [], "session": "R", "dateBasis": "PROVIDER_DATE"}
        raw = canonical(body).decode()
        events.append({"eventId": event_id, "stockCode": "005930", "type": "TRADE", "marketAt": at.isoformat(),
                       "receivedAt": received_at.isoformat(), "payloadJson": raw, "contentHash": digest(raw.encode())})
    quote = copy.deepcopy(events[0])
    quoted = json.loads(quote["payloadJson"])
    quote["type"] = quoted["type"] = "QUOTE"
    quote["eventId"] = quoted["eventId"] = digest(b"quote")
    quoted["dateBasis"] = "RECEIVE_DATE_INFERRED"
    quote["payloadJson"] = canonical(quoted).decode()
    quote["contentHash"] = digest(quote["payloadJson"].encode())
    events.append(quote)
    versions = []
    for n, title in enumerate(["A", "B", "A"], 1):
        body = {"provider": "NAVER_NEWS", "stockCode": "005930", "title": title, "link": "https://news.test/item",
                "summary": "요약", "publishedAt": "2025-11-02T00:00:00Z"}
        raw = canonical(body).decode()
        versions.append({"changeId": n, "kind": "NEWS", "provider": "NAVER_NEWS", "stockCode": "005930", "itemKey": "a" * 64,
                         "revision": n, "observedAt": f"2025-11-03T00:00:{n * 10:02d}Z", "origin": "OBSERVED",
                         "payloadJson": raw, "contentHash": digest(raw.encode())})
    raw = canonical({"provider": "OPEN_DART", "stockCode": "005930", "receiptDate": "2025-11-03", "reportName": "정정 공시"}).decode()
    versions.append({"changeId": 4, "kind": "DISCLOSURE", "provider": "OPEN_DART", "stockCode": "005930", "itemKey": "b" * 64,
                     "revision": 1, "observedAt": "2025-11-03T00:00:40Z", "origin": "OBSERVED", "payloadJson": raw, "contentHash": digest(raw.encode())})
    return {"schemaVersion": "SAGOPALGO_STORED_EXPORT_V1", "stockCode": "005930", "from": "2025-11-03T00:00:00Z",
            "to": "2025-11-03T00:02:00Z", "exportedAt": "2025-11-03T00:05:00Z", "readOnly": True, "usableForTrading": False,
            "consistency": "REPEATABLE_READ", "streamCoverage": "OBSERVED_ONLY", "researchScope": "ALL_VERSIONS_OBSERVED_BEFORE_TO",
            "streamEvents": events, "researchVersions": versions}


def change_payload(row, changes):
    value = json.loads(row["payloadJson"])
    value.update(changes)
    row["payloadJson"] = canonical(value).decode()
    row["contentHash"] = digest(row["payloadJson"].encode())


def test_default_conversion_does_not_invent_past_bar_availability():
    spec, records, report = convert(canonical(fixture()), config())
    bars = [r for r in records if r.kind == "BAR"]
    assert len(bars) == 2 and len(records) == 5
    assert bars[0].payload.open == "100" and bars[0].payload.close == "102" and bars[0].payload.volume == "5"
    assert all(known_at(r, spec) == utc("2025-11-03T00:05:00Z") for r in bars)
    assert [r for r in snapshot(records, spec, utc("2025-11-03T00:02:00Z")) if r.kind == "BAR"] == []
    assert report["excludedCounts"] == {"DATE_ONLY_DISCLOSURE": 1, "QUOTE_NOT_A_BAR": 1}
    assert report["universe"] == "NOT_PROVIDED"


def test_receipt_mode_versions_late_trade_without_future_leak():
    spec, records, _ = convert(canonical(fixture()), config("RECEIPT_DERIVED"))
    bars = [r for r in records if r.kind == "BAR"]
    assert len(bars) == 3
    first = [r for r in bars if r.payload.startAt == utc("2025-11-03T00:00:00Z")]
    assert [(r.revision, r.payload.volume) for r in first] == [(1, "2"), (2, "5")]
    before = snapshot(records, spec, utc("2025-11-03T00:01:05Z"))
    assert [(r.revision, r.payload.close) for r in before if r.kind == "BAR"] == [(1, "100")]
    assert known_at(first[1], spec) == utc("2025-11-03T00:01:10Z")


def test_news_reverts_keep_original_observation_order():
    spec, records, _ = convert(canonical(fixture()), config())
    news = [r for r in records if r.kind == "NEWS"]
    assert [r.payload.title for r in news] == ["A", "B", "A"]
    assert [r.payload.title for r in snapshot(records, spec, utc("2025-11-03T00:00:25Z")) if r.kind == "NEWS"] == ["B"]


@pytest.mark.parametrize("fraction,expected", [("123456000", "123456"), ("123456001", "123457"), ("999999999", "000000")])
def test_nanosecond_timestamps_are_rounded_only_toward_future(fraction, expected):
    at = precise_time(f"2025-11-03T00:00:02.{fraction}Z")
    assert f"{at.microsecond:06d}" == expected
    if fraction == "999999999":
        assert at.second == 3


@pytest.mark.parametrize("edit", [
    lambda v: v["streamEvents"][0].update(contentHash="0" * 64),
    lambda v: change_payload(v["streamEvents"][0], {"accountNumber": "private"}),
    lambda v: change_payload(v["streamEvents"][0], {"eventId": "f" * 64}),
    lambda v: change_payload(v["streamEvents"][0], {"cumulativeVolume": "999"}),
    lambda v: change_payload(v["researchVersions"][0], {"stockCode": "000660"}),
    lambda v: v["researchVersions"][0].update(contentHash="0" * 64),
])
def test_tampering_identity_or_private_fields_fails_whole_conversion(edit):
    value = fixture()
    edit(value)
    with pytest.raises(ResearchError):
        convert(canonical(value), config())


@pytest.mark.parametrize("edit", [
    lambda v: v["streamEvents"].append(v["streamEvents"][0]),
    lambda v: v["researchVersions"].reverse(),
    lambda v: v.update(readOnly=False),
    lambda v: v.update(readOnly=1),
    lambda v: v.update(streamCoverage="COMPLETE"),
    lambda v: v.update(to="2025-11-03T00:02:01Z"),
    lambda v: v["streamEvents"][0].update(stockCode="000660"),
])
def test_export_scope_and_contract_cannot_be_silently_weakened(edit):
    value = fixture()
    edit(value)
    with pytest.raises(ValidationError):
        convert(canonical(value), config())


def test_unknown_date_or_session_excluded_with_reason_not_assumed():
    value = fixture()
    change_payload(value["streamEvents"][0], {"dateBasis": "RECEIVE_DATE_INFERRED"})
    change_payload(value["streamEvents"][1], {"session": "X"})
    _, records, report = convert(canonical(value), config())
    assert report["excludedCounts"]["UNCONFIRMED_BUSINESS_DATE"] == 1
    assert report["excludedCounts"]["UNMAPPED_SESSION"] == 1
    assert len([r for r in records if r.kind == "BAR"]) == 1


def test_partial_news_lineage_is_never_rebased_to_revision_one():
    value = fixture()
    value["researchVersions"] = value["researchVersions"][1:]
    with pytest.raises(ResearchError, match="STORED_RESEARCH_LINEAGE_INVALID"):
        convert(canonical(value), config())


def test_missing_publication_skips_entire_news_lineage():
    value = fixture()
    change_payload(value["researchVersions"][1], {"publishedAt": None})
    _, records, report = convert(canonical(value), config())
    assert not any(r.kind == "NEWS" for r in records)
    assert report["excludedCounts"]["UNKNOWN_PUBLICATION_TIME"] == 3


def test_conversion_artifacts_preserve_original_and_build_replay_bundle(tmp_path):
    raw = canonical({"success": True, "data": fixture(), "error": None, "message": "SYNTHETIC_TEST_ONLY"})
    path = tmp_path / "export.json"
    path.write_bytes(raw)
    target = tmp_path / "converted"
    report = convert_file(path, EXAMPLES / "conversion.json", target)
    assert (target / "source-export.json").read_bytes() == raw
    assert report["inputSha256"] == digest(raw)
    build_bundle(target / "spec.json", target / "records.jsonl", tmp_path / "bundle")
    assert len(load_bundle(tmp_path / "bundle")[2]) == 5
    with pytest.raises(ResearchError, match="OUTPUT_EXISTS"):
        convert_file(path, EXAMPLES / "conversion.json", target)


def test_empty_export_is_explicit_and_does_not_create_fake_prices():
    value = fixture()
    value.update(streamEvents=[], researchVersions=[])
    _, records, report = convert(canonical(value), config())
    assert records == [] and report["status"] == "NO_CONVERTIBLE_RECORDS"


def test_only_excluded_records_are_explicitly_empty():
    value = fixture()
    value.update(streamEvents=[value["streamEvents"][-1]], researchVersions=[value["researchVersions"][-1]])
    _, records, report = convert(canonical(value), config())
    assert records == [] and report["status"] == "NO_CONVERTIBLE_RECORDS"
    assert report["excludedCounts"] == {"DATE_ONLY_DISCLOSURE": 1, "QUOTE_NOT_A_BAR": 1}


def test_cli_conversion(tmp_path, capsys):
    path = tmp_path / "export.json"
    path.write_bytes(canonical(fixture()))
    assert main(["convert-stored", "--input", str(path), "--config", str(EXAMPLES / "conversion.json"), "--output", str(tmp_path / "converted")]) == 0
    assert "CONVERTED_WITH_EXCLUSIONS" in capsys.readouterr().out


def test_old_bundle_remains_loadable_and_receipt_mode_requires_opt_in(tmp_path):
    target = tmp_path / "legacy"
    build_bundle(EXAMPLES / "spec.json", EXAMPLES / "records.jsonl", target)
    manifest = json.loads((target / "manifest.json").read_bytes())
    manifest["engineVersion"] = "R5_FOUNDATION_1"
    del manifest["datasetId"]
    manifest["datasetId"] = digest(canonical(manifest))
    (target / "manifest.json").write_bytes(canonical(manifest))
    load_bundle(target)
    spec, records, _ = convert(canonical(fixture()), config("RECEIPT_DERIVED"))
    replay_config = json.loads((EXAMPLES / "config.json").read_bytes())
    replay_config.update(barSourceId="r2-kis", universeSourceId="r2-kis", intents=[])
    with pytest.raises(ResearchError, match="DERIVED_AVAILABILITY_OPT_IN_REQUIRED"):
        replay({}, spec, records, {}, ReplayConfig.model_validate(replay_config))


@pytest.mark.skipif(not os.getenv("SAGOPALGO_STORED_EXPORT_FIXTURE"), reason="requires isolated Java/MySQL export fixture")
def test_actual_java_mysql_export_cross_runtime_bridge(tmp_path):
    path = Path(os.environ["SAGOPALGO_STORED_EXPORT_FIXTURE"])
    target = tmp_path / "converted"
    report = convert_file(path, EXAMPLES / "conversion.json", target)
    assert report["streamInputCount"] == 4 and report["researchInputCount"] == 4
    assert report["excludedCounts"] == {"DATE_ONLY_DISCLOSURE": 1, "QUOTE_NOT_A_BAR": 1}
    build_bundle(target / "spec.json", target / "records.jsonl", tmp_path / "bundle")
    loaded = load_bundle(tmp_path / "bundle")
    assert len(loaded[2]) == 5
