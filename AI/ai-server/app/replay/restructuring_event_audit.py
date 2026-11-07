"""Resolve H04 review groups while preserving distinct evidence for each filing."""

from collections import defaultdict
from datetime import date
import re

from . import corporate_facts as facts
from .action_listing_inventory import changed_listing
from .corporate_action_outcomes import checked_read, require
from .dataset import read_json
from .models import utc
from .restructuring_census import DATE, original_xml
from .universe_reconciliation import normalized_name

PARTY_ROLES = {"존속회사": "SURVIVOR", "소멸회사": "ABSORBED"}


def party_signature(rows):
    signatures = set()
    for cells in rows:
        parties = []
        for cell in cells:
            match = re.fullmatch(r"(.+?)\s*\((존속회사|소멸회사)\)", cell)
            if match:
                parties.append((PARTY_ROLES[match[2]], normalized_name(match[1])))
            elif re.search(r"존속회사|소멸회사", cell):
                return None
        if (len(set(parties)) >= 2 and len(set(parties)) == len(parties) and
                sum(role == "SURVIVOR" for role, _ in parties) == 1 and all(name for _, name in parties)):
            signatures.add(tuple(sorted(parties)))
    return next(iter(signatures)) if len(signatures) == 1 else None


def kind_anchor(row):
    versions = row.get("viewerVersions") or []
    own = row.get("selectedDocument")
    originals = [v["document"] for v in versions if not v["correctionMarked"]]
    if own and len(originals) == 1 and any(v["document"] == own for v in versions):
        return originals[0]
    return None


def reference_dates(row, scope):
    dates = {d for field in row.get("schedule", []) if field["role"] == "REFERENCE_DATE" for d in field["dates"]}
    return sorted(dates) if len(dates) == 1 and scope[0] <= next(iter(dates)) <= scope[1] else []


def reported_registration(artifacts, census_pin, row):
    receipt = row["receipt"]
    path = (artifacts / census_pin["path"]).parent / "captures" / f"dart-{receipt}" / "body.bin"
    root, proof = original_xml(checked_read(path, row["archiveSha256"]), receipt)
    require(proof["bodySha256"] == row["bodySha256"], "RESTRUCTURING_BODY_BINDING")
    sections = root.findall("./BODY/SECTION-1")
    require(len(sections) == 1, "RESTRUCTURING_REGISTRATION_SECTION")
    body = facts.text(sections[0])
    matches = {date(*map(int, parts)).isoformat()
               for parts in re.findall(DATE + r"\s+(?:분할|합병)등기\s*완료\s*된\s*건", body)}
    # A short day statement is accepted only when the preceding date names the
    # same year and month and the completion day matches the filing date.
    for y, m, old, completed in re.findall(
            r"종료보고서 최초 예정일은 " + DATE + r"이었으나, 등기완료가 (\d{1,2})일 진행되어", body):
        filed = date(*map(int, (y, m, completed))).isoformat()
        if int(old) < int(completed) and filed == row["receiptDate"]:
            matches.add(filed)
    if len(matches) == 1:
        return {"reportedDate": next(iter(matches)), "basis": "ISSUER_REPORTED_REGISTRATION_COMPLETION",
                "sourceUrl": row["sourceUrl"], "bodySha256": proof["bodySha256"], "receipt": receipt,
                "registryRecordVerified": False}
    return None


