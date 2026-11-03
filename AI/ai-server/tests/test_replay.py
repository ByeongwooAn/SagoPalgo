import copy
import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.replay.__main__ import main
from app.replay.dataset import (
    build_bundle, canonical, digest, known_at, load_bundle, normalize, read_json, snapshot,
)
from app.replay.engine import replay
from app.replay.models import DatasetSpec, Record, ReplayConfig, ResearchError, utc
from app.replay.temporal import SplitRequest, temporal_split

EXAMPLES = Path(__file__).parents[1] / "examples" / "replay"


def inputs():
    spec = json.loads((EXAMPLES / "spec.json").read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in (EXAMPLES / "records.jsonl").read_text(encoding="utf-8").splitlines()]
    config = json.loads((EXAMPLES / "config.json").read_text(encoding="utf-8"))
    return spec, rows, config


def dataset(tmp_path, spec=None, rows=None, name="bundle"):
    default_spec, default_rows, _ = inputs()
    spec, rows = spec or default_spec, rows or default_rows
    spec_path, raw_path = tmp_path / f"{name}-spec.json", tmp_path / f"{name}-raw.jsonl"
    spec_path.write_bytes(canonical(spec))
    raw_path.write_bytes(b"".join(canonical(r) + b"\n" for r in rows))
    target = tmp_path / name
    build_bundle(spec_path, raw_path, target)
    return target, load_bundle(target)


def run(tmp_path, config_changes=None, spec=None, rows=None):
    _, loaded = dataset(tmp_path, spec, rows)
    config = inputs()[2]
    config.update(config_changes or {})
    return replay(*loaded, ReplayConfig.model_validate(config))


def news(revision=1, title="original", observed="2026-11-02T00:02:00Z", origin="OBSERVED"):
    return {"sourceId": "demo", "kind": "NEWS", "itemId": "news1", "revision": revision,
            "stockCode": "000001", "exchange": "KRX", "currency": "KRW",
            "publishedAt": "2026-11-01T00:00:00Z", "observedAt": observed,
            "payload": {"title": title, "summary": "", "link": "https://example.test/news", "origin": origin}}


def test_bundle_roundtrip_preserves_exact_raw_and_is_reproducible(tmp_path):
    target, first = dataset(tmp_path, name="a")
    _, second = dataset(tmp_path, name="b")
    assert first[0] == second[0]
    assert (target / "raw.jsonl").read_bytes() == (tmp_path / "a-raw.jsonl").read_bytes()
    assert first[3]["missingBarCount"] == 0
    assert first[3]["usableForStrategyValidation"] is False
    with pytest.raises(ResearchError, match="OUTPUT_EXISTS"):
        build_bundle(tmp_path / "a-spec.json", tmp_path / "a-raw.jsonl", target)


@pytest.mark.parametrize("filename", ["raw.jsonl", "records.jsonl", "quality.json", "spec.json"])
def test_any_bundle_file_tampering_is_detected(tmp_path, filename):
    target, _ = dataset(tmp_path)
    with (target / filename).open("ab") as stream:
        stream.write(b" ")
    with pytest.raises(ResearchError, match="ARTIFACT_HASH_MISMATCH"):
        load_bundle(target)


def test_rehashing_bad_normalized_records_still_fails_reconstruction(tmp_path):
    target, _ = dataset(tmp_path)
    bad = b"{}\n"
    (target / "records.jsonl").write_bytes(bad)
    manifest = read_json((target / "manifest.json").read_bytes())
    manifest["files"]["records.jsonl"] = {"sha256": digest(bad), "bytes": len(bad)}
    del manifest["datasetId"]
    manifest["datasetId"] = digest(canonical(manifest))
    (target / "manifest.json").write_bytes(canonical(manifest))
    with pytest.raises(ResearchError, match="NORMALIZATION_MISMATCH"):
        load_bundle(target)


def test_no_publication_leak_and_corrections_appear_only_when_observed(tmp_path):
    spec, rows, _ = inputs()
    rows += [news(), news(2, "corrected", "2026-11-02T00:04:00Z"), news(3, "original", "2026-11-02T00:05:00Z")]
    _, (_, spec, records, report) = dataset(tmp_path, spec, rows)
    def selected(at):
        return [r.payload.title for r in snapshot(records, spec, utc(at)) if r.kind == "NEWS"]
    assert selected("2026-11-02T00:01:59Z") == []
    assert selected("2026-11-02T00:03:00Z") == ["original"]
    assert selected("2026-11-02T00:04:00Z") == ["corrected"]
    assert selected("2026-11-02T00:05:00Z") == ["original"]
    assert report["revisionCount"] == 2


