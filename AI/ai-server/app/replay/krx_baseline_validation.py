"""Versioned classification review and same-provider cross-endpoint baseline checks."""
import argparse
import copy
import json
from pathlib import Path
import re

from . import krx_universe
from .dataset import canonical, digest, read_bytes, read_json
from .history import atomic_json, job_lock, now
from .models import ResearchError, utc

DAILY_ENDPOINTS = {"KOSPI": "stk_bydd_trd", "KOSDAQ": "ksq_bydd_trd"}
DAILY_FIELDS = {"BAS_DD", "ISU_CD", "ISU_NM", "MKT_NM", "SECT_TP_NM", "TDD_CLSPRC", "CMPPREVDD_PRC", "FLUC_RT",
                "TDD_OPNPRC", "TDD_HGPRC", "TDD_LWPRC", "ACC_TRDVOL", "ACC_TRDVAL", "MKTCAP", "LIST_SHRS"}
POLICY = "KRX_COMMON_SHARE_CLASSIFICATION_2"


def reviewed_snapshot(job):
    original = krx_universe.audit(job)
    result = copy.deepcopy(original)
    for row in result["records"]:
        share, security = row["shareType"], row["securityType"]
        if share == "보통주" and security in krx_universe.SECURITIES | {"선박투자회사"}:
            row["classification"] = "COMMON_SHARE"
        elif share in krx_universe.OTHER_SHARES | {"구형우선주", "종류주권"}:
            row["classification"] = "OTHER_SHARE_CLASS"
    result.update(schemaVersion="SAGOPALGO_KRX_UNIVERSE_REVIEW_V2", classificationPolicy=POLICY,
                  parentSnapshotSha256=digest(canonical(original)),
                  commonShareRecords=sum(v["classification"] == "COMMON_SHARE" for v in result["records"]),
                  unreviewedRecords=sum(v["classification"] == "UNREVIEWED_CLASSIFICATION" for v in result["records"]),
                  recordsSha256=digest(canonical(result["records"])))
    result["classificationChanges"] = [{"symbol": new["symbol"], "market": new["market"], "before": old["classification"],
                                        "after": new["classification"], "shareType": new["shareType"], "securityType": new["securityType"]}
                                       for old, new in zip(original["records"], result["records"]) if old["classification"] != new["classification"]]
    return result


def immutable_json(path, value, require_existing=False):
    if path.exists() or require_existing:
        if read_bytes(path) != canonical(value):
            raise ResearchError("KRX_BASELINE_DERIVED_TAMPERED")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(path, value)


def parse_daily(raw, market, basis_date, captured_at):
    if market not in DAILY_ENDPOINTS or len(raw) > krx_universe.LIMIT:
        raise ResearchError("KRX_DAILY_INPUT_INVALID")
    utc(captured_at)
    value = read_json(raw)
    if (not isinstance(value, dict) or set(value) != {"OutBlock_1"} or not isinstance(value["OutBlock_1"], list)
            or not 1 <= len(value["OutBlock_1"]) <= 20000):
        raise ResearchError("KRX_DAILY_SCHEMA_INVALID")
    result = []
    for row in value["OutBlock_1"]:
        if (not isinstance(row, dict) or set(row) != DAILY_FIELDS or any(not isinstance(v, str) or len(v) > 2000 for v in row.values())
                or row["BAS_DD"] != basis_date.replace("-", "") or not re.fullmatch(r"[A-Z0-9]{6}", row["ISU_CD"])
                or not row["ISU_NM"].strip()
                or row["MKT_NM"] not in ({"KOSPI"} if market == "KOSPI" else {"KOSDAQ", "KOSDAQ GLOBAL"})
                or not re.fullmatch(r"[0-9]{1,20}", row["ACC_TRDVOL"])
                or not re.fullmatch(r"[0-9]{1,20}", row["LIST_SHRS"])):
            raise ResearchError("KRX_DAILY_ROW_INVALID")
        result.append({"symbol": row["ISU_CD"], "market": market, "reportedMarket": row["MKT_NM"], "basisDate": basis_date,
                       "volume": row["ACC_TRDVOL"], "listedShares": row["LIST_SHRS"], "knownAt": captured_at,
                       "sourceRowSha256": digest(canonical(row))})
    if len({v["symbol"] for v in result}) != len(result):
        raise ResearchError("KRX_DAILY_DUPLICATE")
    return sorted(result, key=lambda v: v["symbol"])


