"""Current issuer snapshots are identity seeds, never a historical stock universe."""
from pathlib import Path
from datetime import date
import argparse
import json
import re
from urllib import request

from .dataset import canonical, digest, read_bytes, read_json
from .distribution_facts import Node, XForms
from .history import NoRedirect, atomic_json, now
from .models import ResearchError, utc

LIMIT = 4 * 1024 * 1024
URLS = {market: "https://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13&marketType=" + code
        for market, code in [("KOSPI", "stockMkt"), ("KOSDAQ", "kosdaqMkt")]}
HEADERS = ["회사명", "시장구분", "종목코드", "업종", "주요제품", "상장일", "결산월", "대표자명", "홈페이지", "지역"]


def registry_rows(raw, market, captured_at):
    if market not in URLS or len(raw) > LIMIT:
        raise ResearchError("REGISTRY_INPUT_INVALID")
    utc(captured_at)
    html = raw.decode("cp949")
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)", html, re.I):
        raise ResearchError("REGISTRY_DECLARATION_UNSUPPORTED")
    parser = XForms()
    parser.feed(html)
    parser.close()
    root = parser.root
    if len(parser.stack) != 1 or len(list(root.walk("html"))) != 1:
        raise ResearchError("REGISTRY_HTML_INVALID")
    titles = [v.text() for v in root.walk("title")]
    encoding = [v for v in root.walk("meta") if v.attrs.get("content", "").lower() == "text/html; charset=euc-kr"]
    tables = list(root.walk("table"))
    if titles != ["상장법인목록(EXCEL)"] or len(tables) != 1 or len(encoding) != 1:
        raise ResearchError("REGISTRY_LAYOUT_UNSUPPORTED")
    rows = [[v.text() for v in tr.children if isinstance(v, Node) and v.tag in {"th", "td"}] for tr in tables[0].walk("tr")]
    if not 2 <= len(rows) <= 10001 or rows[0] != HEADERS:
        raise ResearchError("REGISTRY_HEADERS_OR_COUNT_INVALID")
    result = []
    for row in rows[1:]:
        if len(row) != len(HEADERS) or row[1] != {"KOSPI": "유가", "KOSDAQ": "코스닥"}[market]:
            raise ResearchError("REGISTRY_MARKET_OR_ROW_MISMATCH")
        name, symbol, listed = row[0], row[2], row[5]
        if not 1 <= len(name) <= 200 or not re.fullmatch(r"[0-9A-Z]{6}", symbol) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", listed):
            raise ResearchError("REGISTRY_IDENTITY_INVALID")
        if not 1900 <= date.fromisoformat(listed).year <= 2100:
            raise ResearchError("REGISTRY_LISTING_DATE_INVALID")
        result.append({"symbol": symbol, "issuerName": name, "market": market, "reportedListingDate": listed,
                       "knownAt": captured_at, "knowledgeBasis": "FETCH_TIME_ONLY", "sourceSha256": digest(raw),
                       "numericCodeSupported": bool(re.fullmatch(r"[0-9]{6}", symbol)), "commonShareConfirmed": False})
    if len({v["symbol"] for v in result}) != len(result):
        raise ResearchError("REGISTRY_DUPLICATE_SYMBOL")
    return sorted(result, key=lambda v: v["symbol"])


def build_registry(cache):
    rows, sources = [], []
    for market in URLS:
        folder = cache / market
        receipt = audit_capture(folder, market)
        values = registry_rows(read_bytes(folder / "body.html"), market, receipt["capturedAt"])
        rows.extend(values)
        sources.append({"market": market, "url": receipt["url"], "sha256": receipt["bodySha256"],
                        "knownAt": receipt["capturedAt"], "parsedRowCount": len(values)})
    if len({v["symbol"] for v in rows}) != len(rows):
        raise ResearchError("REGISTRY_CROSS_MARKET_DUPLICATE")
    return {"schemaVersion": "SAGOPALGO_KIND_REGISTRY_V1", "sources": sources, "rows": rows,
            "issuerCount": len(rows), "countsByMarket": {v["market"]: v["parsedRowCount"] for v in sources},
            "nonNumericSymbolCount": sum(not v["numericCodeSupported"] for v in rows),
            "providerAsOf": None, "snapshotAtomic": False, "independentTotalVerified": False,
            "historicalMembershipGenerated": False, "marketUniverseComplete": False,
            "usableForTraining": False, "usableForTrading": False}


