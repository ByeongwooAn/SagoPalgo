"""Audit a fixed OpenDART completion index and the parallel KIND issuance route."""

import argparse
from collections import Counter, defaultdict
from datetime import date
import io
import json
from pathlib import Path
import re
from zipfile import ZipFile

from . import corporate_facts as facts
from . import membership_identity_audit as h01
from .dart_documents import inspect_zip
from .dataset import digest, read_bytes, read_json
from .kind_membership_evidence import BASE, html
from .krx_baseline_validation import immutable_json
from .market_calendar_evidence import text as html_text
from .models import ResearchError, utc
from .restructuring_outcomes import DART, SCHEMA, SCOPE, Sources, correction_start, outcome_index, stamp
from .session_notice_inventory import body_path, page_rows, query_spec, viewer_documents

REVIEW_SCHEMA = "SAGOPALGO_H04_CENSUS_SCOPE_V1"
REPORT_SCHEMA = "SAGOPALGO_H04_CENSUS_REPORT_V1"
VIEWER = BASE + "/common/disclsviewer.do"
DATE = r"(?<![0-9])([0-9]{4})(?:\s*년\s*|\s*[./-]\s*)([0-9]{1,2})(?:\s*월\s*|\s*[./-]\s*)([0-9]{1,2})(?:\s*일)?(?![0-9])"
LITERAL_ANGLES = re.compile(r"<(개정\s+[0-9]{4}\.[0-9]{1,2}\.[0-9]{1,2}\.|[가-힣]{2,40}\(주\))>")
KIND_TITLE = re.compile(r"(?:\[정정\])?증권발행실적보고서\(합병등\)")
REFERENCE_LABEL = re.compile(r"(?:[가-힣A-Z]{0,18}사업부)?(?:분할합병|합병|분할)기일(?:$|[(*,])")
RATIO = re.compile(r"(분할합병|합병)비율(?:은|을|이|의)?[:=(]?(?<![0-9.])([0-9]+(?:\.[0-9]+)?):([0-9]+(?:\.[0-9]+)?)(?![0-9.])")
WINDOWS = (("2023-11-01", "2023-12-31"), ("2024-01-01", "2024-12-31"),
           ("2025-01-01", "2025-12-31"), ("2026-01-01", "2026-11-07"))


def need(value, reason):
    if not value:
        raise ResearchError("H04_CENSUS_" + reason)


def pinned(path, sha):
    raw = read_bytes(path)
    need(digest(raw) == sha, "HASH")
    return raw


class Archive:
    def __init__(self, folder, receipt_hashes, at):
        self.folder, self.receipt_hashes, self.at = folder, receipt_hashes, at
        self.visited = set()

    def read(self, name, endpoint=None, params=None, kind_request=None):
        kind = kind_request is not None
        base = self.folder / "aux" if kind else self.folder
        key = ("aux/" if kind else "") + name
        directory = base / "captures" / name
        receipt = read_json(pinned(directory / "receipt.json", self.receipt_hashes[key]))
        if kind:
            need(receipt["schemaVersion"] == "SAGOPALGO_H05_CAPTURE_V1" and receipt["request"] == kind_request,
                 "KIND_REQUEST_BINDING")
        else:
            need(receipt["schemaVersion"] == "SAGOPALGO_H04_CENSUS_RECEIPT_V1" and
                 (receipt["endpoint"], receipt["parameters"]) == (endpoint, params), "DART_REQUEST_BINDING")
        need(receipt["status"] == "CAPTURED" and utc(receipt["startedAt"]) <= utc(receipt["capturedAt"]) <= self.at,
             "CAPTURE_BOUNDARY")
        self.visited.add(key)
        return pinned(directory / ("raw.bin" if kind else "body.bin"), receipt["sha256"]), receipt


