"""Audit issuer-reported cash dividends against the fixed Seibro payment census."""

import argparse
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path
import re

from .corporate_action_outcomes import SCOPE, VIEWER, capture, checked_read, require
from .dataset import digest, read_bytes, read_json
from .krx_baseline_validation import immutable_json
from .market_calendar_evidence import text
from .models import utc
from .session_evidence import validate_url
from .session_notice_inventory import body_path, viewer_documents


SCHEMA = "SAGOPALGO_HISTORICAL_DIVIDEND_PAYMENTS_V1"
CONFIRMED = "ISSUER_REPORTED_PAYMENT_CONFIRMED"
UNRESOLVED = "REVIEWED_PAYMENT_UNCONFIRMED"
UNREVIEWED = "NO_ISSUER_REPORT_REVIEWED"
FIELDS = {"issuer", "recordDate", "actualPaymentDate", "commonCashPerShare"}
REASONS = {"MISSING_ACTUAL_PAYMENT_DATE", "PLANNED_DATE_ONLY", "OTHER_DISTRIBUTION",
           "MISSING_RECORD_DATE", "MISSING_COMMON_SHARE_AMOUNT", "CONFLICTING_FIELD",
           "DIFFERENT_INSTRUMENT_OR_CURRENCY"}
POST_PAYMENT = re.compile(r"실제\s*지급일|지급\s*(?:하였|되었|완료|했|을 완료)")
CORRECTION_TITLE = re.compile(r"\[정정\]\s*현금[ㆍ·]현물\s*배당\s*결정")


def event_key(row, *, prior=False):
    payment, amount = ("paymentDate", "amount") if prior else ("displayedPaymentDate", "cashAmountPerShare")
    return row["market"], row["symbol"], row["recordDate"], row[payment], Decimal(row[amount])


def report_source(job, name, pin, at, notices):
    url = pin["url"]
    validate_url(url)
    raw, proof = capture(job, {name: pin["sha256"]}, name, {"url": url, "method": "GET", "parameters": None}, at)
    year, month, day, _, document = url.split("/")[4:9]
    filed = date.fromisoformat(f"{year}-{month}-{day}")
    require(filed.isoformat() <= SCOPE[2], "DIVIDEND_REPORT_DATE")
    issuer = None
    if "listedReceipt" in pin:
        notice = notices[pin["listedReceipt"]]
        require(notice["membership"]["status"] == "SAME_DATE_NAME_MATCH"
                and notice["listedMinuteKst"][:10] == filed.isoformat(), "DIVIDEND_LISTED_ISSUER_IDENTITY")
        candidate, = notice["membership"]["candidates"]
        issuer = notice["market"], candidate["symbol"]
        receipt = notice["receipt"]
        viewer_key, route_key = "view-" + receipt, "route-" + receipt
        viewer, viewer_proof = capture(job, {viewer_key: pin["viewerSha256"]}, viewer_key,
                                       {"url": notice["sourceUrl"], "method": "GET", "parameters": None}, at)
        require(any(item["document"] == document and item["correctionMarked"] == notice["titleCorrectionFlag"]
                    and item["label"].endswith(f"({filed:%Y.%m.%d})") for item in viewer_documents(viewer)),
                "DIVIDEND_LISTED_VERSION")
        route, route_proof = capture(job, {route_key: pin["routeSha256"]}, route_key,
                                     {"url": VIEWER, "method": "POST",
                                      "parameters": {"method": "searchContents", "docNo": document}}, at)
        require(body_path(route, document) == url, "DIVIDEND_LISTED_BODY")
        proof |= {"receipt": receipt, "viewer": viewer_proof, "route": route_proof}
    else:
        require(document[:8] == filed.strftime("%Y%m%d"), "DIVIDEND_REPORT_DATE")
    return text(raw), proof | {"reportedOn": filed.isoformat(), "documentNumber": document}, issuer


