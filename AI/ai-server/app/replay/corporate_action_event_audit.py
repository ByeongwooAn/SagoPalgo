"""Join H05 disclosure routes to dated KRX observations for offline review."""

import argparse
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
import re
import unicodedata

from . import action_listing_inventory, corporate_facts, krx_universe_history, restructuring_event_audit
from .corporate_action_outcomes import KST, VIEWER, WINDOWS, capture, checked_read, list_page, require
from .dataset import digest, read_bytes, read_json
from .krx_baseline_validation import immutable_json
from .kind_membership_evidence import html
from .market_calendar_evidence import text
from .models import utc
from .session_notice_inventory import body_path, query_spec, viewer_documents
from .universe_reconciliation import normalized_name

MARKETS = ("KOSPI", "KOSDAQ")
CATEGORIES = {
    "rights": ("02", "0303"),
    "halt": ("02", "0311"),
    "cancel": ("01", "0131"),
    "dividend": ("01", "0113"),
}


def category_windows(kind, market):
    if (kind, market) == ("rights", "KOSPI"):
        return WINDOWS[:2] + (
            ("2025-01-01", "2025-06-30"), ("2025-07-01", "2025-12-31"),
            ("2026-01-01", "2026-06-30"), ("2026-07-01", "2026-11-07"),
        )
    return WINDOWS


def category_capture_name(kind, market, start, end, page):
    label = "split" if (start, end) not in WINDOWS else "category"
    return f"{label}-{kind}-{market}-{start}-{page:02}"


def category_query(kind, market, start, end, page):
    field, code = CATEGORIES[kind]
    query = {"kind": "CATEGORY", "market": market, "fromDate": start, "toDate": end}
    spec = query_spec(query, page)
    spec["parameters"].update({"reportNm": "", "disclosureType" + field: code})
    return query, spec


def add_candidate(rows, row, route, proof):
    identity = row["market"], row["receipt"]
    row = {k: v for k, v in row.items() if k not in {"rank", "matchedSearches", "listEvidence"}}
    entry = rows.setdefault(identity, row | {"routes": {}})
    require(all(entry[k] == v for k, v in row.items()), "CROSS_ROUTE_ROW_CONFLICT")
    entry["routes"].setdefault(route, [])
    if proof not in entry["routes"][route]:
        entry["routes"][route].append(proof)


def category_inventory(rows, job, pins, at):
    partitions, used = [], set()
    for kind in CATEGORIES:
        for market in MARKETS:
            for start, end in category_windows(kind, market):
                page, pages, total, receipts = 1, 1, None, set()
                while page <= pages:
                    query, spec = category_query(kind, market, start, end, page)
                    name = category_capture_name(kind, market, start, end, page)
                    raw, proof = capture(job, pins, name, spec, at)
                    count, page_count, batch = list_page(raw, query, page)
                    if page == 1:
                        total, pages = count, page_count
                    require((total, pages) == (count, page_count), "CATEGORY_TOTAL_CHANGED")
                    for row in batch:
                        receipt = row["receipt"]
                        require(receipt not in receipts, "CATEGORY_DUPLICATE_RECEIPT")
                        receipts.add(receipt)
                        add_candidate(rows, row, f"category/{kind}", proof["bodySha256"])
                    used.add(name)
                    page += 1
                require(total == len(receipts), "CATEGORY_COVERAGE")
                partitions.append({"category": kind, "market": market, "from": start, "through": end,
                                   "rows": total, "pages": pages})
    require(used == set(pins), "CATEGORY_CAPTURE_SCOPE")
    return partitions


def name_key(value, instrument=False):
    name = unicodedata.normalize("NFKC", value)
    if instrument:
        name = re.sub(r"\s*보통주(?:식)?$", "", name)
    return normalized_name(name).casefold()


