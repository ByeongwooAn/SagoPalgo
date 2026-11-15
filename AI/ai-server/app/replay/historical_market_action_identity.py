"""Resolve historical common-share identifiers for KIND action notices with different names."""

import argparse
from collections import Counter, defaultdict
from datetime import date
from functools import lru_cache
from pathlib import Path
import re

from . import krx_universe, krx_universe_history
from .corporate_action_event_audit import name_key
from .corporate_action_outcomes import SCOPE, capture, checked_read, require
from .dataset import canonical, digest, read_bytes, read_json
from .krx_baseline_validation import immutable_json
from .market_calendar_evidence import text
from .models import utc


SCHEMA = "SAGOPALGO_H05_HISTORICAL_ACTION_IDENTITY_V1"
MISMATCH = "HISTORICAL_BODY_NAME_DIFFERS_FROM_VIEWER"


def targets(ledger):
    seen = set()
    for notice in (read_json(line) for line in ledger.splitlines()):
        receipt = notice["receipt"]
        require(receipt not in seen, "ACTION_IDENTITY_DUPLICATE_RECEIPT")
        seen.add(receipt)
        for version in [None, *notice.get("versions", [])]:
            review = notice if version is None else version.get("review", {})
            if MISMATCH not in (review.get("reason"), review.get("identityReason")):
                continue
            receipt_date = notice["listedMinuteKst"][:10]
            publication = receipt_date
            if version is not None:
                displayed = re.search(r"\((\d{4}\.\d{2}\.\d{2})\)\s*$", version["label"])
                require(displayed is not None, "ACTION_IDENTITY_VERSION_PUBLICATION_DATE")
                publication = date.fromisoformat(displayed[1].replace(".", "-")).isoformat()
            proof = notice["evidence"] if version is None else notice["evidence"] + version["evidence"]
            applied = review.get("appliedDate")
            yield {
                "receipt": receipt, "document": notice.get("document") if version is None else version["document"],
                "market": notice["market"], "publishedIssuer": review["publishedIssuer"],
                "kindDisplayName": notice["listIssuer"], "viewerSymbol": review["viewerSymbol"],
                "receiptPublicationDate": receipt_date, "publicationDate": publication, "appliedDate": applied,
                "referenceDate": applied or publication,
                "referenceBasis": "PUBLISHED_APPLICATION_DATE" if applied else "NOTICE_PUBLICATION_DATE_ONLY",
                "actionEvidence": proof,
            }


def identity_name(value):
    return name_key(value, instrument=True)


def by_name(issue):
    return {identity_name(issue[field]) for field in ("name", "abbreviatedName")} - {""}


def role_names(fact, side):
    context = fact["instrumentContext"][side]
    names = [fact.get(side + "Name"), fact.get(side + "Korean"), fact.get("observed" + side.title() + "Name"),
             context["name"], context["abbreviatedName"]]
    if side == "after":
        names.append(fact.get("afterAbbreviatedName"))
    return {identity_name(name) for name in names if name}


def notice_proofs(fact):
    versions = fact.get("versions") or [fact]
    links = ["sourceUrl", "sourceSha256", "receipt"]
    proof = [{key: version[key] for key in links} for version in versions if version.get("sourceUrl")]
    if fact.get("existingListingEvidence"):
        proof.append({key: fact["existingListingEvidence"][key] for key in links})
    return {"exchangeRelatedDate": fact["date"], "dateBasis": fact["dateBasis"],
            "beforeName": fact["beforeName"], "afterName": fact["afterName"],
            "knownAt": fact["knownAt"], "documents": proof}


def source_reader(job, plan, latest):
    @lru_cache(maxsize=32)
    def snapshot(stamp, market):
        entry = krx_universe_history.observations(job, plan, latest, stamp).get(market)
        if entry is None or entry["state"] != "CAPTURED":
            return {}
        raw = krx_universe_history.entry_raw(job, entry, entry["seed"])
        issues = {}
        for row in krx_universe_history.envelope(raw):
            if row["KIND_STKCERT_TP_NM"] != "보통주" or row["SECUGRP_NM"] not in krx_universe.SECURITIES:
                continue
            symbol = row["ISU_SRT_CD"]
            require(symbol not in issues, "ACTION_IDENTITY_AMBIGUOUS_CODE")
            issues[symbol] = {
                "symbol": symbol, "isin": row["ISU_CD"], "name": row["ISU_NM"],
                "abbreviatedName": row["ISU_ABBRV"], "market": market, "basisDate": stamp,
                "shareType": row["KIND_STKCERT_TP_NM"], "securityType": row["SECUGRP_NM"],
                "knownAt": entry["capturedAt"], "sourceSha256": entry["sha256"],
                "sourceRowSha256": digest(canonical(row)),
            }
        return issues

    return snapshot


def same_instrument(left, right):
    return (left["market"], left["symbol"], left["isin"]) == (right["market"], right["symbol"], right["isin"])


def name_used_by_other_issue(name, issue, issues):
    return any(
        name in by_name(candidate) for symbol, candidate in issues.items() if symbol != issue["symbol"])


def matching_fact(name, issue, facts):
    for fact in facts:
        side = "before" if issue["basisDate"] < fact["date"] else "after"
        aliases = role_names(fact, side)
        if name in aliases and aliases & by_name(issue):
            return fact
    return None


def read_supplements(spec, job):
    cache = {}
    for label, source in spec["officialCaptures"].items():
        raw, proof = capture(job, {label: source["receiptSha256"]}, label, source["request"], utc(spec["reviewedAt"]))
        value = "".join(text(raw).split())
        require(all("".join(fragment.split()) in value for fragment in source["requiredText"]),
                "ACTION_IDENTITY_NOTICE_TEXT_MISMATCH")
        cache[label] = proof
    return {item["id"]: item | {"officialEvidence": [cache[label] for label in item["captures"]]}
            for item in spec["reviewedLinks"]}