def audit(artifacts, inputs, listing_rows, at):
    parents = {key: read_json(checked_read(artifacts / pin["path"], pin["sha256"])) for key, pin in inputs.items()}
    census, reviewed = parents["census"], parents["reviewed"]
    require(all(utc(source["knownAt"]) <= at for source in parents.values()), "FUTURE_RESTRUCTURING_INPUT")
    scope = census["startDate"], census["endDate"]
    require(scope == (reviewed["startDate"], reviewed["endDate"]), "RESTRUCTURING_SCOPE")
    groups, comparisons, listing_candidates, filings = defaultdict(list), defaultdict(list), defaultdict(list), {}
    cases = reviewed["cases"]
    verified_receipts = defaultdict(set)
    for case in cases:
        for source in case["sources"].values():
            for key in ("receipt", "filingReceipt"):
                if source.get(key):
                    verified_receipts[source[key]].add(case["caseId"])
    audited_receipts = {f["receipt"] for f in census["newlyAuditedE003Filings"]}
    reused = [r for r in reviewed["candidateFilings"] if r["receipt"] in verified_receipts and
              r["receipt"] not in audited_receipts]
    require(len(reused) == census["reusedE003Filings"], "REUSED_RESTRUCTURING_SCOPE")
    for route, rows in (
        ("E003", census["newlyAuditedE003Filings"] + reused),
        ("KIND_ISSUANCE", census["kindIssuanceFilings"]),
    ):
        for row in rows:
            identity = f"{route}/{row['receipt']}"
            require(identity not in filings, "RESTRUCTURING_DUPLICATE_FILING")
            purpose = row.get("documentPurpose", "")
            transaction = purpose.strip("()")
            dates = reference_dates(row, scope)
            issuer = row.get("issuerDisplayName", row.get("issuer"))
            market = row["market"]
            body_cases = sorted(verified_receipts[row["receipt"]])
            evidence = []
            if route == "KIND_ISSUANCE" and row["bodyScope"] != "MERGER_OR_DIVISION":
                group = ("OUTSIDE_TRANSACTION_SCOPE", identity)
            elif len(body_cases) == 1:
                group = ("REVIEWED_CASE_RECEIPT", body_cases[0])
                evidence = body_cases
            elif dates and route == "E003" and transaction == "합병" and (parties := party_signature(row["partyRows"])):
                group = ("PARTIES_AND_REFERENCE_DATE", dates[0], parties)
                evidence = row["partyRows"]
            elif dates and route == "KIND_ISSUANCE" and (anchor := kind_anchor(row)):
                group = ("KIND_VIEWER_VERSION_GROUP", market, normalized_name(issuer), transaction, dates[0], anchor)
                evidence = row["viewerVersions"]
            else:
                group = ("SEPARATE_PENDING_REVIEW", identity)
            groups[group].append(identity)
            schedule = row.get("schedule", [])
            filings[identity] = {"market": market, "issuer": issuer, "referenceDates": dates, "purpose": purpose,
                                 "bodySha256": row.get("bodySha256"), "sourceUrl": row["sourceUrl"],
                                 "groupEvidence": evidence, "legalEffectiveDate": None,
                                 "schedule": schedule, "shareTerms": row.get("shareTerms")}
            if dates and transaction in {"합병", "분할", "분할합병"} and group[0] != "OUTSIDE_TRANSACTION_SCOPE":
                name = normalized_name(issuer)
                comparisons[market, name, transaction, dates[0]].append(identity)
                for listed in {d for field in schedule if field["role"].startswith("LISTING_") for d in field["dates"]}:
                    listing_candidates[market, name, listed].append(identity)
    registrations = [proof for row in census["newlyAuditedE003Filings"]
                     if (proof := reported_registration(artifacts, inputs["census"], row))]
    spin_off = facts.one(case for case in cases if case["caseId"] == "hanwha-aerospace-spin-off")
    shares = spin_off["listingShareCounts"]
    spin_off_listing = changed_listing(listing_rows, spin_off["market"], "한화에어로스페이스",
                                       spin_off["listingDate"], "회사분할(존속)", shares["survivor"] - shares["before"])
    known_listings = []
    for row in listing_rows:
        if not re.search("합병|회사분할|인적분할|물적분할", row["reason"]):
            continue
        key = row["market"], normalized_name(row["issuer"]), row["listingDate"]
        known_listings.append(row | {"sameIssuerSameDateFilingCandidates": sorted(listing_candidates[key]),
                                     "eventLinkConfirmed": False})
    return {
        "filings": filings, "groups": [{"basis": key[0], "filings": sorted(members)} for key, members in groups.items()],
        "crossRouteCandidates": [sorted(v) for v in comparisons.values()
                                 if len({identity.split("/")[0] for identity in v}) > 1],
        "listingRows": known_listings, "previouslyReviewedCases": cases,
        "reviewedListingCrossChecks": [{"caseId": spin_off["caseId"], "symbol": spin_off["instruments"]["survivor"],
                                        "listing": spin_off_listing}],
        "issuerReportedRegistrationCompletions": registrations,
        "momentumCompanyEvidence": census["momentumCompanyEvidence"],
        "withdrawalGroups": census["withdrawalGroups"], "fullEventCoverageConfirmed": False,
        "historicalFirstAvailabilityConfirmed": False,
    }
