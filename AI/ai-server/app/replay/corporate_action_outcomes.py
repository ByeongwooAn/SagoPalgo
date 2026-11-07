"""Offline H05 title inventory and source-bound corporate action outcomes."""

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re

from . import corporate_facts as facts
from .dataset import digest, read_bytes, read_json
from .distribution_facts import Node
from .kind_membership_evidence import BASE, html
from .krx_baseline_validation import immutable_json
from .market_calendar_evidence import text
from .models import ResearchError, utc
from .restructuring_outcomes import DAY, stamp
from .session_evidence import validate_url
from .session_notice_inventory import ListHTML, body_path, query_spec, viewer_documents

TERMS = {"dividend": "현금ㆍ현물배당", "rights": "권리락", "cancel": "주식소각", "halt": "주권매매거래정지",
         "halt-alt": "매매거래 정지", "halt-nospace": "매매거래정지"}
WINDOWS = (("2023-11-01", "2023-12-31"), ("2024-01-01", "2024-12-31"), ("2025-01-01", "2025-12-31"),
           ("2026-01-01", "2026-11-07"))
SCOPE = ("2023-11-01", "2026-11-02", "2026-11-07")
KST = timezone(timedelta(hours=9))
NUMBER = r"([0-9][0-9,]*)"
VIEWER = BASE + "/common/disclsviewer.do"


def require(condition, reason):
    if not condition:
        raise ResearchError("H05_" + reason)


def unique(pattern, value):
    matched = set(re.findall(pattern, value))
    require(len(matched) == 1, "BODY_FIELD_MISSING_OR_CONFLICTING")
    return matched.pop()


def checked_read(path, expected):
    raw = read_bytes(path)
    require(digest(raw) == expected, "INPUT_HASH")
    return raw


def capture(job, pins, name, spec, at):
    folder = job / "captures" / name
    receipt = read_json(checked_read(folder / "receipt.json", pins[name]))
    require(receipt["schemaVersion"] == "SAGOPALGO_H05_CAPTURE_V1" and receipt["status"] == "CAPTURED" and
            receipt["request"] == spec and utc(receipt["startedAt"]) <= utc(receipt["capturedAt"]) <= at, "CAPTURE_BINDING")
    raw = checked_read(folder / "raw.bin", receipt["sha256"])
    return raw, {"sourceUrl": spec["url"], "bodySha256": receipt["sha256"], "observedAt": receipt["capturedAt"]}


