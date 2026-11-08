"""Reconcile H05 stock-issue details, exchange notices and dividend date evidence."""

import argparse
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path
import re

from . import cancellation_evidence, ksd_dividend_evidence
from .corporate_action_event_audit import body_fields, name_key
from .corporate_action_outcomes import VIEWER, capture, checked_read, require
from .dataset import digest, read_bytes, read_json
from .kind_membership_evidence import html
from .krx_baseline_validation import immutable_json
from .market_calendar_evidence import text
from .models import ResearchError, utc
from .restructuring_outcomes import DAY, stamp
from .session_evidence import validate_url
from .session_notice_inventory import body_path, viewer_documents

SCHEMA = "SAGOPALGO_H05_OUTCOME_CENSUS_V1"
PAID_CASES = {
    "dividend-kcfeed": {
        "url": "https://kind.krx.co.kr/external/2025/08/14/002514/20250814007683/11012.htm",
        "issuer": "케이씨피드", "market": "KOSDAQ", "symbol": "025880", "recordDate": "2024-12-31",
        "paymentDate": "2025-04-11", "amount": "100",
        "markers": ("회 사 명 : 주식회사 케이씨피드", "2024년의 결산 배당금은", "보통주 1주당 100원",
                    "2025년 4월 11일 배당금을 지급하였습니다"),
    },
    "dividend-covered": {
        "url": "https://kind.krx.co.kr/external/2026/05/29/000762/20260529001301/99667.htm",
        "issuer": "대교", "market": "KOSPI", "symbol": "019680", "recordDate": "2025-12-31",
        "paymentDate": "2026-04-07", "amount": "60",
        "markers": ("기업명 (주)대교", "보통주(주당 60원)", "배당기준일(2025년 12월 31일)",
                    "2026년 4월 7일 배당금을 지급하였습니다"),
    },
}


def notice_role(row, windows):
    title, day = row["title"], row["listedMinuteKst"][:10]
    cancel, action = (windows[key] for key in ("cancellation", "marketActions"))
    if cancel["from"] <= day <= cancel["through"] and "상장" in title and "소각" in title:
        return "CANCEL"
    if not action["from"] <= day <= action["through"] or re.search("ETF|ETN|수익증권|투자회사|신주인수권", title):
        return None
    if "category/halt" in row["routes"] and re.search(r"거래\s*(?:정지|재개|중단)", title):
        if re.search(r"정지\s*및\s*정지해제|정지\s*기간변경", title):
            return "HALT_BOUNDARY_REVIEW"
        return "REOPENING" if re.search(r"정지\s*해제|거래\s*재개", title) else "HALT"
    if "category/rights" in row["routes"] and re.search("권리락|권배락|배당락", title):
        return "DIVIDEND_OR_COMBINED" if re.search("권배락|배당락", title) else "RIGHTS"
    return None


def kospi_halt_dates(form, body, scope):
    if form not in {"68054.htm", "68060.htm"}:
        return None
    result = {}
    for marker, key in (("매매거래정지일", "haltDate"), ("매매거래정지해제일", "reopeningDate")):
        matches = re.findall(marker + r"\s+" + DAY + r"\s*부터", body)
        if len(matches) == 1:
            value = stamp(matches[0])
            if scope[0] <= value <= scope[1]:
                result[key] = value
    return result or None


def kosdaq_halt_change(form, body, issuer):
    if form != "70798.htm":
        return None
    fields = re.findall(r"1\.\s*대상종목 (.{1,80}?) 보통주(?:식)? 2\..*?가\.변경전\s+(.{1,220}?)\s+"
                        r"나\.변경후\s+(.{1,220}?)\s+4\.근거규정", body)
    if len(fields) == 1 and name_key(fields[0][0]) == name_key(issuer):
        return {"previousDurationDisplay": fields[0][1], "updatedDurationDisplay": fields[0][2],
                "actualFirstTradeAt": None}
    return None


