"""Offline audit of OpenDART completion candidates and reviewed KRX restructuring cases."""

import argparse
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
import io
import json
from pathlib import Path
import re
from zipfile import ZipFile

from . import corporate_facts as facts
from . import membership_identity_audit as h01
from .dart_documents import inspect_zip
from .dataset import digest, read_bytes, read_json
from .krx_baseline_validation import immutable_json
from .market_calendar_evidence import text as html_text
from .models import ResearchError, utc
from .session_evidence import validate_url

SCHEMA = "SAGOPALGO_H04_RESTRUCTURING_AUDIT_V1"
DART = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo="
SCOPE = ("2023-11-01", "2026-11-02", "2026-11-07")
COMMON = {"last_reprt_at": "N", "sort": "date", "sort_mth": "asc", "page_no": "1", "page_count": "100"}
OUTCOME = re.compile(r"(?:\[[^]]+\])*합병등종료보고서\(([^)]+)\)")
TYPES = {"합병": "MERGER", "분할": "DIVISION", "분할합병": "DIVISION_MERGER"}
DAY = r"(\d{4}(?:\s*년\s*|\s*[.-]\s*)\d{1,2}(?:\s*월\s*|\s*[.-]\s*)\d{1,2}(?:\s*일)?)"
NUMBER = r"([0-9][0-9,]*)"


def check(condition, reason):
    if not condition:
        raise ResearchError(f"H04_{reason}")


def unique(pattern, value):
    matches = set(re.findall(pattern, value))
    check(len(matches) == 1, "REVIEWED_FIELD_MISSING_OR_CONFLICTING")
    return matches.pop()


def stamp(value):
    check(re.fullmatch(DAY, value) is not None or re.fullmatch(r"\d{8}", value) is not None, "DATE_FORMAT")
    if len(value) == 8 and value.isascii() and value.isdecimal():
        return date(int(value[:4]), int(value[4:6]), int(value[6:])).isoformat()
    return date(*map(int, re.findall(r"[0-9]+", value))).isoformat()


class Sources:
    def __init__(self, job, receipts, reviewed_at):
        self.job, self.receipts, self.reviewed_at = job, receipts, reviewed_at
        self.visited = set()

    def read(self, name, endpoint, parameters=None):
        check(re.fullmatch(r"[a-zA-Z0-9-]+", name) and name in self.receipts, "CAPTURE_SCOPE")
        folder = self.job / "captures" / name
        receipt_raw = read_bytes(folder / "receipt.json")
        check(digest(receipt_raw) == self.receipts[name], "RECEIPT_HASH")
        receipt = read_json(receipt_raw)
        check(receipt["schemaVersion"] == "SAGOPALGO_H04_CAPTURE_V1" and receipt["status"] == "CAPTURED" and
              receipt["endpoint"] == endpoint and (parameters is None or receipt["parameters"] == parameters) and
              utc(receipt["startedAt"]) <= utc(receipt["capturedAt"]) <= self.reviewed_at, "CAPTURE_BINDING")
        raw = read_bytes(folder / "raw.bin")
        check(digest(raw) == receipt["sha256"], "RAW_HASH")
        self.visited.add(name)
        return raw, receipt

    def listing(self, name, params):
        raw, receipt = self.read(name, "list", COMMON | params)
        result = read_json(raw)
        if result["status"] == "013":
            check(not result.get("list") and not result.get("total_count"), "INDEX_EMPTY_CONFLICT")
            return [], receipt
        rows = result["list"]
        check(result["status"] == "000" and result["page_no"] == 1 and result["total_page"] == 1 and
              result["page_count"] == 100 and len(rows) == result["total_count"] <= 100, "INDEX_PAGINATION")
        for row in rows:
            check(re.fullmatch(r"\d{14}", row["rcept_no"]) and re.fullmatch(r"\d{8}", row["corp_code"]) and
                  row["rcept_no"][:8] <= row["rcept_dt"] and params["bgn_de"] <= row["rcept_dt"] <= params["end_de"] and
                  (not params.get("corp_cls") or row["corp_cls"] == params["corp_cls"]) and
                  (not params.get("corp_code") or row["corp_code"] == params["corp_code"]), "INDEX_ROW_SCOPE")
            stamp(row["rcept_dt"])
            stamp(row["rcept_no"][:8])
        check(len({r["rcept_no"] for r in rows}) == len(rows), "INDEX_DUPLICATE")
        return rows, receipt

    def dart(self, row, form):
        number = row["rcept_no"]
        raw, receipt = self.read("dart-" + number, "document", {"rcept_no": number})
        entries = inspect_zip(raw)
        entry = facts.one(e for e in entries if e["name"] == f"{number}.xml")
        with ZipFile(io.BytesIO(raw)) as archive:
            root, _ = facts.parse_xml(archive.read(entry["name"]))
        name = facts.one(root.iter("DOCUMENT-NAME"))
        company = facts.one(root.iter("COMPANY-NAME"))
        check(name.get("ACODE") == form and company.get("AREGCIK") == row["corp_code"] and "철" not in row["rm"],
              "DART_DOCUMENT_IDENTITY")
        return root, {"receipt": number, "form": form, "sourceUrl": DART + number, "bodySha256": entry["sha256"],
                      "archiveSha256": receipt["sha256"], "observedAt": receipt["capturedAt"]}

    def kind(self, name, url):
        validate_url(url)
        raw, receipt = self.read(name, "kind", {"url": url, "method": "GET", "parameters": None})
        return html_text(raw), {"sourceUrl": url, "bodySha256": receipt["sha256"], "observedAt": receipt["capturedAt"]}


