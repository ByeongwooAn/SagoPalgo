"""Audit listed-share candidates and dated KRX halt evidence for KOSPI KIND notices."""

import argparse
from collections import Counter, defaultdict
import csv
from datetime import date
from functools import lru_cache
from pathlib import Path
import re

from . import krx_universe, krx_universe_history
from .corporate_action_event_audit import name_key
from .corporate_action_outcomes import SCOPE, capture, checked_read, require
from .dataset import canonical, digest, read_bytes, read_json
from .historical_market_action_identity import notice_proofs, role_names
from .kind_membership_evidence import html
from .krx_baseline_validation import immutable_json
from .market_calendar_evidence import text
from .models import utc


SCHEMA = "SAGOPALGO_H05_KOSPI_HALT_SCOPE_V1"
TARGET_STATUSES = {"HALT_DATES_SHARE_CLASS_UNCONFIRMED", "HALT_TIMES_SHARE_CLASS_UNCONFIRMED"}
CSV_FIELDS = ["번호", "일자", "종목코드", "종목명", "시장구분", "정지여부"]
PREFERRED = r"(?:[1-9]\d*)?우선주(?:\(신형\))?"
PREFERRED_SUFFIX = re.compile(rf"{PREFERRED}$")
ISSUE_CLASS_SUFFIX = re.compile(r"(?:[1-9]\d*)?우(?:선주)?(?:\([구신]형\)|[bc])?$")
KOSPI_OTHER_SHARES = krx_universe.OTHER_SHARES | {"구형우선주"}
KOREAN_DATE = r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일"
LISTING_RELEASE = re.compile(rf"변경상장일\s*\(\s*{KOREAN_DATE}\s*\)\s*에\s*매매거래정지\s*해제됨")
LISTING_DATE = re.compile(rf"변경상장일\s*:\s*{KOREAN_DATE}")
LISTING_SYMBOL = re.compile(r"표준코드\s*:\s*([A-Z0-9]{12})\s*\(\s*단축코드\s*:\s*A([A-Z0-9]{6})\s*\)")


def issuer_names(issue):
    return {name_key(issue[key], instrument=True) for key in ("name", "abbreviatedName")} - {""}


def share_name(value):
    value = name_key(value)
    return re.sub(r"우선주\(신형\)$", "우선주", value)


def associated_issues(common, issues):
    roots = issuer_names(common)
    return [issue for issue in issues.values() if issue["symbol"] != common["symbol"]
            and issue["symbol"][:5] == common["symbol"][:5]
            and issue["shareType"] in KOSPI_OTHER_SHARES
            and any(ISSUE_CLASS_SUFFIX.sub("", candidate) in roots for candidate in issuer_names(issue))]


def source_reader(history_job):
    plan, _, _, latest = krx_universe_history.load_job(history_job)
    require(plan["config"]["sourceKind"] == "PROVIDER_HISTORICAL", "KOSPI_HALT_HISTORY_SOURCE")

    @lru_cache(maxsize=24)
    def snapshot(stamp):
        if not SCOPE[0] <= stamp <= SCOPE[1]:
            return None, {}
        entry = krx_universe_history.observations(history_job, plan, latest, stamp).get("KOSPI")
        if entry is None or entry["state"] != "CAPTURED":
            return None, {}
        raw = krx_universe_history.entry_raw(history_job, entry, entry["seed"])
        source = {"date": stamp, "knownAt": entry["capturedAt"], "sha256": entry["sha256"]}
        issues = {}
        for item in krx_universe_history.envelope(raw):
            if item["SECUGRP_NM"] not in krx_universe.SECURITIES:
                continue
            code = item["ISU_SRT_CD"]
            require(code not in issues, "KOSPI_HALT_DUPLICATE_SYMBOL")
            issues[code] = {"symbol": code, "isin": item["ISU_CD"], "name": item["ISU_NM"],
                            "abbreviatedName": item["ISU_ABBRV"], "shareType": item["KIND_STKCERT_TP_NM"],
                            "sourceRowSha256": digest(canonical(item))}
        return source, issues

    return snapshot


def capture_binding(notice, artifacts):
    receipt = notice["receipt"]
    root = artifacts / ("h05-monthly-" + notice["publicationMonth"]) / "captures"
    viewer, _, body = notice["evidence"]
    viewer_raw = checked_read(root / f"proof-viewer-{receipt}" / "raw.bin", viewer["bodySha256"])
    body_raw = checked_read(root / f"proof-body-{receipt}" / "raw.bin", body["bodySha256"])
    heads = [node.text() for node in html(viewer_raw).walk("h1")]
    match = re.fullmatch(r"(.+) \(([0-9A-Z]{6})\)", heads[0]) if len(heads) == 1 else None
    published = notice["publishedTarget"]
    require(match and published in text(body_raw) and notice.get("viewerSymbol", match[2]) == match[2],
            "KOSPI_HALT_NOTICE_BINDING")
    return match.groups()