def build_seed(registry, cases, events):
    if (cases["startDate"], cases["endDate"]) != (events["startDate"], events["endDate"]):
        raise ResearchError("UNIVERSE_SEED_SCOPE_MISMATCH")
    identities = {}

    def include(symbol, observation):
        identities.setdefault(symbol, []).append(observation)

    for row in registry["rows"]:
        include(row["symbol"], {"origin": "CURRENT_ISSUER_SNAPSHOT", "issuerName": row["issuerName"], "market": row["market"],
                                "knownAt": row["knownAt"], "sourceHashes": [row["sourceSha256"]], "caseId": None,
                                "commonShareConfirmed": False})
    for report in [cases, events]:
        for fact in report["facts"]:
            include(fact["stockCode"], {"origin": "HISTORICAL_CASE", "issuerName": fact["issuerName"],
                                       "market": fact.get("market", fact.get("fromMarket")), "knownAt": fact["knownAt"],
                                       "sourceHashes": [fact["sourceSha256"]] if "sourceSha256" in fact else [v["sha256"] for v in fact["sources"]],
                                       "caseId": fact["caseId"],
                                       "commonShareConfirmed": True})
    values = []
    for symbol, observations in sorted(identities.items()):
        current = [v for v in observations if v["origin"] == "CURRENT_ISSUER_SNAPSHOT"]
        values.append({"symbol": symbol, "numericCodeSupported": bool(re.fullmatch(r"[0-9]{6}", symbol)),
                       "currentSnapshotStatus": "PRESENT" if current else "NOT_PRESENT", "observations": observations})
    return {"schemaVersion": "SAGOPALGO_UNIVERSE_SEED_V1", "startDate": cases["startDate"], "endDate": cases["endDate"],
            "registrySha256": digest(canonical(registry)), "caseReportSha256": digest(canonical(cases)),
            "eventReportSha256": digest(canonical(events)), "identityCount": len(values), "currentIssuerCount": registry["issuerCount"],
            "historicalOnlyIdentityCount": sum(v["currentSnapshotStatus"] == "NOT_PRESENT" for v in values),
            "nonNumericSymbolCount": registry["nonNumericSymbolCount"], "identities": values,
            "membershipEventsGeneratedFromCurrentSnapshot": 0, "historicalMembershipComplete": False,
            "marketUniverseComplete": False, "usableForTraining": False, "usableForTrading": False}


def lookup(seed, symbol, at):
    instant = utc(at)
    if not re.fullmatch(r"[0-9A-Z]{6}", symbol):
        raise ResearchError("UNIVERSE_SEED_SYMBOL_INVALID")
    observations = [v for identity in seed["identities"] if identity["symbol"] == symbol
                    for v in identity["observations"] if utc(v["knownAt"]) <= instant]
    return {"symbol": symbol, "asOf": at, "observations": observations,
            "historicalMembershipConfirmed": False, "usableForTrading": False}


