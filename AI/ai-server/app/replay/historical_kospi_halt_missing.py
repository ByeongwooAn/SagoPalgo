"""Audit KIND notice evidence for date pairs missing from the KRX daily halt lookup."""

import argparse
from collections import Counter, defaultdict
from pathlib import Path
import re

from .corporate_action_event_audit import name_key
from .corporate_action_outcomes import VIEWER, capture, checked_read, list_page, require
from .dataset import digest, read_bytes, read_json
from .distribution_facts import Node
from .historical_kospi_halt_scope import changed_listing_release, share_name
from .historical_market_action_monthly import kospi_boundary
from .kind_membership_evidence import BASE, html
from .krx_baseline_validation import immutable_json
from .market_calendar_evidence import text
from .models import utc
from .session_notice_inventory import body_path, viewer_documents


SCHEMA = "SAGOPALGO_H05_KOSPI_HALT_MISSING_V1"
SEARCH_TERMS = {"halt": "매매거래정지", "listing": "변경상장", "delisting": "상장폐지"}


def search_spec(code, term, window, page):
    return {"url": BASE + "/disclosure/details.do", "method": "POST", "parameters": {
        "method": "searchDetailsSub", "forward": "details_sub", "currentPageSize": "100",
        "orderMode": "0", "orderStat": "D", "fromDate": window["from"], "toDate": window["through"],
        "repIsuSrtCd": "A" + code, "searchCodeType": "number", "searchCorpName": code,
        "reportNm": term, "reportCd": "", "allRepIsuSrtCd": "", "marketType": "", "pageIndex": str(page),
    }}


def search_notices(spec, required, get):
    searches, found = {}, defaultdict(dict)
    for code, original in sorted(required.items()):
        searches[code] = {}
        for category, term in SEARCH_TERMS.items():
            rows = []
            page, pages = 1, 1
            while page <= pages:
                request = search_spec(code, term, spec["searchWindow"], page)
                raw, evidence = get(f"query-{code}-{category}-{page}", request)
                count, pages, results = list_page(raw, request["parameters"] | {"market": "KOSPI"}, page)
                rows.extend(results)
                searches[code].setdefault(category, []).append({"total": count, "source": evidence})
                page += 1
            receipts = {row["receipt"] for row in rows}
            require(len(receipts) == len(rows) == count, "H05_MISSING_SEARCH_COUNT")
            if category == "halt":
                require(original <= receipts, "H05_MISSING_SEARCH_ORIGINAL_NOT_FOUND")
            for row in rows:
                found[row["receipt"]][code] = row["title"]
    return searches, found


def delisting_fields(raw):
    tables = []
    for table in html(raw).walk("table"):
        rows = [[c.text() for c in tr.children if isinstance(c, Node) and c.tag in {"th", "td"}]
                for tr in table.walk("tr")]
        if rows and rows[0] and "".join(rows[0][0].split()) in {"1.회사명", "1.상장폐지대상주권및주식수"}:
            tables.append(rows)
    if len(tables) != 1:
        return None
    rows = tables[0]
    dates = [r[1] for r in rows if len(r) == 2 and re.fullmatch(r"[36]\.\s*상장폐지일", r[0])]
    codes = [(r[2][1:], r[0]) for r in rows if len(r) == 3 and re.fullmatch(r"A[0-9A-Z]{6}", r[2])
             and re.fullmatch(r"[\d,]+", r[1])]
    if not codes or len(dict(codes)) != len(codes) or len(dates) != 1 or not re.fullmatch(r"\d{4}-\d{2}-\d{2}|-", dates[0]):
        return None
    return {"date": dates[0] if dates[0] != "-" else None, "stockCodes": dict(codes),
            "issuer": rows[0][1] if len(rows[0]) == 2 else None}


def related_documents(receipts, found, get):
    documents = {}
    require(set(receipts) <= set(found) and len(receipts) == len(set(receipts)), "H05_MISSING_RELATED_SCOPE")
    for receipt in receipts:
        viewer, viewer_proof = get("viewer-" + receipt, {"url": VIEWER + f"?acptno={receipt}&method=search",
                                                       "method": "GET", "parameters": None})
        headers = [node.text() for node in html(viewer).walk("h1")]
        require(len(headers) == 1 and any(headers[0].endswith(f"({code})") for code in found[receipt]),
                "H05_MISSING_RELATED_VIEWER_CODE")
        versions = []
        for version in viewer_documents(viewer):
            doc = version["document"]
            route, _ = get("route-" + doc, {"url": VIEWER, "method": "POST",
                                           "parameters": {"method": "searchContents", "docNo": doc}})
            url = body_path(route, doc)
            raw, proof = get("body-" + doc, {"url": url, "method": "GET", "parameters": None})
            body = text(raw)
            version |= {"source": proof}
            if url.endswith("/68051.htm"):
                version["delisting"] = delisting_fields(raw)
            elif url.endswith("/68155.htm"):
                version["changedListingRelease"] = changed_listing_release(body)
            else:
                fields = kospi_boundary(url.rsplit("/", 1)[-1], body)
                if fields:
                    version["publishedBoundary"] = fields
            versions.append(version)
        documents[receipt] = {"searchTitles": found[receipt], "viewerHeader": headers[0],
                              "viewer": viewer_proof, "versions": versions}
    return documents


