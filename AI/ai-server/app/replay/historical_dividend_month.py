"""Rebuild fixed monthly dividend reviews from pinned OpenDART and Seibro evidence."""

import argparse
from collections import Counter
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from html import unescape
from io import BytesIO
from pathlib import Path
import re
from zipfile import ZipFile

from .corporate_action_outcomes import checked_read, require
from .dataset import canonical, digest, read_json
from .historical_dividend_payments import CONFIRMED, POST_PAYMENT, UNRESOLVED, UNREVIEWED
from .krx_baseline_validation import immutable_json
from .models import utc


SCHEMA = "SAGOPALGO_H05_DIVIDEND_2024_APRIL_V1"
MAY_SCHEMA = "SAGOPALGO_H05_DIVIDEND_2024_MAY_V1"
JUNE_SCHEMA = "SAGOPALGO_H05_DIVIDEND_2024_JUNE_V1"
JULY_SCHEMA = "SAGOPALGO_H05_DIVIDEND_2024_JULY_V1"
AUGUST_SCHEMA = "SAGOPALGO_H05_DIVIDEND_2024_AUGUST_V1"
SEPTEMBER_SCHEMA = "SAGOPALGO_H05_DIVIDEND_2024_SEPTEMBER_V1"
OCTOBER_SCHEMA = "SAGOPALGO_H05_DIVIDEND_2024_OCTOBER_V1"
SCOPES = {
    SCHEMA: ("2024-04", {CONFIRMED: 3, UNRESOLVED: 4, UNREVIEWED: 1123}),
    MAY_SCHEMA: ("2024-05", {UNREVIEWED: 23}),
    JUNE_SCHEMA: ("2024-06", {UNREVIEWED: 5}),
    JULY_SCHEMA: ("2024-07", {UNREVIEWED: 26}),
    AUGUST_SCHEMA: ("2024-08", {UNREVIEWED: 77}),
    SEPTEMBER_SCHEMA: ("2024-09", {UNREVIEWED: 10}),
    OCTOBER_SCHEMA: ("2024-10", {UNREVIEWED: 21}),
}
MARKETS = {"Y": "KOSPI", "K": "KOSDAQ"}
ROW_ID = re.compile(r"[0-9]{14}")
HASH = re.compile(r"[a-f0-9]{64}")
HTML_ROW = re.compile(r"<tr\b[^<>]*>(.*?)</tr>", re.I | re.S)
HTML_CELL = re.compile(r"<t[dh]\b[^<>]*>(.*?)</t[dh]>", re.I | re.S)
TAG = re.compile(r"<[^<>]*>")
DATE = re.compile(r"(?<!\d)(20\d{2}|\d{2})(?:\s*년\s*|[-./]\s*)(\d{1,2})(?:\s*월\s*|[-./]\s*)(\d{1,2})(?!\d)")
NUMBER = re.compile(r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?")
DECISION_TITLE = re.compile(r"현금(?:[ㆍ·.\s]*현물)?\s*배당\s*결정|금전\s*배당\s*결정|금전\s*분배\s*결의")
REPORT_TITLE = re.compile(r"(?:사업|반기|분기|기업지배구조)\s*보고서")
PAID_DIVIDEND_NOTE = re.compile(
    r"(?:현금)?배당\s*\(\s*['’]?(?:20\d{2}|\d{2})[./-]\s*\d{1,2}[./-]\s*\d{1,2}\.?\s*지급\s*\)"
)
PAYMENT_PROGRESS = re.compile(r"배당기준일(?:\s+설정)?\s*\d+\)\s*(.*?)\s*:?\s+배당금\s+지급(?:일)?$")
DART = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo="
NAVER_IR = ("https://kind.krx.co.kr/external/2024/06/26/000486/20240625001176/"
            "NAVER_Integrated_Report_2023_ver3.pdf")
IR_ID = "naver-2023-integrated"
MKIF_H1_ID = "mkif-2024-h1-results"
MKIF_Q3_ID = "mkif-2024-q3-presentation"
MKIF_IR = "https://www.mkif.com/assets/mkif/ko-kr/investor-centre/public-filings-and-reports/2024/"
IR_PDFS = {
    IR_ID: (NAVER_IR, "NAVER 2023 통합보고서", "2024-06-26"),
    MKIF_H1_ID: (MKIF_IR + "ir-release-2407-1h-2024-financial%2Btraffic-results-kor.pdf",
                 "맥쿼리인프라 2024년 상반기 실적 발표", "2024-07-31"),
    MKIF_Q3_ID: (MKIF_IR + "2410-ir-general-presentation-3q-2024-kor.pdf",
                 "맥쿼리인프라 2024년 3분기 실적 발표", "2024-10-31"),
}
SKREIT_HISTORY_ID = "skreit-dividend-history"
SKREIT_HISTORY_URL = "https://www.skreit.co.kr/investment/dividend.php"
SKREIT_HISTORY_HEADER = ["구분", "배당기준일", "배당지급일", "주당배당(원)", "배당총액 (백만원)"]
SKREIT_AMOUNT_HEADER = ["정기배당", "특별배당", "합계"]
HYUNDAI_HISTORY_ID = "hyundai-motor-dividend-history"
HYUNDAI_HISTORY_URL = "https://www.hyundai.com/worldwide/ko/company/ir/stock-information/shareholder-return-policy"
HYUNDAI_HISTORY_HEADER = ["배당기준일", "배당지급일", "보통주", "1우선주", "2우선주", "3우선주"]
ESRKS_HISTORY_ID = "esrks-dividend-history"
ESRKS_HISTORY_URL = "https://www.esrks-reit.com/ir/dividend-status"
ESRKS_HISTORY_HEADER = [
    "연도", "회계연도", "배당락일", "배당기준일", "정기 주주총회 소집일", "주당배당금(원)", "배당지급일",
]
ISSUER_HISTORY_TABLES = {
    HYUNDAI_HISTORY_ID: ("005380", HYUNDAI_HISTORY_URL, "현대자동차 배당 이력", HYUNDAI_HISTORY_HEADER, "보통주", "HYUNDAI"),
    ESRKS_HISTORY_ID: ("365550", ESRKS_HISTORY_URL, "ESR켄달스퀘어리츠 배당 이력",
                       ESRKS_HISTORY_HEADER, "주당배당금(원)", "ESRKS"),
}
FIELD_INPUTS = {"recordDate": "recordDate", "actualPaymentDate": "displayedPaymentDate",
                "commonCashPerShare": "commonCashPerShare"}


def plain(value):
    return " ".join(unescape(TAG.sub(" ", value)).split())


def label(value):
    return re.sub(r"\s+", "", re.sub(r"^\d+\.\s*", "", value))


def dates(value):
    result = []
    for year, month, day in DATE.findall(value):
        try:
            result.append(date(int(year) + (2000 if len(year) == 2 else 0), int(month), int(day)).isoformat())
        except ValueError:
            continue
    return result


def decision_facts(source):
    """Read only value cells in the current decision form, excluding the correction comparison."""
    cells = [[plain(cell) for cell in HTML_CELL.findall(row)] for row in HTML_ROW.findall(source)]
    records, amounts, schedules = {}, {}, {}
    for row in cells:
        values = [label(cell) for cell in row]
        if len(row) == 2 and values[0] in {"배당기준일", "분배기준일"}:
            day = dates(row[1])
            if len(day) == 1:
                records[day[0]] = row
        if len(row) == 3 and values[0] in {"1주당배당금(원)", "주당배당금(원)"} and values[1] in {"보통주식", "보통주"}:
            if NUMBER.fullmatch(row[2]):
                amounts[row[2].replace(",", "")] = row
        if len(row) == 2 and values[0] == "분배금액(원)" and NUMBER.fullmatch(row[1]):
            amounts[row[1].replace(",", "")] = row
        if len(row) == 2 and values[0] in {"배당금지급예정일", "배당금지급예정일자"}:
            schedules[row[1]] = row
    return records, amounts, schedules


def load_indexes(job, pins, selected_receipts, at):
    require(bool(pins), "APRIL_EMPTY_INDEX")
    receipts = {}
    for name, expected_hash in pins.items():
        require(re.fullmatch(r"(?:periodic|decision|target)-[YK]-[0-9-]+", name), "APRIL_INDEX_NAME")
        folder = job / "index" / name
        proof = read_json(checked_read(folder / "receipt.json", expected_hash))
        request = proof["request"]
        require(utc(proof["startedAt"]) <= utc(proof["capturedAt"]) <= at and request["corp_cls"] in MARKETS
                and "crtfc_key" not in request, "APRIL_PAGE_BINDING")
        result = read_json(checked_read(folder / "raw.json", proof["sha256"]))
        if result["status"] == "013":
            continue
        require(result["status"] == "000" and int(result["page_no"]) == int(request["page_no"]), "APRIL_DART_LIST")
        for row in result["list"]:
            receipt = row["rcept_no"]
            if receipt not in selected_receipts:
                continue
            require(ROW_ID.fullmatch(receipt) and row["corp_cls"] == request["corp_cls"]
                    and request["bgn_de"] <= row["rcept_dt"] <= request["end_de"]
                    and row["rcept_dt"] == receipt[:8], "APRIL_LIST_ROW_IDENTITY")
            present = receipts.setdefault(receipt, row)
            require(present == row, "APRIL_LIST_RECEIPT_CONFLICT")
    require(receipts.keys() == selected_receipts, "APRIL_MISSING_INDEX_RECEIPT")
    return receipts


def load_document(job, receipt, expected_hash, item, at):
    require(ROW_ID.fullmatch(receipt), "APRIL_DOCUMENT_RECEIPT")
    folder = job / "documents" / receipt
    capture = read_json(checked_read(folder / "receipt.json", expected_hash))
    require(capture["receiptNumber"] == receipt and capture["source"] == "OpenDART document.xml"
            and utc(capture["startedAt"]) <= utc(capture["capturedAt"]) <= at, "APRIL_DOCUMENT_BINDING")
    status = capture["status"]
    raw = checked_read(folder / ("original.zip" if status == "CAPTURED" else "response.bin"), capture["sha256"])
    filing = date(int(receipt[:4]), int(receipt[4:6]), int(receipt[6:8])).isoformat()
    proof = {"receipt": receipt, "sourceUrl": DART + receipt, "reportedOn": filing, "title": item["report_nm"].strip(),
             "observedAt": capture["capturedAt"], "archiveSha256": capture["sha256"], "status": status}
    if status != "CAPTURED":
        return None, proof
    with ZipFile(BytesIO(raw)) as archive:
        entries = archive.infolist()
        main = [entry for entry in entries if entry.filename == f"{receipt}.xml"]
        if (not main and str(item["report_nm"]).startswith("[첨부정정]") and 1 <= len(entries) <= 32
                and all(re.fullmatch(fr"{receipt}_[0-9]+\.xml", entry.filename) for entry in entries)):
            return None, proof | {"status": "ATTACHMENT_ONLY"}
        require(1 <= len(entries) <= 32 and len(main) == 1
                and 0 < main[0].file_size <= 32 * 1024 * 1024, "APRIL_DART_DOCUMENT_LAYOUT")
        body = archive.read(main[0]).decode("utf-8-sig")
    company = re.search(r'<COMPANY-NAME\b[^<>]*\bAREGCIK="([0-9]{8})"', body)
    if company:
        require(company[1] == item["corp_code"], "APRIL_CONTENT_ISSUER")
    return body, proof


def compare(value, expected, proof, markers):
    same = Decimal(value) == Decimal(expected) if NUMBER.fullmatch(value) and NUMBER.fullmatch(expected) else value == expected
    return {"status": "MATCH" if same else "DIFFERS", "issuerValue": value,
            "seibroValue": expected, "evidence": [proof | {"markers": markers}]}


def unknown(expected, reason, evidence=()):
    return {"status": "UNVERIFIED", "seibroValue": expected, "reason": reason, "evidence": list(evidence)}


def select_decision(target, decisions):
    basis = target["recordDate"]
    matching = [entry for entry in decisions if basis in entry[0][0]]
    return max(matching, key=lambda entry: entry[1]["receipt"]) if matching else None


def decision_fields(target, reviewed, fallback):
    basis, amount = target["recordDate"], target["commonCashPerShare"]
    selected = select_decision(target, reviewed)
    if selected is None:
        evidence = [proof for _, proof in reviewed]
        return unknown(basis, fallback, evidence), unknown(amount, fallback, evidence), None
    (records, amounts, schedules), proof = selected
    record = compare(basis, basis, proof, records[basis])
    if len(amounts) == 1:
        value, markers = next(iter(amounts.items()))
        cash = compare(value, amount, proof, markers)
    else:
        cash = unknown(amount, "대상 회차 결정공시에서 단일 보통주 주당액을 판독하지 못함", [proof])
    plan = next(iter(schedules)) if len(schedules) == 1 else None
    return record, cash, plan


def manual_payment(target, entry, markers_found, report):
    expected = target["displayedPaymentDate"]
    value, marker = entry["value"], entry["marker"]
    expected_basis = target["recordDate"]
    explicit_date = value in dates(marker)
    if report["receipt"] == IR_ID or entry.get("dateContext") == "RECORD_YEAR":
        year, month, day = (int(part) for part in value.split("-"))
        explicit_date = explicit_date or (
            (report["receipt"] == IR_ID and f"{year}년" in marker
             and re.search(fr"\b{month}월\s*{day}일\s*지급", marker))
            or (expected_basis in dates(marker) and expected_basis.startswith(f"{year}-")
                and re.search(fr"{month}월\s*{day}일에\s*(?:지급되었|보통주 .* 현금배당을 실시하였)", marker))
        )
    require(report["reportedOn"] > max(value, expected) and marker in markers_found and explicit_date,
            "APRIL_PAYMENT_MARKER")
    progress = PAYMENT_PROGRESS.search(marker)
    completed_progress = (progress and expected_basis in dates(marker[:progress.start()])
                          and dates(progress[1]) == [value])
    require(not re.search(r"지급\s*예정|지급\s*결의일", marker) and
            (POST_PAYMENT.search(marker) or PAID_DIVIDEND_NOTE.search(marker) or completed_progress
             or re.search(r"배당금\s*지급\s*일(?:자)?(?:은|는|\s|[:：])", marker)
             or (entry.get("dateContext") == "RECORD_YEAR" and "현금배당을 실시하였" in marker
                 and expected_basis in dates(marker))),
            "APRIL_PAYMENT_EXPRESSION")
    if target["symbol"] == "015360":
        require(expected_basis in dates(marker) or entry.get("roundMarker") in {"결산배당", "분기배당"}
                and entry["roundMarker"] in marker, "APRIL_MULTIPLE_DISTRIBUTIONS")
    return compare(value, expected, report, [marker])


def reported_payment(target, entries, reports, markers, reason):
    results = []
    for entry in entries:
        receipt = entry["receipt"]
        require(receipt in reports, "APRIL_PAYMENT_SOURCE_ROLE")
        results.append(manual_payment(target, entry, markers.get(receipt, ()), reports[receipt]))
    if len(results) == 1:
        return results[0]
    require(reason and len({result["issuerValue"] for result in results}) > 1, "DIVIDEND_PAYMENT_CONFLICT")
    evidence = [result["evidence"][0] | {"reportedPaymentDate": result["issuerValue"]} for result in results]
    return unknown(target["displayedPaymentDate"], reason, evidence)


def read_ir_pdf(job, receipt, pin, at):
    from pypdf import PdfReader

    url, title, reported_on = IR_PDFS[receipt]
    folder = job / "ir" / receipt
    proof = read_json(checked_read(folder / "receipt.json", pin["sha256"]))
    require(proof["url"] == url and utc(proof["startedAt"]) <= utc(proof["capturedAt"]) <= at,
            "APRIL_IR_BINDING")
    raw = checked_read(folder / "original.pdf", proof["sha256"])
    page = pin["page"]
    pages = PdfReader(BytesIO(raw)).pages
    require(type(page) is int and 1 <= page <= len(pages), "APRIL_IR_PAGE")
    return " ".join(pages[page - 1].extract_text().split()), {
        "receipt": receipt, "sourceUrl": f"{url}#page={page}", "reportedOn": reported_on,
        "title": title, "observedAt": proof["capturedAt"], "archiveSha256": proof["sha256"],
        "status": "CAPTURED", "page": page,
    }


def hyundai_payment(target, job, receipt_hash, at):
    return issuer_history_payment(target, job, receipt_hash, at, HYUNDAI_HISTORY_ID)


def issuer_history_payment(target, job, receipt_hash, at, history_id):
    symbol, url, title, header, amount_label, error_prefix = ISSUER_HISTORY_TABLES[history_id]
    require(target["symbol"] == symbol and target["market"] == "KOSPI", f"{error_prefix}_HISTORY_ISSUER")
    folder = job / "ir" / history_id
    receipt = read_json(checked_read(folder / "receipt.json", receipt_hash))
    observed = utc(receipt["capturedAt"])
    expected = target["displayedPaymentDate"]
    require(receipt["url"] == url and utc(receipt["startedAt"]) <= observed <= at, f"{error_prefix}_HISTORY_CAPTURE")
    html = checked_read(folder / "original.html", receipt["sha256"]).decode("utf-8-sig")
    basis_col, payment_col, amount_col = (header.index(label) for label in ("배당기준일", "배당지급일", amount_label))
    matches = []
    for table in re.findall(r"<table\b[^<>]*>(.*?)</table>", html, re.I | re.S):
        rows = [[plain(cell) for cell in HTML_CELL.findall(row)] for row in HTML_ROW.findall(table)]
        if rows and rows[0] == header:
            matches.extend(row for row in rows[1:]
                           if len(row) == len(header) and dates(row[basis_col]) == [target["recordDate"]])
    require(len(matches) == 1, f"{error_prefix}_HISTORY_ROUND")
    row = matches[0]
    payment = dates(row[payment_col])
    require(len(payment) == 1 and observed.date().isoformat() > max(expected, payment[0])
            and row[amount_col].replace(",", "") == target["commonCashPerShare"], f"{error_prefix}_HISTORY_PAYMENT")
    proof = {"receipt": history_id, "sourceUrl": url, "title": title,
             "reportedOn": None, "observedAt": receipt["capturedAt"], "archiveSha256": receipt["sha256"],
             "status": "CAPTURED"}
    return compare(payment[0], expected, proof, [*header, *row])


def skreit_payment(target, job, receipt_hash, at):
    require(target["symbol"] == "395400" and target["market"] == "KOSPI", "SKREIT_HISTORY_ISSUER")
    folder = job / "ir" / SKREIT_HISTORY_ID
    receipt = read_json(checked_read(folder / "receipt.json", receipt_hash))
    observed = utc(receipt["capturedAt"])
    expected = target["displayedPaymentDate"]
    require(receipt["url"] == SKREIT_HISTORY_URL and utc(receipt["startedAt"]) <= observed <= at,
            "SKREIT_HISTORY_CAPTURE")
    html = checked_read(folder / "original.html", receipt["sha256"]).decode("utf-8-sig")
    matches = []
    for table in re.findall(r"<table\b[^<>]*>(.*?)</table>", html, re.I | re.S):
        rows = [[plain(cell) for cell in HTML_CELL.findall(row)] for row in HTML_ROW.findall(table)]
        if rows[:2] == [SKREIT_HISTORY_HEADER, SKREIT_AMOUNT_HEADER]:
            matches.extend(row for row in rows[2:] if len(row) == 7 and row[1] == target["recordDate"])
    require(len(matches) == 1, "SKREIT_HISTORY_ROUND")
    row = matches[0]
    value = row[2]
    require(dates(value) == [value] and observed.date().isoformat() > max(expected, value)
            and row[5] == target["commonCashPerShare"], "SKREIT_HISTORY_PAYMENT")
    proof = {"receipt": SKREIT_HISTORY_ID, "sourceUrl": SKREIT_HISTORY_URL,
             "title": "SK리츠 배당 이력", "reportedOn": None, "observedAt": receipt["capturedAt"],
             "archiveSha256": receipt["sha256"], "status": "CAPTURED"}
    return compare(value, expected, proof, [*SKREIT_HISTORY_HEADER, *SKREIT_AMOUNT_HEADER, *row])


def prior_field(target, name):
    expected = target[FIELD_INPUTS[name]]
    if target["status"] == CONFIRMED:
        return compare(expected, expected, target["issuerEvidence"][name], [])
    if target["status"] == UNRESOLVED and name == "actualPaymentDate":
        detail = " · ".join(review["detail"] or {
            "PLANNED_DATE_ONLY": "기존 정정 원문에 지급 예정일만 기재",
            "OTHER_DISTRIBUTION": "기존 정정 원문은 다른 배당 회차",
        }.get(review["reason"], review["reason"]) for review in target["reviews"])
        return unknown(expected, detail, (review["evidence"] for review in target["reviews"]))
    return None


def supplemental_field(name, target, pin, proof, present):
    markers, value = pin["markers"], pin["value"]
    require(markers and set(markers) <= present, "APRIL_SUPPLEMENTAL_MARKERS")
    if name == "recordDate":
        require(value in dates(" ".join(markers)), "APRIL_SUPPLEMENTAL_DATE")
    else:
        amounts = {Decimal(token.replace(",", "")) for token in NUMBER.findall(" ".join(markers))}
        if calculation := pin.get("calculation"):
            total, shares = (Decimal(calculation[k]) for k in ("totalKrw", "shares"))
            require(total in amounts and shares in amounts and shares > 0
                    and (total / shares).quantize(Decimal("0.0000000001"), rounding=ROUND_HALF_UP) == Decimal(value),
                    "APRIL_SUPPLEMENTAL_AMOUNT_FORMULA")
        else:
            require(Decimal(value) in amounts, "APRIL_SUPPLEMENTAL_AMOUNT")
    result = compare(value, target[FIELD_INPUTS[name]], proof, markers)
    if "calculation" in pin:
        result["calculation"] = pin["calculation"]
    return result


def build(manifest, artifacts, job, *, schema=None):
    spec = read_json(manifest.read_bytes())
    version = spec["schemaVersion"]
    require(version in SCOPES and (schema is None or schema == version), "DIVIDEND_MONTH_SCHEMA")
    month, expected_prior = SCOPES[version]
    at = utc(spec["reviewedAt"])
    parent_spec = spec["input"]
    parent = read_json(checked_read(artifacts / parent_spec["path"], parent_spec["sha256"]))
    require(utc(parent["knownAt"]) <= at, "APRIL_FUTURE_PARENT")
    targets = {r["ksdRowSha256"]: r for group in parent["issuerYears"] for r in group["events"]
               if r["displayedPaymentDate"].startswith(month)}
    require(set(targets) == set(spec["rows"]) and Counter(row["status"] for row in targets.values()) == expected_prior,
            "DIVIDEND_MONTH_SCOPE")
    inventory = load_indexes(job, spec["indexPages"], set(spec["documents"]), at)
    results = []
    decision_cache, report_cache = {}, {}
    markers_by_receipt, checked_markers, actual_by_row = {}, {}, {}
    for row_hash, row in spec["rows"].items():
        if "actual" in row:
            actual = row["actual"]
            actual_by_row[row_hash] = actual if isinstance(actual, list) else [actual]
            for entry in actual_by_row[row_hash]:
                markers_by_receipt.setdefault(entry["receipt"], set()).add(entry["marker"])
        for field in row.get("fieldEvidence", {}).values():
            markers_by_receipt.setdefault(field["receipt"], set()).update(field["markers"])
    ir_pins = spec.get("irPdfs", {}) | ({IR_ID: spec["naverIr"]} if "naverIr" in spec else {})
    for receipt in markers_by_receipt.keys() & IR_PDFS.keys():
        content, proof = read_ir_pdf(job, receipt, ir_pins[receipt], at)
        checked_markers[receipt] = {marker for marker in markers_by_receipt[receipt] if marker in content}
        if receipt == MKIF_H1_ID:
            decision_cache[receipt] = ({}, {}, {}), proof
        else:
            report_cache[receipt] = True, proof
    for row_hash, target in sorted(targets.items(), key=lambda pair: (
        pair[1]["market"], pair[1]["symbol"], pair[1]["recordDate"], pair[1]["displayedPaymentDate"],
    )):
        row = spec["rows"][row_hash]
        require(HASH.fullmatch(row_hash), "APRIL_ROW_HASH")
        fields = {}
        documents = {"decisions": [], "reports": []}
        if target["status"] != CONFIRMED:
            for kind, cache in (("decisions", decision_cache), ("reports", report_cache)):
                for receipt in row[kind]:
                    if receipt in IR_PDFS:
                        if receipt == IR_ID:
                            valid = kind == "reports" and target["symbol"] == "035420"
                        else:
                            role = "decisions" if receipt == MKIF_H1_ID else "reports"
                            valid = (version == AUGUST_SCHEMA and kind == role and target["symbol"] == "088980"
                                     and target["market"] == "KOSPI" and target["recordDate"] == "2024-06-30")
                        require(valid and receipt in cache, "APRIL_IR_ISSUER")
                        documents[kind].append(cache[receipt])
                        continue
                    item = inventory[receipt]
                    require(MARKETS[item["corp_cls"]] == target["market"] and item["stock_code"] == target["symbol"],
                            "APRIL_DOCUMENT_WRONG_ISSUER")
                    title = DECISION_TITLE if kind == "decisions" else REPORT_TITLE
                    require(title.search(item["report_nm"]), "APRIL_DOCUMENT_TITLE")
                    if receipt not in cache:
                        body, proof = load_document(job, receipt, spec["documents"][receipt], item, at)
                        if body is not None:
                            markers = markers_by_receipt.get(receipt, set())
                            if markers:
                                normalized = plain(body)
                                checked_markers[receipt] = {marker for marker in markers if marker in normalized}
                            body = decision_facts(body) if kind == "decisions" else True
                        cache[receipt] = body, proof
                    documents[kind].append(cache[receipt])
                    if kind == "reports":
                        require(cache[receipt][1]["reportedOn"] > target["displayedPaymentDate"], "APRIL_REPORT_DATE")
            readable_decisions = [(facts, proof) for facts, proof in documents["decisions"] if facts is not None]
            reason = row.get("decisionGap") or ("확보한 배당 결정공시의 기준일에서 대상 회차를 찾지 못함"
                                                if readable_decisions else "조회한 공시 목록에서 대상 회차의 결정 원문 미확보")
            fields["recordDate"], fields["commonCashPerShare"], plan = decision_fields(target, readable_decisions, reason)
            for key in ("recordDate", "commonCashPerShare"):
                if not fields[key]["evidence"]:
                    searched = documents["decisions"] or documents["reports"]
                    fields[key]["evidence"] = [proof for _, proof in searched]
            referenced = {proof["receipt"]: proof for group in documents.values() for content, proof in group
                          if content is not None}
            for key, pin in row.get("fieldEvidence", {}).items():
                require(key in {"recordDate", "commonCashPerShare"}, "APRIL_SUPPLEMENTAL_FIELD")
                receipt = pin["receipt"]
                fields[key] = supplemental_field(key, target, pin, referenced[receipt], checked_markers[receipt])
            expected = target["displayedPaymentDate"]
            fields["actualPaymentDate"] = prior_field(target, "actualPaymentDate")
            if "skreitHistory" in row:
                require(version in {JUNE_SCHEMA, SEPTEMBER_SCHEMA} and "actual" not in row, "SKREIT_HISTORY_SCOPE")
                fields["actualPaymentDate"] = skreit_payment(target, job, row["skreitHistory"], at)
            if "hyundaiHistory" in row:
                require(version == AUGUST_SCHEMA and "actual" not in row, "HYUNDAI_HISTORY_SCOPE")
                fields["actualPaymentDate"] = hyundai_payment(target, job, row["hyundaiHistory"], at)
            if "esrksHistory" in row:
                require(version == SEPTEMBER_SCHEMA and "actual" not in row, "ESRKS_HISTORY_SCOPE")
                fields["actualPaymentDate"] = issuer_history_payment(target, job, row["esrksHistory"], at, ESRKS_HISTORY_ID)
            if row_hash in actual_by_row:
                require(target["status"] == UNREVIEWED, "APRIL_PRIOR_STATUS")
                reports = {proof["receipt"]: proof for body, proof in documents["reports"] if body is not None}
                fields["actualPaymentDate"] = reported_payment(target, actual_by_row[row_hash], reports,
                                                               checked_markers, row.get("paymentGap"))
            if fields["actualPaymentDate"] is None:
                read = [(text, proof) for text, proof in documents["reports"] if text is not None]
                reason = row.get("paymentGap") or (
                    "지급 후 정기보고서 검토 범위에서 해당 회차의 실제 지급일 근거 미확인" if read
                    else "지급 후 조회 범위에서 해당 회차를 대조할 정기보고서 원문 미확보"
                )
                if plan and plan != "-":
                    reason += f" · 결정공시 예정 표기 {plan}"
                fields["actualPaymentDate"] = unknown(expected, reason, (proof for _, proof in documents["reports"]))
        else:
            fields = {name: prior_field(target, name) for name in FIELD_INPUTS}
        status = CONFIRMED if all(field["status"] == "MATCH" for field in fields.values()) else UNRESOLVED
        require(target["status"] == UNREVIEWED or target["status"] == status, "APRIL_PRIOR_STATUS")
        results.append({"market": target["market"], "symbol": target["symbol"], "issuer": target["issuer"],
                        "ksdRowSha256": row_hash, "ksdScheduleRowSha256": target["ksdScheduleRowSha256"],
                        "priorStatus": target["status"], "status": status, "fields": fields,
                        "reviewedDecisions": [proof for _, proof in documents["decisions"]],
                        "reviewedReports": [proof for _, proof in documents["reports"]]})
    return {"schemaVersion": version, "manifestSha256": digest(canonical(spec)), "knownAt": at.isoformat(),
            "rows": results, "statusCounts": dict(Counter(row["status"] for row in results)),
            "fieldCounts": {name: dict(Counter(row["fields"][name]["status"] for row in results)) for name in FIELD_INPUTS},
            "historicalFirstAvailabilityConfirmed": False, "usableForTraining": False, "usableForTrading": False}


def main(*, schema=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "audit"))
    for name in ("manifest", "artifacts", "job", "rows"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    result = build(args.manifest, args.artifacts, args.job, schema=schema)
    output = b"".join(canonical(row) + b"\n" for row in result["rows"])
    if args.action == "audit" or args.rows.exists():
        require(args.rows.read_bytes().replace(b"\r\n", b"\n") == output, "APRIL_PUBLISHED_ROWS_MISMATCH")
    else:
        args.rows.write_bytes(output)
    immutable_json(args.job / "report.json", result, require_existing=args.action == "audit")
    print(result["statusCounts"], result["fieldCounts"])


if __name__ == "__main__":
    main()