def historical_abbreviations(folder, plan, latest, day, sources, at):
    observations = krx_universe_history.observations(folder, plan, latest, day)
    result = {}
    for market, source in sources.items():
        entry = observations[market]
        require(entry["sha256"] == source["sha256"] and entry["capturedAt"] == source["knownAt"] and
                utc(entry["capturedAt"]) <= at, "UNIVERSE_RAW_BINDING")
        raw = krx_universe_history.entry_raw(folder, entry, entry["seed"])
        values = krx_universe_history.envelope(raw)
        require(len(values) == source["rows"], "UNIVERSE_RAW_ROW_COUNT")
        for issue in values:
            key = market, issue["ISU_SRT_CD"], issue["ISU_CD"]
            require(key not in result, "UNIVERSE_RAW_DUPLICATE")
            result[key] = issue["ISU_NM"], issue["ISU_ABBRV"]
    return result


def membership(candidates, history_path, history, abbreviations):
    day_files = history["dayFiles"]
    dates = [row["date"] for row in day_files]
    require(dates == sorted(set(dates)), "UNIVERSE_DATE_ORDER")
    observations = iter(day_files)
    pending = next(observations, None)
    indexed, sources, observed, day_hash = {}, {}, None, None
    ordered = sorted(candidates, key=lambda row: (row["listedMinuteKst"], row["market"], row["receipt"]))
    for row in ordered:
        filed = row["listedMinuteKst"][:10]
        while pending is not None and pending["date"] <= filed:
            if pending["status"] == "OBSERVED":
                day = pending["date"]
                raw = checked_read(history_path.parent / "days" / f"{day}.json", pending["sha256"])
                document = read_json(raw)
                require(document["date"] == day and document["status"] == "OBSERVED", "UNIVERSE_DAY_BINDING")
                sources = {source["market"]: source for source in document["sources"]}
                require(set(sources) == set(MARKETS) and all(s["status"] == "OBSERVED" for s in sources.values()),
                        "UNIVERSE_MARKET_COVERAGE")
                aliases = abbreviations(day, sources)
                indexed = defaultdict(list)
                for issue in document["issues"]:
                    if issue["classification"] != "COMMON_SHARE":
                        continue
                    full_name, short_name = aliases[issue["market"], issue["symbol"], issue["isin"]]
                    require(full_name == issue["name"], "UNIVERSE_RAW_NAME_BINDING")
                    keys = {name_key(full_name, instrument=True), name_key(short_name)} - {""}
                    for key in keys:
                        indexed[issue["market"], key].append(issue | {"exchangeAbbreviation": short_name})
                observed, day_hash = day, pending["sha256"]
            pending = next(observations, None)
        issuer = name_key(row["issuerDisplayName"])
        possible = indexed.get((row["market"], issuer), [])
        if filed < history["startDate"] or filed > history["endDate"]:
            state, possible = "OUTSIDE_SNAPSHOT_DATES", []
        elif not issuer:
            state, possible = "NO_ISSUER_DISPLAY_NAME", []
        elif observed is None:
            state = "NO_PRIOR_OBSERVATION"
        elif not possible:
            state = "NO_SAME_MARKET_NAME_MATCH"
        elif len(possible) > 1:
            state = "AMBIGUOUS_NAME_MATCH"
        else:
            state = "SAME_DATE_NAME_MATCH" if observed == filed else "PRIOR_DATE_NAME_CANDIDATE"
        yield row | {
            "membership": {"status": state, "observationDate": observed, "daySha256": day_hash,
                           "marketSourceSha256": sources[row["market"]]["sha256"] if observed else None,
                           "candidates": [{k: issue[k] for k in (
                               "symbol", "isin", "name", "exchangeAbbreviation", "sourceRowSha256")}
                                          for issue in possible]},
            "instrumentIdentityConfirmed": False,
            "historicalFirstAvailabilityConfirmed": False,
        }