def original_body(notice, artifacts):
    receipt = notice["receipt"]
    proof = notice["kindEvidence"][-1]
    folder = artifacts / f"h05-monthly-{receipt[:4]}-{receipt[4:6]}" / "captures"
    body = text(checked_read(folder / f"proof-body-{receipt}" / "raw.bin", proof["bodySha256"]))
    fields = kospi_boundary(proof["sourceUrl"].rsplit("/", 1)[-1], body)
    require(fields and fields["publishedTarget"] == notice["publishedTarget"], "H05_MISSING_ORIGINAL_TARGET")
    return body, fields


def matching_release(notice, code, isin):
    return [link for link in notice["additionalPublicEvidence"]
            if link.get("release", {}).get("symbols", {}).get(code) == isin]


def match_scope(notice, boundary, issue, body, delistings, release, phase, stamp):
    if boundary["status"] == "EXPLICIT_PREFERRED_TARGET_MATCHED":
        return "KIND_NAMES_SHARE_IN_TARGET", []
    if len(boundary["candidateIssues"]) == 1:
        if boundary["status"] in {"DATED_KRX_NAME_MATCH", "DATED_KRX_NAME_CHANGE_NOTICE_MATCH"}:
            return "ISSUER_AND_DATE_MATCH_SINGLE_KRX_SHARE", []
        issuer = name_key(notice["publishedTarget"].removesuffix("주권"), instrument=True)
        aliases = [item for item in delistings if (item["date"] and stamp < item["date"] and item["issuer"]
                    and issuer == name_key(item["issuer"], instrument=True)
                    and item["shareClass"] in {"보통주", "보통주식"} and not item["correctionMarked"])]
        if aliases and issue["shareType"] == "보통주":
            return "KIND_DELISTING_BRIDGES_ISSUER_NAME_AND_CODE", aliases
    named = re.search(r"동 매매거래정지로 (.+?)는 (\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일부터", body)
    if named and phase == "halt" and "%04d-%02d-%02d" % tuple(map(int, named.groups()[1:])) == stamp:
        listed = {share_name(name) for name in re.split(r",\s*|\s+및\s+", named[1])}
        if share_name(issue["name"]) in listed:
            return "KIND_NAMES_SHARE_IN_HALT_REMARKS", []
    if phase == "halt" and "매매거래정지해제일 변경상장일" in body and len(release) == 1:
        return "MATCHING_CHANGED_LISTING_IDENTIFIES_HALTED_SHARE", release
    return "KIND_ISSUE_SCOPE_UNCONFIRMED", []


def phase_result(pair, ref, notice, original, delistings):
    code, isin, stamp = (pair[name] for name in ("symbol", "isin", "date"))
    phase = ref["phase"]
    body, fields = original
    release = matching_release(notice, code, isin)
    result = ref | {"document": notice["document"], "noticeTarget": notice["publishedTarget"],
                    "kindNotice": notice["kindEvidence"][-1], "publishedDate": stamp}
    if phase == "changedListingRelease":
        links = [link for link in release if link["release"]["reopeningDate"] == stamp]
        require(len(links) == 1, "H05_MISSING_LISTING_DATE_IDENTITY")
        return result | {"basis": "KIND_LISTING_STATES_RELEASE_DATE_CODE_ISIN", "relatedEvidence": links}

    boundary = notice["boundaries"][phase]
    issues = [i for i in boundary["candidateIssues"] if (i["symbol"], i["isin"]) == (code, isin)]
    require(len(issues) == 1 and fields[phase + "Date"] == boundary["date"] == stamp
            and fields.get(phase + "TimeKst") == notice.get(phase + "TimeKst"), "H05_MISSING_BOUNDARY_BINDING")
    issue = issues[0]
    basis, evidence = match_scope(notice, boundary, issue, body, delistings, release, phase, stamp)
    result |= {"basis": basis, "publishedTimeKst": fields.get(phase + "TimeKst"), "listedKrxSource": boundary["krxSource"],
               "listedIssue": issue, "relatedEvidence": evidence}
    if basis == "KIND_ISSUE_SCOPE_UNCONFIRMED":
        result["reason"] = "PUBLISHED_ISSUER_HAS_MULTIPLE_SHARES_AND_RELATED_NOTICES_DO_NOT_IDENTIFY_THIS_ACTION"
    return result