def original_xml(raw, number):
    entries = inspect_zip(raw)
    entry = facts.one(x for x in entries if x["name"] == number + ".xml")
    with ZipFile(io.BytesIO(raw)) as archive:
        xml = archive.read(entry["name"])
    fixes = 0
    try:
        root, details = facts.parse_xml(xml)
    except ResearchError as exc:
        if str(exc) != "FACT_XML_INVALID":
            raise
        fixed, fixes = LITERAL_ANGLES.subn(lambda m: "&lt;" + m[1] + "&gt;", xml.decode("utf-8-sig"))
        if not fixes:
            raise
        root, details = facts.parse_xml(fixed.encode("utf-8"))
    return root, {"bodySha256": entry["sha256"], "archiveSha256": digest(raw),
                  "escapedLiteralAngleTokens": fixes, **details}


def dates(value):
    return sorted({date(*map(int, match)).isoformat() for match in re.findall(DATE, value)})


def schedule_role(label):
    value = facts.compact(label)
    if len(value) > 68:
        return None
    if REFERENCE_LABEL.match(value):
        return "REFERENCE_DATE"
    if "등기" in value and re.search(r"합병|분할|설립|해산|변경", value):
        if "예정" in value:
            return "REGISTRATION_SCHEDULED"
        if re.search(r"신청|접수", value):
            return "REGISTRATION_APPLICATION"
        return "REGISTRATION_LABEL_UNCONFIRMED"
    if "종료보고" in value or "창립총회" in value:
        return "PROCEDURAL_REPORT"
    if "상장" in value and re.search(r"신주|변경|추가|재상장|상장일|상장예정", value):
        return "LISTING_SCHEDULED" if "예정" in value else "LISTING_LABEL_UNCONFIRMED"
    return None


def schedule_rows(section):
    found, parties = [], []
    for tr in section.iter("TR"):
        children = [n for n in tr if n.tag in {"TD", "TH", "TU", "TE"}]
        if any(list(cell.iter("TR")) for cell in children):
            continue
        cells = [facts.text(n) for n in children]
        if len(cells) < 2:
            continue
        for i, label in enumerate(cells[:2]):
            role = schedule_role(label)
            if not role:
                continue
            preceding = dates(cells[0]) if i else []
            stamps = preceding or dates(" ".join(cells[i + 1:]))
            if stamps:
                found.append({"role": role, "label": label, "dates": stamps})
            break
        values = " ".join(cells[1:])
        if len(values) <= 240 and "존속회사" in values and "소멸회사" in values:
            parties.append(cells)
    return found, parties


def share_terms(body):
    plain = facts.compact(body)
    ratios = sorted(set(RATIO.findall(plain)))
    common_counts = set(re.findall(r"(?:합병신주|분할신주)(?:로|는|의수는|의수)?(?:기명식)?보통주(?:식)?([0-9,]+)주", plain))
    return {"statedRatios": [{"label": label, "left": left, "right": right} for label, left, right in ratios],
            "statedNewCommonShareCounts": sorted(int(facts.integer(n)) for n in common_counts),
            "explicitNoNewShares": bool(re.search(r"(?:신주를발행하지않는무증자|발행하는신주는없|신주발행은없|신주를발행하지않으므로)", plain)),
            "reportedParentAllocation100Percent": bool(re.search(r"분할신설회사.{0,70}분할(?:되는)?회사에100%배정", plain))}


def coverage(row):
    start, end = SCOPE[:2]
    stamps = {stamp for item in row["schedule"] if item["role"] == "REFERENCE_DATE" for stamp in item["dates"]}
    if not stamps:
        return "REFERENCE_DATE_UNCONFIRMED"
    if len(stamps) > 1:
        return "MULTIPLE_REFERENCE_DATES_REVIEW"
    return "REFERENCE_DATE_IN_SCOPE" if start <= next(iter(stamps)) <= end else "REFERENCE_DATE_OUTSIDE_SCOPE"


