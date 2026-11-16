"""Audit field-level issuer evidence for fixed Seibro dividend cohorts."""

import argparse
from collections import Counter
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from io import BytesIO
from pathlib import Path
import re
from urllib.parse import urlsplit

from .corporate_action_outcomes import VIEWER, capture, checked_read, list_page, require
from .dataset import digest, read_bytes, read_json
from .historical_dividend_payments import CONFIRMED, POST_PAYMENT, UNRESOLVED
from .krx_baseline_validation import immutable_json
from .market_calendar_evidence import text
from .models import utc
from .session_evidence import validate_url
from .session_notice_inventory import body_path, query_spec, viewer_documents


SCHEMA = "SAGOPALGO_H05_DIVIDEND_2023_V1"
Q1_2024_SCHEMA = "SAGOPALGO_H05_DIVIDEND_2024_Q1_V1"
SCOPES = {
    SCHEMA: ("2023-01-01", "2023-12-31", 29),
    Q1_2024_SCHEMA: ("2024-01-01", "2024-03-31", 39),
}
WINDOW = {"fromDate": "2023-07-01", "toDate": "2024-06-30"}
FIELDS = {"recordDate": "recordDate", "actualPaymentDate": "displayedPaymentDate", "commonCashPerShare": "commonCashPerShare"}
IR_HOSTS = {"www.samsung.com", "dividend.samsung.com", "www.hanonsystems.com", "www.hanafn.com",
            "www.kbfg.com", "www.dndplatformreit.com", "company.hanssem.com", "www.hyundai.com",
            "www.skreit.co.kr", "www.samsungfnreit.com", "www.masternpremier.com", "koramcothe1.com",
            "www.esrks-reit.com", "www.mkif.com"}
DATE = re.compile(r"(?<!\d)(20\d{2}|\d{2})(?:\s*년\s*|[./-]\s*)(\d{1,2})(?:\s*월\s*|[./-]\s*)(\d{1,2})(?!\d)")
NUMBER = re.compile(r"(?<!\d)\d[\d,]*(?:\.\d+)?")
IR_PAYMENT_COLUMNS = re.compile(r"배당기준일.*주당배당금\(원\)\s*배당지급일")
ROUNDING = {"DOWN": ROUND_DOWN, "HALF_UP": ROUND_HALF_UP}


def validate_ir_url(url):
    parts = urlsplit(url)
    require(parts.scheme == "https" and parts.netloc in IR_HOSTS and not parts.fragment, "DIVIDEND_2023_IR_URL")


def inventory_page(job, name, pin, at, market):
    code, term, page = pin["symbol"], pin["titleTerm"], pin["page"]
    query = {"kind": "TITLE", "market": market, **pin.get("window", WINDOW)}
    request = query_spec(query, page)
    request["parameters"].update(repIsuSrtCd="A" + code, searchCodeType="number", searchCorpName=code,
                                 reportNm=term, marketType="")
    raw, proof = capture(job, {name: pin["sha256"]}, name, request, at)
    _, _, rows = list_page(raw, query, page)
    return code, proof, {r["receipt"]: r for r in rows}