def build(manifest, baseline, artifacts, job):
    raw_manifest = read_bytes(manifest)
    spec = read_json(raw_manifest)
    require(spec["schemaVersion"] == SCHEMA, "H05_MISSING_SCHEMA")
    source = read_json(checked_read(baseline, spec["baselineSha256"]))
    pairs = source["dailyQueryNeeds"]
    symbols = {pair["symbol"] for pair in pairs}
    require(len(pairs) == len({(p["symbol"], p["isin"], p["date"]) for p in pairs}) == 91 and len(symbols) == 32
            and all(p["unavailableReason"] == "STOCK_FINDER_NO_RESULT" for p in pairs), "H05_MISSING_FIXED_SCOPE")
    original = {ref["receipt"] for pair in pairs for ref in pair["notices"]}
    notices = {n["receipt"]: n for n in source["notices"] if n["receipt"] in original}
    require(set(notices) == original, "H05_MISSING_ORIGINAL_RECEIPTS")
    originals = {rec: original_body(notice, artifacts) for rec, notice in notices.items()}
    required = defaultdict(set)
    for rec, n in notices.items():
        required[n["viewerSymbol"]].add(rec)

    used = set()

    def get(name, request):
        used.add(name)
        return capture(job, spec["captures"], name, request, utc(spec["reviewedAt"]))

    searches, found = search_notices(spec, required, get)
    related = related_documents(spec["relatedReceipts"], found, get)
    require(used == set(spec["captures"]), "H05_MISSING_UNUSED_CAPTURE")
    listing_versions = {version["document"]: version for doc in related.values() for version in doc["versions"]
                        if version.get("changedListingRelease")}
    delistings = defaultdict(list)
    for receipt, doc in related.items():
        for version in doc["versions"]:
            item = version.get("delisting")
            if item:
                for code, kind in item["stockCodes"].items():
                    if code in symbols:
                        delistings[code].append({"receipt": receipt, "document": version["document"],
                                                "date": item["date"], "issuer": item["issuer"], "shareClass": kind,
                                                "correctionMarked": version["correctionMarked"], "source": version["source"]})
    results = []
    for pair in pairs:
        reviews = [phase_result(pair, ref, notices[ref["receipt"]], originals[ref["receipt"]], delistings[pair["symbol"]])
                   for ref in pair["notices"]]
        for review in reviews:
            for link in review["relatedEvidence"]:
                if "listingDocument" in link:
                    version = listing_versions.get(link["listingDocument"])
                    require(version and version["changedListingRelease"] == link["release"]
                            and version["source"]["bodySha256"] == link["source"]["bodySha256"],
                            "H05_MISSING_CHANGED_LISTING_RECAPTURE")
        confirmed = all(review["basis"] != "KIND_ISSUE_SCOPE_UNCONFIRMED" for review in reviews)
        results.append(pair | {"status": "KIND_SCOPE_AND_DATE_LINKED" if confirmed else "KIND_ISSUE_SCOPE_UNCONFIRMED",
                               "phaseReviews": reviews})
    return {"schemaVersion": SCHEMA, "manifestSha256": digest(raw_manifest), "baselineSha256": spec["baselineSha256"],
            "observedThrough": spec["searchWindow"]["through"], "searches": searches, "relatedNotices": related,
            "relatedDelistingsBySymbol": dict(delistings), "pairCounts": dict(Counter(r["status"] for r in results)),
            "referenceBasisCounts": dict(Counter(ref["basis"] for r in results for ref in r["phaseReviews"])),
            "actualStateTransitionsConfirmed": False, "usableForTrading": False, "usableForTraining": False,
            "pairs": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "audit"))
    for flag in ("manifest", "baseline", "artifacts", "job", "output"):
        parser.add_argument("--" + flag, type=Path, required=True)
    args = parser.parse_args()
    result = build(args.manifest, args.baseline, args.artifacts, args.job)
    immutable_json(args.output, result, require_existing=args.action == "audit")
    print(result["pairCounts"], result["referenceBasisCounts"])


if __name__ == "__main__":
    main()