def common_candidate(published, viewer_code, stamp, issues, name_facts):
    issuer = name_key(published.removesuffix("주권").strip(), instrument=True)
    exact = [issue for issue in issues.values() if issue["shareType"] == "보통주" and issuer in issuer_names(issue)]
    viewer = issues.get(viewer_code)
    viewer = viewer if viewer and viewer["shareType"] == "보통주" else None
    if exact:
        if len(exact) == 1 and (viewer is None or exact[0]["symbol"] == viewer_code):
            return exact[0], "DATED_KRX_NAME_MATCH", None
        return None, "NAME_OR_CODE_CONFLICT", None
    if viewer:
        for fact in name_facts.get(viewer_code, ()):
            side = "before" if stamp < fact["date"] else "after"
            if fact["historyIsin"] == viewer["isin"] and issuer in role_names(fact, side):
                return viewer, "DATED_KRX_NAME_CHANGE_NOTICE_MATCH", notice_proofs(fact)
        return viewer, "VIEWER_CODE_MATCH_ISSUER_NAME_NOT_LINKED", None
    return None, "LISTED_COMMON_SHARE_NOT_MATCHED", None


def preferred_candidates(published, viewer_code, issues):
    named = share_name(published)
    return [issue for issue in issues.values() if issue["shareType"] in KOSPI_OTHER_SHARES
            and issue["symbol"][:5] == viewer_code[:5]
            and named in {share_name(issue["name"]), share_name(issue["abbreviatedName"])}]


def krx_daily_rows(raw):
    decoded = raw.decode("cp949")
    reader = csv.DictReader(decoded.splitlines())
    require(reader.fieldnames == CSV_FIELDS, "KOSPI_HALT_DAILY_CSV_HEADER")
    rows = {}
    for row in reader:
        stamp = date.fromisoformat(row["일자"].replace("/", "-")).isoformat()
        code = row["종목코드"]
        key = code, stamp
        require(row["시장구분"] == "KOSPI" and row["정지여부"] in {"Y", "N"}
                and re.fullmatch(r"[A-Z0-9]{6}", code) and key not in rows, "KOSPI_HALT_DAILY_CSV_ROW")
        rows[key] = {"date": stamp, "symbol": code, "name": row["종목명"], "haltFlag": row["정지여부"],
                     "sourceRowSha256": digest(canonical(row))}
    return rows


def daily_index(sources, job):
    result = {}
    for item in sources:
        raw = checked_read(job / item["path"], item["sha256"])
        for key, row in krx_daily_rows(raw).items():
            require(key[0] == item["symbol"] and item["from"] <= key[1] <= item["through"]
                    and key not in result, "KOSPI_HALT_DAILY_SOURCE_SCOPE")
            result[key] = row | {"csvSha256": item["sha256"]}
    return result


def boundary(stamp, published, viewer_code, snapshot, name_facts, daily):
    source, issues = snapshot(stamp)
    if not SCOPE[0] <= stamp <= SCOPE[1]:
        return {"date": stamp, "status": "OUTSIDE_H05_EFFECTIVE_SCOPE", "candidateIssues": []}
    if not issues:
        return {"date": stamp, "status": "KRX_LIST_UNAVAILABLE", "candidateIssues": []}
    supporting = None
    if PREFERRED_SUFFIX.search(published):
        selected = preferred_candidates(published, viewer_code, issues)
        status = "EXPLICIT_PREFERRED_TARGET_MATCHED" if len(selected) == 1 else "EXPLICIT_PREFERRED_CODE_UNRESOLVED"
        candidates = selected if len(selected) == 1 else []
    else:
        common, basis, supporting = common_candidate(published, viewer_code, stamp, issues, name_facts)
        candidates = [common, *associated_issues(common, issues)] if common else []
        status = basis
    return {"date": stamp, "status": status, "krxSource": source, "relatedNameNotice": supporting,
            "candidateIssues": [issue | {"dailyHaltEvidence": daily.get((issue["symbol"], stamp))}
                               for issue in candidates]}


