"""Audit selected issuer payments, exchange actions and restructuring follow-ups."""

import argparse
from collections import Counter
from decimal import Decimal
from pathlib import Path

from .corporate_action_outcome_census import notice_review, notice_role
from .corporate_action_outcomes import SCOPE, capture, checked_read, require
from .dataset import digest, read_bytes, read_json
from .krx_baseline_validation import immutable_json
from .market_calendar_evidence import text
from .models import utc
from .session_evidence import validate_url

SCHEMA = "SAGOPALGO_HISTORICAL_ACTIONS_FOLLOWUP_V1"
WINDOWS = {"marketActions": {"from": "2023-12-01", "through": SCOPE[2]},
           "cancellation": {"from": SCOPE[0], "through": SCOPE[0]}}


def action_sample(parent):
    candidates = [(row, notice_role(row, WINDOWS)) for row in parent["candidateRows"]
                  if row["listedMinuteKst"][:10] >= WINDOWS["marketActions"]["from"]]
    candidates = [(row, role) for row, role in candidates if role]
    selected, counts = set(), Counter()
    for row, role in sorted(candidates, key=lambda item: (item[0]["listedMinuteKst"], item[0]["receipt"])):
        if row["titleCorrectionFlag"] or row["membership"]["status"] != "SAME_DATE_NAME_MATCH":
            continue
        group = row["market"], role, row["listedMinuteKst"][:4]
        if counts[group] < 2:
            counts[group] += 1
            selected.add(row["receipt"])
    return candidates, selected


def issuer_payment(case, bodies, candidates, market_identities):
    paid = case["paymentDate"]
    data = bodies[case["source"]]
    reported_after_payment = data["sourceUrl"].split("/")[4:7]
    require(SCOPE[0] <= paid <= SCOPE[1] and paid < "-".join(reported_after_payment) <= SCOPE[2], "PAYMENT_REPORT_DATE")
    require(bool(case["markers"]) and all(marker in data["body"] for marker in case["markers"]), "ISSUER_PAYMENT_FIELDS")
    if case.get("noticeReceipt"):
        identities = [candidate for candidate in market_identities if candidate["receipt"] == case["noticeReceipt"]]
        require(len(identities) == 1 and identities[0]["market"] == case["market"] and
                identities[0]["membership"]["status"] == "SAME_DATE_NAME_MATCH" and
                [c["symbol"] for c in identities[0]["membership"]["candidates"]] == [case["symbol"]],
                "PAYMENT_NOTICE_ISSUER_IDENTITY")
    matched = [r for r in candidates if r["status"] == "DISPLAYED_DATE_AGREES" and
               (r["market"], r["symbol"], r["recordDate"], r["displayedPaymentDate"], Decimal(r["cashAmountPerShare"])) ==
               (case["market"], case["symbol"], case["recordDate"], paid, Decimal(case["amount"]))]
    require(len(matched) == 1, "ISSUER_PAYMENT_KSD_MATCH")
    return {k: case[k] for k in ("market", "symbol", "recordDate", "paymentDate", "amount")} | {
        "status": "ISSUER_REPORTED_PAYMENT_MATCH", "ksdRowSha256": matched[0]["sourceRowSha256"],
        "issuerEvidence": data["proof"], "ksdEvidence": matched[0]["evidence"]}


def restructuring_review(case, bodies, parent):
    require(case["fields"].keys() == case["markersByField"].keys(), "RESTRUCTURING_MARKER_SCOPE")
    prior = {r["receipt"]: r for r in parent["newlyAuditedE003Filings"]}
    filings = [prior[receipt] for receipt in case["e003Receipts"]]
    require(all(case["referenceDate"] in {day for value in row["schedule"] if value["role"] == "REFERENCE_DATE"
                                         for day in value["dates"]} for row in filings), "RESTRUCTURING_REFERENCE_DATE")
    evidence = {}
    for field, marks in case["markersByField"].items():
        require(bool(marks), "RESTRUCTURING_MARKER_SCOPE")
        evidence[field] = []
        for source, markers in marks.items():
            require(bool(markers) and all(marker in bodies[source]["body"] for marker in markers), "RESTRUCTURING_BODY_FIELDS")
            evidence[field].append(bodies[source]["proof"])
    return {"case": case["case"], "referenceDate": case["referenceDate"], "e003Receipts": case["e003Receipts"],
            "reportedFields": case["fields"], "fieldEvidence": evidence, "registryExtractVerified": False,
            "legalEffectiveDate": None}


def build(manifest, artifacts, job):
    raw = read_bytes(manifest)
    spec = read_json(raw)
    require(spec["schemaVersion"] == SCHEMA, "FOLLOWUP_SCHEMA")
    at = utc(spec["reviewedAt"])
    inputs = {key: read_json(checked_read(artifacts / p["path"], p["sha256"])) for key, p in spec["inputs"].items()}
    require(all(utc(report["knownAt"]) <= at for report in inputs.values()), "FOLLOWUP_FUTURE_INPUT")
    inventory, outcomes, restructuring = (inputs[key] for key in ("inventory", "outcomes", "restructuring"))
    candidates, targets = action_sample(inventory)
    require(len(candidates) == 4033 and len(targets) == 70, "FOLLOWUP_ACTION_SAMPLE_SCOPE")
    source = inventory | {"candidateRows": [row for row, _ in candidates if row["receipt"] in targets]}
    actions = notice_review(job, spec["actionReceipts"], source, at, SCOPE[:2], WINDOWS, set())
    require(len(actions) == len(targets), "FOLLOWUP_ACTION_REPORT_SCOPE")
    bodies = {}
    named_sources = {case["source"] for case in spec["payments"]} | {
        name for case in spec["restructuringCases"] for marks in case["markersByField"].values() for name in marks}
    require(named_sources == spec["issuerReceipts"].keys(), "FOLLOWUP_ISSUER_RECEIPT_SCOPE")
    for key, pin in spec["issuerReceipts"].items():
        name, url = "proof-followup-" + key, pin["url"]
        validate_url(url)
        body, proof = capture(job, {name: pin["sha256"]}, name, {"method": "GET", "url": url, "parameters": None}, at)
        bodies[key] = {"body": text(body), "proof": proof, "sourceUrl": url}
    payments = [issuer_payment(case, bodies, outcomes["dividend"]["dividendRows"], inventory["candidateRows"])
                for case in spec["payments"]]
    cases = [restructuring_review(case, bodies, restructuring) for case in spec["restructuringCases"]]
    require(len({(p["market"], p["symbol"], p["recordDate"]) for p in payments}) == len(payments), "FOLLOWUP_PAYMENT_DUPLICATE")
    return {"schemaVersion": SCHEMA, "manifestSha256": digest(raw), "knownAt": at.isoformat(),
            "actionCandidates": len(candidates), "actionSample": actions, "actionCounts": dict(Counter(r["status"] for r in actions)),
            "issuerPayments": payments, "restructuringCases": cases, "historicalFirstAvailabilityConfirmed": False,
            "usableForTraining": False, "usableForTrading": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "audit"))
    for name in ("manifest", "artifacts", "job"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    report = build(args.manifest, args.artifacts, args.job)
    immutable_json(args.job / "report.json", report, require_existing=args.action == "audit")
    print(report["actionCounts"], len(report["issuerPayments"]), len(report["restructuringCases"]))


if __name__ == "__main__":
    main()
