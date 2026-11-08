"""Reconcile issuer-reported retirement dates for the 14 unresolved KOSDAQ notices."""

import argparse
from collections import Counter
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from . import ksd_dividend_evidence as ksd
from .corporate_action_event_audit import name_key
from .corporate_action_outcomes import capture, checked_read, require
from .dart_documents import inspect_zip
from .dart_history import BASE, PATHS, integer
from .dataset import digest, read_bytes, read_json
from .krx_baseline_validation import immutable_json
from .market_calendar_evidence import text
from .membership_identity_audit import dart_registry
from .models import utc
from .restructuring_outcomes import DAY, stamp

SCHEMA = "SAGOPALGO_H05_KOSDAQ_CANCELLATION_DATES_V1"
PUBLICATION_THROUGH = "20261107"
REPORT = re.compile(r"사업보고서|반기보고서|분기보고서")
SELECTED = re.compile(r"사업보고서|반기보고서|분기보고서|주식\s*소각|자기주식보고서|자기주식\s*취득결과")
TRUST_FOLLOWUP = {"20260821000304", "20260824000258"}
ACTUAL_FIELDS = {"BRN_DT", "BRN_MTD", "SHR_KND", "BRN_QTY"}
QUANTITY = r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)"


def request(endpoint, parameters):
    return {"method": "GET", "url": BASE + PATHS[endpoint], "parameters": parameters}


def catalog(job, pins, at, target, corp, early=False):
    listed = date.fromisoformat(target["listingDate"])
    start = listed - timedelta(days=180 if early else 90)
    end = (listed - timedelta(days=91)).strftime("%Y%m%d") if early else PUBLICATION_THROUGH
    rows, seen, visited = [], set(), set()
    page, pages, total = 1, 1, None
    while page <= pages:
        params = {"corp_code": corp, "bgn_de": start.strftime("%Y%m%d"), "end_de": end, "last_reprt_at": "N",
                  "sort": "date", "sort_mth": "asc", "page_no": str(page), "page_count": "100"}
        tag = "-early" if early else ""
        name = f"list-{target['symbol']}{tag}-{page:02}"
        raw, proof = capture(job, pins, name, request("list", params), at)
        doc = read_json(raw)
        require(doc["status"] == "000" and integer(doc["page_no"]) == page and
                integer(doc["page_count"]) == 100, "ISSUER_CATALOG_PAGE")
        count, page_count = integer(doc["total_count"]), integer(doc["total_page"])
        if page == 1:
            total, pages = count, page_count
        require((count, page_count) == (total, pages) and 1 <= pages == (total + 99) // 100 <= 10 and
                len(doc["list"]) == min(100, total - (page - 1) * 100), "ISSUER_CATALOG_COUNT")
        for row in doc["list"]:
            number = row["rcept_no"]
            require(row["corp_code"] == corp and row["stock_code"] == target["symbol"] and row["corp_cls"] == "K" and
                    re.fullmatch(r"[0-9]{14}", number) and number not in seen and
                    params["bgn_de"] <= row["rcept_dt"] <= end, "ISSUER_CATALOG_BINDING")
            seen.add(number)
            title = row["report_nm"].strip()
            selected = (re.search(r"주식\s*소각|사업보고서", title) if early else
                        SELECTED.search(title) and "종속회사의" not in title)
            if selected or target["symbol"] == "206650" and number in TRUST_FOLLOWUP:
                rows.append({"receipt": number, "receiptDate": stamp(row["rcept_dt"]), "title": title,
                             "issuer": row["corp_name"], "listEvidence": proof})
        visited.add(name)
        page += 1
    return rows, visited, total


