"""Offline, evidence-bound H03 comparison of historical KRX stock sessions."""

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import re

from .dataset import digest, read_bytes, read_json
from .intraday import KST, Timeline
from .krx_baseline_validation import immutable_json
from .models import ResearchError, utc

MARKETS = ("KOSPI", "KOSDAQ")
PAGE = "/contents/OPN/05/05000000/OPN05000000T1.jsp"
PRESS = "https://open.krx.co.kr/contents/OPN/05/05000000/OPN05000000.jsp"
TERMS = {
    "trading-hours": "거래시간", "market-closure": "휴장", "stock-trading": "매매거래",
    "market-operation": "시장운영", "circuit-breaker": "Circuit Breakers", "pre-market": "프리마켓",
    "disruption": "장애", "correction": "정정",
}
KIND_URL = re.compile(r"https://kind\.krx\.co\.kr/external/(\d{4})/(\d{2})/(\d{2})/(\d{6})/(\d{14})/\d+\.htm")
CB_TITLE = re.compile(r"(유가증권시장|코스닥시장) 1단계 Circuit Breakers\((?:일시중단|매매거래중단)\) 발동(?:상황)?")


def require(condition, reason):
    if not condition:
        raise ResearchError(f"H03_{reason}")


def pinned(path, expected):
    raw = read_bytes(path)
    require(digest(raw) == expected, "INPUT_HASH")
    return raw


def key(row):
    return row["market"], row["businessDate"]


def index(rows, identity=key):
    result = {identity(row): row for row in rows}
    require(len(result) == len(rows), "DUPLICATE_IDENTITY")
    return result


def press_date(value, fmt):
    return datetime.strptime(value, fmt).date().isoformat()


def scheduled_date(title, posted):
    exam = re.search(r"대학수학능력시험일\((\d{1,2})\.(\d{1,2})\).*거래시간 임시 변경", title)
    if exam:
        return date(int(posted[:4]), *map(int, exam.groups())).isoformat()
    opening = re.search(r"(\d{4})년 연초 개장일\((\d{1,2})\.(\d{1,2})\).*매매거래시간 안내", title)
    if opening:
        return date(*map(int, opening.groups())).isoformat()
    return None


def read_press(job, manifest, reviewed_at):
    start, end = manifest["publicationSearchStart"], manifest["publicationSearchEnd"]
    by_id, details, counts = {}, {}, {}
    for name, sha in sorted(manifest["pressReceipts"].items()):
        mode, _, argument = name.partition("-")
        if mode == "list":
            expected = {"sch_tp": "title", "sch_word": TERMS[argument], "fromdate": start.replace("-", ""),
                        "todate": end.replace("-", ""), "pagePath": PAGE, "curPage": "1", "pageSize": "100"}
        else:
            require(mode == "view" and re.fullmatch(r"\d+", argument), "PRESS_CAPTURE_KEY")
            expected = {"seq": argument, "pagePath": PAGE}
        folder = job / "press" / name
        receipt = read_json(pinned(folder / "receipt.json", sha))
        require(receipt["schemaVersion"] == "SAGOPALGO_H03_PRESS_CAPTURE_V1" and
                receipt["kind"] == mode and receipt["parameters"] == expected and
                receipt["endpoint"] == "https://open.krx.co.kr/contents/OPN/99/OPN99000001.jspx" and
                receipt["selector"] == "OPN/05/05000000/opn05000000t1_" + ("01" if mode == "list" else "02") and
                receipt["status"] == "COMPLETE" and receipt["httpRequests"] == 2 and
                utc(receipt["startedAt"]) <= utc(receipt["capturedAt"]) <= reviewed_at, "PRESS_RECEIPT")
        rows = read_json(pinned(folder / "body.json", receipt["sha256"]))["output"]
        unique = index(rows, lambda row: row["noti_no"])
        if mode == "list":
            require(len(rows) <= 100 and all(int(row["totCnt"]) == len(rows) for row in rows), "PRESS_PAGINATION")
            counts[argument] = len(rows)
        else:
            require(set(unique) == {argument}, "PRESS_DETAIL_IDENTITY")
        for number, row in unique.items():
            fmt = "%Y/%m/%d" if mode == "list" else "%Y%m%d"
            published = press_date(row["noti_dd"], fmt)
            created = press_date(row["creat_ddtm"], fmt)
            require(start <= published <= end and start <= created <= end and
                    row["use_yn"] == row["opn_yn"] == "Y", "PRESS_PUBLICATION_SCOPE")
            item = {"noticeId": number, "postedDate": published, "createdDate": created, "title": row["title"],
                    "url": f"{PRESS}#fe3647848b826aa1ddee224c4b5526f4=1&view={number}"}
            if mode == "list":
                require(by_id.setdefault(number, item) == item, "PRESS_LIST_CONFLICT")
            else:
                details[number] = item | {"boardUpdatedDate": press_date(row["adj_ddtm"], "%Y%m%d")}
    require(set(counts) == set(TERMS), "PRESS_QUERY_MISSING")
    for number, item in details.items():
        require({k: v for k, v in item.items() if k != "boardUpdatedDate"} == by_id.get(number), "PRESS_DETAIL_CONFLICT")
    require(all(number in details for number, item in by_id.items()
                if scheduled_date(item["title"], item["postedDate"])), "PRESS_SCHEDULE_DETAIL_MISSING")
    return by_id, details, counts


