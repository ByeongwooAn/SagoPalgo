"""Bounded KIND listing/delisting status tables; issuer keys are not stock ISINs."""
import argparse
import json
from pathlib import Path
import re
import time
from urllib import parse, request

from .dataset import canonical, digest, read_bytes, read_json
from .distribution_facts import Node, XForms
from .history import NoRedirect, day, job_lock, now
from .krx_storage import atomic_json
from .models import ResearchError, utc

LIMIT = 4 * 1024 * 1024
ENDPOINTS = {"LISTING": "https://kind.krx.co.kr/listinvstg/listingcompany.do",
             "DELISTING": "https://kind.krx.co.kr/investwarn/delcompany.do"}
MARKETS = {"KOSPI": ("1", "유가증권"), "KOSDAQ": ("2", "코스닥")}
SCHEMA = "SAGOPALGO_KIND_MEMBERSHIP_STATUS_PLAN_V1"


def parameters(kind, market, start, end):
    if kind not in ENDPOINTS or market not in MARKETS or day(start) > day(end):
        raise ResearchError("KIND_STATUS_SCOPE_INVALID")
    value = {"method": "searchListingTypeSub" if kind == "LISTING" else "searchDelCompanySub",
             "currentPageSize": "3000", "pageIndex": "1", "orderMode": "1", "orderStat": "D",
             "repIsuSrtCd": "", "isurCd": "", "forward": "listingtype_sub" if kind == "LISTING" else "delcompany_sub",
             "marketType": MARKETS[market][0], "fromDate": start, "toDate": end,
             "searchCorpName": "", "searchCorpNameTmp": "", "searchCodeType": ""}
    if kind == "LISTING":
        value.update(listTypeArrStr="01|02|03|04|05|", choicTypeArrStr="", secuGrpArrStr="0|ST|FS|MF|SC|RT|DR|",
                     country="", industry="", repMajAgntDesignAdvserComp="", repMajAgntComp="", designAdvserComp="")
    return value


def parse_status(raw, kind, market, start, end, captured_at, source_kind):
    parameters(kind, market, start, end)
    utc(captured_at)
    if source_kind not in {"PROVIDER_OBSERVATIONS", "SYNTHETIC"} or len(raw) > LIMIT:
        raise ResearchError("KIND_STATUS_INPUT_INVALID")
    parser = XForms()
    parser.feed(raw.decode("utf-8-sig"))
    parser.close()
    root = parser.root
    tables = list(root.walk("table"))
    if len(parser.stack) != 1 or len(tables) != 1:
        raise ResearchError("KIND_STATUS_LAYOUT_INVALID")
    table = tables[0]
    expected = "회사명, 상장일, 상장유형,증권구분," if kind == "LISTING" else "번호, 회사명, 폐지일자, 폐지사유, 비고"
    if (not table.attrs.get("summary", "").startswith(expected)
            or [v.text() for v in table.walk("caption")] != ["신규상장기업현황 목록" if kind == "LISTING" else "목록"]):
        raise ResearchError("KIND_STATUS_LAYOUT_INVALID")
    info = [v for v in root.walk("div") if v.attrs.get("class") == "info type-00"]
    totals = re.findall(r"전체\s*([0-9,]+)\s*건\s*:\s*([0-9]+)\s*/\s*([0-9]+)", info[0].text()) if len(info) == 1 else []
    if len(totals) != 1:
        raise ResearchError("KIND_STATUS_TOTAL_MISSING")
    count, page, pages = [int(v.replace(",", "")) for v in totals[0]]
    if not 0 <= count <= 3000 or page != 1 or pages != 1:
        raise ResearchError("KIND_STATUS_INCOMPLETE_PAGE")
    bodies = list(table.walk("tbody"))
    if len(bodies) != 1:
        raise ResearchError("KIND_STATUS_LAYOUT_INVALID")
    result = []
    for tr in bodies[0].walk("tr"):
        cells = [v for v in tr.children if isinstance(v, Node) and v.tag == "td"]
        if count == 0 and len(cells) == 1 and "조회된" in cells[0].text():
            continue
        if len(cells) != (7 if kind == "LISTING" else 5):
            raise ResearchError("KIND_STATUS_ROW_INVALID")
        name_cell = cells[0 if kind == "LISTING" else 1]
        markets = [v.attrs.get("alt") for v in name_cell.walk("img") if v.attrs.get("alt") in {"유가증권", "코스닥", "코넥스"}]
        if markets != [MARKETS[market][1]]:
            raise ResearchError("KIND_STATUS_MARKET_MISMATCH")
        if kind == "LISTING":
            matched = re.fullmatch(r"fnDetailView\('([A-Z0-9]{5})','([0-9]{14})'\)", tr.attrs.get("onclick", ""))
            name = name_cell.attrs.get("title", "")
            event_date, event_type, security = [v.text() for v in cells[1:4]]
            reference = {"listingReviewReceipt": matched[2] if matched else None}
        else:
            links = [v for v in name_cell.walk("a") if v.attrs.get("id") == "companysum"]
            if len(links) != 1:
                raise ResearchError("KIND_STATUS_ROW_INVALID")
            matched = re.fullmatch(r"companysummary_open\('([A-Z0-9]{5})'\);\s*return false;", links[0].attrs.get("onclick", ""))
            name = links[0].attrs.get("title", "")
            event_date, event_type, security = cells[2].text(), cells[3].text(), None
            reference = {"remarks": cells[4].text()}
        if not matched or not name.strip() or len(name) > 200 or not event_type or len(event_type) > 2000:
            raise ResearchError("KIND_STATUS_ROW_INVALID")
        day(event_date)
        if not start <= event_date <= end:
            raise ResearchError("KIND_STATUS_DATE_OUTSIDE_SCOPE")
        row = {"kind": kind, "market": market, "providerIssuerKey": matched[1], "issuerName": name,
               "date": event_date, "eventType": event_type, "securityType": security, **reference,
               "knownAt": captured_at, "knowledgeBasis": "FETCH_TIME_ONLY", "sourceKind": source_kind,
               "sourceRowSha256": digest(canonical({"cells": [v.text() for v in cells], "issuerKey": matched[1]})),
               "fullStockCodeProvided": False, "isinProvided": False}
        result.append(row)
    if len(result) != count or len({(v["providerIssuerKey"], v["date"]) for v in result}) != len(result):
        raise ResearchError("KIND_STATUS_COUNT_OR_DUPLICATE")
    return sorted(result, key=lambda v: (v["date"], v["providerIssuerKey"]))