def notice_review(job, pins, parent, at, scope, windows, gap_targets):
    result, visited = [], set()
    require(set(windows) == {"cancellation", "marketActions"}, "NOTICE_CENSUS_WINDOWS")
    for window in windows.values():
        start, end = window["from"], window["through"]
        require(date.fromisoformat(start).isoformat() == start and date.fromisoformat(end).isoformat() == end and
                scope[0] <= start <= end <= parent["scope"]["publicationThrough"], "NOTICE_CENSUS_WINDOW")

    def read(stage, receipt, spec):
        name = f"proof-{stage}-{receipt}"
        if name in pins:
            visited.add(name)
            return capture(job, pins, name, spec, at)
        return None, None

    for row in parent["candidateRows"]:
        role = "CANCEL" if row["receipt"] in gap_targets else notice_role(row, windows)
        if role is None:
            continue
        market, receipt = row["market"], row["receipt"]
        record = {"market": market, "receipt": receipt, "title": row["title"], "role": role,
                  "listedMinuteKst": row["listedMinuteKst"], "listIssuer": row["issuerDisplayName"],
                  "status": "NOTICE_VIEWER_NOT_CAPTURED", "evidence": []}
        result.append(record)
        viewer, proof = read("viewer", receipt, {"method": "GET", "url": row["sourceUrl"], "parameters": None})
        if viewer is None:
            continue
        record["evidence"].append(proof)
        try:
            docs = viewer_documents(viewer)
        except ResearchError:
            record["status"] = "NOTICE_VIEWER_LAYOUT_UNCONFIRMED"
            continue
        if len(docs) != 1 or docs[0]["correctionMarked"] or row["titleCorrectionFlag"]:
            record.update(status="NOTICE_VERSION_REVIEW", viewerVersions=docs)
            continue
        document = docs[0]["document"]
        record.update(document=document, status="NOTICE_ROUTE_NOT_CAPTURED")
        route, proof = read("route", receipt, {"method": "POST", "url": VIEWER,
                                             "parameters": {"method": "searchContents", "docNo": document}})
        if route is None:
            continue
        record["evidence"].append(proof)
        try:
            url = body_path(route, document)
        except ResearchError:
            record["status"] = "NOTICE_BODY_ROUTE_UNCONFIRMED"
            continue
        raw, proof = read("body", receipt, {"method": "GET", "url": url, "parameters": None})
        if raw is None:
            record["status"] = "NOTICE_BODY_NOT_CAPTURED"
            continue
        record["evidence"].append(proof)
        record["status"] = "BODY_SCOPE_OR_FIELDS_UNCONFIRMED"
        headers = [n.text() for n in html(viewer).walk("h1")]
        match = re.fullmatch(r"(.+) \(([0-9A-Z]{6})\)", headers[0]) if len(headers) == 1 else None
        if not match:
            continue
        issuer, symbol = match.groups()
        form, body = url.rsplit("/", 1)[1], text(raw)
        if role == "CANCEL":
            fields = cancellation_evidence.common_notice(market, form, body, symbol)
            if fields:
                record.update(fields, status="COMMON_SHARE_NOTICE_FIELDS", noticeIssuer=issuer)
        else:
            fields = body_fields(market, role, form, body, issuer, symbol)
            if fields:
                status = ("EXCHANGE_NOTICE_FIELDS_VERIFIED" if scope[0] <= fields["appliedDate"] <= scope[1]
                          else "APPLIED_DATE_OUTSIDE_SCOPE")
                record.update(fields, status=status, noticeIssuer=issuer, noticeSymbol=symbol)
            elif market == "KOSPI" and role in {"HALT", "REOPENING", "HALT_BOUNDARY_REVIEW"}:
                dates = kospi_halt_dates(form, body, scope)
                if dates:
                    record.update(dates, status="HALT_DATES_SHARE_CLASS_UNCONFIRMED",
                                  noticeIssuer=issuer, viewerSymbol=symbol)
            elif market == "KOSDAQ" and role == "HALT_BOUNDARY_REVIEW":
                change = kosdaq_halt_change(form, body, issuer)
                if change:
                    record.update(change, status="HALT_PERIOD_CHANGE_FIELDS",
                                  noticeIssuer=issuer, noticeSymbol=symbol)
    require(visited == set(pins), "NOTICE_CENSUS_CAPTURE_SCOPE")
    return result