def matching_supplement(target, issue, links):
    for link in links:
        if (target["receipt"] in link["receipts"] and same_instrument(issue, link)
                and identity_name(target["publishedIssuer"]) == identity_name(link["bodyName"])
                and identity_name(link["exchangeName"]) in by_name(issue)):
            return link
    return None


def resolve(target, snapshot, facts_by_instrument, supplements):
    result = target | {"historicalSymbol": None, "historicalIsin": None}
    stamp = target["referenceDate"]
    if not SCOPE[0] <= stamp <= SCOPE[1]:
        return result | {"status": "OUTSIDE_H05_EFFECTIVE_SCOPE"}
    issue_set = snapshot(stamp, target["market"])
    issue = issue_set.get(target["viewerSymbol"])
    if issue is None:
        return result | {"status": "HISTORICAL_COMMON_SHARE_SNAPSHOT_UNAVAILABLE"}
    name = identity_name(target["publishedIssuer"])
    facts = facts_by_instrument.get((issue["market"], issue["symbol"], issue["isin"]), ())
    attached = [notice_proofs(fact) for fact in facts]
    result["referenceObservation"] = issue
    result["availableNameNotices"] = attached
    result["kindDisplayNameMatchesReferenceObservation"] = identity_name(target["kindDisplayName"]) in by_name(issue)
    if name_used_by_other_issue(name, issue, issue_set):
        return result | {"status": "HISTORICAL_NAME_CONFLICTS_WITH_OTHER_SYMBOL"}
    binding = matching_supplement(target, issue, supplements)
    if binding:
        result["supplementalNameEvidence"] = binding

    publication = target["publicationDate"]
    if name in by_name(issue):
        basis = "ISSUER_NAME_MATCH_ON_REFERENCE_DATE"
    elif (fact := matching_fact(name, issue, facts)) is not None:
        basis = "ISSUER_NAME_LINKED_BY_AUDITED_CHANGE_OR_ALIAS_NOTICE"
        result["matchedNameNotice"] = notice_proofs(fact)
    elif binding:
        basis = "ISSUER_NAME_LINKED_BY_ADDITIONAL_OFFICIAL_NOTICE"
    else:
        prior = snapshot(publication, target["market"])
        published_issue = prior.get(issue["symbol"])
        if (published_issue is None or not same_instrument(issue, published_issue)
                or name not in by_name(published_issue) or name_used_by_other_issue(name, published_issue, prior)):
            return result | {"status": "HISTORICAL_NAME_AND_IDENTIFIER_LINK_UNRESOLVED"}
        basis = "ISSUER_NAME_MATCH_AT_PUBLICATION_SAME_INSTRUMENT_ON_REFERENCE_DATE"
        result["publicationObservation"] = published_issue

    observed_times = [proof["observedAt"] for proof in target["actionEvidence"]]
    observed_times.extend([issue["knownAt"], *(fact["knownAt"] for fact in attached)])
    if binding:
        observed_times.extend(proof["observedAt"] for proof in binding["officialEvidence"])
    if "publicationObservation" in result:
        observed_times.append(result["publicationObservation"]["knownAt"])
    return result | {"status": "HISTORICAL_COMMON_SHARE_IDENTITY_VERIFIED", "identityBasis": basis,
                     "historicalSymbol": issue["symbol"], "historicalIsin": issue["isin"],
                     "knownAt": max(utc(value) for value in observed_times).isoformat()}


def build(manifest, ledger, artifacts, job):
    raw = read_bytes(manifest)
    spec = read_json(raw)
    require(spec["schemaVersion"] == SCHEMA, "ACTION_IDENTITY_SCHEMA")
    ledger_raw = checked_read(ledger, spec["monthlyLedgerSha256"])
    inputs = {name: checked_read(artifacts / pin["path"], pin["sha256"]) for name, pin in spec["inputs"].items()}
    history_job = (artifacts / spec["inputs"]["historyPlan"]["path"]).parent
    require(history_job / "journal.json" == artifacts / spec["inputs"]["historyJournal"]["path"],
            "ACTION_IDENTITY_HISTORY_PATH")
    plan, _, _, latest = krx_universe_history.load_job(history_job)
    require(plan["config"]["sourceKind"] == "PROVIDER_HISTORICAL", "ACTION_IDENTITY_HISTORY_SOURCE")
    snapshot = source_reader(history_job, plan, latest)
    facts = defaultdict(list)
    for name in ("nameChanges", "aliasChanges"):
        for fact in read_json(inputs[name])["facts"]:
            if fact["classification"] == "MARKET_TRANSFER_COMMON_SHARE_LABEL":
                continue
            facts[fact["market"], fact["stockCode"], fact["historyIsin"]].append(fact)
    supplements = list(read_supplements(spec, job).values())
    rows = [resolve(target, snapshot, facts, supplements) for target in targets(ledger_raw)]
    return {
        "schemaVersion": SCHEMA, "manifestSha256": digest(raw), "monthlyLedgerSha256": digest(ledger_raw),
        "receiptCount": len({row["receipt"] for row in rows}), "targetCount": len(rows),
        "statusCounts": dict(Counter(row["status"] for row in rows)),
        "historicalFirstAvailabilityConfirmed": False, "usableForTrading": False, "usableForTraining": False,
        "rows": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "audit"))
    for name in ("manifest", "ledger", "artifacts", "job", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    report = build(args.manifest, args.ledger, args.artifacts, args.job)
    immutable_json(args.output, report, require_existing=args.action == "audit")
    print(report["receiptCount"], report["targetCount"], report["statusCounts"])


if __name__ == "__main__":
    main()
