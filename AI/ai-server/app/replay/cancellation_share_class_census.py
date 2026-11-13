"""Cross-check KRX stock-issue detail rows against instrument-specific notices."""

import argparse
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
import re

from . import ksd_dividend_evidence as ksd
from .cancellation_evidence import REASONS, signed_quantity
from .corporate_action_event_audit import name_key
from .corporate_action_outcomes import VIEWER, capture, checked_read, require
from .dataset import digest, read_bytes, read_json
from .krx_baseline_validation import immutable_json
from .market_calendar_evidence import text
from .models import ResearchError, utc
from .restructuring_outcomes import DAY, stamp
from .session_notice_inventory import body_path, viewer_documents

SCHEMA = "SAGOPALGO_H05_CANCELLATION_SHARE_CLASS_V1"
AMOUNT = r"[0-9]+(?:,[0-9]{3})*"
CLASS = (r"(?<![가-힣A-Z0-9])(?:보통주(?:식)?|(?:상환전환|상환|전환|[0-9]*\s*)"
         r"우선주(?:식)?(?:\([^)]{1,18}\))?|종류주식(?:[0-9]+)?(?:\([^)]{1,18}\))?|KDR)(?![가-힣A-Z0-9])")
SERIAL = r"\(제\s*[0-9]+(?:\s*~\s*[0-9]+)?\s*회\)"
CONFIRMED = {"COMMON", "PREFERRED", "OTHER_SHARE_CLASS"}


def reason_key(value):
    return "주식소각" if value == "이익소각" else value


def candidate_links(rows, inventory):
    indexed = defaultdict(list)
    for row in rows:
        indexed[row["market"], name_key(row["issuer"])].append(row)
    for notice in inventory:
        if "상장" not in notice["title"] or "소각" not in notice["title"]:
            continue
        matched = []
        for row in indexed[notice["market"], name_key(notice["issuerDisplayName"])]:
            start = (date.fromisoformat(row["listingDate"]) - timedelta(days=14)).isoformat()
            if start <= notice["listedMinuteKst"][:10] <= row["listingDate"]:
                matched.append(row["processId"])
        if matched:
            yield notice, sorted(matched)


def class_key(label):
    value = re.sub(r"\s+|식$", "", label)
    if value == "보통주":
        return value, "COMMON"
    if "우선주" in value:
        return value, "PREFERRED"
    return value, "OTHER_SHARE_CLASS"


def kospi_lines(body):
    if body.count("◎") > 1:
        return [line for section in body.split("◎") if section.strip() for line in kospi_section(section)]
    return kospi_section(body)


def kospi_section(body):
    layout = re.search(r"②\s*주식의 종류와 수.*?(?=▶)(.*?)③.*?④\s*(?:발행일(?:\(소각일\))?|소각일)\s*:?"
                       r"\s*(.*?)⑤.*?⑦\s*변경상장일\s*:\s*" + DAY +
                       r"\s*⑧\s*변경사유\s*:\s*(.*?)\s*⑨\s*코드\s*(.*)$", body)
    if not layout:
        return []
    amounts, issuance, listed, reason, codes = layout.groups()
    if reason not in REASONS:
        return []
    listed = stamp(listed)
    rows = re.findall(r"▶\s*기명식\s+(" + CLASS + r")\s*:?\s*(" + AMOUNT + r")주(?:\s*" + SERIAL + r")?\s*→\s*(" +
                      AMOUNT + r")\s*주?(?:\s*" + SERIAL + r")?\s*▶?\s*[-(]?\s*변경주식수\s*:\s*(-" +
                      AMOUNT + r")주", amounts)
    identities = re.findall(r"▶\s*(?:(" + CLASS + r")\s+)?표준코드\s*:\s*([A-Z0-9]{12})\s*"
                            r"\(단축코드\s*:\s*A([A-Z0-9]{6})\)", codes)
    if not rows or len(identities) != len(rows):
        return []
    if len(rows) == len(identities) == 1 and not identities[0][0]:
        identities[0] = (rows[0][0], *identities[0][1:])
    code_by_class = {class_key(label)[0]: (isin, symbol) for label, isin, symbol in identities}
    if (len(code_by_class) != len(rows) or len({symbol for _, _, symbol in identities}) != len(rows) or
            len({isin for _, isin, _ in identities}) != len(rows) or
            set(code_by_class) != {class_key(row[0])[0] for row in rows}):
        return []
    shared_date = re.fullmatch(DAY, issuance.strip())
    dates = defaultdict(set)
    for label, value in re.findall(r"▶\s*기명식\s+(" + CLASS + r")(?:\s*" + SERIAL +
                                   r")?\s*:\s*" + DAY, issuance):
        dates[class_key(label)[0]].add(stamp(value))
    result = []
    for label, before, after, change in rows:
        key, share_class = class_key(label)
        outstanding, change = signed_quantity(after), signed_quantity(change)
        if outstanding - signed_quantity(before) != change or change >= 0 or outstanding < 0:
            return []
        issue_dates = [stamp(shared_date[1])] if shared_date else sorted(dates[key])
        if any(day > listed for day in issue_dates):
            return []
        isin, symbol = code_by_class[key]
        result.append({"symbol": symbol, "isin": isin, "shareClass": share_class, "shareClassLabel": label,
                       "listingDate": listed, "reportedIssueDates": issue_dates, "reason": reason,
                       "signedShareChange": change, "outstanding": outstanding})
    return result