def filing(archive, source):
    number = source["receipt"]
    raw, receipt = archive.read("dart-" + number, "document", {"rcept_no": number})
    root, proof = original_xml(raw, number)
    title = facts.one(root.iter("DOCUMENT-NAME"))
    company = facts.one(root.iter("COMPANY-NAME"))
    purpose = facts.one(n for n in root.iter("TU") if n.get("AUNIT") == "RPT_RSN_TP")
    stated = facts.compact(facts.text(purpose))
    need(title.get("ACODE") == "12000" and company.get("AREGCIK") == source["corpCode"] and
         stated in {"(합병)", "(분할)", "(분할합병)"}, "OUTCOME_DOCUMENT_IDENTITY")
    section = facts.one(root.findall("./BODY/SECTION-1"))
    schedule, parties = schedule_rows(section)
    body = facts.text(section)
    if re.search(r"합병등기일(?:자는|은).{0,12}등기(?:접수|신청)", facts.compact(body)):
        for item in schedule:
            if item["role"] == "REGISTRATION_LABEL_UNCONFIRMED":
                item["role"] = "REGISTRATION_APPLICATION"
                item["interpretationBasis"] = "DOCUMENT_FOOTNOTE_IDENTIFIES_APPLICATION"
    # Some filers use the generic merger cover for a split-merger. Preserve the
    # actual schedule labels alongside the provider classification.
    correction_sections = list(root.iter("CORRECTION"))
    try:
        original = correction_start(root)
    except (ValueError, ResearchError):
        original = None
    row = source | {"evidencePath": "DART_E003", "observedAt": receipt["capturedAt"],
                    "documentIssuer": facts.text(company), "documentPurpose": stated, "schedule": schedule,
                    "partyRows": parties, "shareTerms": share_terms(body), "originalSubmissionDateInCorrection": original,
                    "bodyCorrectionSection": bool(correction_sections), "legalEffectiveDate": None,
                    "disposition": "BODY_AUDITED_LEGAL_EFFECT_PENDING", **proof}
    return row | {"referenceDateScope": coverage(row)}


def selected_kind_body(archive, receipt):
    viewer, _ = archive.read("viewer-" + receipt, kind_request={
        "url": VIEWER + f"?acptno={receipt}&method=search", "method": "GET", "parameters": None})
    root = html(viewer)
    heading = facts.one(n.text() for n in root.walk("h1"))
    # Current viewer identity is retained as a label, including for issuers
    # that were later renamed or delisted.
    selector = facts.one(n for n in root.walk("select") if n.attrs.get("id") == "mainDoc")
    chosen = facts.one(n for n in selector.walk("option") if n.attrs.get("selected") == "selected")
    document = chosen.attrs["value"].split("|")[0]
    versions = viewer_documents(viewer)
    need(document in {v["document"] for v in versions}, "KIND_SELECTED_DOCUMENT")
    route, _ = archive.read("route-" + receipt, kind_request={
        "url": VIEWER, "method": "POST", "parameters": {"method": "searchContents", "docNo": document}})
    url = body_path(route, document)
    need("".join(url.split("/")[4:8]) == receipt and url.endswith("/10810.htm"), "KIND_DOCUMENT_RECEIPT")
    raw, proof = archive.read("body-" + receipt, kind_request={"url": url, "method": "GET", "parameters": None})
    return html_text(raw), {"sourceUrl": url, "bodySha256": proof["sha256"], "observedAt": proof["capturedAt"],
                            "viewerIssuerLabel": heading, "selectedDocument": document, "viewerVersions": versions}