def immutable_report(path, value, audit_only=False):
    if path.exists() or audit_only:
        if read_bytes(path) != canonical(value):
            raise ResearchError("REGISTRY_REPORT_TAMPERED")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(path, value)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ["capture", "build", "audit", "seed-build", "seed-audit", "seed-lookup"]:
        p = sub.add_parser(command)
        p.add_argument("--cache", type=Path, required=True)
        if command == "capture":
            p.add_argument("--max-new-requests", type=int, default=0, choices=range(3))
        else:
            p.add_argument("--report", type=Path, required=True)
        if command.startswith("seed-"):
            for arg in ["case-cache", "case-scope", "case-report", "event-scope", "event-report"]:
                p.add_argument("--" + arg, type=Path, required=True)
        if command == "seed-lookup":
            p.add_argument("--symbol", required=True)
            p.add_argument("--at", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "capture":
            needed = sum(not (args.cache / market).exists() for market in URLS)
            if needed > args.max_new_requests:
                raise ResearchError("REGISTRY_REQUEST_BUDGET_EXCEEDED")
            for market in URLS:
                if (args.cache / market).exists():
                    audit_capture(args.cache / market, market)
            reused = sum(capture_registry(market, args.cache)[2] for market in URLS)
            result = {"capturedSources": 2 - reused, "reusedSources": reused}
        else:
            result = build_registry(args.cache)
            if args.command.startswith("seed-"):
                from . import kind_cases, universe_events
                cases = kind_cases.audit_report(kind_cases.load_scope(args.case_scope), args.case_cache, args.case_report)
                events = universe_events.audit_report(universe_events.load_scope(args.event_scope), args.case_cache, args.event_report)
                result = build_seed(result, cases, events)
            immutable_report(args.report, result, args.command not in {"build", "seed-build"})
            if args.command == "seed-lookup":
                result = lookup(result, args.symbol, args.at)
            else:
                result = {key: value for key, value in result.items() if key not in {"rows", "identities"}}
        print(json.dumps(result, ensure_ascii=True, sort_keys=True))
        return 0
    except (ValueError, OSError) as exc:
        print(json.dumps({"diagnostic": str(exc) if isinstance(exc, ResearchError) else "REGISTRY_INVALID_INPUT"}))
        return 2


def audit_capture(folder, market):
    if market not in URLS:
        raise ResearchError("REGISTRY_MARKET_INVALID")
    receipt = read_json(read_bytes(folder / "receipt.json")) if (folder / "receipt.json").is_file() else {}
    if not isinstance(receipt, dict) or receipt.get("status") != "COMPLETE":
        raise ResearchError("REGISTRY_CAPTURE_RESERVED")
    if (set(receipt) != {"schemaVersion", "market", "url", "status", "startedAt", "capturedAt", "bodySha256", "maxGetRequests"}
            or receipt["schemaVersion"] != "SAGOPALGO_KIND_REGISTRY_CAPTURE_V1" or receipt["market"] != market
            or receipt["url"] != URLS[market] or type(receipt["maxGetRequests"]) is not int or receipt["maxGetRequests"] != 1
            or utc(receipt["startedAt"]) > utc(receipt["capturedAt"])):
        raise ResearchError("REGISTRY_CACHE_TAMPERED")
    raw = read_bytes(folder / "body.html")
    if len(raw) > LIMIT or digest(raw) != receipt["bodySha256"]:
        raise ResearchError("REGISTRY_CACHE_TAMPERED")
    return receipt


def capture_registry(market, cache, opener=None):
    if market not in URLS:
        raise ResearchError("REGISTRY_MARKET_INVALID")
    folder = cache / market
    folder.parent.mkdir(parents=True, exist_ok=True)
    try:
        folder.mkdir()
    except FileExistsError:
        return audit_capture(folder, market), folder, True
    receipt = {"schemaVersion": "SAGOPALGO_KIND_REGISTRY_CAPTURE_V1", "market": market, "url": URLS[market],
               "status": "IN_FLIGHT", "startedAt": now(), "maxGetRequests": 1}
    atomic_json(folder / "receipt.json", receipt)
    try:
        client = opener or request.build_opener(NoRedirect())
        req = request.Request(URLS[market], headers={"Accept": "text/html", "User-Agent": "SagoPalgo-local-research/1"}, method="GET")
        with client.open(req, timeout=25) as response:
            raw = response.read(LIMIT + 1)
        if len(raw) > LIMIT:
            raise ResearchError("REGISTRY_RESPONSE_LIMIT")
        (folder / "body.html").write_bytes(raw)
        receipt.update(status="COMPLETE", bodySha256=digest(raw), capturedAt=now())
        atomic_json(folder / "receipt.json", receipt)
        return receipt, folder, False
    except Exception as exc:
        code = str(exc) if isinstance(exc, ResearchError) else "REGISTRY_CAPTURE_FAILED"
        receipt.update(status="FAILED", diagnostic=code, finishedAt=now())
        atomic_json(folder / "receipt.json", receipt)
        raise ResearchError(code) from None


if __name__ == "__main__":
    raise SystemExit(main())