def test_legacy_baseline_never_gains_assumed_historical_availability(tmp_path):
    spec, rows, _ = inputs()
    spec["sources"][0]["availability"] = "PUBLICATION_ASSUMED"
    rows.append(news(origin="LEGACY_BASELINE"))
    _, (_, spec, records, quality) = dataset(tmp_path, spec, rows)
    item = next(r for r in records if r.kind == "NEWS")
    assert known_at(item, spec) == utc("2026-11-02T00:02:00Z")
    assert quality["assumedAvailability"] == ["demo"]


def test_delisted_stock_does_not_disappear_from_earlier_universe(tmp_path):
    spec, rows, _ = inputs()
    removed = copy.deepcopy(rows[0])
    removed.update(itemId="removed", publishedAt="2026-11-02T00:03:00Z", observedAt="2026-11-02T00:03:00Z")
    removed["payload"].update(effectiveAt="2026-11-02T00:04:00Z", eligible=False)
    rows.append(removed)
    report = run(tmp_path, spec=spec, rows=rows)
    assert len(report["fills"]) == 1
    assert next(o for o in report["outcomes"] if o["intentId"] == "sell-demo")["status"] == "NOT_ELIGIBLE_AT_EXECUTION"


@pytest.mark.parametrize("change,code", [
    (lambda r: r.update(sourceId="unknown"), "UNKNOWN_SOURCE"),
    (lambda r: r.update(revision=2), "REVISION_GAP"),
])
def test_bad_identity_or_revision_fails_import(change, code):
    spec, rows, _ = inputs()
    change(rows[1])
    with pytest.raises(ResearchError, match=code):
        normalize(b"\n".join(canonical(r) for r in rows), DatasetSpec.model_validate(spec))


@pytest.mark.parametrize("field,value", [
    ("open", 100), ("open", "NaN"), ("open", "-1"), ("open", "1e2"), ("open", "0"),
    ("volume", "1.5"), ("volume", "-1"), ("priceBasis", "ADJUSTED"), ("high", "99"),
])
def test_invalid_or_future_adjusted_bar_values_are_rejected(field, value):
    _, rows, _ = inputs()
    rows[1]["payload"][field] = value
    with pytest.raises(ValidationError):
        Record.model_validate(rows[1])


@pytest.mark.parametrize("at", ["2026-11-02T00:01:00", "2026-11-02", "1999-01-01T00:00:00Z",
                               "2026-11-02T00:01:00.0000001Z", "2026-11-02 00:01:00Z"])
def test_timezone_or_supported_date_required(at):
    with pytest.raises(ValueError):
        utc(at)


def test_ohlc_unclosed_bar_is_not_accepted():
    _, rows, _ = inputs()
    rows[1]["publishedAt"] = "2026-11-02T00:00:59Z"
    with pytest.raises(ValidationError):
        Record.model_validate(rows[1])


def test_duplicate_conflicts_and_out_of_order_revision_times_rejected():
    spec, rows, _ = inputs()
    policy = DatasetSpec.model_validate(spec)
    assert len(normalize(b"\n".join(canonical(r) for r in rows + [rows[1]]), policy)) == len(rows)
    changed = copy.deepcopy(rows[1])
    changed["payload"]["close"] = "100"
    with pytest.raises(ResearchError, match="REVISION_CONFLICT"):
        normalize(b"\n".join(canonical(r) for r in rows + [changed]), policy)
    changed["revision"] = 2
    changed["observedAt"] = "2026-11-02T00:01:00Z"
    with pytest.raises(ResearchError, match="REVISION_TIME_REVERSED"):
        normalize(b"\n".join(canonical(r) for r in rows + [changed]), policy)


def test_two_ids_for_same_bar_and_overlapping_intervals_rejected():
    spec, rows, _ = inputs()
    extra = copy.deepcopy(rows[1])
    extra["itemId"] = "duplicate-slot"
    with pytest.raises(ResearchError, match="AMBIGUOUS_BAR"):
        normalize(b"\n".join(canonical(r) for r in rows + [extra]), DatasetSpec.model_validate(spec))
    extra["payload"].update(startAt="2026-11-02T00:00:30Z", endAt="2026-11-02T00:01:30Z")
    extra.update(publishedAt="2026-11-02T00:01:30Z", observedAt="2026-11-02T00:01:30Z")
    with pytest.raises(ResearchError, match="OVERLAPPING_BARS"):
        normalize(b"\n".join(canonical(r) for r in rows + [extra]), DatasetSpec.model_validate(spec))