class DailyTransport(krx_universe.Transport):
    endpoints = DAILY_ENDPOINTS


def expected_plan(snapshot):
    if snapshot["missingMarkets"] or snapshot["status"] != "CAPTURED":
        raise ResearchError("KRX_BASELINE_NOT_CAPTURED")
    return {"schemaVersion": "SAGOPALGO_KRX_DAILY_CHECK_PLAN_V1", "parentPlanId": snapshot["planId"],
            "parentSnapshotSha256": digest(canonical(snapshot)), "basisDate": snapshot["basisDate"],
            "sourceKind": snapshot["sourceKind"], "maxRequests": 2, "endpoints": DAILY_ENDPOINTS}


def audit_receipt(folder, market, plan):
    receipt = read_json(read_bytes(folder / "receipt.json")) if (folder / "receipt.json").is_file() else {}
    if not isinstance(receipt, dict) or receipt.get("state") != "CAPTURED_RAW":
        raise ResearchError("KRX_DAILY_EXPLICIT_RECOVERY_REQUIRED")
    if (set(receipt) != {"market", "basisDate", "parentPlanId", "state", "startedAt", "capturedAt", "sha256"}
            or receipt["market"] != market or receipt["basisDate"] != plan["basisDate"] or receipt["parentPlanId"] != plan["parentPlanId"]
            or utc(receipt["capturedAt"]) < utc(receipt["startedAt"])):
        raise ResearchError("KRX_DAILY_RECEIPT_INVALID")
    raw = read_bytes(folder / "body.json")
    if len(raw) > krx_universe.LIMIT or digest(raw) != receipt["sha256"]:
        raise ResearchError("KRX_DAILY_RAW_TAMPERED")
    return receipt, raw


def capture_daily(snapshot, output, transport):
    plan = expected_plan(snapshot)
    output.mkdir(parents=True, exist_ok=True)
    with job_lock(output):
        immutable_json(output / "plan.json", plan)
        # All existing reservations must be valid before any new network request.
        for market in DAILY_ENDPOINTS:
            if (output / market).exists():
                audit_receipt(output / market, market, plan)
        missing = [m for m in DAILY_ENDPOINTS if not (output / m).exists()]
        if missing:
            if transport.source_kind != plan["sourceKind"]:
                raise ResearchError("KRX_SOURCE_KIND_MISMATCH")
            transport.ready()
        for market in missing:
            folder = output / market
            folder.mkdir()
            receipt = {"market": market, "basisDate": plan["basisDate"], "parentPlanId": plan["parentPlanId"],
                       "state": "RESERVED", "startedAt": now()}
            atomic_json(folder / "receipt.json", receipt)
            try:
                raw = transport.fetch(market, plan["basisDate"])
                (folder / "body.json").write_bytes(raw)
                receipt.update(state="CAPTURED_RAW", capturedAt=now(), sha256=digest(raw))
                atomic_json(folder / "receipt.json", receipt)
            except Exception as exc:
                code = str(exc) if isinstance(exc, ResearchError) else "KRX_DAILY_CAPTURE_FAILED"
                receipt.update(state="FAILED", diagnostic=code, finishedAt=now())
                atomic_json(folder / "receipt.json", receipt)
                raise ResearchError(code) from None
    return {"capturedSources": len(missing), "reusedSources": 2 - len(missing), "maxRequests": 2}


def daily_report(snapshot, folder):
    plan = expected_plan(snapshot)
    immutable_json(folder / "plan.json", plan, True)
    records, sources = [], []
    for market in DAILY_ENDPOINTS:
        receipt, raw = audit_receipt(folder / market, market, plan)
        records.extend(parse_daily(raw, market, plan["basisDate"], receipt["capturedAt"]))
        sources.append({"market": market, "sha256": receipt["sha256"], "knownAt": receipt["capturedAt"]})
    if len({v["symbol"] for v in records}) != len(records):
        raise ResearchError("KRX_DAILY_CROSS_MARKET_DUPLICATE")
    return {"schemaVersion": "SAGOPALGO_KRX_DAILY_CHECK_REPORT_V1", "plan": plan, "sources": sources, "records": records,
            "rowCounts": {m: sum(v["market"] == m for v in records) for m in DAILY_ENDPOINTS}}