def confirm(row, fields, sources):
    require(fields.keys() == FIELDS, "DIVIDEND_FIELDS")
    evidence = {}
    for field, reference in fields.items():
        body, proof, issuer = sources[reference["source"]]
        marks = reference["markers"]
        require(issuer is None or issuer == (row["market"], row["symbol"]), "DIVIDEND_REPORT_ISSUER")
        require(isinstance(marks, list) and (bool(marks) or (field == "issuer" and issuer is not None))
                and all(mark and mark in body for mark in marks),
                "DIVIDEND_BODY_MARKERS")
        evidence[field] = proof
    require(row["displayedPaymentDate"] < evidence["actualPaymentDate"]["reportedOn"], "DIVIDEND_POST_PAYMENT_REPORT")
    require(POST_PAYMENT.search(" ".join(fields["actualPaymentDate"]["markers"])), "DIVIDEND_PAYMENT_COMPLETION_MARKER")
    for field, key in (("actualPaymentDate", "displayedPaymentDate"), ("recordDate", "recordDate")):
        expected = tuple(map(int, row[key].split("-")))
        marks = " ".join(fields[field]["markers"])
        dates = re.findall(r"(?<!\d)((?:20)?\d{2})(?:년\s*|[-./]\s*)(\d{1,2})(?:월\s*|[-./]\s*)(\d{1,2})(?!\d)", marks)
        require(expected in {(int(year) if len(year) == 4 else 2000 + int(year), int(month), int(day))
                             for year, month, day in dates}, "DIVIDEND_DATE_MARKER")
    amounts = re.findall(r"[0-9][0-9,]*(?:\.[0-9]+)?", " ".join(fields["commonCashPerShare"]["markers"]))
    require(Decimal(row["cashAmountPerShare"]) in {Decimal(value.replace(",", "")) for value in amounts},
            "DIVIDEND_AMOUNT_MARKER")
    return evidence


def summarize(rows):
    grouped = defaultdict(list)
    markets = defaultdict(Counter)
    for row in rows:
        year = row["displayedPaymentDate"][:4]
        grouped[year, row["market"], row["symbol"]].append(row)
        markets[year, row["market"]][row["status"]] += 1
    return {
        "statusCounts": dict(Counter(row["status"] for row in rows)),
        "marketYears": [{"paymentYear": year, "market": market, "counts": dict(counts)}
                       for (year, market), counts in sorted(markets.items())],
        "issuerYears": [{"paymentYear": year, "market": market, "symbol": symbol,
                         "counts": dict(Counter(row["status"] for row in events)), "events": events}
                        for (year, market, symbol), events in sorted(grouped.items())],
    }


def correction_candidates(candidates, notices):
    securities = defaultdict(list)
    for row in candidates:
        securities[row["market"], row["symbol"]].append(row)
    result = {}
    for notice in notices:
        if (not CORRECTION_TITLE.fullmatch(notice["title"]) or "title/dividend" not in notice["routes"]
                or notice["membership"]["status"] != "SAME_DATE_NAME_MATCH"):
            continue
        issuer, = notice["membership"]["candidates"]
        filed = date.fromisoformat(notice["listedMinuteKst"][:10])
        matches = [row["sourceRowSha256"] for row in securities[notice["market"], issuer["symbol"]]
                   if 0 < (filed - date.fromisoformat(row["displayedPaymentDate"])).days <= 90]
        if matches:
            result[notice["receipt"]] = matches
    return result


