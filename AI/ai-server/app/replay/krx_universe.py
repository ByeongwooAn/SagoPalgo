"""Bounded KRX historical issue snapshots. Sample data cannot establish a live baseline."""
import argparse
from datetime import date
import json
import os
from pathlib import Path
import re
from typing import Literal
from urllib import error, request

from pydantic import Field, model_validator

from .dataset import canonical, digest, read_bytes, read_json
from .history import NoRedirect, atomic_json, day, job_lock, now
from .models import ResearchError, StrictModel, utc

BASE = "https://data-dbg.krx.co.kr/svc/apis/sto/"
ENDPOINTS = {"KOSPI": "stk_isu_base_info", "KOSDAQ": "ksq_isu_base_info"}
FIELDS = {"ISU_CD", "ISU_SRT_CD", "ISU_NM", "ISU_ABBRV", "ISU_ENG_NM", "LIST_DD", "MKT_TP_NM",
          "SECUGRP_NM", "SECT_TP_NM", "KIND_STKCERT_TP_NM", "PARVAL", "LIST_SHRS"}
SECURITIES = {"주권", "외국주권", "주식예탁증권", "부동산투자회사", "사회간접자본투융자회사", "투자회사"}
OTHER_SHARES = {"우선주", "신형우선주", "종류주식"}
LIMIT = 8 * 1024 * 1024


class Config(StrictModel):
    schemaVersion: Literal["SAGOPALGO_KRX_UNIVERSE_PLAN_V1"]
    basisDate: str
    sourceKind: Literal["PROVIDER_HISTORICAL", "SYNTHETIC"] = "PROVIDER_HISTORICAL"
    maxRequests: Literal[2] = 2

    @model_validator(mode="after")
    def bounds(self):
        if not day(self.basisDate) >= date(2010, 1, 4):
            raise ValueError("KRX documented historical window begins 2010-01-04")
        return self


def parse_snapshot(raw, market, basis_date, captured_at, source_kind):
    if market not in ENDPOINTS or source_kind not in {"PROVIDER_HISTORICAL", "SYNTHETIC", "OFFICIAL_SAMPLE"} or len(raw) > LIMIT:
        raise ResearchError("KRX_SNAPSHOT_INPUT_INVALID")
    day(basis_date)
    utc(captured_at)
    value = read_json(raw)
    if not isinstance(value, dict) or set(value) != {"OutBlock_1"} or not isinstance(value["OutBlock_1"], list):
        raise ResearchError("KRX_RESPONSE_SCHEMA_INVALID")
    rows = value["OutBlock_1"]
    if not 1 <= len(rows) <= 20000:
        raise ResearchError("KRX_RESPONSE_COUNT_INVALID")
    result = []
    for row in rows:
        if (not isinstance(row, dict) or set(row) != FIELDS or any(not isinstance(v, str) or len(v) > 2000 for v in row.values())
                or not re.fullmatch(r"[A-Z0-9]{12}", row["ISU_CD"]) or not re.fullmatch(r"[A-Z0-9]{6}", row["ISU_SRT_CD"])
                or not row["ISU_NM"].strip() or row["MKT_TP_NM"] != market):
            raise ResearchError("KRX_ISSUE_IDENTITY_INVALID")
        listed = row["LIST_DD"]
        if not re.fullmatch(r"[0-9]{8}", listed):
            raise ResearchError("KRX_LISTING_DATE_INVALID")
        listed = date.fromisoformat(listed[:4] + "-" + listed[4:6] + "-" + listed[6:])
        if not 1900 <= listed.year <= 2100 or listed > day(basis_date):
            raise ResearchError("KRX_FUTURE_LISTING_IN_HISTORICAL_RESPONSE")
        share, security = row["KIND_STKCERT_TP_NM"], row["SECUGRP_NM"]
        if share == "보통주" and security in SECURITIES:
            classification = "COMMON_SHARE"
        elif share in OTHER_SHARES:
            classification = "OTHER_SHARE_CLASS"
        else:
            classification = "UNREVIEWED_CLASSIFICATION"
        result.append({"symbol": row["ISU_SRT_CD"], "isin": row["ISU_CD"], "name": row["ISU_NM"], "market": market,
                       "reportedListingDate": listed.isoformat(), "securityType": security, "shareType": share,
                       "classification": classification, "basisDate": basis_date, "dateBasis": "REQUEST_BAS_DD",
                       "knownAt": captured_at, "knowledgeBasis": "FETCH_TIME_ONLY", "sourceKind": source_kind,
                       "sourceRowSha256": digest(canonical(row)), "numericCodeSupported": bool(re.fullmatch(r"[0-9]{6}", row["ISU_SRT_CD"]))})
    if any(len({v[key] for v in result}) != len(result) for key in ["symbol", "isin"]):
        raise ResearchError("KRX_DUPLICATE_ISSUE")
    return sorted(result, key=lambda v: v["symbol"])