def classify(row, points):
    if PREFERRED_SUFFIX.search(row["publishedTarget"]):
        return ("EXPLICIT_PREFERRED_TARGET" if any(v["status"] == "EXPLICIT_PREFERRED_TARGET_MATCHED"
                                                  for v in points.values()) else "EXPLICIT_PREFERRED_CODE_UNRESOLVED")
    boundaries = [v for key, v in points.items() if key != "publication"]
    halt = points.get("halt", {})
    daily = [issue["dailyHaltEvidence"] for issue in halt.get("candidateIssues", []) if issue["dailyHaltEvidence"]]
    if any(issue["haltFlag"] == "Y" for issue in daily):
        return "CODE_LEVEL_HALT_DAY_EVIDENCE_AVAILABLE"
    if any(len(point["candidateIssues"]) > 1 for point in boundaries):
        return "MULTIPLE_LISTED_SHARE_CANDIDATES"
    if boundaries and all(point["status"] in {"DATED_KRX_NAME_MATCH", "DATED_KRX_NAME_CHANGE_NOTICE_MATCH"}
           for point in boundaries):
        return "SINGLE_COMMON_SHARE_CANDIDATE"
    if any(point["candidateIssues"] for point in boundaries):
        return "LISTED_CANDIDATE_WITH_BOUNDARY_OR_ISSUER_GAP"
    return "PUBLISHED_BOUNDARY_WITHOUT_LISTED_CANDIDATE"


def changed_listing_release(body):
    if body.count("◎") != 1 or not re.search(r"변경상장\s*\([^)]*(?:감자|자본감소|분할|병합|액면)", body):
        return None
    release, listing = LISTING_RELEASE.findall(body), LISTING_DATE.findall(body)
    if len(release) != 1 or len(listing) != 1 or release[0] != listing[0]:
        return None
    pairs = LISTING_SYMBOL.findall(body)
    symbols = {code: isin for isin, code in pairs}
    if not symbols or len(symbols) != len(pairs):
        return None
    return {"reopeningDate": date(*map(int, release[0])).isoformat(), "symbols": symbols}


def public_support(spec, job, snapshots):
    root = job / "public-evidence"
    captures = {}
    for label, source in spec["publicCaptures"].items():
        raw, evidence = capture(root, {label: source["receiptSha256"]}, label, source["request"],
                                utc(spec["reviewedAt"]))
        body = text(raw)
        value = "".join(body.split())
        require(all("".join(term.split()) in value for term in source["requiredText"]),
                "KOSPI_HALT_PUBLIC_EVIDENCE_TEXT")
        captures[label] = body, evidence
    result = defaultdict(list)
    for item in spec["publicLinks"]:
        body, evidence = captures[item["captureKey"]]
        support = item | {"source": evidence}
        if item["kind"] == "CHANGED_LISTING_STATES_RELEASE_DATE_AND_CODES":
            require(changed_listing_release(body) == item["release"], "KOSPI_HALT_PUBLIC_RELEASE_MISMATCH")
            stamp = item["release"]["reopeningDate"]
            release_source, issues = snapshots(stamp)
            codes = item["release"]["symbols"]
            matched = [issues[symbol] for symbol, isin in codes.items()
                       if symbol in issues and issues[symbol]["isin"] == isin]
            require(len(matched) == len(codes), "KOSPI_HALT_PUBLIC_RELEASE_KRX_MISMATCH")
            support |= {"reopeningKrxSource": release_source, "reopeningIssues": matched}
        result[item["receipt"]].append(support)
    return result


def query_plan(results):
    pairs = defaultdict(list)
    for row in results:
        for phase in ("halt", "reopening"):
            boundary = row["boundaries"].get(phase)
            if boundary is None:
                continue
            for issue in boundary["candidateIssues"]:
                key = issue["symbol"], issue["isin"], boundary["date"]
                pairs[key].append({"receipt": row["receipt"], "phase": phase})
        for public in row["additionalPublicEvidence"]:
            if "reopeningIssues" not in public:
                continue
            stamp = public["release"]["reopeningDate"]
            for issue in public["reopeningIssues"]:
                key = issue["symbol"], issue["isin"], stamp
                reference = {"receipt": row["receipt"], "phase": "changedListingRelease"}
                if reference not in pairs[key]:
                    pairs[key].append(reference)
    return [{"symbol": symbol, "isin": isin, "date": stamp, "notices": values}
            for (symbol, isin, stamp), values in sorted(pairs.items())]


def daily_query_outcomes(planned, daily, sources, unavailable):
    ranges = defaultdict(list)
    for source in [*sources, *unavailable]:
        ranges[source["symbol"]].append(source)
    returned, missing = [], []
    for row in planned:
        code, stamp = row["symbol"], row["date"]
        evidence = daily.get((code, stamp))
        if evidence is not None:
            returned.append(row | {"evidence": evidence})
        else:
            relevant = [source for source in ranges[code] if source["from"] <= stamp <= source["through"]]
            require(len(relevant) <= 1, "KOSPI_HALT_OVERLAPPING_DAILY_QUERIES")
            reason = (relevant[0].get("reason", "DATE_NOT_RETURNED_IN_KRX_CSV") if relevant
                      else "QUERY_OUTCOME_UNVERIFIED")
            missing.append(row | {"unavailableReason": reason})
    return returned, missing