def minute_relation(label: str | None, effect: datetime):
    if label is None:
        return "UNATTRIBUTED"
    minute = datetime.strptime(label, "%Y-%m-%d %H:%M").replace(tzinfo=KST)
    if effect < minute:
        return "EFFECT_BEFORE_LISTED_MINUTE"
    if effect >= minute + timedelta(minutes=1):
        return "EFFECT_AFTER_LISTED_MINUTE"
    return "SAME_MINUTE_ORDER_UNPROVEN"


def kind_publication(inventories, reviewed_bodies, reviewed_at):
    receipts, documents, lineages = {}, {}, set()
    for inventory in inventories:
        require(utc(inventory["knownAt"]) <= reviewed_at, "FUTURE_KIND_INVENTORY")
        for row in inventory["rows"]:
            identity = row["market"], row["receipt"]
            label = row["reportedAtKstText"]
            require(label.startswith(datetime.strptime(row["receipt"][:8], "%Y%m%d").date().isoformat()), "KIND_RECEIPT_DATE")
            require(receipts.setdefault(identity, label) == label, "KIND_RECEIPT_CONFLICT")
            for version in row["versions"]:
                match = KIND_URL.fullmatch(version["url"])
                require(match and match[5] == version["document"], "KIND_DOCUMENT_URL")
                kind_key = row["market"], version["document"], version["bodySha256"]
                source_known = utc(version.get("sourceKnownAt") or version["knownAt"])
                require(source_known <= reviewed_at, "FUTURE_KIND_DOCUMENT")
                value = ("".join(match.groups()[:4]), version["url"], version["correctionMarked"])
                existing = documents.setdefault(kind_key, value)
                require(existing == value, "KIND_DOCUMENT_CONFLICT")
            if len(row["versions"]) > 1:
                lineages.add((row["market"], tuple((v["document"], v["bodySha256"]) for v in row["versions"])))

    publication = {
        identity: {"receipt": number, "listedMinuteKst": receipts.get((identity[0], number)), "url": url,
                   "correctionMarked": corrected, "historicalFirstAvailabilityConfirmed": False}
        for identity, (number, url, corrected) in documents.items()
    }
    reviews = index(reviewed_bodies, lambda row: (row["market"], row["document"], row["bodySha256"]))
    corrections = []
    for market, versions in sorted(lineages):
        facts = [publication[(market, document, sha)] | {"document": document, "bodySha256": sha}
                 for document, sha in versions]
        require(len(facts) == 2 and not facts[0]["correctionMarked"] and facts[1]["correctionMarked"], "KIND_LINEAGE")
        before, after = (fact["listedMinuteKst"] for fact in facts)
        order = "ORDERED_BY_DISTINCT_LISTED_MINUTES" if before and after and before < after else "ORDER_UNCONFIRMED"
        body_reviews = [reviews.get((market, document, sha)) for document, sha in versions]
        issuers = {row["subjectIssuer"] for row in body_reviews if row and row["classification"] == "ISSUER_SPECIFIC_HALT"
                   and utc(row["knownAt"]) <= reviewed_at}
        issuer_only = len(issuers) == 1 and all(row and row["classification"] == "ISSUER_SPECIFIC_HALT" and
                                               row["subjectIssuer"] in issuers and utc(row["knownAt"]) <= reviewed_at
                                               for row in body_reviews)
        corrections.append({"market": market, "scope": "ISSUER_ONLY" if issuer_only else "UNREVIEWED",
                            "subjectIssuer": next(iter(issuers)) if issuer_only else None,
                            "publicationOrder": order, "versions": facts})
    return publication, corrections