def prepare(output, basis_date="2023-11-01", source_kind="PROVIDER_HISTORICAL"):
    config = Config.model_validate({"schemaVersion": "SAGOPALGO_KRX_UNIVERSE_PLAN_V1", "basisDate": basis_date, "sourceKind": source_kind})
    value = config.model_dump(mode="json")
    plan = {"config": value, "planId": digest(canonical(value)), "markets": list(ENDPOINTS), "autoRetry": False}
    output.mkdir(parents=True, exist_ok=False)
    (output / "raw").mkdir()
    atomic_json(output / "plan.json", plan)
    atomic_json(output / "journal.json", {"planId": plan["planId"], "attempts": []})
    return plan


def load_job(folder):
    plan = read_json(read_bytes(folder / "plan.json"))
    config = Config.model_validate(plan["config"])
    if plan != {"config": config.model_dump(mode="json"), "planId": digest(canonical(config.model_dump(mode="json"))),
                "markets": list(ENDPOINTS), "autoRetry": False}:
        raise ResearchError("KRX_PLAN_TAMPERED")
    journal = read_json(read_bytes(folder / "journal.json"))
    if not isinstance(journal, dict) or set(journal) != {"planId", "attempts"} or journal["planId"] != plan["planId"]:
        raise ResearchError("KRX_JOURNAL_INVALID")
    attempts = journal["attempts"]
    if not isinstance(attempts, list) or len(attempts) > 2:
        raise ResearchError("KRX_JOURNAL_INVALID")
    records = []
    for index, attempt in enumerate(attempts):
        if (not isinstance(attempt, dict) or attempt.get("market") != list(ENDPOINTS)[index]
                or attempt.get("basisDate") != config.basisDate or attempt.get("state") not in {"RESERVED", "CAPTURED", "FAILED"}):
            raise ResearchError("KRX_JOURNAL_INVALID")
        utc(attempt["startedAt"])
        base_fields = {"market", "basisDate", "state", "startedAt"}
        received = {"sha256", "capturedAt"}
        expected = base_fields | received if attempt["state"] == "CAPTURED" else base_fields
        if attempt["state"] == "FAILED":
            expected |= {"diagnostic", "finishedAt"}
            if "sha256" in attempt or "capturedAt" in attempt:
                expected |= received
            if utc(attempt["finishedAt"]) < utc(attempt["startedAt"]):
                raise ResearchError("KRX_JOURNAL_INVALID")
        if set(attempt) != expected:
            raise ResearchError("KRX_JOURNAL_INVALID")
        if "sha256" in attempt:
            raw = read_bytes(folder / "raw" / (attempt["market"] + ".json"))
            if digest(raw) != attempt["sha256"] or utc(attempt["capturedAt"]) < utc(attempt["startedAt"]):
                raise ResearchError("KRX_RAW_TAMPERED")
        if attempt["state"] == "CAPTURED":
            records.extend(parse_snapshot(raw, attempt["market"], config.basisDate, attempt["capturedAt"], config.sourceKind))
        elif index != len(attempts) - 1:
            raise ResearchError("KRX_JOURNAL_INVALID")
    if any(len({v[key] for v in records}) != len(records) for key in ["symbol", "isin"]):
        raise ResearchError("KRX_CROSS_MARKET_DUPLICATE")
    return plan, config, journal, records


