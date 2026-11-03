"""Bounded issuer-bound OpenDART disclosure index. No inferred listing/action effects."""
import argparse
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Literal
from urllib import parse, request

from pydantic import Field, ValidationError, model_validator

from .dataset import canonical, digest, read_bytes, read_json
from .history import NoRedirect, atomic_json, audit as history_audit, day, job_lock, now
from .local_use import load_local_use
from .models import ResearchError, StrictModel, utc

BASE = "https://opendart.fss.or.kr/api/"
LIMIT = 2 * 1024 * 1024
PATHS = {"company": "company.json", "list": "list.json", "document": "document.xml"}


class Config(StrictModel):
    schemaVersion: Literal["SAGOPALGO_DART_HISTORY_V1"]
    historyPlanId: str = Field(pattern=r"^[a-f0-9]{64}$")
    dailySha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    stockCode: str = Field(pattern=r"^[0-9]{6}$")
    corpCode: str = Field(pattern=r"^[0-9]{8}$")
    startDate: str
    endDate: str
    maxRequests: int = Field(default=12, ge=3, le=64)
    pageCount: Literal[100] = 100
    minIntervalSeconds: int = Field(default=1, ge=1, le=10)

    @model_validator(mode="after")
    def bounds(self):
        first, last = day(self.startDate), day(self.endDate)
        if first > last or (last - first).days > 3653 or first.year < 2015:
            raise ValueError("supported bounded historical window required")
        return self


def prepare(history_job: Path, local_use: Path, corp_code: str, output: Path, max_requests=12):
    with job_lock(history_job):
        report, rows = history_audit(history_job, check_daily=True)
        raw = read_bytes(history_job / "daily.jsonl")
        load_local_use(local_use, report, raw)
        config = Config.model_validate({"schemaVersion": "SAGOPALGO_DART_HISTORY_V1", "historyPlanId": report["planId"],
            "dailySha256": digest(raw), "stockCode": rows[0]["stockCode"], "corpCode": corp_code,
            "startDate": report["requestStart"], "endDate": report["requestEnd"], "maxRequests": max_requests})
    value = config.model_dump(mode="json")
    plan = {"config": value, "planId": digest(canonical(value)), "queryTypes": ["B", "I"], "lastReportOnly": False}
    output.mkdir(parents=True, exist_ok=False)
    (output / "plan.json").write_bytes(canonical(plan))
    (output / "raw").mkdir()
    atomic_json(output / "journal.json", {"planId": plan["planId"], "status": "PLANNED", "attempts": []})
    return plan


def load_job(folder):
    plan = read_json(read_bytes(folder / "plan.json"))
    config = Config.model_validate(plan["config"])
    if plan != {"config": config.model_dump(mode="json"), "planId": digest(canonical(plan["config"])),
                "queryTypes": ["B", "I"], "lastReportOnly": False}:
        raise ResearchError("DART_PLAN_TAMPERED")
    journal = read_json(read_bytes(folder / "journal.json"))
    if journal.get("planId") != plan["planId"] or not isinstance(journal.get("attempts"), list) or len(journal["attempts"]) > config.maxRequests:
        raise ResearchError("DART_JOURNAL_INVALID")
    for seq, attempt in enumerate(journal["attempts"], 1):
        if attempt.get("seq") != seq or attempt.get("endpoint") not in PATHS or attempt.get("state") not in {"RESERVED", "CAPTURED", "FAILED"}:
            raise ResearchError("DART_JOURNAL_INVALID")
        params = attempt.get("params")
        if not isinstance(params, dict) or "crtfc_key" in params or attempt.get("requestId") != request_id(attempt["endpoint"], params):
            raise ResearchError("DART_JOURNAL_INVALID")
        if attempt["state"] == "CAPTURED":
            body = read_bytes(folder / "raw" / f"{seq:04d}.json")
            if digest(body) != attempt.get("sha256"):
                raise ResearchError("DART_RAW_TAMPERED")
            utc(attempt["capturedAt"])
    return plan, config, journal


def request_id(endpoint, params):
    return digest(canonical({"endpoint": endpoint, "params": params}))