def kosdaq_lines(body):
    layout = re.search(r"2\.\s*변경주식의 종류와 수 (.*?)3\.\s*1주당.*?4\.\s*변경상장 후 상장주식총수 "
                       r"(.*?)5\.\s*상장일 (\d{4}-\d{2}-\d{2}).*?발행회수\(발행일\)\s+(.*)$", body)
    if not layout:
        return []
    securities, balances, listed, issuance = layout.groups()
    listed_year = date.fromisoformat(listed).year
    changes = defaultdict(list)
    for label, symbol, change in re.findall(r"(" + CLASS + r")\s+A([A-Z0-9]{6})\s+(-" + AMOUNT + r")(?=\s|$)", securities):
        changes[class_key(label)[0]].append((label, symbol, signed_quantity(change)))
    outstanding = defaultdict(list)
    for label, amount in re.findall(r"(" + CLASS + r")\s+(" + AMOUNT + r")\s+\d{4}-\d{2}-\d{2}", balances):
        outstanding[class_key(label)[0]].append(signed_quantity(amount))
    events = defaultdict(list)
    reasons = "|".join(re.escape(reason) for reason in sorted(REASONS))
    for label, reason, change, issued in re.findall(r"(" + CLASS + r")\s+(" + reasons + r")\s+-\s+(-" + AMOUNT +
                                                     r")\s+-\s+(\(['’]\d{2}\.\d{2}\.\d{2}\)|-)(?=\s|$)", issuance):
        issue_date = None
        if issued != "-":
            yy, month, day = map(int, re.findall(r"\d+", issued))
            years = {year for year in (listed_year - 1, listed_year) if year % 100 == yy}
            if len(years) != 1:
                continue
            issue_date = date(years.pop(), month, day).isoformat()
        events[class_key(label)[0]].append((reason, signed_quantity(change), issue_date))
    result = []
    for key, candidates in changes.items():
        if len(candidates) != 1 or len(outstanding[key]) != 1 or len(events[key]) != 1:
            continue
        label, symbol, change = candidates[0]
        reason, event_change, issued = events[key][0]
        if change != event_change or change >= 0 or issued and issued > listed:
            continue
        result.append({"symbol": symbol, "isin": None, "shareClass": class_key(label)[1], "shareClassLabel": label,
                       "listingDate": listed, "reportedIssueDates": [issued] if issued else [], "reason": reason,
                       "signedShareChange": change, "outstanding": outstanding[key][0]})
    return result