def prepare(folder, start="2023-11-01", end="2026-11-02", source_kind="PROVIDER_OBSERVATIONS"):
    if source_kind not in {"PROVIDER_OBSERVATIONS", "SYNTHETIC"} or (day(end) - day(start)).days > 3653:
        raise ResearchError("KIND_STATUS_SCOPE_INVALID")
    sources = [{"kind": kind, "market": market, "url": ENDPOINTS[kind], "parameters": parameters(kind, market, start, end)}
               for kind in ENDPOINTS for market in MARKETS]
    payload = {"schemaVersion": SCHEMA, "startDate": start, "endDate": end, "sourceKind": source_kind,
               "maxRequests": 4, "minIntervalSeconds": 1, "sources": sources}
    plan = {**payload, "planId": digest(canonical(payload))}
    folder.mkdir(parents=True, exist_ok=False)
    (folder / "raw").mkdir()
    atomic_json(folder / "plan.json", plan)
    atomic_json(folder / "journal.json", {"planId": plan["planId"], "attempts": []})
    return plan


def load_plan(folder):
    plan = read_json(read_bytes(folder / "plan.json"))
    expected = {"schemaVersion": SCHEMA, "startDate": plan["startDate"], "endDate": plan["endDate"],
                "sourceKind": plan["sourceKind"], "maxRequests": 4, "minIntervalSeconds": 1,
                "sources": [{"kind": k, "market": m, "url": ENDPOINTS[k], "parameters": parameters(k, m, plan["startDate"], plan["endDate"])}
                            for k in ENDPOINTS for m in MARKETS]}
    if plan != {**expected, "planId": digest(canonical(expected))} or plan["sourceKind"] not in {"PROVIDER_OBSERVATIONS", "SYNTHETIC"}:
        raise ResearchError("KIND_STATUS_PLAN_TAMPERED")
    return plan


def load(folder):
    plan = load_plan(folder)
    journal = read_json(read_bytes(folder / "journal.json"))
    if (set(journal) != {"planId", "attempts"} or journal["planId"] != plan["planId"]
            or not isinstance(journal["attempts"], list) or len(journal["attempts"]) > 4):
        raise ResearchError("KIND_STATUS_JOURNAL_INVALID")
    records, sources = [], []
    for seq, entry in enumerate(journal["attempts"]):
        expected = plan["sources"][seq]
        if (not isinstance(entry, dict) or entry.get("source") != expected or type(entry.get("seq")) is not int or entry["seq"] != seq + 1
                or entry.get("state") not in {"RESERVED", "CAPTURED", "FAILED"}):
            raise ResearchError("KIND_STATUS_JOURNAL_INVALID")
        utc(entry["startedAt"])
        if (("sha256" in entry) != ("capturedAt" in entry)
                or entry["state"] == "CAPTURED" and not {"sha256", "capturedAt", "rowCount"} <= set(entry)):
            raise ResearchError("KIND_STATUS_JOURNAL_INVALID")
        fields = {"source", "seq", "state", "startedAt"}
        if "sha256" in entry:
            fields |= {"sha256", "capturedAt"}
            if utc(entry["capturedAt"]) < utc(entry["startedAt"]):
                raise ResearchError("KIND_STATUS_JOURNAL_INVALID")
            raw = read_bytes(folder / "raw" / f"{seq+1}.html")
            if digest(raw) != entry["sha256"]:
                raise ResearchError("KIND_STATUS_RAW_TAMPERED")
        if entry["state"] == "CAPTURED":
            fields |= {"sha256", "capturedAt", "rowCount"}
            rows = parse_status(raw, expected["kind"], expected["market"], plan["startDate"], plan["endDate"], entry["capturedAt"], plan["sourceKind"])
            if type(entry.get("rowCount")) is not int or len(rows) != entry["rowCount"]:
                raise ResearchError("KIND_STATUS_COUNT_OR_DUPLICATE")
            sources.append({**expected, "sha256": entry["sha256"], "knownAt": entry["capturedAt"], "rows": len(rows)})
            records.extend({**v, "sourceSha256": entry["sha256"]} for v in rows)
        elif entry["state"] == "FAILED":
            fields |= {"diagnostic", "finishedAt"}
            if utc(entry["finishedAt"]) < utc(entry["startedAt"]):
                raise ResearchError("KIND_STATUS_JOURNAL_INVALID")
        if set(entry) != fields or (entry["state"] != "CAPTURED" and seq != len(journal["attempts"]) - 1):
            raise ResearchError("KIND_STATUS_JOURNAL_INVALID")
    return plan, journal, records, sources