def outcome_index(sources):
    start, _, through = map(date.fromisoformat, SCOPE)
    candidates, counts, seen = {}, Counter(), set()
    while start <= through:
        month = start.year * 12 + start.month - 1 + 3
        end = min(through, date(month // 12, month % 12 + 1, 1) - timedelta(days=1))
        for market, provider in (("KOSPI", "Y"), ("KOSDAQ", "K")):
            rows, capture = sources.listing(f"e003-{provider}-{start:%Y%m%d}-01", {
                "pblntf_detail_ty": "E003", "corp_cls": provider, "bgn_de": f"{start:%Y%m%d}", "end_de": f"{end:%Y%m%d}"})
            for row in rows:
                match = OUTCOME.fullmatch(facts.compact(row["report_nm"]))
                number = row["rcept_no"]
                check(match and number not in seen, "INDEX_FILTER_OR_DUPLICATE")
                seen.add(number)
                counts[market] += 1
                if match[1] not in TYPES:
                    continue
                candidates[number] = {"receipt": number, "receiptDate": stamp(row["rcept_dt"]), "market": market,
                                      "receiptIdDatePrefix": stamp(number[:8]),
                                      "receiptAfterEffectScope": stamp(row["rcept_dt"]) > SCOPE[1],
                                      "corpCode": row["corp_code"], "issuer": row["corp_name"],
                                      "stockCodeAtIndex": row["stock_code"].strip() or None, "title": row["report_nm"],
                                      "category": TYPES[match[1]], "correctionLabel": "정정]" in row["report_nm"],
                                      "withdrawalFlag": "철" in row["rm"], "sourceUrl": DART + number,
                                      "indexSha256": capture["sha256"], "observedAt": capture["capturedAt"],
                                      "disposition": "DOCUMENT_REVIEW_PENDING", "legalEffectiveDate": None}
        start = end + timedelta(days=1)
    return candidates, counts


def correction_start(root):
    section = list(root.iter("CORRECTION"))
    check(len(section) <= 1, "CORRECTION_LAYOUT")
    if not section:
        return None
    return stamp(unique(r"최초제출일\s*:\s*" + DAY, facts.text(section[0])))


def typed_date(scope, code):
    node, evidence = facts.field(scope, "TU", "AUNIT", code)
    value = node.get("AUNITVALUE")
    check(stamp(value) == stamp(evidence["sourceText"]), "DATE_DISPLAY_CONFLICT")
    return stamp(value)


def plans(sources, company, first, end, merger=False):
    rows, _ = sources.listing(f"plans-{company}-{first}-01", {"corp_code": company, "bgn_de": first, "end_de": end,
                                                            "pblntf_ty": "B", "pblntf_detail_ty": "B001"})
    label = "회사합병결정" if merger else "회사분할결정"
    rows = sorted((row for row in rows if facts.normalized_title(row["report_nm"]) == f"주요사항보고서({label})"),
                  key=lambda row: row["rcept_no"])
    check(len(rows) >= 2 and len({r["rcept_dt"] for r in rows}) == len(rows), "PLAN_SEQUENCE")
    result = []
    original = stamp(rows[0]["rcept_no"][:8])
    for i, row in enumerate(rows):
        root, evidence = sources.dart(row, "11344" if merger else "11345")
        parent_date = correction_start(root)
        check((i == 0 and parent_date is None or i > 0 and parent_date == original and "정정]" in row["report_nm"]) and
              ("정" in row["rm"]) == (i < len(rows) - 1), "CORRECTION_OR_WITHDRAWAL_UNRESOLVED")
        group = facts.one(t for t in root.iter("TABLE-GROUP") if t.get("ACLASS") == ("RSL_MGR" if merger else "RSL_SPL"))
        reference = typed_date(group, "MGR_DT" if merger else "SPL_DT")
        registration = typed_date(group, "MGR_RGS_DT" if merger else "SPL_RGS_DT")
        code = "MGR_CSY" if merger else "CPR_CED"
        listing, _ = facts.field(group, "TU", "AUNIT", code)
        check(reference <= registration, "PLAN_DATE_ORDER")
        result.append(evidence | {"receiptDate": stamp(row["rcept_dt"]), "receiptIdDatePrefix": stamp(row["rcept_no"][:8]),
                                 "originalSubmissionDate": parent_date,
                                 "plannedReferenceDate": reference, "plannedRegistrationDate": registration,
                                 "plannedListingDate": None if listing.get("AUNITVALUE") == "-" else typed_date(group, code)})
    return result, group


def consolidated_ratio(ratio, published, divisor):
    adjusted = Decimal(ratio) / divisor
    check(adjusted.quantize(Decimal("0.0000001"), rounding=ROUND_HALF_UP) == Decimal(published), "MERGER_ADJUSTED_RATIO")
    return str(adjusted)


def merger_case(sources, artifacts, parent_receipts):
    plan, group = plans(sources, "01276901", "20260401", "20260814", merger=True)
    texts, evidence = {}, {}
    for name, pin in parent_receipts.items():
        texts[name], metadata = h01.kind_text(artifacts / "historical-membership-identity-20261107" / "kind" / name, name, pin)
        evidence[name] = metadata | {"observedAt": metadata["knownAt"]}
    known = h01.case_facts(texts)
    check(plan[-1]["plannedReferenceDate"] == known["disclosedMergerReferenceDate"], "MERGER_REFERENCE_DATE")
    ratio = unique(r"위지윅스튜디오 보통주 1주당 ([0-9.]+)주의 비율", texts["issuance-report"])
    _, rate_field = facts.field(group, "TE", "ACODE", "OTH_MGR_RATE")
    check(unique(r"위지윅스튜디오\s*=\s*1\s*:\s*([0-9.]+)", rate_field["sourceText"]) == ratio, "MERGER_RATIO")
    issued, before = map(lambda v: int(facts.integer(v)), unique(
        rf"보통주 A291230 {NUMBER} 3\.1주당 액면가/자본금\(원\) 100 .*?보통주 {NUMBER} 2026-01-01", texts["new-shares"]))
    for name, id_, path in (
        ("capital", "20260811001988", "000918/20260811001988/70763.htm"),
        ("consolidation", "20260811001993", "000923/20260811001993/70764.htm"),
    ):
        texts[name], evidence[name] = sources.kind(f"kind-body-np-{name}-{id_}", f"{h01.KIND}/external/2026/08/11/{path}")
    removed, after_capital = map(lambda v: int(facts.integer(v)), unique(
        rf"보통주 A291230 -{NUMBER} 3\.1주당 액면가/자본금\(원\) 100 .*?보통주 {NUMBER} 2026-01-01", texts["capital"]))
    check("액면병합 4.액면변경내역 변경전액면가(원) 100 변경후액면가(원) 500" in texts["consolidation"], "FACE_VALUE_RATIO")
    final = int(facts.integer(unique(rf"보통주 {NUMBER} 2026-01-01", texts["consolidation"])))
    date_ = known["successorNewSharesListingDate"]
    check(all(f"상장일 {date_}" in texts[name] for name in ("capital", "consolidation")) and
          before - removed == after_capital and after_capital // 5 == final, "MERGER_LISTING_SHARE_RECONCILIATION")
    published = unique(r"실질적인 합병비율은 ([0-9.]+)으로 조정", texts["issuance-report"])
    adjusted = consolidated_ratio(ratio, published, 5)
    return {"caseId": "np-wys-merger", "market": "KOSDAQ", "type": "MERGER", "plans": plan, "sources": evidence,
            "instruments": {"source": "299900", "destination": "291230", "shareClass": "COMMON"},
            "referenceDate": known["disclosedMergerReferenceDate"], "reportedCompletionDate": known["issuerReportedMergerEffectiveDate"],
            "legalEffectiveDate": known["issuerReportedMergerEffectiveDate"], "legalBasis": "ISSUER_REPORTED_REGISTRATION_AND_EFFECTIVE_DATE",
            "listingDate": date_, "sourceDelistingDate": known["exchangeAnnouncedDelistingDate"],
            "publicAllocation": {"preConsolidationSharesPerSourceShare": ratio,
                                 "postConsolidationCalculated": adjusted, "postConsolidationPublished": published},
            "listingShareCounts": {"mergerNewSharesBeforeConsolidation": issued, "totalAfterMergerListingNotice": before,
                                   "capitalReduction": removed, "totalAfterCapitalReductionNotice": after_capital,
                                   "totalAfterConsolidationNotice": final, "aggregateDivisionRemainder": after_capital % 5}}


def spin_off_case(sources):
    plan, group = plans(sources, "00126566", "20240401", "20240930")
    rows, _ = sources.listing("hae-september-01", {"corp_code": "00126566", "bgn_de": "20240828", "end_de": "20240930"})
    issuance = sorted((row for row in rows if facts.normalized_title(row["report_nm"]) == "증권발행실적보고서(합병등)"),
                      key=lambda row: row["rcept_no"])
    original, revised = issuance
    original_root, original_proof = sources.dart(original, "10810")
    revised_root, revised_proof = sources.dart(revised, "10810")
    check(correction_start(original_root) is None and correction_start(revised_root) == stamp(original["rcept_dt"]) and
          "정" in original["rm"] and "정정]" in revised["report_nm"] and "정" not in revised["rm"], "ISSUANCE_CORRECTION")
    text_before, text_after = (facts.text(facts.one(root.findall("./BODY/SECTION-1"))) for root in (original_root, revised_root))
    _, allocation = facts.field(group, "TE", "ACODE", "NEW_SPL_RATE")
    _, distribution = facts.field(group, "TE", "ACODE", "CPR_DBN")
    target_ratio = unique(r"분할회사 보통주식 1주당 ([0-9.]+)주를 배정", distribution["sourceText"])
    survivor_ratio = unique(r"분할존속회사:\s*([0-9.]+)", allocation["sourceText"])
    asset_ratio = unique(r"분할신설회사:\s*([0-9.]+)", allocation["sourceText"])
    check(all(unique(r"한화인더스트리얼솔루션즈 주식회사 보통주 ([0-9.]+)주", body) == target_ratio
              for body in (text_before, text_after)) and Decimal(asset_ratio) * 10 == Decimal(target_ratio) and
          Decimal(survivor_ratio) + Decimal(asset_ratio) == 1, "DIVISION_ALLOCATION")
    evidence = {"originalIssuance": original_proof, "correctedIssuance": revised_proof}
    registration, evidence["registration"] = sources.kind("kind-body-hae-registration-20250317004519",
                                                           f"{h01.KIND}/external/2025/03/17/001075/20250317004519/11011.htm")
    survivor, evidence["survivorListing"] = sources.kind("kind-body-hae-change-20240924000088",
                                                        f"{h01.KIND}/external/2024/09/24/000043/20240924000088/68155.htm")
    new, evidence["newListing"] = sources.kind("kind-body-hae-relist-20240925001494",
                                               f"{h01.KIND}/external/2024/09/25/000568/20240925001494/68156.htm")
    check("KR7012450003 (단축코드:A012450)" in survivor and "KR7489790006(단축코드 : A489790)" in new, "DIVISION_LISTING_IDENTITY")
    reported_registration = stamp(unique(DAY + r" - 창립총회 갈음 공고 승인 이사회 결의 - 한화비전.*?설립등기", registration))
    application = stamp(unique(r"분할등기 신청일 " + DAY, text_after))
    reference = stamp(unique(r"분할기일\s*,\s*분할보고총회 갈음 이사회 결의 " + DAY, text_after))
    listing = stamp(unique(r"② 상장일 : " + DAY, new))
    check(plan[-1]["plannedReferenceDate"] == reference and reference < reported_registration == application < listing and
          stamp(unique(r"⑦ 변경상장일 : " + DAY, survivor)) == listing, "DIVISION_DATE_SCOPE")
    new_count = int(facts.integer(unique(rf"⑤ 주식의 종류와 수 : 보통주 {NUMBER}주", new)))
    old_count, survivor_count = map(lambda v: int(facts.integer(v)), unique(rf"기명식 보통주 {NUMBER}주 → {NUMBER}주", survivor))
    group_shares = r"계 보통주 [0-9,]+ [0-9.]+ [0-9,]+ [0-9.]+ ([0-9,]+) 34\.10"
    original_group, corrected_group = (unique(group_shares, body) for body in (text_before, text_after))
    check(unique(r"최대주주등 : ([0-9,]+)주", new) == corrected_group, "DIVISION_CORRECTED_GROUP_SHARES")
    return {"caseId": "hanwha-aerospace-spin-off", "market": "KOSPI", "type": "SPIN_OFF", "plans": plan, "sources": evidence,
            "instruments": {"source": "012450", "survivor": "012450", "destination": "489790", "shareClass": "COMMON"},
            "referenceDate": reference, "reportedCompletionDate": reported_registration,
            "legalEffectiveDate": reported_registration, "legalBasis": "NEW_ISSUER_REPORTED_INCORPORATION_REGISTRATION",
            "registrationApplicationDate": application, "listingDate": listing,
            "survivorIssueDate": stamp(unique(r"④ 발행일 ▶ 기명식 보통주\(제21회\): " + DAY, survivor)),
            "publicAllocation": {"survivorSharesPerSourceShare": survivor_ratio, "newSharesPerSourceShare": target_ratio,
                                 "newCompanyNetAssetRatio": asset_ratio, "newToOldShareCountMultiplier": 10},
            "listingShareCounts": {"before": old_count, "survivor": survivor_count, "new": new_count},
            "correctedNewCompanyMajorShareholderGroup": {"original": int(facts.integer(original_group)),
                                                         "corrected": int(facts.integer(corrected_group))}}


def physical_case(sources, candidates):
    plan, group = plans(sources, "00160588", "20240401", "20240731")
    selected = candidates["20240701000361"]
    check(selected["corpCode"] == "00160588" and not selected["withdrawalFlag"] and
          selected["category"] == "DIVISION", "PHYSICAL_INDEX_IDENTITY")
    row = {"rcept_no": selected["receipt"], "corp_code": selected["corpCode"], "rm": ""}
    root, proof = sources.dart(row, "12000")
    body = facts.text(root)
    _, allocation = facts.field(group, "TE", "ACODE", "NEW_SPL_RATE")
    _, relisting = facts.field(group, "TU", "AUNIT", "NEW_RR")
    check("100%" in allocation["sourceText"] and "분할되는 회사에 100% 배정되었습니다" in body and
          "단순ㆍ물적분할" in body and relisting["sourceText"] == "아니오", "PHYSICAL_ALLOCATION")
    reference = stamp(unique(r"분할기일 " + DAY, body))
    planned_registration = stamp(unique(r"분할등기일\(예정\) " + DAY, body))
    followup, metadata = sources.kind("kind-expanded-momentum-quarter",
                                      f"{h01.KIND}/external/2024/11/13/000755/20241113001603/11013.htm")
    completion = stamp(unique(DAY + r" ㈜한화로부터 물적분할 이후", followup))
    contribution_date, shares = unique(rf"한화모멘텀 주식회사 계열회사 {DAY} 보통주 출자 {NUMBER} ", followup)
    check(plan[-1]["plannedReferenceDate"] == reference == completion == stamp(contribution_date), "PHYSICAL_DATE_SCOPE")
    selected["disposition"] = "REVIEWED_REGISTRATION_UNCONFIRMED"
    return {"caseId": "hanwha-momentum-physical-division", "market": "KOSPI", "type": "PHYSICAL_DIVISION",
            "plans": plan, "sources": {"termination": proof, "completionFollowup": metadata},
            "instruments": {"source": "000880", "recipient": "PARENT_COMPANY", "destination": None, "shareClass": "COMMON"},
            "referenceDate": reference, "reportedCompletionDate": completion, "plannedRegistrationDateInOutcome": planned_registration,
            "legalEffectiveDate": None, "legalBasis": "ACTUAL_REGISTRATION_DATE_UNCONFIRMED", "listingDate": None,
            "listingStatus": "NEW_COMPANY_NOT_LISTED_IN_TRANSACTION",
            "publicAllocation": None, "newSharesOwnership": {"parentAllocationPercent": "100",
                                                              "parentContributionShares": int(facts.integer(shares)),
                                                              "publicShareholdersReceiveNewShares": False}}


def build(manifest_path, artifacts, job):
    manifest = read_json(read_bytes(manifest_path))
    check(manifest["schemaVersion"] == "SAGOPALGO_H04_REVIEW_V1" and
          tuple(manifest[name] for name in ("startDate", "endDate", "publicationThrough")) == SCOPE, "MANIFEST_SCOPE")
    reviewed_at = utc(manifest["reviewedAt"])
    sources = Sources(job, manifest["receipts"], reviewed_at)
    candidates, counts = outcome_index(sources)
    cases = [merger_case(sources, artifacts, manifest["h01Receipts"]), spin_off_case(sources), physical_case(sources, candidates)]
    check(sources.visited == set(manifest["receipts"]) and all(SCOPE[0] <= case["referenceDate"] <= SCOPE[1] for case in cases),
          "REVIEWED_SOURCE_OR_CASE_SCOPE")
    for case in cases:
        timings = [v["observedAt"] for v in list(case["sources"].values()) + case["plans"]]
        check(all(utc(value) <= reviewed_at for value in timings), "FUTURE_SOURCE")
        case.update(knownAt=reviewed_at.isoformat(), availability="LOCAL_REVIEW_ONLY", automaticEffectAllowed=False)
    return {"schemaVersion": SCHEMA, "startDate": SCOPE[0], "endDate": SCOPE[1], "publicationThrough": SCOPE[2],
            "knownAt": reviewed_at.isoformat(), "manifestSha256": digest(read_bytes(manifest_path)),
            "indexFilingCounts": dict(counts), "candidateCounts": dict(Counter(row["market"] for row in candidates.values())),
            "candidateFilings": [candidates[number] for number in sorted(candidates)], "cases": cases,
            "fullEventCoverageConfirmed": False, "historicalFirstAvailabilityConfirmed": False,
            "priceAdjustmentApplied": False, "referenceEventsEmitted": 0, "usableForTraining": False, "usableForTrading": False}


def as_of(report, at):
    visible = utc(at) >= utc(report["knownAt"])
    return {"auditVisible": visible, "cases": report["cases"] if visible else [],
            "candidateFilings": report["candidateFilings"] if visible else []}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "audit", "as-of"))
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--job", type=Path, required=True)
    parser.add_argument("--at")
    args = parser.parse_args()
    if args.action == "as-of" and not args.at:
        parser.error("as-of requires --at")
    report = build(args.manifest, args.artifacts, args.job)
    immutable_json(args.job / "report.json", report, require_existing=args.action != "build")
    if args.action == "as-of":
        value = as_of(report, args.at)
        result = {"auditVisible": value["auditVisible"], "visibleCases": len(value["cases"]),
                  "visibleCandidateFilings": len(value["candidateFilings"])}
    else:
        result = {"candidateCounts": report["candidateCounts"], "cases": [case["caseId"] for case in report["cases"]]}
    print(json.dumps(result))


if __name__ == "__main__":
    main()