def document_body(raw, filing, corp):
    number = filing["receipt"]
    entries = inspect_zip(raw)
    entry, = [entry for entry in entries if entry["name"] == number + ".xml"]
    with ZipFile(BytesIO(raw)) as archive:
        contents = archive.read(entry["name"]).decode("utf-8-sig")
    require(not re.search(r"<!\s*(?:DOCTYPE|ENTITY)", contents, re.I), "ISSUER_DOCUMENT_DECLARATION")
    if re.search(r"<DOCUMENT\b", contents[:300]):
        identities = re.findall(r'<COMPANY-NAME\b[^>]*\bAREGCIK="([0-9]{8})"[^>]*>([^<]+)</COMPANY-NAME>', contents)
        require(len(identities) == 1 and identities[0][0] == corp, "ISSUER_DOCUMENT_COMPANY")
        source_issuer = identities[0][1].strip()
        fmt = "DART_XML_FRAGMENTS"
    else:
        require(re.match(r"\s*<html\b", contents, re.I), "ISSUER_DOCUMENT_FORMAT")
        header = text(contents[:24000].encode())
        require("/" in header, "ISSUER_HTML_COMPANY")
        source_issuer = header.split("/", 1)[0]
        fmt = "KIND_HTML_IN_DART_ARCHIVE"
    return contents, {"documentSha256": entry["sha256"], "archiveSha256": digest(raw), "format": fmt,
                      "sourceIssuerName": source_issuer}


def actual_table_dates(contents, shares):
    for raw in re.finditer(r"<TR\b[^>]*>.*?</TR>", contents, re.S):
        fragment = raw.group()
        if not all(k in fragment for k in ACTUAL_FIELDS) or "이익소각" not in fragment:
            continue
        row = ET.fromstring(fragment)
        fields = {}
        for node in row:
            key = node.get("AUNIT") if node.tag == "TU" else node.get("ACODE") if node.tag == "TE" else None
            if key in ACTUAL_FIELDS:
                require(key not in fields, "ISSUER_ACTUAL_FIELD_DUPLICATE")
                fields[key] = node
        if fields.keys() != ACTUAL_FIELDS:
            continue
        quantity = (fields["BRN_QTY"].text or "").strip()
        if not re.fullmatch(QUANTITY, quantity) or int(quantity.replace(",", "")) != shares:
            continue
        if (fields["SHR_KND"].text or "").strip() not in {"보통주", "보통주식"}:
            continue
        method = fields["BRN_MTD"]
        require(method.tag == fields["BRN_DT"].tag == "TU" and
                fields["SHR_KND"].tag == fields["BRN_QTY"].tag == "TE" and
                method.get("AUNITVALUE") == "1" and (method.text or "").strip() == "이익소각", "ISSUER_ACTUAL_METHOD")
        day = fields["BRN_DT"]
        value = stamp(day.get("AUNITVALUE", ""))
        require(stamp((day.text or "").strip()) == value, "ISSUER_ACTUAL_DATE_DISPLAY_CONFLICT")
        yield value, "ISSUER_RETIREMENT_TABLE", digest(fragment.encode())


def actual_note_dates(contents, shares):
    amounts = rf"(?:{shares}|{shares:,})"
    # This report footnote explicitly says the dated transaction was completed.
    pattern = (DAY + r"\s+(?:회사|연결회사)가 당반기 취득한 자기주식\(보통주\s+" + amounts +
               r"주, 취득금액\s+" + QUANTITY + r"원\)을\s+소각하였습니다")
    for raw in re.finditer(r"<P\b[^>]*>(.*?)</P>", contents, re.S):
        if "당반기 취득한 자기주식" not in raw[1]:
            continue
        body = text(raw[1].encode())
        for match in re.finditer(pattern, body):
            yield stamp(match[1]), "ISSUER_REPORTED_COMPLETION_NOTE", digest(raw[1].encode())


def planned_date(contents, shares, outstanding):
    body = text(contents.encode())
    pairs = re.findall(r"1\.\s*소각할 주식의 종류와 수\s+보통주식\(주\)\s+(" + QUANTITY +
                       r")\s+종류주식\(주\)\s+-\s+2\.\s*발행주식총수\s+보통주식\(주\)\s+(" + QUANTITY +
                       r")(?=\s)", body)
    dates = re.findall(r"7\.\s*소각\s*예정일\s+" + DAY, body)
    if len(pairs) != 1 or len(dates) != 1:
        return None
    number, before = (int(x.replace(",", "")) for x in pairs[0])
    if number == shares and before - number == outstanding:
        return stamp(dates[0])
    return None