def issuer_payment_evidence(job, pins, prior, at, dividend):
    cases = []
    existing, = [c for c in prior["previouslyReviewedCases"] if c["kind"] == "CASH_DIVIDEND"]
    cases.append({"market": existing["market"], "symbol": existing["symbol"], "recordDate": existing["recordDate"],
                  "paymentDate": existing["paymentDate"], "amount": str(existing["approvedKrwPerCommonShare"]),
                  "evidence": existing["evidence"]})
    require(set(pins) <= set(PAID_CASES), "ISSUER_PAYMENT_CAPTURE_SCOPE")
    for name, case in PAID_CASES.items():
        if name not in pins:
            continue
        url = case["url"]
        validate_url(url)
        raw, proof = capture(job, pins, name, {"method": "GET", "url": url, "parameters": None}, at)
        contents = text(raw)
        require(all(marker in contents for marker in case["markers"]), "ISSUER_PAYMENT_STATEMENT_MISSING")
        cases.append({k: case[k] for k in ("market", "symbol", "recordDate", "paymentDate", "amount")} | {"evidence": [proof]})
    for case in cases:
        matched = [row for row in dividend["dividendRows"]
                   if all(row[k] == case[k] for k in ("market", "symbol", "recordDate"))]
        if len(matched) != 1:
            case["status"] = "ISSUER_PAYMENT_KSD_LINK_MISSING_OR_AMBIGUOUS"
            continue
        row = matched[0]
        if row["displayedPaymentDate"] != case["paymentDate"] or Decimal(row["cashAmountPerShare"]) != Decimal(case["amount"]):
            case["status"] = "ISSUER_PAYMENT_KSD_CONFLICT"
            continue
        case["status"] = "ISSUER_REPORTED_PAYMENT_CONFIRMED"
        row.update(actualPaymentDate=case["paymentDate"], actualPaymentBasis=case["status"], issuerEvidence=case["evidence"])
    return cases


def build(manifest, artifacts, job):
    raw = read_bytes(manifest)
    spec = read_json(raw)
    require(spec["schemaVersion"] == SCHEMA, "OUTCOME_CENSUS_SCOPE")
    at = utc(spec["reviewedAt"])
    pin = spec["parent"]
    parent = read_json(checked_read(artifacts / pin["path"], pin["sha256"]))
    require(utc(parent["knownAt"]) <= at, "FUTURE_OUTCOME_PARENT")
    scope = parent["scope"]["startDate"], parent["scope"]["endDate"]
    require(scope == ksd_dividend_evidence.PAYMENT_SCOPE, "OUTCOME_CENSUS_PERIOD")
    cancellations = cancellation_evidence.audit(job, spec["stockReceipts"], parent, at, scope)
    gaps = cancellation_evidence.gap_targets(cancellations, parent["candidateRows"])
    notices = notice_review(job, spec["noticeReceipts"], parent, at, scope, spec["noticeWindows"], gaps)
    dividend = ksd_dividend_evidence.audit(job, spec["ksdReceipts"], at)
    paid = issuer_payment_evidence(job, spec["issuerReceipts"], parent, at, dividend)
    prior = parent["cancellationListingCrossChecks"][0]
    existing, = [case for case in parent["previouslyReviewedCases"] if case["kind"] == "SHARE_CANCELLATION"]
    carried = {"market": existing["market"], "noticeIssuer": prior["listing"]["issuer"], "symbol": prior["symbol"],
               "isin": "KR7005930003", "listingDate": existing["changedListingDate"], "after": existing["after"],
               "signedShareChange": -existing["cancelledCommonShares"], "cancellationDate": existing["actualCancellationDate"],
               "status": "COMMON_SHARE_NOTICE_FIELDS", "evidence": existing["evidence"]}
    cancellation_evidence.notice_links([*notices, carried], cancellations, scope)
    return {"schemaVersion": SCHEMA, "manifestSha256": digest(raw), "knownAt": at.isoformat(), "scope": parent["scope"],
            "cancellations": cancellations, "cancellationCounts": cancellation_evidence.counts(cancellations),
            "notices": notices, "noticeWindows": spec["noticeWindows"], "noticeCounts": dict(Counter(n["status"] for n in notices)),
            "issueDateGapNoticeTargets": sorted(gaps),
            "priorCancellationCrossCheck": carried, "issuerPayments": paid, "dividend": dividend,
            "fullEventCoverageConfirmed": False, "historicalFirstAvailabilityConfirmed": False,
            "usableForTraining": False, "usableForTrading": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "audit"))
    for name in ("manifest", "artifacts", "job"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    report = build(args.manifest, args.artifacts, args.job)
    immutable_json(args.job / "outcome-census.json", report, require_existing=args.action == "audit")
    print({key: report[key] for key in ("cancellationCounts", "noticeCounts")})
    print(report["dividend"]["dividendCounts"])


if __name__ == "__main__":
    main()
