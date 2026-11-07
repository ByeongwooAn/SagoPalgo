"""Audit observed historical securities, issuer evidence, and separately published totals."""
import argparse
from calendar import monthrange
from collections import Counter, defaultdict
from datetime import timedelta
from io import BytesIO
import json
from pathlib import Path
import re
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from . import krx_baseline_validation as daily, krx_universe as krx, market_calendar_evidence as sources
from .dataset import canonical, digest, read_bytes, read_json
from .distribution_facts import XForms
from .history import day
from .krx_baseline_validation import immutable_json
from .models import ResearchError, utc
from .session_notice_inventory import body_path, viewer_documents
from .universe_reconciliation import normalized_name


SCHEMA = "SAGOPALGO_MEMBERSHIP_IDENTITY_AUDIT_V1"
KIND = "https://kind.krx.co.kr"
KOSIS = "https://kosis.kr"
DART_REGISTRY = "https://opendart.fss.or.kr/api/corpCode.xml"
TABLES = {"KOSPI": "DT_343_2010_S0013", "KOSDAQ": "DT_343_2010_S0054"}
FILINGS = {
    "delisting": ("20260814002694", "70769"),
    "new-shares": ("20260811000910", "70791"),
    "rename": ("20260811000938", "70765"),
    "issuance-report": ("20260715000296", "10810"),
    "half-year-report": ("20260812000802", "11012"),
}
TARGETS = {"299900": "KR7299900001", "291230": "KR7291230001"}
BOUNDARIES = ("2026-07-15", "2026-08-13", "2026-08-14", "2026-08-15", "2026-08-17", "2026-08-18")


def pinned(path, expected):
    raw = read_bytes(path)
    if digest(raw) != expected:
        raise ResearchError("MEMBERSHIP_IDENTITY_INPUT_HASH")
    return read_json(raw)


def kosis_months(folder, market, receipt_sha):
    receipt = pinned(folder / "receipt.json", receipt_sha)
    table = TABLES[market]
    data = pinned(folder / "body.json", receipt["sha256"])
    if (receipt["orgId"] != "343" or receipt["market"] != market or receipt["tableId"] != table
            or receipt["queryUrl"] != KOSIS + "/statHtml/html.do"
            or receipt["sourceUrl"] != f"{KOSIS}/statHtml/statHtml.do?orgId=343&tblId={table}"
            or data["ParamInfo"]["orgId"] != "343" or data["ParamInfo"]["tblId"] != table
            or utc(receipt["startedAt"]) > utc(receipt["capturedAt"])):
        raise ResearchError("MEMBERSHIP_KOSIS_SCOPE")
    parser = XForms()
    parser.feed(data["result"][0])
    parser.close()
    rows = {}
    for tr in parser.root.walk("tr"):
        cells = [v.text() for v in (list(tr.walk("td")) or list(tr.walk("th")))]
        if cells and cells[0] in ("주식지표별", "회사수 (개)", "종목수 (개)"):
            if cells[0] in rows:
                raise ResearchError("MEMBERSHIP_KOSIS_DUPLICATE_ROW")
            rows[cells[0]] = cells[1:]
    labels, companies, issues = (rows[k] for k in ("주식지표별", "회사수 (개)", "종목수 (개)"))
    periods = receipt["periods"]
    if (not periods or len(set(periods)) != len(periods) or len(parser.stack) != 1
            or not (len(labels) == len(companies) == len(issues) == len(periods))
            or any(not re.fullmatch(r"[0-9]{4}\.(0[1-9]|1[0-2])", value) for value in labels)
            or [label.replace(".", "") for label in labels] != sorted(periods, reverse=True)):
        raise ResearchError("MEMBERSHIP_KOSIS_PERIOD")
    results = {}
    for label, company, issue in zip(labels, companies, issues):
        year, month = map(int, label.split("."))
        count = int(issue.replace(",", ""))
        company_count = int(company.replace(",", ""))
        if not 0 < company_count <= count:
            raise ResearchError("MEMBERSHIP_KOSIS_COUNT")
        stamp = f"{year}-{month:02}-{monthrange(year, month)[1]:02}"
        results[stamp] = {"month": label, "publishedIssues": count, "publishedCompanies": company_count,
                          "knownAt": receipt["capturedAt"], "tableId": table,
                          "sourceUrl": receipt["sourceUrl"], "bodySha256": receipt["sha256"]}
    return results