def build(manifest, ledger, artifacts, job):
    manifest_raw = read_bytes(manifest)
    spec = read_json(manifest_raw)
    require(spec["schemaVersion"] == SCHEMA, "KOSPI_HALT_SCOPE_SCHEMA")
    ledger_raw = checked_read(ledger, spec["monthlyLedgerSha256"])
    pins = spec["inputs"]
    for pin in pins.values():
        checked_read(artifacts / pin["path"], pin["sha256"])
    history_job = (artifacts / pins["historyPlan"]["path"]).parent
    require(history_job / "journal.json" == artifacts / pins["historyJournal"]["path"], "KOSPI_HALT_HISTORY_PATH")
    snapshots = source_reader(history_job)
    listing_search = spec["publicListingSearch"]
    search_rows = read_json(checked_read(job / listing_search["path"], listing_search["sha256"]))
    require(len(search_rows) == listing_search["receiptCount"], "KOSPI_HALT_PUBLIC_SEARCH_COUNT")
    name_facts = defaultdict(list)
    for label in ("nameChanges", "aliasChanges"):
        for fact in read_json(checked_read(artifacts / pins[label]["path"], pins[label]["sha256"]))["facts"]:
            if fact.get("market") == "KOSPI":
                name_facts[fact["stockCode"]].append(fact)
    daily = daily_index(spec["dailySources"], job)
    public_links = public_support(spec, job, snapshots)
    results = []
    for notice in (read_json(line) for line in ledger_raw.splitlines()):
        if notice["market"] != "KOSPI" or notice["status"] not in TARGET_STATUSES:
            continue
        issuer, code = capture_binding(notice, artifacts)
        dates = {"publication": notice["listedMinuteKst"][:10],
                 "halt": notice.get("haltDate"), "reopening": notice.get("reopeningDate")}
        points = {label: boundary(stamp, notice["publishedTarget"], code, snapshots, name_facts, daily)
                  for label, stamp in dates.items() if stamp}
        related = public_links.pop(notice["receipt"], [])
        for link in related:
            if link["kind"] == "CHANGED_LISTING_STATES_RELEASE_DATE_AND_CODES":
                release = link["release"]
                search_candidates = search_rows.get(notice["receipt"], [])
                require(dates["halt"] and dates["halt"] < release["reopeningDate"]
                        and dates["reopening"] in {None, release["reopeningDate"]}
                        and code in release["symbols"] and isinstance(search_candidates, list)
                        and any(candidate["document"] == link["listingDocument"]
                                and candidate["bodySha256"] == link["source"]["bodySha256"]
                                for candidate in search_candidates), "KOSPI_HALT_PUBLIC_RELEASE_SCOPE")
        results.append({"receipt": notice["receipt"], "document": notice["document"],
                        "publishedTarget": notice["publishedTarget"], "viewerIssuerName": issuer, "viewerSymbol": code,
                        "haltTimeKst": notice.get("haltTimeKst"), "reopeningTimeKst": notice.get("reopeningTimeKst"),
                        "status": classify(notice, points), "boundaries": points, "kindEvidence": notice["evidence"],
                        "additionalPublicEvidence": related})
    require(len(results) == len({row["receipt"] for row in results}) == spec["expectedNotices"],
            "KOSPI_HALT_SCOPE_COUNT")
    require(not public_links, "KOSPI_HALT_PUBLIC_LINK_SCOPE")
    require(set(search_rows).issubset(row["receipt"] for row in results), "KOSPI_HALT_PUBLIC_SEARCH_SCOPE")
    planned = query_plan(results)
    report = {"schemaVersion": SCHEMA, "manifestSha256": digest(manifest_raw), "monthlyLedgerSha256": digest(ledger_raw),
              "statusCounts": dict(Counter(row["status"] for row in results)),
              "exactCodeLevelHaltTimesConfirmed": False, "usableForTrading": False, "usableForTraining": False,
              "notices": results, "dailyQueryNeeds": planned}
    if spec["dailySources"] or spec.get("dailyUnavailableRanges"):
        returned, missing = daily_query_outcomes(
            planned, daily, spec["dailySources"], spec.get("dailyUnavailableRanges", []))
        report.update(dailyQueryEvidence=returned, dailyQueryNeeds=missing,
                      dailyQueryCounts={"planned": len(planned), "returned": len(returned),
                                        "haltFlags": dict(Counter(row["evidence"]["haltFlag"] for row in returned)),
                                        "missingReasons": dict(Counter(row["unavailableReason"] for row in missing))})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "audit"))
    for flag in ("manifest", "ledger", "artifacts", "job", "output"):
        parser.add_argument("--" + flag, type=Path, required=True)
    args = parser.parse_args()
    report = build(args.manifest, args.ledger, args.artifacts, args.job)
    immutable_json(args.output, report, require_existing=args.action == "audit")
    print(report["statusCounts"])


if __name__ == "__main__":
    main()