class Transport:
    source_kind = "PROVIDER_OBSERVATIONS"

    def __init__(self, opener=None):
        self.opener = opener

    def fetch(self, source):
        req = request.Request(source["url"], data=parse.urlencode(source["parameters"]).encode(), method="POST",
                              headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "text/html",
                                       "User-Agent": "SagoPalgo-local-research/1", "Referer": source["url"]})
        try:
            with (self.opener or request.build_opener(NoRedirect())).open(req, timeout=20) as response:
                raw = response.read(LIMIT + 1)
        except Exception:
            raise ResearchError("KIND_STATUS_TRANSPORT_FAILED") from None
        if len(raw) > LIMIT:
            raise ResearchError("KIND_STATUS_RESPONSE_LIMIT")
        return raw


def capture(folder, transport, max_new_requests, sleep=time.sleep):
    if type(max_new_requests) is not int or not 0 <= max_new_requests <= 4:
        raise ResearchError("KIND_STATUS_RUN_BUDGET_INVALID")
    with job_lock(folder):
        plan, journal, _, _ = load(folder)
        if any(v["state"] != "CAPTURED" for v in journal["attempts"]):
            raise ResearchError("KIND_STATUS_CAPTURE_RESERVED")
        if transport.source_kind != plan["sourceKind"]:
            raise ResearchError("KIND_STATUS_SOURCE_KIND_MISMATCH")
        used = 0
        while len(journal["attempts"]) < 4 and used < max_new_requests:
            if journal["attempts"]:
                elapsed = (utc(now()) - utc(journal["attempts"][-1]["startedAt"])).total_seconds()
                if elapsed < 0:
                    raise ResearchError("KIND_STATUS_CLOCK_REGRESSION")
                delay = 1 - elapsed
                if delay > 0:
                    sleep(delay)
            seq = len(journal["attempts"]) + 1
            source = plan["sources"][seq-1]
            entry = {"source": source, "seq": seq, "state": "RESERVED", "startedAt": now()}
            journal["attempts"].append(entry)
            atomic_json(folder / "journal.json", journal)
            try:
                raw = transport.fetch(source)
                (folder / "raw" / f"{seq}.html").write_bytes(raw)
                entry.update(sha256=digest(raw), capturedAt=now())
                rows = parse_status(raw, source["kind"], source["market"], plan["startDate"], plan["endDate"], entry["capturedAt"], plan["sourceKind"])
                entry.update(state="CAPTURED", rowCount=len(rows))
                atomic_json(folder / "journal.json", journal)
            except Exception as exc:
                code = str(exc) if isinstance(exc, ResearchError) else "KIND_STATUS_CAPTURE_FAILED"
                entry.pop("rowCount", None)
                entry.update(state="FAILED", diagnostic=code, finishedAt=now())
                atomic_json(folder / "journal.json", journal)
                raise ResearchError(code) from None
            used += 1
        return report(folder)


def report(folder):
    plan, journal, records, sources = load(folder)
    return {"schemaVersion": "SAGOPALGO_KIND_MEMBERSHIP_STATUS_V1", "planId": plan["planId"], "startDate": plan["startDate"],
            "endDate": plan["endDate"], "sourceKind": plan["sourceKind"], "attemptsUsed": len(journal["attempts"]),
            "capturedSources": len(sources), "missingSources": 4 - len(sources), "sources": sources, "records": records,
            "listingStatusExcludesSomeSpacMergers": True, "independentProvider": False,
            "completeMarketMembershipConfirmed": False, "usableForTraining": False, "usableForTrading": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ["plan", "capture", "audit"]:
        p = sub.add_parser(command)
        p.add_argument("--job", type=Path, required=True)
        if command == "plan":
            p.add_argument("--start", default="2023-11-01")
            p.add_argument("--end", default="2026-11-02")
        if command == "capture":
            p.add_argument("--max-new-requests", type=int, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            result = prepare(args.job, args.start, args.end)
        else:
            result = capture(args.job, Transport(), args.max_new_requests) if args.command == "capture" else report(args.job)
        print(json.dumps({k:v for k,v in result.items() if k != "records"}, sort_keys=True), flush=True)
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"diagnostic": str(exc) if isinstance(exc, ResearchError) else "KIND_STATUS_INPUT_INVALID"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