def kind_text(folder, name, receipt_sha):
    receipt = pinned(folder / "receipt.json", receipt_sha)
    number, form = FILINGS[name]
    stages = receipt["stages"]
    if (receipt["schemaVersion"] != "SAGOPALGO_H01_KIND_CAPTURE_V1" or receipt["filingReceipt"] != number
            or set(stages) != {"viewer", "route", "body"}
            or stages["viewer"]["url"] != KIND + f"/common/disclsviewer.do?acptno={number}&method=search"):
        raise ResearchError("MEMBERSHIP_KIND_SCOPE")
    raw = {}
    for stage, facts in stages.items():
        data = read_bytes(folder / (stage + ".bin"))
        if digest(data) != facts["sha256"] or utc(facts["capturedAt"]) < utc(facts["startedAt"]):
            raise ResearchError("MEMBERSHIP_KIND_CAPTURE")
        raw[stage] = data
    docs = viewer_documents(raw["viewer"])
    if len(docs) != 1 or docs[0]["correctionMarked"]:
        raise ResearchError("MEMBERSHIP_KIND_CORRECTION")
    document = docs[0]["document"]
    url = body_path(raw["route"], document)
    if (stages["route"]["url"] != KIND + "/common/disclsviewer.do"
            or stages["route"]["params"] != {"method": "searchContents", "docNo": document}
            or stages["body"]["url"] != url or not url.endswith(f"/{form}.htm")):
        raise ResearchError("MEMBERSHIP_KIND_ROUTE")
    return sources.text(raw["body"]), {
        "sourceUrl": url, "filingReceipt": number, "bodySha256": stages["body"]["sha256"],
        "knownAt": max((item["capturedAt"] for item in stages.values()), key=utc),
    }


def case_facts(texts):
    merger = re.search(r"합병계약을 승인하였으며, (20\d{2})년 (\d{1,2})월 (\d{1,2})일부로 합병\(합병효력발생일\)을 완료", texts["half-year-report"])
    delist = re.search(r"7\.상장폐지일 (20\d{2}-\d\d-\d\d)", texts["delisting"])
    issue = re.search(r"5\.상장일 (20\d{2}-\d\d-\d\d)", texts["new-shares"])
    rename = re.search(r"4\.상장일 (20\d{2}-\d\d-\d\d)", texts["rename"])
    planned = re.search(r"합병기일 (20\d{2}-\d\d-\d\d) 합병종료보고", texts["issuance-report"])
    if (not all((merger, delist, issue, rename, planned))
            or not all(fragment in texts["delisting"] for fragment in (
                "(주)위지윅스튜디오", "보통주 A299900", "피흡수합병", "(주)컴투스엔", "별도의 정리매매는 없으며"))
            or not all(fragment in texts["new-shares"] for fragment in ("(주)엔피", "보통주 A291230", "타법인흡수합병"))
            or not all(fragment in texts["rename"] for fragment in ("(주)엔피", "(주)컴투스엔", "상호변경"))
            or not all(fragment in texts["half-year-report"] for fragment in ("주식회사 위지윅스튜디오", "주식회사 컴투스엔"))):
        raise ResearchError("MEMBERSHIP_CASE_FILING_FACTS")
    effective = f"{int(merger[1]):04}-{int(merger[2]):02}-{int(merger[3]):02}"
    if (f"합병등기일인 {int(merger[1])}년 {int(merger[2])}월 {int(merger[3])}일" not in texts["half-year-report"]
            or not day(planned[1]) <= day(effective) < day(delist[1]) or not delist[1] == issue[1] == rename[1]):
        raise ResearchError("MEMBERSHIP_CASE_DATE_CONFLICT")
    return {"disclosedMergerReferenceDate": planned[1], "issuerReportedMergerEffectiveDate": effective,
            "exchangeAnnouncedDelistingDate": delist[1], "successorNewSharesListingDate": issue[1],
            "successorExchangeRenameDate": rename[1]}