def read_source(job, name, pin, at, pages):
    url = pin["url"]
    listed = None
    if "list" in pin:
        validate_url(url)
        code, page_proof, rows = pages[pin["list"]]
        receipt = pin["receipt"]
        row = rows[receipt]
        listed = row["listedMinuteKst"][:10]
        document = url.split("/")[-2]
        require("/".join(url.split("/")[4:7]) == listed.replace("-", "/"), "DIVIDEND_2023_LIST_DATE")
        view_key, route_key = "view-" + receipt, "route-" + receipt
        viewer, _ = capture(job, {view_key: pin["viewerSha256"]}, view_key,
                            {"method": "GET", "url": row["sourceUrl"], "parameters": None}, at)
        formatted = listed.replace("-", ".")
        require(any(item["document"] == document and item["label"].endswith(f"({formatted})")
                    for item in viewer_documents(viewer)), "DIVIDEND_2023_VIEWER_DOCUMENT")
        request = {"url": VIEWER, "method": "POST", "parameters": {"method": "searchContents", "docNo": document}}
        route, _ = capture(job, {route_key: pin["routeSha256"]}, route_key, request, at)
        require(body_path(route, document) == url, "DIVIDEND_2023_BODY_URL")
        proof_metadata = {"receipt": receipt, "reportedOn": listed, "title": row["title"], "inventory": page_proof}
    else:
        validate_ir_url(url)
        code = pin["symbol"]
        proof_metadata = {"title": pin["title"], "reportedOn": None}
    raw, proof = capture(job, {name: pin["sha256"]}, name, {"method": "GET", "url": url, "parameters": None}, at)
    if "page" in pin:
        from pypdf import PdfReader

        page = pin["page"]
        require(listed is None and urlsplit(url).path.endswith(".pdf") and type(page) is int and page > 0,
                "DIVIDEND_FOLLOWUP_IR_PDF_PAGE")
        pages = PdfReader(BytesIO(raw)).pages
        require(page <= len(pages), "DIVIDEND_FOLLOWUP_IR_PDF_PAGE")
        return code, " ".join(pages[page - 1].extract_text().split()), proof | proof_metadata | {"page": page}
    return code, text(raw), proof | proof_metadata


def assess(field, selected, expected, code, sources):
    value = selected.get("value")
    reason = selected.get("reason")
    require((value is None) != (reason is None) and (reason is None or bool(reason.strip())), "DIVIDEND_2023_FIELD_DISPOSITION")
    evidence = []
    for point in selected["evidence"]:
        symbol, body, proof = sources[point["source"]]
        markers = point["markers"]
        require(symbol == code and bool(markers) and all(mark and mark in body for mark in markers), "DIVIDEND_2023_FIELD_SOURCE")
        evidence.append(proof)
    if value is None:
        return {"status": "UNVERIFIED", "reason": reason, "seibroValue": expected, "evidence": evidence}

    require(len(evidence) == 1, "DIVIDEND_2023_VALUE_SOURCE")
    marks = " ".join(selected["evidence"][0]["markers"])
    calculation = selected.get("calculation")
    if field == "commonCashPerShare":
        numbers = {Decimal(x.replace(",", "")) for x in NUMBER.findall(marks)}
        if calculation:
            total, shares = (Decimal(calculation[key]) for key in ("totalKrw", "shares"))
            require(total in numbers and shares in numbers and shares > 0 and calculation["scale"] == 10
                    and calculation["rounding"] in ROUNDING, "DIVIDEND_2023_AMOUNT_INPUTS")
            amount = (total / shares).quantize(Decimal("0.0000000001"), rounding=ROUNDING[calculation["rounding"]])
            require(amount == Decimal(value), "DIVIDEND_2023_AMOUNT_CALCULATION")
        else:
            require(Decimal(value) in numbers, "DIVIDEND_2023_AMOUNT")
        agrees = Decimal(value) == Decimal(expected)
    else:
        dates = [f"{int(y) + (2000 if len(y) == 2 else 0):04}-{int(m):02}-{int(d):02}"
                 for y, m, d in DATE.findall(marks)]
        require(value in dates, "DIVIDEND_2023_DATE")
        agrees = value == expected
    if field == "actualPaymentDate":
        proof = evidence[0]
        if proof["reportedOn"] is None:
            # Retrospective IR sources carry observation time, with no KIND receipt date.
            completion = (bool(POST_PAYMENT.search(marks)) if "page" in proof else
                          "배당 내역" in marks and bool(IR_PAYMENT_COLUMNS.search(marks)) and dates[-1] == value)
            supported = max(value, expected) < proof["observedAt"][:10] and completion
        else:
            supported = max(value, expected) < proof["reportedOn"] and bool(POST_PAYMENT.search(marks))
        require(supported, "DIVIDEND_2023_ACTUAL_PAYMENT")
    return {"status": "MATCH" if agrees else "DIFFERS", "issuerValue": value, "seibroValue": expected,
            "evidence": evidence} | ({"calculation": calculation} if calculation else {})