def kind_issuance(archive, h01_receipt, artifacts):
    result = []
    for market in ("KOSPI", "KOSDAQ"):
        for start, end in WINDOWS:
            query = {"market": market, "fromDate": start, "toDate": end, "kind": "TITLE"}
            spec = query_spec(query, 1)
            spec["parameters"]["reportNm"] = "증권발행실적보고서(합병등)"
            raw, _ = archive.read(f"issuance-{market}-{start}-01", kind_request=spec)
            page = page_rows(raw, query, 1)
            need(page["pages"] == 1, "KIND_ISSUANCE_PAGINATION")
            for row in page["rows"]:
                receipt = row["receipt"]
                need(KIND_TITLE.fullmatch(facts.compact(row["title"])), "KIND_TITLE_SCOPE")
                if receipt == "20260715000296":
                    body, proof = h01.kind_text(artifacts / "historical-membership-identity-20261107/kind/issuance-report",
                                                "issuance-report", h01_receipt)
                    proof["observedAt"] = proof["knownAt"]
                else:
                    body, proof = selected_kind_body(archive, receipt)
                purpose = list(re.finditer(r"증권발행실적보고서\s*\(([^)]+)\)\s*금융감독원장\s*귀하", body))
                declared_purpose = facts.compact(purpose[-1][1]) if purpose else None
                main_body = body[purpose[-1].end():] if purpose else body
                if declared_purpose in {"합병", "분할", "분할합병"}:
                    body_scope = "MERGER_OR_DIVISION"
                elif declared_purpose and re.search(r"교환|이전|자산|영업", declared_purpose):
                    body_scope = "OTHER_TRANSACTION"
                else:
                    body_scope = "BODY_PURPOSE_UNCONFIRMED"
                main = re.search(r"(?:Ⅰ|I)\.\s*(?:일정|합병.*?일정)(.*?)(?:(?:Ⅱ|II)\.|$)", main_body)
                schedule_text = main[1] if main else ""
                labels = (r"(?:분할합병|합병|분할)\s*기일(?:\s*,\s*분할보고총회 갈음 이사회 결의)?|(?:합병|분할|설립)(?:\s*\(해산\))?\s*등기"
                          r"\s*(?:신청|접수)?\s*(?:예정)?일(?:\s*\(예정\))?|(?:신주|변경|추가|재)\s*상장(?:예정)?일")
                matched = re.findall(r"(?<![가-힣])(" + labels + r")(?:\s*등)?\s+(" + DATE + r")", schedule_text)
                schedule = [{"role": role, "label": m[0], "dates": dates(m[1])} for m in matched
                            if (role := schedule_role(m[0])) is not None]
                item = {"evidencePath": "KIND_ISSUANCE_10810", "market": market, "receipt": receipt,
                        "listedMinuteKst": row["reportedAtKstText"], "issuerDisplayName": row["issuer"],
                        "title": row["title"], "documentPurpose": declared_purpose, "bodyScope": body_scope,
                        "schedule": schedule, "shareTerms": share_terms(main_body),
                        "legalEffectiveDate": None, **proof}
                date_scope = coverage(item) if body_scope == "MERGER_OR_DIVISION" else "OUTSIDE_TRANSACTION_TYPE"
                result.append(item | {"referenceDateScope": date_scope})
    need(len({row["receipt"] for row in result}) == len(result), "KIND_ISSUANCE_DUPLICATE")
    return result


def correction_groups(rows):
    originals = defaultdict(list)
    for row in rows:
        if not row["correctionLabel"] and not row["bodyCorrectionSection"]:
            for original in {row["receiptDate"], row["receiptIdDatePrefix"]}:
                originals[(row["corpCode"], row["category"], original)].append(row["receipt"])
    result = []
    for row in rows:
        if not (row["correctionLabel"] or row["bodyCorrectionSection"]):
            continue
        original = row["originalSubmissionDateInCorrection"]
        candidates = sorted(x for x in originals[(row["corpCode"], row["category"], original)] if x < row["receipt"])
        state = "ONE_ORIGINAL_CANDIDATE" if len(candidates) == 1 else "AMBIGUOUS" if candidates else "ORIGINAL_UNRESOLVED"
        result.append({"correction": row["receipt"], "originalSubmissionDate": original,
                       "possibleOriginalReceipts": candidates, "status": state, "directParentProven": False})
    return result