def report(folder):
    plan, config, journal, records = load_job(folder)
    captured = [v["market"] for v in journal["attempts"] if v["state"] == "CAPTURED"]
    bad = [v for v in journal["attempts"] if v["state"] != "CAPTURED"]
    return {"schemaVersion": "SAGOPALGO_KRX_UNIVERSE_REPORT_V1", "planId": plan["planId"], "basisDate": config.basisDate,
            "sourceKind": config.sourceKind, "status": "STOPPED" if bad else "CAPTURED" if len(captured) == 2 else "PLANNED_OR_PARTIAL",
            "attemptsUsed": len(journal["attempts"]), "maxRequests": 2, "capturedMarkets": captured,
            "missingMarkets": sorted(set(ENDPOINTS) - set(captured)), "sourceRecords": len(records),
            "providerHistoricalRecords": len(records) if config.sourceKind == "PROVIDER_HISTORICAL" else 0,
            "countsByMarket": {m: sum(v["market"] == m for v in records) for m in ENDPOINTS},
            "commonShareRecords": sum(v["classification"] == "COMMON_SHARE" for v in records),
            "unreviewedRecords": sum(v["classification"] == "UNREVIEWED_CLASSIFICATION" for v in records),
            "records": records, "recordsSha256": digest(canonical(records)), "independentTotalVerified": False,
            "marketUniverseComplete": False, "usableForTraining": False, "usableForTrading": False}


class Transport:
    source_kind = "PROVIDER_HISTORICAL"
    endpoints = ENDPOINTS

    def __init__(self, key, enabled, opener=None):
        self.key, self.enabled = key, enabled
        self.opener = opener

    def ready(self):
        if not self.enabled:
            raise ResearchError("KRX_COLLECTION_DISABLED")
        if not self.key:
            raise ResearchError("KRX_AUTH_KEY_MISSING")
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,256}", self.key):
            raise ResearchError("KRX_AUTH_KEY_INVALID")

    def fetch(self, market, basis_date):
        self.ready()
        if market not in self.endpoints:
            raise ResearchError("KRX_MARKET_INVALID")
        day(basis_date)
        req = request.Request(BASE + self.endpoints[market] + "?basDd=" + basis_date.replace("-", ""),
                              headers={"AUTH_KEY": self.key, "Accept": "application/json"}, method="GET")
        try:
            client = self.opener or request.build_opener(NoRedirect())
            with client.open(req, timeout=20) as response:
                raw = response.read(LIMIT + 1)
        except error.HTTPError as exc:
            raise ResearchError("KRX_ACCESS_DENIED" if exc.code in {401, 403} else "KRX_HTTP_FAILED") from None
        except Exception:
            raise ResearchError("KRX_TRANSPORT_FAILED") from None
        if len(raw) > LIMIT:
            raise ResearchError("KRX_RESPONSE_LIMIT")
        if self.key.encode() in raw:
            raise ResearchError("KRX_RESPONSE_SECRET_REFLECTION")
        return raw


def collect(folder, transport):
    with job_lock(folder):
        plan, config, journal, _ = load_job(folder)
        if (folder / "report.json").exists() and read_bytes(folder / "report.json") != canonical(report(folder)):
            raise ResearchError("KRX_REPORT_TAMPERED")
        if len(journal["attempts"]) == 2 and all(v["state"] == "CAPTURED" for v in journal["attempts"]):
            return report(folder)
        if any(v["state"] != "CAPTURED" for v in journal["attempts"]):
            raise ResearchError("KRX_EXPLICIT_RECOVERY_REQUIRED")
        if transport.source_kind != config.sourceKind:
            raise ResearchError("KRX_SOURCE_KIND_MISMATCH")
        transport.ready()  # No reservation or network when credentials are absent/disabled.
        for market in list(ENDPOINTS)[len(journal["attempts"]):]:
            attempt = {"market": market, "basisDate": config.basisDate, "state": "RESERVED", "startedAt": now()}
            journal["attempts"].append(attempt)
            atomic_json(folder / "journal.json", journal)
            try:
                raw = transport.fetch(market, config.basisDate)
                captured = now()
                (folder / "raw" / (market + ".json")).write_bytes(raw)
                attempt.update(capturedAt=captured, sha256=digest(raw))
                parse_snapshot(raw, market, config.basisDate, captured, config.sourceKind)
                attempt.update(state="CAPTURED")
                atomic_json(folder / "journal.json", journal)
            except Exception as exc:
                code = str(exc) if isinstance(exc, ResearchError) else "KRX_CAPTURE_FAILED"
                attempt.update(state="FAILED", diagnostic=code, finishedAt=now())
                atomic_json(folder / "journal.json", journal)
                raise ResearchError(code) from None
        return report(folder)