def build(manifest, artifacts, job):
    raw = read_bytes(manifest)
    spec = read_json(raw)
    require(spec["schemaVersion"] == SCHEMA, "DIVIDEND_SCHEMA")
    at = utc(spec["reviewedAt"])
    inputs = {name: read_json(checked_read(artifacts / pin["path"], pin["sha256"]))
              for name, pin in spec["inputs"].items()}
    require(all(utc(value["knownAt"]) <= at for value in inputs.values()), "DIVIDEND_FUTURE_INPUT")
    candidates = [row for row in inputs["census"]["dividend"]["dividendRows"] if row["status"] == "DISPLAYED_DATE_AGREES"]
    by_event = {event_key(row): row for row in candidates}
    by_hash = {row["sourceRowSha256"]: row for row in candidates}
    require(len(candidates) == len(by_event) == len(by_hash) == 4343, "DIVIDEND_CANDIDATE_SCOPE")
    prior = {}
    for source in ("census", "followup"):
        for entry in inputs[source]["issuerPayments"]:
            row_hash = by_event[event_key(entry, prior=True)]["sourceRowSha256"]
            require(row_hash not in prior, "DIVIDEND_PRIOR_DUPLICATE")
            prior[row_hash] = {"priorAudit": entry.get("evidence") or [entry["issuerEvidence"]]}
    require(len(prior) == 6, "DIVIDEND_PRIOR_SCOPE")

    notices = {row["receipt"]: row for row in inputs["inventory"]["candidateRows"]}
    sources = {name: report_source(job, name, pin, at, notices) for name, pin in spec["sources"].items()}
    corrections = correction_candidates(candidates, notices.values())
    require(all("correction-" + receipt in sources for receipt in corrections), "DIVIDEND_CORRECTION_COVERAGE")
    cases = {}
    for item in spec["confirmed"]:
        row_hash = item["rowSha256"]
        require(row_hash in by_hash and row_hash not in prior and row_hash not in cases, "DIVIDEND_CONFIRMATION_SCOPE")
        cases[row_hash] = confirm(by_hash[row_hash], item["fields"], sources)
    reviews = defaultdict(list)
    for item in spec["unconfirmedReviews"]:
        row_hash = item["rowSha256"]
        require(row_hash in by_hash and item["reason"] in REASONS, "DIVIDEND_REVIEW_SCOPE")
        _, proof, issuer = sources[item["source"]]
        row = by_hash[row_hash]
        require(issuer is None or issuer == (row["market"], row["symbol"]), "DIVIDEND_REVIEW_ISSUER")
        reviews[row_hash].append({"reason": item["reason"], "evidence": proof, "reference": item["reference"],
                                  "detail": item.get("detail")})

    rows = []
    for key, row in sorted(by_event.items()):
        row_hash = row["sourceRowSha256"]
        review = reviews.get(row_hash, [])
        issuer_report = prior.get(row_hash) or cases.get(row_hash)
        status = UNREVIEWED
        if issuer_report:
            status = CONFIRMED
        elif review:
            status = UNRESOLVED
        rows.append({"market": key[0], "symbol": key[1], "issuer": row["issuer"], "recordDate": key[2],
                     "displayedPaymentDate": key[3], "commonCashPerShare": row["cashAmountPerShare"],
                     "actualPaymentDate": key[3] if issuer_report else None, "status": status,
                     "ksdRowSha256": row_hash, "ksdEvidence": row["evidence"],
                     "ksdScheduleRowSha256": row["scheduleMatches"][0]["sourceRowSha256"],
                     "issuerEvidence": issuer_report, "reviews": review})
    return {"schemaVersion": SCHEMA, "manifestSha256": digest(raw), "knownAt": at.isoformat(),
            "seibroCandidateCount": len(rows), "previouslyConfirmed": len(prior), "newlyConfirmed": len(cases),
            "reviewedSources": len(sources), "correctionCandidates": corrections,
            **summarize(rows), "historicalFirstAvailabilityConfirmed": False,
            "usableForTraining": False, "usableForTrading": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "audit"))
    for name in ("manifest", "artifacts", "job"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    report = build(args.manifest, args.artifacts, args.job)
    immutable_json(args.job / "report.json", report, require_existing=args.action == "audit")
    print(report["statusCounts"], len(report["issuerYears"]), report["reviewedSources"])


if __name__ == "__main__":
    main()