def outcome(actual, plans, depository=None):
    dates = {item["date"] for item in actual}
    if depository:
        dates.add(depository["date"])
    if len(dates) == 1:
        basis = "ISSUER_REPORTED_CANCELLATION_DATE" if actual else "KSD_REPORTED_CANCELLATION_DATE"
        return basis, dates.pop()
    if dates:
        return "CONFLICTING_COMPLETION_DATES", None
    return ("SCHEDULED_DATE_ONLY" if plans else "ISSUER_COMPLETION_DATE_UNCONFIRMED"), None


def depository_record(job, pins, artifacts, at, target, prior):
    name = "ksd-stat-KOSDAQ-2025-rows"
    source, source_proof = capture(artifacts / prior["job"], {name: prior["receiptSha256"]}, name,
                                   ksd.request_spec("stat", "KOSDAQ", 2025, "rows"), at)
    codes = {row["ISSUCO_CUSTNO"] for row in ksd.parse_rows(source)
             if (row["SHOTN_ISIN"], row["LIST_TPNM"], row["SECN_DTAIL_KANM"]) ==
             (target["symbol"], "코스닥시장", "보통주")
             and name_key(row["KOR_SECN_NM"]) == name_key(target["issuer"])}
    require(len(codes) == 1 and next(iter(codes)).isdigit(), "KSD_ISSUER_BINDING")
    fields = {"ISSUCO_CUSTNO": codes.pop(), "RGT_LINK_RACD": "", "SECN_KACD": "", "ISSU_DT_FROM": "20260901",
              "ISSU_DT_TO": PUBLICATION_THROUGH, "STARTPAGE": "1", "ENDPAGE": "15"}
    evidence, used, responses = [], set(), {}
    for role, action in (("rows", "chgDetailsListEL1"), ("count", "chgDetailsListCnt")):
        name = f"ksd-eubiologics-{role}"
        spec = {"method": "POST", "url": ksd.SERVICE, "parameters": {
            "task": ksd.TASK + "EntrFnafInfoPTask", "action": action, "fields": fields, "page": "01012"}}
        responses[role], proof = capture(job, pins, name, spec, at)
        evidence.append(proof | {"sourceUrl": ksd.source_url("01012")})
        used.add(name)
    rows = list(ksd.parse_rows(responses["rows"]))
    require(len(rows) == ksd.parse_count(responses["count"]) <= 15, "KSD_ISSUE_RECORD_COUNT")
    matches = [row for row in rows if name_key(row["REP_SECN_NM"]) == name_key(target["issuer"])
               and (row["SECN_KACD"], row["SECN_KACD_NM"], row["RGT_LINK_RACD"], row["RGT_LINK_RACD_NM"]) ==
               ("0101", "보통주", "907", "이익소각")
               and ksd.ksd_date(row["LIST_DT"]) == target["listingDate"]
               and row["ISSU_QTY"] == str(target["signedShareChange"])]
    require(len(matches) == 1, "KSD_ISSUE_RECORD_BINDING")
    row = matches[0]
    require(fields["ISSU_DT_FROM"] <= row["ISSU_DT"] <= row["LIST_DT"] <= fields["ISSU_DT_TO"],
            "KSD_ISSUE_RECORD_DATE")
    return {"date": ksd.ksd_date(row["ISSU_DT"]), "basis": "KSD_REPORTED_RETIREMENT_ISSUE_DATE",
            "sourceField": "ISSU_DT", "issuanceSequence": row["SECN_ISSU_NTIMES"],
            "evidence": evidence, "issuerBindingEvidence": source_proof}, used