def test_gap_report_uses_only_explicit_slots_and_never_fills_prices(tmp_path):
    spec, rows, _ = inputs()
    rows = [r for r in rows if r["itemId"] != "m2"]
    _, (_, _, records, report) = dataset(tmp_path, spec, rows)
    assert report["missingBarCount"] == 1
    assert len([r for r in records if r.kind == "BAR"]) == 4


def test_costs_partial_fill_cash_and_unliquidated_equity_are_exact(tmp_path):
    report = run(tmp_path)
    buy, sell = report["fills"]
    assert buy["quantity"] == 5
    assert buy["at"] == "2026-11-02T00:02:00+00:00"
    assert buy["estimatedPrice"] == "103"
    assert sell["quantity"] == 2 and sell["estimatedPrice"] == "105"
    assert report["totalFees"] == "2" and report["totalSellTax"] == "1"
    assert report["finalCash"] == "9692"
    assert report["holdings"][0]["quantity"] == 3
    assert report["netPnl"] == "13"
    assert report["status"] == "BAR_ESTIMATE_ONLY"
    assert report["outcomes"][0]["status"] == "PARTIAL_CANCELLED"


def test_repeat_run_produces_same_report_id_and_order_independent_intents(tmp_path):
    _, loaded = dataset(tmp_path)
    config = inputs()[2]
    first = replay(*loaded, ReplayConfig.model_validate(config))
    second = replay(*load_bundle(tmp_path / "bundle"), ReplayConfig.model_validate(config))
    assert canonical(first) == canonical(second)
    assert first["reportId"] == digest(canonical({k: v for k, v in first.items() if k != "reportId"}))
    config["intents"].reverse()
    reverse = replay(*loaded, ReplayConfig.model_validate(config))
    assert reverse["fills"] == first["fills"]


@pytest.mark.parametrize("change,code", [
    ({"allowSynthetic": False}, "SYNTHETIC_OPT_IN_REQUIRED"),
    ({"barSourceId": "missing"}, "REPLAY_SOURCE_MISSING"),
])
def test_replay_requires_explicit_source_and_synthetic_opt_in(tmp_path, change, code):
    with pytest.raises(ResearchError, match=code):
        run(tmp_path, change)


def test_publication_assumption_requires_separate_opt_in(tmp_path):
    spec, rows, _ = inputs()
    spec["sources"][0]["availability"] = "PUBLICATION_ASSUMED"
    with pytest.raises(ResearchError, match="ASSUMED_AVAILABILITY_OPT_IN_REQUIRED"):
        run(tmp_path, spec=spec, rows=rows)


@pytest.mark.parametrize("evidence", [["demo/BAR/m2/1"], ["demo/BAR/m1/2"]])
def test_future_or_nonexistent_evidence_is_rejected(tmp_path, evidence):
    config = inputs()[2]
    config["intents"][0]["evidence"] = evidence
    with pytest.raises(ResearchError, match="EVIDENCE_NOT_VISIBLE_AT_DECISION"):
        run(tmp_path, config)


def test_revised_evidence_cannot_use_superseded_version(tmp_path):
    spec, rows, config = inputs()
    changed = copy.deepcopy(rows[1])
    changed.update(revision=2, publishedAt="2026-11-02T00:01:01Z", observedAt="2026-11-02T00:01:01Z")
    changed["payload"]["close"] = "100"
    rows.append(changed)
    with pytest.raises(ResearchError, match="EVIDENCE_NOT_VISIBLE_AT_DECISION"):
        run(tmp_path, config, spec, rows)


def test_assumed_publication_cannot_backdate_a_correction(tmp_path):
    spec, rows, _ = inputs()
    spec["sources"][0]["availability"] = "PUBLICATION_ASSUMED"
    rows += [news(), news(2, "late correction", "2026-11-02T00:04:00Z")]
    _, (_, spec, records, _) = dataset(tmp_path, spec, rows)
    visible = snapshot(records, spec, utc("2026-11-02T00:03:00Z"))
    assert [r.payload.title for r in visible if r.kind == "NEWS"] == ["original"]