def schedules(details, job, reviewed, boundary, reference_packs, publication, start, end):
    planned = {number: scheduled_date(item["title"], item["postedDate"]) for number, item in details.items()}
    planned = {number: stamp for number, stamp in planned.items() if stamp}
    require(set(reviewed) <= set(planned), "PRESS_SCHEDULE_IDENTITY")
    by_day = index(boundary, key)
    pack = index([row for market in MARKETS for row in reference_packs[market]["sessions"]])
    result = []
    for number, stamp in sorted(planned.items(), key=lambda pair: pair[1]):
        inside = start <= stamp <= end
        item = details[number]
        require(item["postedDate"] < stamp, "PRESS_SCHEDULE_PUBLICATION_ORDER")
        verified = reviewed.get(number)
        if verified:
            meta = read_json(pinned(job / "attachments" / f"{number}.json", verified["attachmentListSha256"]))
            pdf = pinned(job / "attachments" / f"{number}.pdf", verified["pdfSha256"])
            matches = [row for row in meta["block1"] if row["file_nm"] == f'(보도자료) {item["title"]}.pdf']
            require(verified["businessDate"] == stamp and verified["page"] > 0 and pdf.startswith(b"%PDF-") and
                    len(matches) == 1, "PRESS_PDF_IDENTITY")
        require(not inside or verified, "PRESS_SCHEDULE_PDF_REQUIRED")
        for market in MARKETS:
            identity = market, stamp
            fact = by_day[identity]
            start_at, end_at = utc(fact["openAt"]).astimezone(KST), utc(fact["closeAt"]).astimezone(KST)
            if verified:
                require((start_at.strftime("%H:%M"), end_at.strftime("%H:%M")) ==
                        (verified["open"], verified["close"]), "PRESS_KIND_SCHEDULE_CONFLICT")
            if inside:
                require(identity in pack and utc(pack[identity]["openAt"]) == start_at and
                        utc(pack[identity]["closeAt"]) == end_at, "REFERENCE_SCHEDULE_CONFLICT")
            require(start_at.date().isoformat() == end_at.date().isoformat() == stamp and start_at < end_at,
                    "SCHEDULE_EFFECT_DATE")
            sha = re.search(r"raw-sha256:([a-f0-9]{64})", fact["evidence"])[1]
            listed = publication[(market, fact["document"], sha)]
            result.append({"market": market, "businessDate": stamp, "insideEffectiveScope": inside,
                           "scheduledOpenAt": start_at.isoformat(), "scheduledCloseAt": end_at.isoformat(),
                           "press": item, "pressPdfSha256": verified["pdfSha256"] if verified else None,
                           "pressPdfPage": verified["page"] if verified else None,
                           "kind": listed | {"document": fact["document"], "bodySha256": sha,
                                            "relationToScheduledOpen": minute_relation(listed["listedMinuteKst"], start_at)},
                           "confirmedScope": "SCHEDULE_ONLY"})
    require({key(row) for row in result} == set(by_day) and
            {key(row) for row in result if row["insideEffectiveScope"]} == set(pack), "SCHEDULE_COVERAGE")
    return result