def build(manifest, artifacts, job):
    spec_raw = read_bytes(manifest)
    spec = read_json(spec_raw)
    require(spec["schemaVersion"] == SCHEMA, "ISSUER_CANCELLATION_SCOPE")
    at, pins = utc(spec["reviewedAt"]), spec["receipts"]
    parent = read_json(checked_read(artifacts / spec["parent"]["path"], spec["parent"]["sha256"]))
    require(utc(parent["knownAt"]) <= at, "ISSUER_CANCELLATION_PARENT_TIME")
    registry, registry_proof = dart_registry(artifacts / spec["registry"]["path"], spec["registry"]["receiptSha256"])
    require(utc(registry_proof["knownAt"]) <= at, "ISSUER_CANCELLATION_REGISTRY_TIME")
    targets = [r for r in parent["cancellations"] if r["status"] == "COMMON_SHARE_CANCELLATION_DATE_MISSING"]
    require(len(targets) == len({row["symbol"] for row in targets}) == 14 and
            all(r["market"] == "KOSDAQ" and r["shareClass"] == "COMMON" for r in targets), "ISSUER_CANCELLATION_TARGETS")
    used, cases = set(), []
    for target in targets:
        symbol, listed = target["symbol"], target["listingDate"]
        issuer, = registry[symbol]
        corp = issuer["dartCorpCode"]
        shares = -target["signedShareChange"]
        filings, visited, count = catalog(job, pins, at, target, corp)
        used.update(visited)
        if symbol == "033830":
            early, visited, early_count = catalog(job, pins, at, target, corp, early=True)
            used.update(visited)
            filings = early + filings
            count += early_count
        actual, plans, documents = [], [], []
        for filing in filings:
            receipt = filing["receipt"]
            name = "doc-" + receipt
            raw, proof = capture(job, pins, name, request("document", {"rcept_no": receipt}), at)
            used.add(name)
            contents, body_proof = document_body(raw, filing, corp)
            proof = proof | body_proof | {"sourceUrl": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + receipt}
            documents.append(filing | {"evidence": proof})
            if REPORT.search(filing["title"]):
                dates = set(actual_table_dates(contents, shares)) | set(actual_note_dates(contents, shares))
                earliest = (date.fromisoformat(listed) - timedelta(days=180)).isoformat()
                actual.extend({"date": day, "basis": basis, "fragmentSha256": sha, "receipt": receipt,
                               "receiptDate": filing["receiptDate"]}
                              for day, basis, sha in sorted(dates) if earliest <= day <= min(listed, filing["receiptDate"]))
            if "주식소각결정" in re.sub(r"\s+", "", filing["title"]):
                planned = planned_date(contents, shares, target["stockIssueReportedOutstanding"])
                if planned and filing["receiptDate"] <= planned <= listed:
                    plans.append({"date": planned, "receipt": receipt, "receiptDate": filing["receiptDate"]})
        issuer_names = {name_key(issuer["issuerName"])}
        issuer_names.update(name_key(doc["issuer"]) for doc in documents)
        issuer_names.update(name_key(doc["evidence"]["sourceIssuerName"]) for doc in documents
                            if doc["evidence"]["format"] == "DART_XML_FRAGMENTS")
        require(all(name_key(doc["evidence"]["sourceIssuerName"]) in issuer_names for doc in documents),
                "ISSUER_HTML_COMPANY")
        depository = None
        if symbol == "206650":
            depository, visited = depository_record(job, pins, artifacts, at, target, spec["ksdIssuerBinding"])
            used.update(visited)
        status, confirmed = outcome(actual, plans, depository)
        cases.append({"symbol": symbol, "issuer": target["issuer"], "corpCode": corp, "processId": target["processId"],
                      "shareClass": "COMMON", "shares": shares, "listingDate": listed, "status": status,
                      "actualCancellationDate": confirmed, "reportedCompletions": actual, "scheduledDates": plans,
                      "depositoryEvidence": depository,
                      "catalogRecords": count, "documents": documents})
    require(used == set(pins), "ISSUER_CANCELLATION_CAPTURE_SCOPE")
    return {"schemaVersion": SCHEMA, "knownAt": at.isoformat(), "manifestSha256": digest(spec_raw),
            "registryEvidence": registry_proof, "publicationThrough": stamp(PUBLICATION_THROUGH), "cases": cases,
            "statusCounts": dict(Counter(row["status"] for row in cases)),
            "historicalFirstAvailabilityConfirmed": False, "usableForTrading": False, "usableForTraining": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "audit"))
    for key in ("manifest", "artifacts", "job"):
        parser.add_argument("--" + key, type=Path, required=True)
    args = parser.parse_args()
    result = build(args.manifest, args.artifacts, args.job)
    immutable_json(args.job / "report.json", result, require_existing=args.action == "audit")
    print(result["statusCounts"])


if __name__ == "__main__":
    main()