def test_same_instant_revisions_use_revision_order(tmp_path):
    spec, rows, _ = inputs()
    rows += [news(), news(2, "same timestamp correction", "2026-11-02T00:02:00Z")]
    _, (_, spec, records, _) = dataset(tmp_path, spec, rows)
    assert [r.revision for r in snapshot(records, spec, utc("2026-11-02T00:02:00Z")) if r.kind == "NEWS"] == [2]


def test_observation_delay_cannot_be_replaced_by_early_publication(tmp_path):
    spec, rows, config = inputs()
    rows[1]["observedAt"] = "2026-11-02T00:02:00Z"
    with pytest.raises(ResearchError, match="EVIDENCE_NOT_VISIBLE_AT_DECISION"):
        run(tmp_path, config, spec, rows)


def test_same_bar_execution_is_never_allowed_and_latency_can_expire_intent(tmp_path):
    config = inputs()[2]
    config["intents"] = [config["intents"][0]]
    config["intents"][0]["decisionAt"] = "2026-11-02T00:02:00Z"
    report = run(tmp_path, config)
    assert report["fills"] == [] and report["outcomes"][0]["status"] == "NO_NEXT_BAR"


def test_stale_price_or_halt_never_fills(tmp_path):
    spec, rows, config = inputs()
    rows[3]["payload"]["status"] = "HALTED"
    config["intents"] = [config["intents"][0]]
    report = run(tmp_path, config, spec, rows)
    assert report["fills"] == [] and report["outcomes"][0]["status"] == "HALTED"


def test_missing_expected_first_execution_bar_does_not_choose_later_price(tmp_path):
    spec, rows, config = inputs()
    rows = [r for r in rows if r["itemId"] != "m3"]
    config["intents"] = [config["intents"][0]]
    config["intents"][0]["expiresAt"] = "2026-11-02T00:04:00Z"
    report = run(tmp_path, config, spec, rows)
    assert report["fills"] == []
    assert report["outcomes"][0]["status"] == "MISSING_EXECUTION_BAR"


def test_first_execution_record_arriving_after_horizon_does_not_choose_later_bar(tmp_path):
    spec, rows, config = inputs()
    rows[3]["observedAt"] = "2026-11-02T01:00:00Z"
    config["intents"] = [config["intents"][0]]
    report = run(tmp_path, config, spec, rows)
    assert report["fills"] == []
    assert report["outcomes"][0]["status"] == "EXECUTION_BAR_UNAVAILABLE"


def test_stale_signal_is_rejected_even_if_bar_is_tradable(tmp_path):
    config = inputs()[2]
    config.update(maxSignalAgeSeconds=1, intents=[config["intents"][0]])
    report = run(tmp_path, config)
    assert report["fills"] == [] and report["outcomes"][0]["status"] == "STALE_SIGNAL"


def test_aggregate_volume_cap_across_two_intents_and_no_overspending(tmp_path):
    config = inputs()[2]
    buy = config["intents"][0]
    other = {**buy, "intentId": "buy-second"}
    config["intents"] = [buy, other]
    report = run(tmp_path, config)
    assert sum(f["quantity"] for f in report["fills"]) == 5
    assert any(o["status"] == "NO_LIQUIDITY" for o in report["outcomes"])
    assert Decimal(report["finalCash"]) >= 0


def test_tiny_cash_includes_rounded_fee_and_prevents_short_sale(tmp_path):
    config = inputs()[2]
    config["initialCash"] = "103"
    report = run(tmp_path, config)
    assert report["fills"] == []
    assert report["finalCash"] == "103"
    assert report["holdings"] == []


def test_rounded_sell_costs_cannot_create_negative_cash(tmp_path):
    spec, rows, config = inputs()
    for row in rows:
        if row["kind"] == "BAR":
            row["payload"].update(open="1", high="1", low="1", close="1")
    config.update(initialCash="2", feeBps="1000", sellTaxBps="1000", halfSpreadBps="0", slippageBps="0")
    for intent in config["intents"]:
        intent["quantity"] = 1
    report = run(tmp_path, config, spec, rows)
    assert len(report["fills"]) == 1 and report["fills"][0]["side"] == "BUY"
    assert report["finalCash"] == "0" and report["holdings"][0]["quantity"] == 1


def test_order_notional_cap_limits_quantity(tmp_path):
    config = inputs()[2]
    config.update(maxOrderNotional="206", intents=[config["intents"][0]])
    report = run(tmp_path, config)
    assert report["fills"][0]["quantity"] == 2
    assert report["fills"][0]["notional"] == "206"