def compare_interruptions(decision, timeline, press, publication, start, end):
    by_cb = {}
    for item in press.values():
        match = CB_TITLE.fullmatch(item["title"])
        if match:
            identity = ("KOSPI" if match[1] == "유가증권시장" else "KOSDAQ"), item["postedDate"]
            require(identity not in by_cb, "DUPLICATE_PRESS_CB")
            by_cb[identity] = item
    pairs = index(decision["interruptionPairing"])
    require(pairs.keys() == by_cb.keys(), "PRESS_KIND_CB_SET_MISMATCH")
    intervals = {(p.market, p.businessDate, p.kind): p for p in timeline.phases if p.kind in {"HALT", "REOPENING_AUCTION"}}
    require(len(intervals) == sum(p.kind in {"HALT", "REOPENING_AUCTION"} for p in timeline.phases), "DUPLICATE_CB_PHASE")
    events = index(decision["marketEvents"], lambda row: (row["market"], row["document"]))
    result = []
    for (market, stamp), pair in sorted(pairs.items()):
        inside = start <= stamp <= end
        halt = utc(pair["haltAt"])
        quote_resume = utc(pair["quoteAcceptanceResumesAt"])
        continuous_resume = utc(pair["continuousTradingResumesAt"])
        records = []
        for document, effect, event_type in [(pair["haltDocument"], halt, "HALT"),
                                              (pair["resumptionDocument"], quote_resume, "RESUMPTION")]:
            event = events.pop((market, document))
            require(key(event) == (market, stamp) and utc(event["eventAt"]) == effect and
                    event["eventType"] == event_type, "KIND_CB_EVENT_MISMATCH")
            listed = publication[(market, document, event["bodySha256"])]
            require(listed["url"] == event["url"], "KIND_CB_URL_MISMATCH")
            records.append(event | listed | {"relationToEffect": minute_relation(listed["listedMinuteKst"], effect)})
        if inside:
            halted = intervals.pop((market, stamp, "HALT"))
            auction = intervals.pop((market, stamp, "REOPENING_AUCTION"))
            require((halted.startAt, halted.endAt, auction.startAt, auction.endAt) ==
                    (halt, quote_resume, quote_resume, continuous_resume), "CB_TIMELINE_MISMATCH")
        result.append(pair | {"insideEffectiveScope": inside, "press": by_cb[(market, stamp)], "kindEvents": records})
    require(not intervals and not events, "UNMATCHED_CB_EVIDENCE")
    return result


def candidates(decision, rules, calendar, timeline, scheduled, reviewed_at):
    phases = defaultdict(list)
    for phase in timeline.phases:
        phases[(phase.market, phase.businessDate)].append(phase)
    normal = index(decision["promotionDecisions"])
    scheduled_keys = {key(row) for row in scheduled}
    require(not scheduled_keys.intersection(normal) and set(phases) <= set(normal), "CANDIDATE_SCOPE_COLLISION")
    result = []
    for market in MARKETS:
        rule = rules["markets"][market]
        dates = index(rule["candidates"], lambda row: row["businessDate"])
        days = index(calendar["markets"][market]["rows"], lambda row: row["businessDate"])
        require(set(dates) == {stamp for name, stamp in normal if name == market}, "RULE_CANDIDATE_SET_MISMATCH")
        for stamp, row in sorted(dates.items()):
            prior = normal[(market, stamp)]
            matching = [p for p in rule["rulePeriods"] if p["startDate"] <= stamp <= p["endDate"]]
            trade = days[stamp]["krxTradingSchedule"]
            require(len(matching) == 1 and trade["candidate"]["value"] is True and trade["value"] is not False and
                    row["ordinaryRuleConfirmed"] and prior["decision"] == "DEFERRED" and
                    utc(prior["knownAt"]) <= reviewed_at and utc(row["knownAt"]) <= reviewed_at, "RULE_OR_CALENDAR_CONFLICT")
            period = matching[0]
            require(period["continuityConfirmed"] and period["bookIds"] == prior["ruleBookIds"] and
                    (period["nominalOpen"], period["nominalClose"]) == (row["open"], row["close"]) ==
                    (prior["nominalOpen"], prior["nominalClose"]), "RULE_PERIOD_MISMATCH")
            observed = phases[(market, stamp)]
            market_halt = any(p.kind == "HALT" for p in observed)
            coverage = ("PARTIAL_MARKET_RESTRICTION" if market_halt else
                        "PARTIAL_PROGRAM_RESTRICTION" if observed else "RULE_ONLY")
            blockers = [v for v in prior["blockers"] if not (
                market_halt and v == "MARKET_WIDE_INTRADAY_HALT_REQUIRES_INTERVAL_MODEL")]
            require(blockers and not prior["actualSessionConfirmed"] and not prior["includedInReferencePack"], "UNSUPPORTED_PROMOTION")
            result.append(prior | {"coverage": coverage, "blockers": blockers, "knownAt": reviewed_at.isoformat(),
                                   "phaseIds": sorted(p.phaseId for p in observed), "actualOpenAt": None,
                                   "actualCloseAt": None, "wholeSessionConfirmed": False})
    return result