def body_fields(market, role, form, body, issuer, symbol):
    day = r"([0-9]{4}-[0-9]{2}-[0-9]{2})"
    amount = r"([0-9][0-9,]*)"
    if (market, role, form) in {("KOSPI", "RIGHTS", "99301.htm"),
                               ("KOSPI", "DIVIDEND_OR_COMBINED", "99311.htm"),
                               ("KOSPI", "DIVIDEND_OR_COMBINED", "99303.htm")}:
        if "1. 회사명 " + issuer + " 2." not in body:
            return None
        pattern = r"보통주식 " + amount + r" 3\. 사유 ([^\n]{1,60}?) 4\. 적용일 " + day
        matches = [(d, v, reason) for v, reason, d in re.findall(pattern, body)]
    elif market == "KOSDAQ" and role in {"RIGHTS", "DIVIDEND_OR_COMBINED"} and form in {
            "70766.htm", "70767.htm", "70768.htm"}:
        pattern = re.escape(issuer) + r" 보통주식 A" + symbol + " " + amount + " " + day + r" (.{1,70}?)$"
        matches = re.findall(pattern, body)
        matches = [(d, v, reason) for v, d, reason in matches]
    elif market == "KOSDAQ" and (role, form) in {("HALT", "70797.htm"), ("REOPENING", "70799.htm")}:
        match = re.search(r"1\.\s*대상종목 (.+?) 보통주(?:식)? 2\.", body)
        if not match or name_key(match[1]) != name_key(issuer):
            return None
        marker = r"정지일시 " if role == "HALT" else r"해제일시 "
        matches = set(re.findall(marker + day + r" (\d\d:\d\d:\d\d|-)", body))
        if len(matches) != 1:
            return None
        applied, value = matches.pop()
        return {"appliedDate": date.fromisoformat(applied).isoformat(),
                "noticeTimeKst": None if value == "-" else utc(f"{applied}T{value}+09:00").astimezone(KST).isoformat(),
                "actualFirstTradeAt": None}
    else:
        return None
    if len(set(matches)) != 1:
        return None
    applied, value, reason = matches[0]
    return {"appliedDate": date.fromisoformat(applied).isoformat(), "referencePriceKrw": int(value.replace(",", "")),
            "publishedCause": reason}


def reviewed_notices(job, spec, rows, at, scope):
    pins, used, result = spec["receipts"], set(), []
    for receipt, target in sorted(spec["targets"].items()):
        market, role = target["market"], target["role"]
        row = rows[market, receipt]
        require(not row["titleCorrectionFlag"] and ("category/halt" if role in {"HALT", "REOPENING"}
                else "category/rights") in row["routes"], "NOTICE_SAMPLE_BINDING")
        name = "proof-viewer-" + receipt
        viewer, viewer_proof = capture(job, pins, name, {
            "url": row["sourceUrl"], "method": "GET", "parameters": None}, at)
        used.add(name)
        docs = viewer_documents(viewer)
        record = {"market": market, "receipt": receipt, "title": row["title"], "role": role,
                  "evidence": [viewer_proof], "historicalFirstAvailabilityConfirmed": False}
        if len(docs) != 1 or docs[0]["correctionMarked"]:
            result.append(record | {"status": "VERSION_REVIEW"})
            continue
        document = docs[0]["document"]
        name = "proof-route-" + receipt
        route, route_proof = capture(job, pins, name, {
            "url": VIEWER, "method": "POST", "parameters": {"method": "searchContents", "docNo": document}}, at)
        used.add(name)
        url = body_path(route, document)
        name = "proof-body-" + receipt
        raw, body_proof = capture(job, pins, name, {"url": url, "method": "GET", "parameters": None}, at)
        used.add(name)
        record["evidence"] += [route_proof, body_proof]
        headers = [n.text() for n in html(viewer).walk("h1")]
        match = re.fullmatch(r"(.+) \(([0-9A-Z]{6})\)", headers[0]) if len(headers) == 1 else None
        record["document"] = document
        fields = body_fields(market, role, url.rsplit("/", 1)[1], text(raw), *match.groups()) if match else None
        if fields is None:
            result.append(record | {"status": "BODY_SCOPE_OR_FIELDS_UNCONFIRMED"})
        else:
            status = ("EXCHANGE_NOTICE_FIELDS_VERIFIED" if scope[0] <= fields["appliedDate"] <= scope[1]
                      else "APPLIED_DATE_OUT_OF_SCOPE")
            result.append(record | {"status": status, "noticeIssuer": match[1], "noticeSymbol": match[2], **fields})
    require(used == set(pins), "NOTICE_SAMPLE_CAPTURE_SCOPE")
    return result