class Transport:
    def __init__(self, key, enabled=False, opener=None):
        if not enabled:
            raise ResearchError("DART_DISABLED")
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9]{40}", key):
            raise ResearchError("DART_CREDENTIALS_MISSING")
        self.key = key
        self.fingerprint = digest(key.encode())
        self.opener = opener or request.build_opener(NoRedirect())

    def fetch(self, endpoint, params):
        if endpoint not in PATHS or "crtfc_key" in params:
            raise ResearchError("DART_REQUEST_INVALID")
        url = BASE + PATHS[endpoint] + "?" + parse.urlencode({**params, "crtfc_key": self.key})
        try:
            with self.opener.open(request.Request(url, method="GET", headers={"Accept": "application/octet-stream" if endpoint == "document" else "application/json"}), timeout=20) as response:
                body = response.read(LIMIT + 1)
        except Exception:
            raise ResearchError("DART_HTTP_FAILED") from None
        if len(body) > LIMIT:
            raise ResearchError("DART_RESPONSE_LIMIT")
        if self.key.encode() in body:
            raise ResearchError("DART_SENSITIVE_RESPONSE")
        return body


def integer(value):
    if isinstance(value, bool) or not isinstance(value, (str, int)) or not re.fullmatch(r"[0-9]{1,8}", str(value)):
        raise ResearchError("DART_PAGINATION_INVALID")
    return int(value)


def categories(title):
    compact = re.sub(r"[\sㆍ·]", "", title)
    groups = {"DIVIDEND_NOTICE": ["배당"], "MERGER_NOTICE": ["합병"], "CORPORATE_DIVISION_NOTICE": ["회사분할", "분할합병"],
              "SHARE_SPLIT_OR_CONSOLIDATION_NOTICE": ["주식분할", "주식병합"], "DELISTING_NOTICE": ["상장폐지"],
              "LISTING_NOTICE": ["신규상장", "재상장", "이전상장", "변경상장"], "SUSPENSION_NOTICE": ["거래정지"],
              "CAPITAL_CHANGE_NOTICE": ["유상증자", "무상증자", "감자"],
              "TREASURY_OR_CANCELLATION_NOTICE": ["자기주식", "주식소각", "이익소각"]}
    return [name for name, tokens in groups.items() if any(token in compact for token in tokens)]


def instrument_scope(title):
    compact = re.sub(r"\s", "", title)
    if "해외증권시장" in compact:
        return "OVERSEAS_SECURITIES"
    if "종속회사" in compact or "자회사" in compact:
        return "SUBSIDIARY"
    return "UNVERIFIED"