def withdrawals(archive, scopes):
    result = []
    for name, params in scopes.items():
        raw, _ = archive.read("withdrawal-" + name, "list", params)
        listing = read_json(raw)
        need(listing["status"] == "000" and listing["total_page"] == 1 and
             len(listing["list"]) == listing["total_count"], "WITHDRAWAL_INDEX")
        reviewed = []
        for row in listing["list"]:
            if facts.normalized_title(row["report_nm"]) != "주요사항보고서(회사분할결정)":
                continue
            number = row["rcept_no"]
            need(row["corp_code"] == params["corp_code"] and params["bgn_de"] <= row["rcept_dt"] <= params["end_de"],
                 "WITHDRAWAL_LIST_SCOPE")
            raw, receipt = archive.read("dart-" + number, "document", {"rcept_no": number})
            if receipt.get("providerStatus") == "014":
                need("첨부정정]" in row["report_nm"] and not raw.startswith(b"PK"), "WITHDRAWAL_MISSING_MAIN_BODY")
                reviewed.append({"receipt": number, "receiptDate": stamp(row["rcept_dt"]),
                                 "declaredNewCompany": None, "initialSubmissionDate": None,
                                 "withdrawalExplicit": False, "bodyAvailability": "ATTACHMENT_AMENDMENT_MAIN_NOT_RETURNED",
                                 "sourceUrl": DART + number, "observedAt": receipt["capturedAt"],
                                 "bodySha256": receipt["sha256"]})
                continue
            root, proof = original_xml(raw, number)
            need(facts.one(root.iter("DOCUMENT-NAME")).get("ACODE") == "11345" and
                 facts.one(root.iter("COMPANY-NAME")).get("AREGCIK") == row["corp_code"], "WITHDRAWAL_FORM")
            body = facts.compact(facts.text(root))
            cancelled = ("분할결정철회에따른분할관련모든사항철회" in body and
                         bool(re.search(r"분할결정을철회하기로(?:결의하였습니다|하였습니다)", body)))
            parent_date = correction_start(root)
            if cancelled:
                need(parent_date and "정정]" in row["report_nm"], "WITHDRAWAL_PROVENANCE")
            target = [facts.text(n) for n in root.iter("TE") if n.get("ACODE") == "NEW_INC"]
            reviewed.append({"receipt": number, "receiptDate": stamp(row["rcept_dt"]), "initialSubmissionDate": parent_date,
                             "declaredNewCompany": target[0] if len(target) == 1 and target[0] != "-" else None,
                             "withdrawalExplicit": cancelled, "sourceUrl": DART + number, "observedAt": receipt["capturedAt"], **proof})
        cancelled = [r["receipt"] for r in reviewed if r["withdrawalExplicit"]]
        need(cancelled, "WITHDRAWAL_NOT_IN_BODY")
        result.append({"case": name, "reviewedPlanVersions": sorted(reviewed, key=lambda row: row["receipt"]),
                       "withdrawalReceipts": sorted(cancelled), "effectiveDate": None,
                       "sourceGroupLinksOnly": name == "jusung"})
    return result


def momentum(archive):
    raw, proof = archive.read("company-momentum", "company", {"corp_code": "01857593"})
    value = read_json(raw)
    need(value["status"] == "000" and value["corp_code"] == "01857593" and value["corp_cls"] == "E" and
         value["corp_name"] == "한화모멘텀 주식회사", "MOMENTUM_COMPANY")
    return {"establishmentDate": stamp(value["est_dt"]), "legalRegistrationDate": None,
            "dateBasis": "DART_COMPANY_PROFILE_ESTABLISHMENT_DATE", "observedAt": proof["capturedAt"],
            "bodySha256": proof["sha256"],
            "sourceUrl": "https://englishdart.fss.or.kr/dsbc001/selectPopup.ax?selectKey=01857593"}