def reconcile(row, lines):
    matched = [line for line in lines if line["listingDate"] == row["listingDate"] and
               line["signedShareChange"] == row["signedShareChange"] and reason_key(line["reason"]) == reason_key(row["reason"])]
    if not matched:
        return "NO_MATCHING_INSTRUMENT", []
    identities = {(line["symbol"], class_key(line["shareClassLabel"])[0]) for line in matched}
    isins = {line["isin"] for line in matched if line["isin"]}
    if len(identities) != 1 or len(isins) > 1 or any(
            line["outstanding"] != row["stockIssueReportedOutstanding"] for line in matched):
        return "NOTICE_DETAIL_CONFLICT", matched
    return matched[0]["shareClass"], matched


def date_comparison(row, matched):
    if any(line.get("issueDatesVaryByVersion") for line in matched):
        return "NOTICE_VERSION_DATES_DIFFER"
    notice_dates = [line["reportedIssueDates"] for line in matched if line["reportedIssueDates"]]
    if not notice_dates:
        return "NOTICE_DATE_NOT_STATED"
    if any(row["reportedIssueDate"] not in dates for dates in notice_dates):
        return "ISSUE_DATE_DISAGREES"
    return "ISSUE_DATE_AGREES"


def unchanged_instruments(versions):
    if len(versions) < 2:
        return []
    dated = "reportedIssueDates"
    stable = []
    for line in versions[0]:
        fields = {k: v for k, v in line.items() if k != dated}
        alternatives = [[item for item in version if {k: v for k, v in item.items() if k != dated} == fields]
                        for version in versions]
        if all(len(variants) == 1 for variants in alternatives):
            dates = [variants[0][dated] for variants in alternatives]
            stable.append(line | {dated: sorted({day for values in dates for day in values}),
                                  "issueDatesVaryByVersion": any(values != dates[0] for values in dates[1:])})
    return stable


def review(job, prior, pins, old_pins, candidate, at, used):
    receipt = candidate["receipt"]

    def read(stage, spec, document=None):
        name = f"proof-{stage}-{receipt}" + (f"-{document}" if document else "")
        if name in old_pins:
            return capture(prior, old_pins, name, spec, at)
        if name in pins:
            used.add(name)
            return capture(job, pins, name, spec, at)
        return None, None

    evidence = []
    try:
        raw, proof = read("viewer", {"method": "GET", "url": candidate["sourceUrl"], "parameters": None})
        if raw is None:
            return "VIEWER_UNAVAILABLE", [], evidence
        evidence.append(proof)
        docs = viewer_documents(raw)
        multiple = len(docs) != 1 or docs[0]["correctionMarked"] or candidate["titleCorrectionFlag"]
        versions = []
        for version in docs:
            document = version["document"]
            suffix = document if multiple else None
            raw, proof = read("route", {"method": "POST", "url": VIEWER,
                                        "parameters": {"method": "searchContents", "docNo": document}}, suffix)
            if raw is None:
                return ("NOTICE_VERSION_REVIEW" if multiple else "DOCUMENT_ROUTE_UNAVAILABLE"), [], evidence
            evidence.append(proof | version)
            url = body_path(raw, document)
            raw, proof = read("body", {"method": "GET", "url": url, "parameters": None}, suffix)
            if raw is None:
                return ("NOTICE_VERSION_REVIEW" if multiple else "DOCUMENT_UNAVAILABLE"), [], evidence
            evidence.append(proof | version)
            status, lines = parse_notice(candidate["market"], url, raw)
            if not multiple:
                return status, lines, evidence
            versions.append(lines)
        # Only share-class facts identical in every version can bypass lineage review.
        stable = unchanged_instruments(versions)
        return ("NOTICE_PARSED_ACROSS_VERSIONS" if stable else "NOTICE_VERSION_REVIEW"), stable, evidence
    except ResearchError as exc:
        if str(exc).startswith("SESSION_INVENTORY_"):
            return "PROVIDER_NOTICE_LAYOUT_UNCONFIRMED", [], evidence
        raise