def build(manifest_path, artifacts, job):
    raw = read_bytes(manifest_path)
    spec = read_json(raw)
    require(spec["schemaVersion"] == "SAGOPALGO_H05_EVENT_AUDIT_V1", "EVENT_AUDIT_SCOPE")
    at = utc(spec["reviewedAt"])
    parent = spec["titleInventory"]
    title = read_json(checked_read(artifacts / parent["path"], parent["sha256"]))
    require(utc(title["knownAt"]) <= at, "FUTURE_TITLE_INVENTORY")
    history = spec["universeInventory"]
    history_path = artifacts / history["path"]
    rows = {}
    for row in title["candidateRows"]:
        require(len(row["matchedSearches"]) == len(row["listEvidence"]), "TITLE_PROOF_COUNT")
        for route, proof in zip(row["matchedSearches"], row["listEvidence"]):
            add_candidate(rows, row, f"title/{route}", proof)
    title_count = len(rows)
    partitions = category_inventory(rows, job, spec["categoryReceipts"], at)
    history_data = read_json(checked_read(history_path, history["sha256"]))
    universe_job = history_path.parent.parent / "job"
    for filename, expected in history["jobPins"].items():
        require(filename in {"plan.json", "journal.json"}, "UNIVERSE_JOB_PATH")
        checked_read(universe_job / filename, expected)
    require(set(history["jobPins"]) == {"plan.json", "journal.json"}, "UNIVERSE_JOB_SCOPE")
    plan, _, _, latest = krx_universe_history.load_job(universe_job)
    require(history_data["planId"] == plan["planId"], "UNIVERSE_PLAN_BINDING")

    def abbreviations(day, sources):
        return historical_abbreviations(universe_job, plan, latest, day, sources, at)

    joined = list(membership(rows.values(), history_path, history_data, abbreviations))
    category_only = Counter(route for row in joined if not any(k.startswith("title/") for k in row["routes"])
                            for route in row["routes"])
    status = Counter(row["membership"]["status"] for row in joined)
    listing = action_listing_inventory.inventory(job, spec["stockReceipts"], at)
    cancel = corporate_facts.one(row for row in title["cases"] if row["kind"] == "SHARE_CANCELLATION" and
                                 row["symbol"] == "005930")
    cancellation_listing = action_listing_inventory.changed_listing(
        listing["relevantRows"], cancel["market"], "삼성전자", cancel["changedListingDate"], "주식소각",
        -cancel["cancelledCommonShares"])
    notices = reviewed_notices(job, spec["sample"], rows, at, (title["startDate"], title["endDate"]))
    return {
        "schemaVersion": spec["schemaVersion"], "manifestSha256": digest(raw), "knownAt": at.isoformat(),
        "scope": {k: title[k] for k in ("startDate", "endDate", "publicationThrough")},
        "titleCandidates": title_count, "uniqueCandidates": len(joined), "categoryPartitions": partitions,
        "categoryOnlyCandidates": len(joined) - title_count, "categoryOnlyByRoute": dict(category_only),
        "membershipCounts": dict(status), "candidateRows": joined, "previouslyReviewedCases": title["cases"],
        "stockListingInventory": listing, "exchangeNoticeSamples": notices,
        "cancellationListingCrossChecks": [{"symbol": cancel["symbol"], "listing": cancellation_listing,
                                            "cancellationDateFromNotice": cancel["actualCancellationDate"]}],
        "noticeSampleCounts": dict(Counter(row["status"] for row in notices)),
        "restructuring": restructuring_event_audit.audit(artifacts, spec["restructuring"], listing["relevantRows"], at),
        "allHistoricalActionsComplete": False, "historicalFirstAvailabilityConfirmed": False,
        "referenceEventsEmitted": 0, "usableForTrading": False, "usableForTraining": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "audit"))
    for name in ("manifest", "artifacts", "job"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    report = build(args.manifest, args.artifacts, args.job)
    immutable_json(args.job / "event-audit.json", report, require_existing=args.action == "audit")
    print({key: report[key] for key in ("uniqueCandidates", "categoryOnlyCandidates", "membershipCounts")})


if __name__ == "__main__":
    main()