def test_stale_final_mark_returns_unknown_equity_instead_of_zero_price(tmp_path):
    report = run(tmp_path, {"endAt": "2026-11-02T01:00:00Z"})
    assert report["finalEquity"] is None and report["netPnl"] is None
    assert report["holdings"][0]["value"] is None


def test_missing_historical_membership_rejects_decision(tmp_path):
    spec, rows, _ = inputs()
    rows[0]["observedAt"] = "2026-11-02T00:02:00Z"
    with pytest.raises(ResearchError, match="DECISION_OUTSIDE_KNOWN_UNIVERSE"):
        run(tmp_path, spec=spec, rows=rows)


def test_ambiguous_historical_membership_is_not_silently_selected(tmp_path):
    spec, rows, _ = inputs()
    other = copy.deepcopy(rows[0])
    other["itemId"] = "same-effective-other-membership"
    other["payload"]["eligible"] = False
    rows.append(other)
    with pytest.raises(ResearchError, match="AMBIGUOUS_MEMBERSHIP"):
        run(tmp_path, spec=spec, rows=rows)


def test_temporal_windows_purge_overlapping_labels_and_keep_timestamp_groups():
    config = read_json((EXAMPLES / "split.json").read_bytes())
    extra = copy.deepcopy(config["samples"][2])
    extra["sampleId"] = "same-time-other-stock"
    config["samples"].append(extra)
    result = temporal_split(SplitRequest.model_validate(config))
    assert result["train"] == ["train-example"]
    assert result["validation"] == ["same-time-other-stock", "validation-example"]
    assert result["test"] == ["test-example"]
    assert result["excluded"] == [{"sampleId": "purged-example", "reason": "LABEL_OVERLAP_OR_EMBARGO"}]


def test_empty_split_or_duplicate_sample_is_rejected():
    config = read_json((EXAMPLES / "split.json").read_bytes())
    config["samples"] = config["samples"][:2]
    with pytest.raises(ResearchError, match="EMPTY_TIME_SPLIT"):
        temporal_split(SplitRequest.model_validate(config))
    config["samples"].append(config["samples"][0])
    with pytest.raises(ValidationError):
        SplitRequest.model_validate(config)


def test_cli_end_to_end_build_inspect_snapshot_replay_split_and_exclusive_output(tmp_path, capsys):
    target = tmp_path / "bundle"
    assert main(["build", "--spec", str(EXAMPLES / "spec.json"), "--input", str(EXAMPLES / "records.jsonl"), "--output", str(target)]) == 0
    assert main(["inspect", "--dataset", str(target)]) == 0
    assert main(["snapshot", "--dataset", str(target), "--at", "2026-11-02T00:01:01Z", "--output", str(tmp_path / "snapshot.json")]) == 0
    assert len(read_json((tmp_path / "snapshot.json").read_bytes())["records"]) == 2
    args = ["replay", "--dataset", str(target), "--config", str(EXAMPLES / "config.json"), "--output", str(tmp_path / "replay.json")]
    assert main(args) == 0
    original = (tmp_path / "replay.json").read_bytes()
    assert main(args) == 2
    assert (tmp_path / "replay.json").read_bytes() == original
    assert main(["split", "--config", str(EXAMPLES / "split.json"), "--output", str(tmp_path / "split.json")]) == 0
    assert "FILE_OPERATION_FAILED" in capsys.readouterr().err


def test_cli_never_echoes_sensitive_invalid_input(tmp_path, capsys):
    path = tmp_path / "bad.json"
    path.write_text('{"secret":"do-not-print-me"}', encoding="utf-8")
    assert main(["split", "--config", str(path), "--output", str(tmp_path / "output")]) == 2
    captured = capsys.readouterr()
    assert "INPUT_SCHEMA_INVALID" in captured.err
    assert "do-not-print-me" not in captured.err + captured.out


def test_duplicate_json_keys_and_nan_are_not_silently_accepted():
    for raw in [b'{"a":1,"a":2}', b'{"a":NaN}']:
        with pytest.raises(ResearchError):
            read_json(raw)


def test_real_cli_output_is_utf8_and_readable_on_windows(tmp_path):
    target, _ = dataset(tmp_path)
    completed = subprocess.run([sys.executable, "-m", "app.replay", "inspect", "--dataset", str(target)],
                               cwd=EXAMPLES.parents[1], capture_output=True, check=True)
    value = json.loads(completed.stdout.decode("utf-8"))
    assert "가상 종목" in value["quality"]["limitations"][0]