def reconcile_daily(job, reviewed, daily):
    original = krx_universe.audit(job)
    if reviewed != reviewed_snapshot(job) or daily["plan"] != expected_plan(original):
        raise ResearchError("KRX_BASELINE_PARENT_MISMATCH")
    basic = {(v["market"], v["symbol"]): v for v in reviewed["records"]}
    prices = {(v["market"], v["symbol"]): v for v in daily["records"]}
    missing_daily, daily_only = sorted(set(basic) - set(prices)), sorted(set(prices) - set(basic))
    raw_shares = {}
    for market in DAILY_ENDPOINTS:
        data = read_json(read_bytes(job / "raw" / (market + ".json")))
        for row in data["OutBlock_1"]:
            value = row["LIST_SHRS"]
            if not re.fullmatch(r"[0-9]{1,20}", value):
                raise ResearchError("KRX_BASIC_SHARE_COUNT_INVALID")
            raw_shares[(market, row["ISU_SRT_CD"])] = value
    share_mismatches = sorted(key for key in set(basic) & set(prices) if int(raw_shares[key]) != int(prices[key]["listedShares"]))
    common = {key for key, value in basic.items() if value["classification"] == "COMMON_SHARE"}
    zero_volume = sorted(key for key in common & set(prices) if int(prices[key]["volume"]) == 0)
    matched = not missing_daily and not daily_only and not share_mismatches
    live = original["sourceKind"] == "PROVIDER_HISTORICAL"
    return {"schemaVersion": "SAGOPALGO_KRX_BASELINE_RECONCILIATION_V1", "basisDate": original["basisDate"],
            "parentSnapshotSha256": digest(canonical(original)), "reviewedSnapshotSha256": digest(canonical(reviewed)),
            "dailyReportSha256": digest(canonical(daily)), "sourceKind": original["sourceKind"],
            "status": "TEST_ONLY" if not live else "CROSS_ENDPOINT_MATCH" if matched and not reviewed["unreviewedRecords"] else "GAPS",
            "basicRowCounts": original["countsByMarket"], "dailyRowCounts": daily["rowCounts"],
            "commonShareCounts": {m: sum(key[0] == m for key in common) for m in DAILY_ENDPOINTS},
            "missingDailySymbols": missing_daily, "dailyOnlySymbols": daily_only, "shareCountMismatches": share_mismatches,
            "zeroVolumeCommonSymbolsPreserved": zero_volume, "unreviewedRecords": reviewed["unreviewedRecords"],
            "crossEndpointTotalsVerified": live and matched, "sameProviderCrossCheck": True,
            "independentTotalVerified": False, "tradingHaltCoverageVerified": False,
            "marketUniverseComplete": False, "usableForTraining": False, "usableForTrading": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ["review", "audit-review", "capture-daily", "reconcile"]:
        p = sub.add_parser(command)
        p.add_argument("--job", type=Path, required=True)
        p.add_argument("--output", type=Path, required=True)
        if command == "capture-daily":
            p.add_argument("--env-file", type=Path)
        if command == "reconcile":
            p.add_argument("--reviewed", type=Path, required=True)
            p.add_argument("--daily", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "capture-daily":
            key, enabled = krx_universe.load_environment(args.env_file)
            result = capture_daily(krx_universe.audit(args.job), args.output, DailyTransport(key, enabled))
        elif args.command == "reconcile":
            reviewed = reviewed_snapshot(args.job)
            immutable_json(args.reviewed, reviewed, True)
            daily = daily_report(krx_universe.audit(args.job), args.daily)
            result = reconcile_daily(args.job, reviewed, daily)
            immutable_json(args.output, result)
        else:
            result = reviewed_snapshot(args.job)
            immutable_json(args.output, result, args.command == "audit-review")
            result = {key: value for key, value in result.items() if key not in {"records", "classificationChanges"}}
        print(json.dumps(result, ensure_ascii=True, sort_keys=True))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"diagnostic": str(exc) if isinstance(exc, ResearchError) else "KRX_BASELINE_INPUT_INVALID"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