def build(manifest, artifacts, job, *, schema=None):
    raw = read_bytes(manifest)
    spec = read_json(raw)
    version = spec["schemaVersion"]
    require(version in SCOPES and (schema is None or version == schema), "DIVIDEND_2023_SCHEMA")
    start, end, row_count = SCOPES[version]
    at = utc(spec["reviewedAt"])
    pin = spec["input"]
    parent = read_json(checked_read(artifacts / pin["path"], pin["sha256"]))
    require(utc(parent["knownAt"]) <= at, "DIVIDEND_2023_FUTURE_PARENT")
    cohort = [row for group in parent["issuerYears"] for row in group["events"]
              if start <= row["displayedPaymentDate"] <= end]
    targets = {row["symbol"]: row for row in cohort}
    by_symbol = {row["symbol"]: row for row in spec["rows"]}
    require(len(cohort) == len(targets) == len(by_symbol) == len(spec["rows"]) == row_count
            and targets.keys() == by_symbol.keys(), "DIVIDEND_2023_SCOPE")
    pages = {name: inventory_page(job, name, page, at, targets[page["symbol"]]["market"])
             for name, page in spec["listPages"].items()}
    sources = {name: read_source(job, name, source, at, pages) for name, source in spec["sources"].items()}
    results = []
    for code, target in sorted(targets.items()):
        selected = by_symbol[code]
        require(selected["fields"].keys() == FIELDS.keys() and selected["reviewedReports"], "DIVIDEND_2023_REVIEW_FIELDS")
        if version == Q1_2024_SCHEMA:
            require(selected["ksdRowSha256"] == target["ksdRowSha256"], "DIVIDEND_Q1_2024_ROW_IDENTITY")
        reviewed = []
        for name in selected["reviewedReports"]:
            symbol, _, proof = sources[name]
            require(symbol == code and proof["reportedOn"] > target["displayedPaymentDate"], "DIVIDEND_2023_REVIEW_REPORT_DATE")
            reviewed.append(proof)
        ir = []
        for name in selected["reviewedIr"]:
            symbol, _, proof = sources[name]
            require(symbol == code and proof["reportedOn"] is None, "DIVIDEND_2023_REVIEW_IR")
            ir.append(proof)
        fields = {field: assess(field, selected["fields"][field], target[key], code, sources) for field, key in FIELDS.items()}
        confirmed = all(field["status"] == "MATCH" for field in fields.values())
        results.append({"market": target["market"], "symbol": code, "issuer": target["issuer"],
                        "ksdRowSha256": target["ksdRowSha256"], "ksdEvidence": target["ksdEvidence"],
                        "reviewedReports": reviewed, "reviewedIr": ir, "fields": fields,
                        "status": CONFIRMED if confirmed else UNRESOLVED})
    field_counts = {field: dict(Counter(row["fields"][field]["status"] for row in results)) for field in FIELDS}
    return {"schemaVersion": version, "manifestSha256": digest(raw), "knownAt": at.isoformat(), "rows": results,
            "statusCounts": dict(Counter(row["status"] for row in results)), "fieldCounts": field_counts,
            "historicalFirstAvailabilityConfirmed": False, "usableForTraining": False, "usableForTrading": False}


def main(*, schema=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "audit"))
    for name in ("manifest", "artifacts", "job"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    report = build(args.manifest, args.artifacts, args.job, schema=schema)
    immutable_json(args.job / "report.json", report, require_existing=args.action == "audit")
    print(report["statusCounts"], report["fieldCounts"])


if __name__ == "__main__":
    main()