def list_page(raw, query, page):
    parser = ListHTML()
    parser.feed(raw.decode("utf-8-sig"))
    parser.close()
    require(len(parser.stack) == 1, "LIST_LAYOUT")
    info = facts.one(node.text() for node in parser.root.walk("div") if node.attrs.get("class") == "info type-00")
    total, actual, pages = (int(n.replace(",", "")) for n in unique(r"전체\s*([0-9,]+)\s*건\s*:\s*(\d+)\s*/\s*(\d+)", info))
    require(total <= 2000 and pages == max(1, (total + 99) // 100) and 1 <= page == actual <= pages, "LIST_PAGE_RANGE")
    rows = []
    for row in parser.root.walk("tr"):
        cells = [x for x in row.children if isinstance(x, Node) and x.tag == "td"]
        if not cells or (total == 0 and len(cells) == 1 and "조회" in cells[0].text()):
            continue
        require(len(cells) == 6, "LIST_COLUMNS")
        rank, listed, issuer, title, submitter = (x.text() for x in cells[:5])
        link = facts.one(x for x in cells[3].walk("a") if x.attrs.get("href") == "#viewer")
        number = unique(r"^openDisclsViewer\('(\d{14})',''\);?$", link.attrs.get("onclick", ""))
        normalized = datetime.strptime(listed, "%Y-%m-%d %H:%M").strftime("%Y-%m-%d %H:%M")
        require(rank.isdecimal() and normalized == listed and query["fromDate"] <= listed[:10] <= query["toDate"] and
                number[:8] == listed[:10].replace("-", ""), "LIST_ROW_SCOPE")
        rows.append({"rank": int(rank), "receipt": number, "market": query["market"], "listedMinuteKst": listed,
                     "issuerDisplayName": issuer, "title": title, "submitter": submitter,
                     "titleCorrectionFlag": "정정]" in title, "sourceUrl": VIEWER + f"?acptno={number}&method=search"})
    ranks = list(range(total - (page - 1) * 100, max(0, total - page * 100), -1))
    require([r["rank"] for r in rows] == ranks and len({r["receipt"] for r in rows}) == len(rows), "LIST_RANK")
    return total, pages, rows


def inventory(job, pins, at):
    all_rows, partitions, used = {}, [], set()
    for key, title in TERMS.items():
        markets = ("KOSPI",) if key.startswith("halt-") else ("KOSPI", "KOSDAQ")
        for market in markets:
            for start, end in WINDOWS:
                query = {"kind": "TITLE", "market": market, "fromDate": start, "toDate": end}
                label = f"list-{key}-{market}-{start}"
                page, pages, total, receipts = 1, 1, None, set()
                while page <= pages:
                    spec = query_spec(query, page)
                    spec["parameters"]["reportNm"] = title
                    name = label + f"-{page:02d}"
                    raw, proof = capture(job, pins, name, spec, at)
                    used.add(name)
                    observed_total, observed_pages, rows = list_page(raw, query, page)
                    if page == 1:
                        pages, total = observed_pages, observed_total
                    require((total, pages) == (observed_total, observed_pages), "LIST_TOTAL_CHANGED")
                    for row in rows:
                        number = row["receipt"]
                        require(number not in receipts, "LIST_DUPLICATE_ACROSS_PAGES")
                        receipts.add(number)
                        row.pop("rank")
                        identity = market, number
                        previous = all_rows.setdefault(identity, row | {"matchedSearches": [], "listEvidence": []})
                        require(all(previous[k] == v for k, v in row.items()), "LIST_IDENTITY_CONFLICT")
                        previous["matchedSearches"].append(key)
                        previous["listEvidence"].append(proof["bodySha256"])
                    page += 1
                require(total == len(receipts), "LIST_COVERAGE")
                partitions.append({"query": key, "market": market, "from": start, "through": end, "count": total, "pages": pages})
    require(used == {name for name in pins if name.startswith("list-")}, "LIST_SCOPE")
    return all_rows, partitions


def source_receipt(url):
    validate_url(url)
    bits = url.split("/")
    return "".join(bits[4:8])


def observed_body(job, pins, key, url, at):
    validate_url(url)
    raw, proof = capture(job, pins, "body-" + key, {"url": url, "method": "GET", "parameters": None}, at)
    return text(raw), proof


def payment(plan, vote, paid):
    approval = stamp(unique(r"주주총회일자 " + DAY, vote))
    per_share = int(facts.integer(unique(r"보통주식 기말배당금 " + NUMBER + r" 중간", vote)))
    approved_total = int(facts.integer(unique(r"배당금총액\(원\) " + NUMBER, vote)))
    paid_approval, paid_total, date_paid = unique(DAY + r" 개최된 (?:지배기업|당사)의 주주총회에서 승인된 배당금은 " +
                                                 NUMBER + r"천원으로, " + DAY + r"에 지급되었습니다", paid)
    decision = stamp(unique(r"이사회결의일\(결정일\) " + DAY, plan))
    scheduled = stamp(unique(r"배당금지급 예정일자 " + DAY, plan))
    record = stamp(unique(r"배당기준일 " + DAY, plan))
    planned_per_share = int(facts.integer(unique(r"1주당 배당금\(원\) 보통주식 " + NUMBER, plan)))
    planned_total = int(facts.integer(unique(r"배당금총액\(원\) " + NUMBER, plan)))
    require("회 사 명 : 주식회사 원익큐엔씨" in paid and approval == stamp(paid_approval) and
            planned_total == approved_total == int(facts.integer(paid_total)) * 1000 and
            per_share == planned_per_share and decision <= approval <= stamp(date_paid), "DIVIDEND_PAYMENT_CONFLICT")
    return {"decisionDate": decision, "recordDate": record, "plannedPaymentDate": scheduled, "exDividendDate": None,
            "approvedDate": approval, "paymentDate": stamp(date_paid), "approvedKrwPerCommonShare": per_share,
            "reportedTotalPaidKrw": approved_total, "paymentBasis": "ISSUER_REPORTED_ACTUAL_PAYMENT"}


def cancellation(plan, body):
    require(plan["kind"] == "SHARE_CANCELLATION_PLAN" and plan["stockCode"] == "005930" and
            "보통주 표준코드 : KR7005930003 (단축코드:A005930)" in body and "변경사유 : 주식소각" in body, "CANCEL_SCOPE")
    decision, scheduled = (facts.one(x["value"] for x in plan["dates"] if x["role"] == role)
                           for role in ("DECISION_DATE", "CANCELLATION_PLANNED_DATE"))
    before, after, removed = (int(facts.integer(n)) for n in unique(
        r"기명식 보통주 " + NUMBER + r"주 → " + NUMBER + r"주 ▶ 변경주식수 : -" + NUMBER + r"주", body))
    planned = int(facts.one(x["value"] for x in plan["numbers"] if x["role"] == "PLANNED_CANCELLATION" and x["shareClass"] == "COMMON"))
    issued = int(facts.one(x["value"] for x in plan["numbers"] if x["role"] == "REPORTED_ISSUED_SHARES" and x["shareClass"] == "COMMON"))
    canceled = stamp(unique(r"발행일\(소각일\) : " + DAY, body))
    listing = stamp(unique(r"변경상장일 : " + DAY, body))
    require(before == issued and before - after == removed == planned and decision <= canceled <= listing, "CANCEL_RECONCILIATION")
    return {"decisionDate": decision, "plannedCancellationDate": scheduled, "actualCancellationDate": canceled,
            "changedListingDate": listing, "before": before, "after": after, "cancelledCommonShares": removed}


def rights_notice(job, pins, case, at):
    market, label, number = case["market"], case["label"], case["receipt"]
    viewer, _ = capture(job, pins, "viewer-" + label,
                        {"url": VIEWER + f"?acptno={number}&method=search", "method": "GET", "parameters": None}, at)
    header = facts.one(x.text() for x in html(viewer).walk("h1"))
    issuer, code = unique(r"^(.+) \(([0-9A-Z]{6})\)$", header)
    doc = facts.one(viewer_documents(viewer))
    require(not doc["correctionMarked"], "RIGHTS_CORRECTION")
    d = doc["document"]
    route, _ = capture(job, pins, "route-" + label + "-" + d,
                       {"url": VIEWER, "method": "POST", "parameters": {"method": "searchContents", "docNo": d}}, at)
    url = body_path(route, d)
    require(source_receipt(url) == number, "RIGHTS_RECEIPT")
    body, proof = observed_body(job, pins, label + "-" + d, url, at)
    if market == "KOSPI":
        require(url.endswith("/99301.htm") and "1. 회사명 " + issuer in body, "RIGHTS_BODY_ISSUER")
        value, cause, applied = unique(r"보통주식 " + NUMBER + r" 3\. 사유 권리락\((유상증자|무상증자)\) 4\. 적용일 " + DAY, body)
    else:
        require(url.endswith("/70766.htm") and issuer + " 보통주식 A" + code in body, "RIGHTS_BODY_ISSUER")
        value, applied, cause = unique(r"보통주식 A" + code + " " + NUMBER + " " + DAY + r" (유상증자|무상증자)", body)
    return {"market": market, "symbol": code, "kind": "RIGHTS_EX_DATE", "issuer": issuer, "receipt": number,
            "appliedDate": stamp(applied), "exchangeReferencePriceKrw": int(facts.integer(value)), "cause": cause, "evidence": [proof]}


def halt_period(start_body, end_body, stamp_date):
    require("동양철관 종목" in start_body and "동양철관(008970) 종목" in end_body, "HALT_ISSUER")
    hour, minute = unique(r"(\d{1,2})시(\d{2})분부터 시장관리상 사유로 매매거래정지", start_body)
    start = datetime.fromisoformat(f"{stamp_date}T{int(hour):02}:{minute}:00").replace(tzinfo=KST)
    quote = datetime.fromisoformat(stamp_date + "T" + unique(r"거래를 (\d\d:\d\d:\d\d)부터 재개", end_body)).replace(tzinfo=KST)
    first, last = unique(r"10분간\((\d\d:\d\d)~(\d\d:\d\d)\) 호가접수를 거쳐 단일가매매", end_body)
    continuous = datetime.fromisoformat(f"{stamp_date}T{last}:00").replace(tzinfo=KST)
    require(start < quote and quote.strftime("%H:%M") == first and continuous - quote == timedelta(minutes=10),
            "HALT_REOPENING_INTERVAL")
    return {"haltDate": stamp_date, "haltLocalMinute": start.isoformat(timespec="minutes"), "haltPrecision": "MINUTE",
            "quoteAcceptanceResumesAt": quote.isoformat(), "continuousTradingReferenceAt": continuous.isoformat(),
            "basis": "EXCHANGE_REOPENING_NOTICE", "actualFirstTradeAt": None}


def build(manifest, artifacts, job):
    spec = read_json(read_bytes(manifest))
    require(spec["schemaVersion"] == "SAGOPALGO_H05_SCOPE_V1", "SCOPE")
    at = utc(spec["reviewedAt"])
    pins = spec["receipts"]
    rows, partitions = inventory(job, pins, at)
    old = {k: read_json(checked_read(artifacts / v["path"], v["sha256"])) for k, v in spec["prior"].items()}
    proofs = {k: observed_body(job, pins, k, url, at) for k, url in spec["bodyUrls"].items()}
    payment_sources = ("dividend-plan", "dividend-vote", "dividend-paid")
    dividend = {"kind": "CASH_DIVIDEND", "market": "KOSDAQ", "symbol": "074600",
                **payment(*(proofs[x][0] for x in payment_sources)), "evidence": [proofs[x][1] for x in payment_sources]}
    cancel_text, cancel_proof = proofs["samsung-cancel"]
    cancel = {"kind": "SHARE_CANCELLATION", "market": "KOSPI", "symbol": "005930",
              **cancellation(old["cancellationPlan"], cancel_text), "evidence": [cancel_proof],
              "planFactId": old["cancellationPlan"]["factId"]}
    rights = [rights_notice(job, pins, case, at) for case in spec["rights"]]
    preferred, preferred_proof = proofs["rights-preferred"]
    require("1우선주" in preferred and "보통주" not in preferred, "OUT_OF_SCOPE_CONTROL")
    halt_bodies, halt_proofs = [], []
    prior = old["haltInventory"]
    for number in ("20250318001877", "20250318002918"):
        versions = [v for row in prior["rows"] for v in row["versions"] if v["document"] == number]
        version = versions[0]
        require(all(v == version for v in versions) and version["rawFile"].startswith("raw/"), "PRIOR_HALT_SOURCE")
        raw = checked_read(artifacts / "session-inventory-20261105" / "job" / version["rawFile"], version["bodySha256"])
        halt_bodies.append(text(raw))
        halt_proofs.append({"sourceUrl": version["url"], "bodySha256": version["bodySha256"],
                            "observedAt": version["knownAt"]})
    exact = {"kind": "SECURITY_HALT", "market": "KOSPI", "symbol": "008970",
             **halt_period(*halt_bodies, "2025-03-18"), "evidence": halt_proofs}
    starts, ends = [facts.one(v for v in old["kindCases"]["facts"] if v["caseId"] == name)
                    for name in ("ecopro-suspension-2024", "ecopro-resumption-2024")]
    require(starts["stockCode"] == ends["stockCode"] == "086520" and starts["market"] == ends["market"] == "KOSDAQ" and
            starts["precision"] == ends["precision"] == "DATE_ONLY" and starts["date"] < ends["date"], "PRIOR_DATE_ONLY_HALT")
    date_only = {"kind": "SECURITY_HALT", "market": "KOSDAQ", "symbol": "086520", "haltDate": starts["date"],
                 "resumptionDate": ends["date"], "haltPrecision": "DATE_ONLY", "haltLocalMinute": None,
                 "quoteAcceptanceResumesAt": None, "actualFirstTradeAt": None,
                 "evidence": [{"sourceUrl": item["sourceUrl"], "bodySha256": item["sourceSha256"], "observedAt": item["knownAt"]}
                              for item in (starts, ends)]}
    cases = [dividend, cancel, *rights, exact, date_only]
    for row in rights:
        require((row["market"], row["receipt"]) in rows, "RIGHTS_INDEX_MISSING")
    for row in cases:
        require(all(utc(proof["observedAt"]) <= at for proof in row["evidence"]), "FUTURE_SOURCE")
        row.update(knownAt=at.isoformat(), automaticEffectAllowed=False)
    counts = Counter((m, key) for (m, _), row in rows.items() for key in row["matchedSearches"])
    return {"schemaVersion": "SAGOPALGO_H05_CORPORATE_OUTCOMES_V1", "knownAt": at.isoformat(), "startDate": SCOPE[0],
            "endDate": SCOPE[1], "publicationThrough": SCOPE[2], "manifestSha256": digest(read_bytes(manifest)),
            "partitions": partitions, "searchCounts": {m: {k: counts[m, k] for k in TERMS} for m in ("KOSPI", "KOSDAQ")},
            "candidateRows": [rows[k] for k in sorted(rows)], "cases": cases, "outOfScopeControl": preferred_proof,
            "allHistoricalActionsComplete": False, "historicalFirstAvailabilityConfirmed": False,
            "referenceEventsEmitted": 0, "priceAdjustmentApplied": False, "usableForTrading": False, "usableForTraining": False}


def as_of(report, at):
    visible = utc(at) >= utc(report["knownAt"])
    return report["cases"] if visible else []


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "audit", "as-of"))
    for name in ("manifest", "artifacts", "job"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--at")
    args = parser.parse_args()
    if args.action == "as-of" and not args.at:
        parser.error("as-of requires --at")
    report = build(args.manifest, args.artifacts, args.job)
    immutable_json(args.job / "report.json", report, require_existing=args.action != "build")
    summary = ({"visibleCases": len(as_of(report, args.at))} if args.action == "as-of" else
               {"candidateRows": len(report["candidateRows"]), "verifiedCases": len(report["cases"])})
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