def catalog(config, fetch):
    company_raw, company_at = fetch("company", {"corp_code": config.corpCode})
    company = read_json(company_raw)
    if not isinstance(company, dict) or company.get("status") != "000":
        raise ResearchError("DART_COMPANY_REJECTED")
    if company.get("stock_code") != config.stockCode or company.get("corp_cls") not in {"Y", "K", "N"}:
        raise ResearchError("DART_ISSUER_MISMATCH")
    records, scopes = {}, {}
    for kind in ["B", "I"]:
        page, totals, seen = 1, None, set()
        while True:
            params = {"corp_code": config.corpCode, "bgn_de": config.startDate.replace("-", ""), "end_de": config.endDate.replace("-", ""),
                      "last_reprt_at": "N", "pblntf_ty": kind, "sort": "date", "sort_mth": "asc", "page_no": str(page), "page_count": str(config.pageCount)}
            raw, captured_at = fetch("list", params)
            data = read_json(raw)
            if not isinstance(data, dict):
                raise ResearchError("DART_RESPONSE_INVALID")
            if data.get("status") == "013" and page == 1:
                if data.get("list") not in (None, []):
                    raise ResearchError("DART_EMPTY_CONFLICT")
                scopes[kind] = {"records": 0, "pages": 1, "providerStatus": "013"}
                break
            if data.get("status") != "000":
                raise ResearchError("DART_PROVIDER_REJECTED")
            count, pages = integer(data.get("total_count")), integer(data.get("total_page"))
            if (integer(data.get("page_no")) != page or integer(data.get("page_count")) != config.pageCount
                    or pages != max(1, (count + config.pageCount - 1) // config.pageCount) or (totals is not None and totals != (count, pages))):
                raise ResearchError("DART_PAGE_DRIFT")
            totals = count, pages
            rows = data.get("list")
            if not isinstance(rows, list) or len(rows) != min(config.pageCount, count - (page - 1) * config.pageCount):
                raise ResearchError("DART_PAGE_LENGTH_INVALID")
            for row in rows:
                if not isinstance(row, dict) or row.get("corp_code") != config.corpCode or row.get("stock_code") not in {"", config.stockCode}:
                    raise ResearchError("DART_ROW_ISSUER_MISMATCH")
                receipt, stamp, title, remarks = [row.get(name) for name in ["rcept_no", "rcept_dt", "report_nm", "rm"]]
                if not isinstance(receipt, str) or not re.fullmatch(r"[0-9]{14}", receipt) or not isinstance(stamp, str) or not re.fullmatch(r"[0-9]{8}", stamp):
                    raise ResearchError("DART_RECEIPT_INVALID")
                date = stamp[:4] + "-" + stamp[4:6] + "-" + stamp[6:]
                day(date)
                if not config.startDate <= date <= config.endDate or not isinstance(title, str) or not title or not isinstance(remarks, str):
                    raise ResearchError("DART_ROW_INVALID")
                if receipt in seen:
                    raise ResearchError("DART_DUPLICATE_RECEIPT")
                seen.add(receipt)
                if receipt in records:
                    if records[receipt]["providerRowSha256"] != digest(canonical(row)):
                        raise ResearchError("DART_RECEIPT_CONFLICT")
                    records[receipt]["queryTypes"].append(kind)
                    continue
                records[receipt] = {"receiptNumber": receipt, "receiptDate": date, "datePrecision": "DATE", "publishedAt": None,
                    "observedAt": captured_at, "knownAt": captured_at, "availability": "OBSERVED_AT", "stockCode": config.stockCode,
                    "corpCode": config.corpCode, "reportedCorpClass": row.get("corp_cls"), "reportName": title, "remarks": remarks,
                    "queryTypes": [kind], "categories": categories(title), "correctionIndicated": "정정" in title or "정" in remarks,
                    "instrumentScope": instrument_scope(title),
                    "withdrawalIndicated": "철회" in title or "철" in remarks, "parentReceiptNumber": None,
                    "reviewState": "ORIGINAL_DOCUMENT_REQUIRED", "effectiveDate": None,
                    "providerRowSha256": digest(canonical(row)), "link": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + receipt}
            if page == pages:
                scopes[kind] = {"records": count, "pages": pages, "providerStatus": "000"}
                break
            page += 1
    ordered = [records[key] for key in sorted(records)]
    counts = {}
    for row in ordered:
        for category in row["categories"]:
            counts[category] = counts.get(category, 0) + 1
    summary = {"schemaVersion": "SAGOPALGO_DART_HISTORY_REPORT_V1", "historyPlanId": config.historyPlanId, "dailySha256": config.dailySha256,
        "stockCode": config.stockCode, "corpCode": config.corpCode, "startDate": config.startDate, "endDate": config.endDate,
        "status": "DISCLOSURE_INDEX_COLLECTED", "queryScopes": scopes, "uniqueReceipts": len(ordered),
        "reviewCandidates": sum(bool(v["categories"]) for v in ordered), "categoryCounts": counts,
        "correctionIndications": sum(v["correctionIndicated"] for v in ordered), "withdrawalIndications": sum(v["withdrawalIndicated"] for v in ordered),
        "overseasScopeIndications": sum(v["instrumentScope"] == "OVERSEAS_SECURITIES" for v in ordered),
        "currentIssuer": {"stockCode": config.stockCode, "corpCode": config.corpCode, "corpClass": company["corp_cls"],
                          "observedAt": company_at, "rawSha256": digest(company_raw)},
        "historicalUniverseComplete": False, "corporateActionsComplete": False, "usableForTraining": False,
        "usableForTrading": False, "referenceEventsEmitted": 0, "priceAdjustmentApplied": False}
    return summary, b"".join(canonical(row) + b"\n" for row in ordered)


def cached(folder, journal, endpoint, params):
    matches = [a for a in journal["attempts"] if a["requestId"] == request_id(endpoint, params) and a["state"] == "CAPTURED"]
    if not matches:
        raise ResearchError("DART_CAPTURE_MISSING")
    item = matches[-1]
    return read_bytes(folder / "raw" / f"{item['seq']:04d}.json"), item["capturedAt"]


def collect(folder: Path, transport, sleeper=time.sleep):
    with job_lock(folder):
        plan, config, journal = load_job(folder)
        if journal.get("keyFingerprint", transport.fingerprint) != transport.fingerprint:
            raise ResearchError("DART_KEY_SCOPE_MISMATCH")
        journal["keyFingerprint"] = transport.fingerprint
        def fetch(endpoint, params):
            try:
                return cached(folder, journal, endpoint, params)
            except ResearchError as exc:
                if str(exc) != "DART_CAPTURE_MISSING":
                    raise
            if len(journal["attempts"]) >= config.maxRequests:
                raise ResearchError("DART_REQUEST_BUDGET_EXHAUSTED")
            if journal["attempts"]:
                sleeper(config.minIntervalSeconds)
            item = {"seq": len(journal["attempts"]) + 1, "endpoint": endpoint, "params": params,
                    "requestId": request_id(endpoint, params), "state": "RESERVED", "startedAt": now()}
            journal["attempts"].append(item)
            journal["status"] = "COLLECTING"
            atomic_json(folder / "journal.json", journal)
            try:
                body = transport.fetch(endpoint, params)
                (folder / "raw" / f"{item['seq']:04d}.json").write_bytes(body)
                item.update(state="CAPTURED", sha256=digest(body), capturedAt=now())
            except Exception:
                item.update(state="FAILED", diagnostic="DART_TRANSPORT_FAILED")
                raise
            finally:
                atomic_json(folder / "journal.json", journal)
            return body, item["capturedAt"]
        try:
            report, records = catalog(config, fetch)
            report.update(planId=plan["planId"], callsUsed=len(journal["attempts"]), maxRequests=config.maxRequests, recordsSha256=digest(records))
            temporary = folder / "disclosures.jsonl.tmp"
            temporary.write_bytes(records)
            os.replace(temporary, folder / "disclosures.jsonl")
            atomic_json(folder / "report.json", report)
            journal["status"] = "COLLECTED"
            journal.pop("diagnostic", None)
            atomic_json(folder / "journal.json", journal)
            return report
        except Exception as exc:
            journal.update(status="PARTIAL", diagnostic=str(exc) if isinstance(exc, ResearchError) else "DART_COLLECTION_FAILED")
            atomic_json(folder / "journal.json", journal)
            raise


def audit(folder: Path):
    with job_lock(folder):
        return audit_locked(folder)


def audit_locked(folder: Path):
    plan, config, journal = load_job(folder)
    try:
        report, records = catalog(config, lambda endpoint, params: cached(folder, journal, endpoint, params))
    except ResearchError as exc:
        if str(exc) != "DART_CAPTURE_MISSING":
            raise
        return {"status": "PARTIAL", "callsUsed": len(journal["attempts"]), "maxRequests": config.maxRequests}
    report.update(planId=plan["planId"], callsUsed=len(journal["attempts"]), maxRequests=config.maxRequests, recordsSha256=digest(records))
    if read_bytes(folder / "disclosures.jsonl") != records or read_json(read_bytes(folder / "report.json")) != report:
        raise ResearchError("DART_DERIVATION_TAMPERED")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Issuer-bound, bounded OpenDART historical disclosure research")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("plan")
    create.add_argument("--history-job", required=True, type=Path)
    create.add_argument("--local-use", required=True, type=Path)
    create.add_argument("--corp-code", required=True)
    create.add_argument("--output", required=True, type=Path)
    create.add_argument("--max-requests", type=int, default=12)
    for name in ["collect", "audit"]:
        commands.add_parser(name).add_argument("--job", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            result = prepare(args.history_job, args.local_use, args.corp_code, args.output, args.max_requests)
            result = {"status": "PLANNED", "planId": result["planId"]}
        elif args.command == "collect":
            client = Transport(os.getenv("SAGOPALGO_OPEN_DART_API_KEY"), os.getenv("SAGOPALGO_OPEN_DART_ENABLED", "false").lower() == "true")
            result = collect(args.job, client)
        else:
            result = audit(args.job)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 1 if result["status"] == "PARTIAL" else 0
    except ResearchError as exc:
        code = str(exc)
    except (ValidationError, ValueError, TypeError, KeyError, UnicodeError):
        code = "DART_INPUT_INVALID"
    except OSError:
        code = "DART_FILE_FAILED"
    print(json.dumps({"status": "FAILED", "code": code}), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