def trade_comparison(observed, records, proof):
    basic = {row["symbol"]: row for row in observed}
    traded = {row["symbol"]: row for row in records}
    missing = sorted(basic.keys() - traded.keys())
    additional = sorted(traded.keys() - basic.keys())
    return {"status": "MATCH" if not missing and not additional else "CONFLICT", "tradingIssueRows": len(traded),
            "basicOnlySymbols": missing, "tradingOnlySymbols": additional,
            "commonRowsMatchedBySymbol": sum(basic[key]["classification"] == "COMMON_SHARE" for key in basic.keys() & traded.keys()),
            "targetVolume": {symbol: int(traded[symbol]["volume"]) if symbol in traded else None for symbol in TARGETS},
            **proof}


def issuer_edges(parent_rows):
    edges = defaultdict(dict)
    for row in parent_rows:
        observation = row["observation"]
        for fact in row["evidence"]:
            url, name = fact.get("sourceUrl"), fact.get("issuerName")
            isin, code, market = fact.get("historyIsin"), fact.get("stockCode"), fact.get("market")
            if (not name or not url or not url.startswith(KIND + "/external/")
                    or isin != observation["isin"] or fact.get("sourceIsin") not in (None, isin)):
                continue
            if not any(side and side["symbol"] == code and side["market"] == market and side["isin"] == isin
                       for side in (observation["before"], observation["after"])):
                continue
            edge = {"issuerName": name, "symbol": code, "market": market, "sourceUrl": url, "sourceIsin": fact.get("sourceIsin"),
                    "knownAt": fact["knownAt"], "observationId": row["observationId"]}
            edges[isin][digest(canonical(edge))] = edge
    return edges


def dart_registry(folder, receipt_sha):
    receipt = pinned(folder / "receipt.json", receipt_sha)
    raw = read_bytes(folder / "body.zip")
    if (receipt["schemaVersion"] != "SAGOPALGO_H01_DART_REGISTRY_CAPTURE_V1"
            or receipt["url"] != DART_REGISTRY or receipt["status"] != "COMPLETE"
            or utc(receipt["startedAt"]) > utc(receipt["capturedAt"])
            or len(raw) > 12 * 1024 * 1024 or digest(raw) != receipt["sha256"]):
        raise ResearchError("MEMBERSHIP_DART_REGISTRY_CAPTURE")
    try:
        with ZipFile(BytesIO(raw)) as archive:
            items = archive.infolist()
            if len(items) != 1 or items[0].filename != "CORPCODE.xml" or items[0].file_size > 64 * 1024 * 1024:
                raise ResearchError("MEMBERSHIP_DART_REGISTRY_ARCHIVE")
            xml = archive.read(items[0]).decode("utf-8-sig")
        if "<!DOCTYPE" in xml or "<!ENTITY" in xml:
            raise ResearchError("MEMBERSHIP_DART_REGISTRY_XML")
        root = ElementTree.fromstring(xml)
    except (BadZipFile, ElementTree.ParseError, RuntimeError):
        raise ResearchError("MEMBERSHIP_DART_REGISTRY_ARCHIVE") from None
    if root.tag != "result" or not 1 <= len(root) <= 200_000:
        raise ResearchError("MEMBERSHIP_DART_REGISTRY_XML")
    listed = defaultdict(list)
    for row in root:
        code = (row.findtext("stock_code") or "").strip()
        if not code:
            continue
        corp, name = row.findtext("corp_code") or "", row.findtext("corp_name") or ""
        if row.tag != "list" or not re.fullmatch(r"[A-Z0-9]{6}", code) or not re.fullmatch(r"[0-9]{8}", corp) or not name.strip():
            raise ResearchError("MEMBERSHIP_DART_REGISTRY_ROW")
        listed[code].append({"dartCorpCode": corp, "issuerName": name})
    return listed, {"sourceUrl": DART_REGISTRY, "bodySha256": receipt["sha256"], "knownAt": receipt["capturedAt"]}


def endpoint_issuer_check(issue, registry):
    candidates = registry.get(issue["symbol"], [])
    if not candidates:
        return {"status": "NOT_FOUND"}
    if len(candidates) != 1:
        return {"status": "AMBIGUOUS_CODE"}
    expected = normalized_name(issue["name"].removesuffix("보통주")).casefold()
    if normalized_name(candidates[0]["issuerName"]).casefold() != expected:
        return {"status": "NAME_MISMATCH"}
    return {"status": "MATCH", **candidates[0]}