def parse_notice(market, url, raw):
    form = url.rsplit("/", 1)[1]
    parser = {("KOSPI", "68155.htm"): kospi_lines, ("KOSPI", "68151.htm"): kospi_lines,
              ("KOSDAQ", "70763.htm"): kosdaq_lines}.get((market, form))
    try:
        lines = parser(text(raw)) if parser else []
    except ValueError:
        return "NOTICE_INVALID_DATE", []
    return ("NOTICE_PARSED" if lines else "NOTICE_INSTRUMENT_FIELDS_UNCONFIRMED"), lines


def unresolved_status(notice_statuses):
    if not notice_statuses:
        return "NO_NOTICE_CANDIDATE"
    if notice_statuses & {"NOTICE_PARSED", "NOTICE_PARSED_ACROSS_VERSIONS"}:
        return "NO_MATCHING_INSTRUMENT"
    if "NOTICE_VERSION_REVIEW" in notice_statuses:
        return "NOTICE_VERSION_REVIEW"
    if notice_statuses & {"NOTICE_INSTRUMENT_FIELDS_UNCONFIRMED", "NOTICE_INVALID_DATE"}:
        return "NOTICE_INSTRUMENT_FIELDS_UNCONFIRMED"
    return "SOURCE_UNAVAILABLE"


def depository_spec(issuer_number, start, end, kind):
    fields = {"ISSUCO_CUSTNO": issuer_number, "RGT_LINK_RACD": "", "SECN_KACD": "",
              "ISSU_DT_FROM": start.replace("-", ""), "ISSU_DT_TO": end.replace("-", ""),
              "STARTPAGE": "1", "ENDPAGE": "100"}
    return {"method": "POST", "url": ksd.SERVICE, "parameters": {
        "task": ksd.TASK + "EntrFnafInfoPTask", "page": "01012", "fields": fields,
        "action": {"rows": "chgDetailsListEL1", "count": "chgDetailsListCnt"}[kind]}}


def depository_review(target, row, matches, job, prior, pins, old_pins, at, used):
    market, symbol, year = row["market"], target["symbol"], target["registryYear"]
    name = f"ksd-stat-{market}-{year}-rows"
    data, binding = capture(prior, old_pins, name, ksd.request_spec("stat", market, year, "rows"), at)
    issuer_numbers = {r["ISSUCO_CUSTNO"] for r in ksd.parse_rows(data) if r["SHOTN_ISIN"] == symbol and
                      name_key(r["KOR_SECN_NM"]) == name_key(row["issuer"])}
    require(len(issuer_numbers) == 1 and next(iter(issuer_numbers)).isdigit(), "SHARE_CLASS_KSD_ISSUER")
    issuer_number = issuer_numbers.pop()
    values = {}
    evidence = []
    for kind in ("count", "rows"):
        name = f"ksd-issue-{row['processId']}-{kind}"
        request = depository_spec(issuer_number, target["from"], row["listingDate"], kind)
        values[kind], proof = capture(job, pins, name, request, at)
        evidence.append(proof | {"sourceUrl": ksd.source_url("01012")})
        used.add(name)
    data = list(ksd.parse_rows(values["rows"]))
    require(len(data) == ksd.parse_count(values["count"]) <= 100, "SHARE_CLASS_KSD_COUNT")
    candidate = []
    for item in data:
        if (item["RGT_LINK_RACD"], item["RGT_LINK_RACD_NM"]) != ("907", "이익소각"):
            continue
        if name_key(item["REP_SECN_NM"]) != name_key(row["issuer"]) or not item["LIST_DT"]:
            continue
        if ksd.ksd_date(item["LIST_DT"]) != row["listingDate"] or item["ISSU_QTY"] != str(row["signedShareChange"]):
            continue
        issue_day = ksd.ksd_date(item["ISSU_DT"])
        require(target["from"] <= issue_day <= row["listingDate"], "SHARE_CLASS_KSD_DATE")
        candidate.append({"shareClassLabel": item["SECN_KACD_NM"], "reportedIssueDate": issue_day})
    agrees = (len(candidate) == 1 and matches and target["symbol"] == matches[0]["symbol"] and
              class_key(candidate[0]["shareClassLabel"])[0] == class_key(matches[0]["shareClassLabel"])[0])
    status = "KSD_CLASS_AGREES" if agrees else "KSD_CANDIDATE_REVIEW" if candidate else "KSD_NO_MATCH"
    return {"status": status, "matches": candidate, "issuerBindingEvidence": binding, "evidence": evidence}