def audit(folder):
    with job_lock(folder):
        result = report(folder)
        target = folder / "report.json"
        if target.exists() and read_bytes(target) != canonical(result):
            raise ResearchError("KRX_REPORT_TAMPERED")
        return result


def load_environment(path=None):
    values = {key: os.getenv(key) for key in ["SAGOPALGO_KRX_OPEN_API_ENABLED", "SAGOPALGO_KRX_AUTH_KEY"]}
    if path is not None:
        for line in read_bytes(path).decode("utf-8-sig").splitlines():
            key, separator, value = line.partition("=")
            if separator and key in values and values[key] is None:
                values[key] = value.strip().strip('"').strip("'")
    return values.get("SAGOPALGO_KRX_AUTH_KEY"), values.get("SAGOPALGO_KRX_OPEN_API_ENABLED", "false") == "true"


def compare_evidence(snapshot, cases, events, cache):
    from . import universe_events
    from .kind_cases import document_rows, iso_date

    basis = snapshot["basisDate"]
    if not cases["startDate"] <= basis <= cases["endDate"] or not events["startDate"] <= basis <= events["endDate"]:
        raise ResearchError("KRX_COMPARISON_OUTSIDE_EVIDENCE_SCOPE")
    expectations = []

    def expect(fact, market, expected):
        expectations.append({"caseId": fact["caseId"], "symbol": fact["stockCode"], "market": market,
                             "expected": expected, "evidenceKnownAt": fact["knownAt"],
                             "evidenceBasis": "RETROSPECTIVE_CHECK_NOT_HISTORICAL_KNOWLEDGE"})

    for fact in cases["facts"]:
        if fact["kind"] == "IPO" and basis <= fact["date"]:
            expect(fact, fact["market"], "PRESENT_COMMON_SHARE" if basis == fact["date"] else "ABSENT")
        elif fact["kind"] == "DELISTING":
            if fact["details"]["originalListingDate"] <= basis < fact["date"]:
                expect(fact, fact["market"], "PRESENT_COMMON_SHARE")
            elif basis >= fact["date"]:
                expect(fact, fact["market"], "ABSENT")
    for fact in events["facts"]:
        raw, _ = universe_events.source(cache, fact["sources"][0]["url"])
        case = universe_events.delisting_case(fact["stockCode"], fact["issuerName"], fact["caseId"], fact["sources"][0]["url"])
        rows = document_rows(raw, case)
        original = iso_date(next(row for row in rows if "A" + fact["stockCode"] in row)[-1])
        if original <= basis < fact["date"]:
            expect(fact, fact["fromMarket"], "PRESENT_COMMON_SHARE")
            if fact["kind"] == "MARKET_TRANSFER":
                expect(fact, fact["toMarket"], "ABSENT")
        elif basis >= fact["date"]:
            expect(fact, fact["fromMarket"], "ABSENT")
            if fact["kind"] == "MARKET_TRANSFER" and basis == fact["date"]:
                expect(fact, fact["toMarket"], "PRESENT_COMMON_SHARE")
    observed = {(v["market"], v["symbol"]): v for v in snapshot["records"]}
    for value in expectations:
        row = observed.get((value["market"], value["symbol"]))
        if value["market"] in snapshot["missingMarkets"]:
            value.update(status="PENDING_SOURCE", actual=None)
        else:
            actual = "ABSENT" if row is None else "PRESENT_COMMON_SHARE" if row["classification"] == "COMMON_SHARE" else row["classification"]
            value.update(actual=actual, status="PASS" if actual == value["expected"] else "MISMATCH")
    mismatches = sum(v["status"] == "MISMATCH" for v in expectations)
    pending = sum(v["status"] == "PENDING_SOURCE" for v in expectations)
    status = ("WAITING_PROVIDER_SNAPSHOTS" if snapshot["missingMarkets"] else "CLASSIFICATION_GAPS" if snapshot["unreviewedRecords"]
              else "ANCHOR_MISMATCHES" if mismatches else "NO_ANCHORS" if not expectations else "ANCHORS_PASS_TOTAL_UNCONFIRMED")
    if snapshot["sourceKind"] != "PROVIDER_HISTORICAL":
        status = "TEST_ONLY"
    return {"schemaVersion": "SAGOPALGO_KRX_UNIVERSE_COMPARISON_V1", "planId": snapshot["planId"], "basisDate": basis,
            "snapshotSha256": digest(canonical(snapshot)), "caseReportSha256": digest(canonical(cases)),
            "eventReportSha256": digest(canonical(events)), "status": status, "checks": expectations,
            "pendingChecks": pending, "mismatches": mismatches, "independentTotalVerified": False,
            "tradingHaltCoverageVerified": False, "marketUniverseComplete": False,
            "usableForTraining": False, "usableForTrading": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--date", default="2023-11-01")
    for command in ["status", "collect", "audit"]:
        p = sub.add_parser(command)
        p.add_argument("--job", type=Path, required=True)
        p.add_argument("--env-file", type=Path)
    p = sub.add_parser("check")
    p.add_argument("--job", type=Path, required=True)
    p.add_argument("--reviewed", type=Path)
    for arg in ["case-cache", "case-scope", "case-report", "event-scope", "event-report", "output"]:
        p.add_argument("--" + arg, type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            result = prepare(args.output, args.date)
        elif args.command == "check":
            from . import kind_cases, universe_events
            cases = kind_cases.audit_report(kind_cases.load_scope(args.case_scope), args.case_cache, args.case_report)
            events = universe_events.audit_report(universe_events.load_scope(args.event_scope), args.case_cache, args.event_report)
            snapshot = audit(args.job)
            if args.reviewed:
                from .krx_baseline_validation import immutable_json, reviewed_snapshot
                snapshot = reviewed_snapshot(args.job)
                immutable_json(args.reviewed, snapshot, True)
            result = compare_evidence(snapshot, cases, events, args.case_cache)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            if args.output.exists():
                if read_bytes(args.output) != canonical(result):
                    raise ResearchError("KRX_COMPARISON_TAMPERED")
            else:
                atomic_json(args.output, result)
        elif args.command == "collect":
            key, enabled = load_environment(args.env_file)
            result = collect(args.job, Transport(key, enabled))
            with job_lock(args.job):
                target = args.job / "report.json"
                if target.exists():
                    if read_bytes(target) != canonical(result):
                        raise ResearchError("KRX_REPORT_TAMPERED")
                else:
                    atomic_json(target, result)
        else:
            result = audit(args.job)
            if args.command == "status":
                key, enabled = load_environment(args.env_file)
                live_access = result["sourceKind"] == "PROVIDER_HISTORICAL"
                result.update(collectionEnabled=enabled, keyConfigured=bool(key),
                              serviceApprovalStatus="SUCCESSFUL_REQUESTS_OBSERVED" if live_access and result["capturedMarkets"] else "NOT_VERIFIED",
                              serviceAccessObservedByMarket={m: live_access and m in result["capturedMarkets"] for m in ENDPOINTS})
        result = {key: value for key, value in result.items() if key != "records"}
        print(json.dumps(result, ensure_ascii=True, sort_keys=True))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"diagnostic": str(exc) if isinstance(exc, ResearchError) else "KRX_INPUT_INVALID"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