def observed_span(spans, issue, stamp, known_at):
    row = {field: issue[field] for field in ("symbol", "market", "name")}
    previous = spans[-1] if spans else None
    if (previous is not None and all(previous[field] == item for field, item in row.items())
            and day(stamp) - day(previous["lastObserved"]) == timedelta(days=1)):
        previous["lastObserved"] = stamp
        previous["knownAt"] = max(previous["knownAt"], known_at, key=utc)
    else:
        spans.append({**row, "firstObserved": stamp, "lastObserved": stamp, "knownAt": known_at})


def trade_source(cache, stamp, market, receipt_sha):
    folder = cache / f"{stamp}-{market}"
    receipt = pinned(folder / "receipt.json", receipt_sha)
    raw = read_bytes(folder / "body.json")
    if (receipt["schemaVersion"] != "SAGOPALGO_H01_DAILY_CAPTURE_V1" or receipt["status"] != "COMPLETE"
            or (receipt["date"], receipt["market"], receipt["url"]) != (stamp, market, krx.BASE + daily.DAILY_ENDPOINTS[market])
            or utc(receipt["startedAt"]) > utc(receipt["capturedAt"]) or digest(raw) != receipt["sha256"]):
        raise ResearchError("MEMBERSHIP_TRADING_CAPTURE")
    return raw, receipt["capturedAt"]