def build(manifest, artifacts, job):
    raw = read_bytes(manifest)
    spec = read_json(raw)
    require(spec["schemaVersion"] == SCHEMA, "SHARE_CLASS_SCOPE")
    at = utc(spec["reviewedAt"])
    inputs = {k: read_json(checked_read(artifacts / pin["path"], pin["sha256"])) for k, pin in spec["inputs"].items()}
    require(all(utc(item["knownAt"]) <= at for item in inputs.values()), "SHARE_CLASS_FUTURE_INPUT")
    rows = [row for row in inputs["outcomes"]["cancellations"] if row["status"] == "CANCELLATION_DATE_UNVERIFIED_SHARE_CLASS"]
    require(len(rows) == len({row["processId"] for row in rows}) == 962, "SHARE_CLASS_TARGETS")
    known = read_json(checked_read(manifest.parent / "corporate-action-outcome-census.json", spec["priorManifestSha256"]))
    prior = (artifacts / spec["inputs"]["outcomes"]["path"]).parent
    depository_targets = spec.get("depositoryTargets", {})
    require(depository_targets.keys() <= {row["processId"] for row in rows}, "SHARE_CLASS_KSD_SCOPE")
    used, notices, evidence_by_row = set(), {}, defaultdict(list)
    for candidate, ids in candidate_links(rows, inputs["inventory"]["candidateRows"]):
        status, lines, proof = review(job, prior, spec["receipts"], known["noticeReceipts"], candidate, at, used)
        receipt = candidate["receipt"]
        notices[receipt] = {"status": status, "title": candidate["title"], "rows": ids, "evidence": proof}
        for process in ids:
            evidence_by_row[process].append((receipt, lines))
    result = []
    for row in rows:
        evidence = evidence_by_row[row["processId"]]
        candidates = [line | {"receipt": receipt} for receipt, lines in evidence for line in lines]
        status, matched = reconcile(row, candidates)
        receipts = [receipt for receipt, _ in evidence]
        if status == "NO_MATCHING_INSTRUMENT":
            status = unresolved_status({notices[receipt]["status"] for receipt in receipts})
        confirmed = matched[0] if status in CONFIRMED else {}
        depository = depository_targets.get(row["processId"])
        isins = sorted({line["isin"] for line in matched if line["isin"]})
        ksd_result = depository_review(depository, row, matched if confirmed else [], job, prior, spec["receipts"],
                                       known["ksdReceipts"], at, used) if depository else None
        result.append(row | {"shareClassReviewStatus": status, "matches": matched,
                             "noticeReceipts": receipts, "confirmedShareClass": confirmed.get("shareClass"),
                             "confirmedSymbol": confirmed.get("symbol"),
                             "confirmedIsin": isins[0] if confirmed and isins else None, "depositoryReview": ksd_result,
                             "issueDateComparison": date_comparison(row, matched) if confirmed else "IDENTITY_UNCONFIRMED"})
    require(used == set(spec["receipts"]), "SHARE_CLASS_CAPTURE_SCOPE")
    return {"schemaVersion": SCHEMA, "manifestSha256": digest(raw), "knownAt": at.isoformat(), "rows": result,
            "rowCounts": dict(Counter(r["shareClassReviewStatus"] for r in result)), "notices": notices,
            "issueDateCounts": dict(Counter(r["issueDateComparison"] for r in result)),
            "noticeCounts": dict(Counter(r["status"] for r in notices.values())),
            "historicalFirstAvailabilityConfirmed": False, "usableForTraining": False, "usableForTrading": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "audit"))
    for name in ("manifest", "artifacts", "job"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    report = build(args.manifest, args.artifacts, args.job)
    immutable_json(args.job / "report.json", report, require_existing=args.action == "audit")
    print(report["rowCounts"])
    print(report["noticeCounts"])


if __name__ == "__main__":
    main()