def build(manifest_path, artifacts, job):
    manifest_raw = read_bytes(manifest_path)
    manifest = read_json(manifest_raw)
    need(manifest["schemaVersion"] == REVIEW_SCHEMA, "MANIFEST")
    at = utc(manifest["reviewedAt"])
    parent_dir = artifacts / "merger-division-outcomes-20261107"
    parent_raw = pinned(parent_dir / "report.json", manifest["parentSha256"])
    parent = read_json(parent_raw)
    parent_spec = read_json(pinned(manifest_path.parent / "restructuring-outcomes.json", manifest["parentManifestSha256"]))
    need(parent["schemaVersion"] == SCHEMA and parent["manifestSha256"] == manifest["parentManifestSha256"] and
         tuple(parent[key] for key in ("startDate", "endDate", "publicationThrough")) == SCOPE and utc(parent["knownAt"]) <= at,
         "PARENT_SCOPE")
    indexed, _ = outcome_index(Sources(parent_dir, parent_spec["receipts"], utc(parent_spec["reviewedAt"])))
    prior = {row["receipt"]: row for row in parent["candidateFilings"]}
    need(set(indexed) == set(prior) and all(all(prior[n][key] == val for key, val in row.items() if key != "disposition")
                                          for n, row in indexed.items()), "PARENT_INDEX")
    plan = read_json(pinned(job / "plan.json", manifest["planSha256"]))
    pending = sorted(n for n, row in prior.items() if row["disposition"] == "DOCUMENT_REVIEW_PENDING")
    need(plan["schemaVersion"] == "SAGOPALGO_H04_CENSUS_PLAN_V1" and plan["parentSha256"] == manifest["parentSha256"] and
         plan["indexManifestSha256"] == manifest["parentManifestSha256"] and plan["pendingReceipts"] == pending, "PLAN_BINDING")
    archive = Archive(job, manifest["receipts"], at)
    outcomes = [filing(archive, prior[n]) for n in pending]
    issuance = kind_issuance(archive, parent_spec["h01Receipts"]["issuance-report"], artifacts)
    cancelled = withdrawals(archive, manifest["withdrawalScopes"])
    company = momentum(archive)
    need(archive.visited == set(manifest["receipts"]), "CAPTURE_SCOPE")
    corrections = correction_groups(outcomes)
    return {"schemaVersion": REPORT_SCHEMA, "knownAt": at.isoformat(), "startDate": SCOPE[0], "endDate": SCOPE[1],
            "publicationThrough": SCOPE[2], "manifestSha256": digest(manifest_raw), "parentSha256": digest(parent_raw),
            "newlyAuditedE003Filings": outcomes, "reusedE003Filings": len(prior) - len(outcomes),
            "kindIssuanceFilings": issuance, "e003Corrections": corrections, "withdrawalGroups": cancelled,
            "momentumCompanyEvidence": company,
            "e003Counts": dict(Counter(row["market"] for row in outcomes)),
            "e003ReferenceDateScopes": dict(Counter(row["referenceDateScope"] for row in outcomes)),
            "kindIssuanceCounts": dict(Counter(row["market"] for row in issuance)),
            "fullEventCoverageConfirmed": False, "historicalFirstAvailabilityConfirmed": False,
            "referenceEventsEmitted": 0, "priceAdjustmentApplied": False, "usableForTraining": False, "usableForTrading": False}


def as_of(report, at):
    return report if utc(at) >= utc(report["knownAt"]) else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "audit", "as-of"))
    for field in ("manifest", "artifacts", "job"):
        parser.add_argument("--" + field, type=Path, required=True)
    parser.add_argument("--at")
    args = parser.parse_args()
    if args.action == "as-of" and not args.at:
        parser.error("as-of requires --at")
    report = build(args.manifest, args.artifacts, args.job)
    immutable_json(args.job / "report.json", report, require_existing=args.action != "build")
    if args.action == "as-of":
        report = as_of(report, args.at)
    summary = {key: report[key] for key in ("e003Counts", "e003ReferenceDateScopes", "kindIssuanceCounts")} if report else {}
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