def build(manifest_path, history_folder, v7_path, baseline_daily, job):
    manifest_raw = read_bytes(manifest_path)
    manifest = read_json(manifest_raw)
    history = pinned(history_folder / "report.json", manifest["historySha256"])
    parent = pinned(v7_path, manifest["v7Sha256"])
    start, end = history["startDate"], history["endDate"]
    entries = history["dayFiles"]
    if (manifest["schemaVersion"] != SCHEMA + "_INPUT" or history["schemaVersion"] != "SAGOPALGO_KRX_HISTORY_REPORT_V1"
            or parent["schemaVersion"] != "SAGOPALGO_UNIVERSE_RECONCILIATION_V7"
            or parent["historyReportSha256"] != manifest["historySha256"] or history["sourceKind"] != "PROVIDER_HISTORICAL"
            or [item["date"] for item in entries] != [
                (day(start) + timedelta(days=offset)).isoformat() for offset in range((day(end) - day(start)).days + 1)]):
        raise ResearchError("MEMBERSHIP_IDENTITY_SCOPE")
    baseline_plan = pinned(baseline_daily / "plan.json", manifest["baselineDailyPlanSha256"])
    monthly = {market: kosis_months(job / "kosis" / market, market, manifest["kosisReceiptSha256"][market])
               for market in TABLES}
    registry, registry_proof = dart_registry(job / "dart", manifest["dartReceiptSha256"])
    filing_text, filings = {}, {}
    for name in FILINGS:
        filing_text[name], filings[name] = kind_text(job / "kind" / name, name, manifest["kindReceiptSha256"][name])
    facts = case_facts(filing_text)
    conflicts = [row for row in parent["rows"] if row.get("individualDisclosureStatus") == "REVIEW_REQUIRED"]
    if (len(conflicts) != 1 or conflicts[0]["observation"]["isin"] != TARGETS["299900"]
            or conflicts[0]["observation"]["observedTo"] != BOUNDARIES[-1]):
        raise ResearchError("MEMBERSHIP_CASE_PARENT_SCOPE")
    conflict = conflicts[0]
    review = conflict["membershipDisclosureReview"]
    matching_notices = [v["announcement"] for v in review["candidateVersions"] if v.get("announcement")
                        and v["announcement"]["sourceUrl"] == filings["delisting"]["sourceUrl"]
                        and v["announcement"]["announcedDelistingDate"] == facts["exchangeAnnouncedDelistingDate"]]
    prior_file = manifest["v7DelistingCaptureFile"]
    if (not any(e.get("date") == BOUNDARIES[-1] and e.get("market") == "KOSDAQ" for e in conflict["evidence"])
            or len(matching_notices) != 1 or not re.fullmatch(r"[0-9]{4}\.bin", prior_file)):
        raise ResearchError("MEMBERSHIP_CASE_PARENT_EVIDENCE")
    prior_body = read_bytes(v7_path.parent / "job" / "raw" / prior_file)
    prior_body_sha = digest(prior_body)
    if (prior_body_sha != matching_notices[0]["sourceSha256"]
            or sources.text(prior_body) != filing_text["delisting"]):
        raise ResearchError("MEMBERSHIP_CASE_PARENT_EVIDENCE")

    spans, counts, case_rows = defaultdict(list), [], []
    market_stats = {market: Counter() for market in TABLES}
    issuer_checks = {market: Counter() for market in TABLES}
    endpoint_relationships = {}
    remaining_trading = set(manifest["dailyReceiptSha256"])
    for entry in entries:
        stamp = entry["date"]
        snapshot = pinned(history_folder / "days" / (stamp + ".json"), entry["sha256"])
        if (snapshot["date"] != stamp or snapshot["status"] != "OBSERVED" or snapshot["unreviewedRecords"]
                or {item["market"] for item in snapshot["sources"]} != set(TABLES)):
            raise ResearchError("MEMBERSHIP_IDENTITY_DAY")
        record = {"date": stamp, "markets": {}}
        target_row = {"date": stamp, "issues": {}}
        for source in snapshot["sources"]:
            market = source["market"]
            observed = [issue for issue in snapshot["issues"] if issue["market"] == market]
            common = [issue for issue in observed if issue["classification"] == "COMMON_SHARE"]
            if len(observed) != source["rows"]:
                raise ResearchError("MEMBERSHIP_IDENTITY_COUNT")
            for issue in common:
                observed_span(spans[issue["isin"]], issue, stamp, source["knownAt"])
                if stamp == end:
                    checked = endpoint_issuer_check(issue, registry)
                    issuer_checks[market][checked["status"]] += 1
                    endpoint_relationships[issue["isin"]] = {**checked, "symbol": issue["symbol"], "market": market,
                        "snapshotDate": stamp, "knownAt": max(source["knownAt"], registry_proof["knownAt"], key=utc)}
            result = {"basicTotal": len(observed), "basicCommon": len(common), "knownAt": source["knownAt"],
                      "dailyTradingCheck": None, "monthlyPublicationCheck": None}
            tag = f"{stamp}-{market}"
            trading = None
            if tag in remaining_trading:
                trading = trade_source(job / "daily", stamp, market, manifest["dailyReceiptSha256"][tag])
                remaining_trading.remove(tag)
            elif stamp == baseline_plan["basisDate"]:
                pinned(baseline_daily / market / "receipt.json", manifest["baselineDailyReceiptSha256"][market])
                receipt, raw = daily.audit_receipt(baseline_daily / market, market, baseline_plan)
                if receipt["sha256"] != manifest["baselineDailyBodySha256"][market]:
                    raise ResearchError("MEMBERSHIP_BASELINE_TRADING_HASH")
                trading = raw, receipt["capturedAt"]
            if trading:
                raw, captured_at = trading
                proof = {"knownAt": max(captured_at, source["knownAt"], key=utc), "bodySha256": digest(raw)}
                result["dailyTradingCheck"] = trade_comparison(observed, daily.parse_daily(raw, market, stamp, captured_at), proof)
                market_stats[market]["trading" + result["dailyTradingCheck"]["status"]] += 1
            month = monthly[market].pop(stamp, None)
            if month:
                status = "MATCH" if month["publishedIssues"] == len(observed) else "CONFLICT"
                result["monthlyPublicationCheck"] = {**month, "status": status,
                    "knownAt": max(month["knownAt"], source["knownAt"], key=utc)}
                market_stats[market]["monthly" + status] += 1
            record["markets"][market] = result
            if market == "KOSDAQ" and stamp in BOUNDARIES:
                target_row.update(knownAt=source["knownAt"], tradingCheck=result["dailyTradingCheck"])
                for issue in common:
                    if TARGETS.get(issue["symbol"]) == issue["isin"]:
                        target_row["issues"][issue["symbol"]] = issue
        counts.append(record)
        if stamp in BOUNDARIES:
            case_rows.append(target_row)
    if remaining_trading or any(monthly.values()):
        raise ResearchError("MEMBERSHIP_IDENTITY_COUNT_SCOPE")

    edges = issuer_edges(parent["rows"])
    for symbol, label, proof in (("299900", "위지윅스튜디오", "delisting"), ("291230", "엔피", "new-shares")):
        isin = TARGETS[symbol]
        fact = {"symbol": symbol, "issuerName": label, "market": "KOSDAQ", "sourceIsin": None, **filings[proof]}
        edges[isin][digest(canonical(fact))] = fact
    by_date = {row["date"]: row for row in case_rows}
    announced, observed = by_date[facts["exchangeAnnouncedDelistingDate"]], by_date[BOUNDARIES[-1]]
    if ("299900" not in announced["issues"] or "299900" in observed["issues"]
            or "299900" not in by_date[BOUNDARIES[-2]]["issues"] or "291230" not in announced["issues"]
            or announced["tradingCheck"]["targetVolume"]["299900"] != 0
            or observed["tradingCheck"]["targetVolume"]["299900"] is not None
            or spans[TARGETS["299900"]][-1]["lastObserved"] != BOUNDARIES[-2]
            or by_date[BOUNDARIES[1]]["issues"]["291230"]["name"] != "엔피"
            or announced["issues"]["291230"]["name"] != "컴투스엔"):
        raise ResearchError("MEMBERSHIP_CASE_BOUNDARY")
    market_dates = {market: {**stats, "dates": len(entries), "independentDailyTotalUnknown": len(entries)}
                    for market, stats in market_stats.items()}
    return {
        "schemaVersion": SCHEMA, "manifestSha256": digest(manifest_raw), "startDate": start, "endDate": end,
        "case": {**facts, "statusListDelistingDate": BOUNDARIES[-1], "basicListFirstAbsenceDate": BOUNDARIES[-1],
                 "lastBasicListPresenceDate": BOUNDARIES[-2], "caseDisposition": "SOURCE_DATES_SEPARATED_CAUSE_UNCONFIRMED",
                 "statusListDiscrepancyExplained": False, "survivingIssuer": "엔피 / 컴투스엔", "absorbedIssuer": "위지윅스튜디오",
                 "knownAt": max([conflict["knownAt"], *(f["knownAt"] for f in filings.values()),
                                 *(r["knownAt"] for r in case_rows),
                                 *(r["tradingCheck"]["knownAt"] for r in case_rows if r["tradingCheck"])], key=utc),
                 "filings": filings, "priorDelistingBodySha256": prior_body_sha, "observations": case_rows},
        "summary": {"markets": market_dates, "commonIsins": len(spans), "isinWithIssuerNameProof": len(spans.keys() & edges.keys()),
                    "isinWithoutIssuerNameProof": len(spans.keys() - edges.keys()),
                    "observedSpans": sum(map(len, spans.values())), "stableLegalIssuerIdsVerifiedForAllIssues": False},
        "dartEndpointRegistryCheck": {**registry_proof, "snapshotDate": end, "markets": issuer_checks,
                                      "historicalMembershipInferred": False},
        "counts": counts, "relations": {isin: {"observedSpans": intervals, "issuerNameEvidence": list(edges[isin].values())}
                                       for isin, intervals in spans.items()},
        "endpointIssuerRelationships": endpoint_relationships,
        "sourceKind": "PROVIDER_OBSERVATIONS", "independentTotalVerified": False, "allLegalEffectsConfirmed": False,
        "marketUniverseComplete": False, "usableForTraining": False, "usableForTrading": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "audit"))
    for name in ("manifest", "history", "v7", "baseline-daily", "job", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = build(args.manifest, args.history, args.v7, args.baseline_daily, args.job)
        immutable_json(args.output, result, require_existing=args.command == "audit")
        print(canonical({**result["summary"], "dartEndpointCheck": result["dartEndpointRegistryCheck"]["markets"],
                         "reportSha256": digest(canonical(result))}).decode())
        return 0
    except (KeyError, ValueError, TypeError, OSError) as error:
        print(json.dumps({"diagnostic": str(error) if isinstance(error, ResearchError) else "MEMBERSHIP_IDENTITY_INPUT_INVALID"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