def build(manifest_path, artifacts, job):
    manifest = read_json(read_bytes(manifest_path))
    require(manifest["schemaVersion"] == "SAGOPALGO_H03_AUDIT_SCOPE_V1", "MANIFEST_SCHEMA")
    start, end = manifest["startDate"], manifest["endDate"]
    reviewed_at = utc(manifest["reviewedAt"])
    source = {name: read_json(pinned(artifacts / entry["file"], entry["sha256"]))
              for name, entry in manifest["inputs"].items()}
    decision, rules, calendar, boundary = (source[name] for name in ("decisions", "rules", "calendar", "boundary"))
    for value in (decision, rules, calendar, boundary, source["originalReview"]):
        require((value["startDate"], value["endDate"]) == (start, end), "INPUT_DATE_SCOPE")
        require(not value.get("knownAt") or utc(value["knownAt"]) <= reviewed_at, "FUTURE_INPUT")
    require(decision["rulesSha256"] == boundary["rulesSha256"] == manifest["inputs"]["rules"]["sha256"], "RULE_HASH_LINK")
    require(decision["parentReviewSha256"] == manifest["inputs"]["originalReview"]["sha256"] and
            manifest["inputs"]["boundary"]["sha256"] in decision["reviewReportSha256s"] and
            source["originalReview"]["inventorySha256"] == manifest["inputs"]["kindOriginal"]["sha256"] and
            boundary["inventorySha256"] == manifest["inputs"]["kindBoundary"]["sha256"], "KIND_HASH_LINK")
    timeline = Timeline.model_validate(source["timeline"])
    require(timeline.provenance == "EVIDENCED_PARTIAL" and timeline.createdAt <= reviewed_at and
            timeline.sourceDecisionSha256 == manifest["inputs"]["decisions"]["sha256"], "TIMELINE_SOURCE")
    press, details, query_counts = read_press(job, manifest, reviewed_at)
    reviewed_bodies = { (row["market"], row["document"], row["bodySha256"]): row
                       for review in (source["originalReview"], boundary) for row in review["reviewedBodies"]}
    publication, corrections = kind_publication([source["kindOriginal"], source["kindBoundary"], source["kindCategory"]],
                                               list(reviewed_bodies.values()), reviewed_at)
    scheduled = schedules(details, job, manifest["reviewedPressSchedules"], boundary["scheduledSessions"],
                          decision["referencePacks"], publication, start, end)
    interruptions = compare_interruptions(decision, timeline, press, publication, start, end)
    rows = candidates(decision, rules, calendar, timeline, scheduled, reviewed_at)
    return {"schemaVersion": "SAGOPALGO_H03_SESSION_AUDIT_V1", "startDate": start, "endDate": end,
            "knownAt": reviewed_at.isoformat(), "sourceHashes": manifest["inputs"], "pressReceiptHashes": manifest["pressReceipts"],
            "pressSearch": {"from": manifest["publicationSearchStart"], "through": manifest["publicationSearchEnd"],
                            "queryCounts": query_counts, "uniqueNotices": len(press),
                            "verifiedPublicRequests": len(manifest["pressReceipts"]) * 2},
            "otherPressDetails": [details[number] for number in sorted(details) if number not in
                                  {row["press"]["noticeId"] for row in scheduled + interruptions}],
            "candidateCounts": {market: dict(Counter(r["coverage"] for r in rows if r["market"] == market)) for market in MARKETS},
            "candidateDecisions": rows, "scheduledExceptions": scheduled, "circuitBreakerComparisons": interruptions,
            "scopedCorrectionLineages": corrections, "actualWholeSessionsPromoted": 0,
            "allHistoricalSessionsComplete": False, "historicalFirstPublicationConfirmed": False,
            "fullTemporaryChangeInventoryComplete": False, "fullCorrectionLineageComplete": False,
            "usableForTraining": False, "usableForStrategyValidation": False, "usableForTrading": False}


def as_of(report, market, stamp, at):
    date.fromisoformat(stamp)
    visible = utc(at) >= utc(report["knownAt"])
    return {"market": market, "businessDate": stamp, "auditVisible": visible,
            **{name: [row for row in report[name] if key(row) == (market, stamp)] if visible else []
               for name in ("candidateDecisions", "scheduledExceptions", "circuitBreakerComparisons")}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "audit", "as-of"))
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--job", type=Path, required=True)
    parser.add_argument("--market", choices=MARKETS)
    parser.add_argument("--date")
    parser.add_argument("--at")
    args = parser.parse_args()
    report = build(args.manifest, args.artifacts, args.job)
    immutable_json(args.job / "report.json", report, require_existing=args.action != "build")
    if args.action == "as-of":
        if not (args.market and args.date and args.at):
            parser.error("as-of requires --market, --date and --at")
        result = as_of(report, args.market, args.date, args.at)
    else:
        result = report["candidateCounts"]
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
