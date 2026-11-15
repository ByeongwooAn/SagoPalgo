"""Audit KIND exchange action notices and their displayed versions by publication month."""

import argparse
from collections import Counter
from datetime import date
from pathlib import Path
import re

from .corporate_action_event_audit import body_fields, name_key
from .corporate_action_outcome_census import kospi_halt_dates
from .corporate_action_outcomes import KST, SCOPE, VIEWER, capture, checked_read, require
from .dataset import digest, read_bytes, read_json
from .historical_market_action_expansion import build as build_expansion, extra_fields
from .kind_membership_evidence import html
from .krx_baseline_validation import immutable_json
from .market_calendar_evidence import text
from .models import ResearchError, utc
from .session_notice_inventory import body_path, viewer_documents


SCHEMA = "SAGOPALGO_H05_MARKET_ACTION_MONTHLY_V1"
PREFERRED_ONLY = r"(?:[0-9]+)?우선주(?:식|[A-Z])?"
MIXED_HALT_TARGET = re.compile(rf"1\.\s*대상종목 .+? (보통주(?:식)?\s*[,·]\s*{PREFERRED_ONLY}) 2\.")
PERIOD_CHANGE = re.compile(
    r"1\.\s*대상종목 (.+?) 보통주(?:식)? 2\.\s*변경사유 (.+?) "
    r"3\.\s*정지기간 가\.\s*변경전 (.+?) 나\.\s*변경후 (.+?) 4\.\s*근거규정"
)
KOSDAQ_TARGET = re.compile(r"1\.\s*대상종목 (.+?) 보통주(?:식)? 2\.")
KOSPI_RIGHTS_TARGET = re.compile(r"1\. 회사명 (.+?) 2\. (?:주식의 종류|주권종류)와 가격")
KOSPI_BOUNDARIES = {
    "halt": r"매매거래정지\s*(?:일시|일)",
    "reopening": r"매매거래정지\s*해제\s*(?:일시|일)",
}
ACTION_HEADINGS = {
    "HALT": r"주권매매거래정지\s+(?=1\.\s*대상종목)",
    "REOPENING": r"주권매매거래정지해제\s+(?=1\.\s*대상종목)",
    "HALT_BOUNDARY_REVIEW": r"주권매매거래정지 기간변경\s+(?=1\.\s*대상종목)",
}
REASONS = {
    "NOTICE_VIEWER_NOT_CAPTURED": "VIEWER_RESPONSE_UNAVAILABLE",
    "NOTICE_VIEWER_LAYOUT_UNCONFIRMED": "VIEWER_DOCUMENT_SELECTOR_UNVERIFIED",
    "NOTICE_ROUTE_NOT_CAPTURED": "BODY_ROUTE_RESPONSE_UNAVAILABLE",
    "NOTICE_BODY_ROUTE_UNCONFIRMED": "DOCUMENT_ROUTE_UNVERIFIED",
    "NOTICE_BODY_NOT_CAPTURED": "BODY_RESPONSE_UNAVAILABLE",
    "HALT_TIMES_SHARE_CLASS_UNCONFIRMED": "BODY_DOES_NOT_IDENTIFY_COMMON_SHARES",
    "HALT_DATES_SHARE_CLASS_UNCONFIRMED": "BODY_DOES_NOT_IDENTIFY_COMMON_SHARES",
    "HALT_PERIOD_CHANGE_FIELDS": "SEPARATE_CHANGE_EFFECTIVE_TIME_NOT_ESTABLISHED",
    "APPLIED_DATE_OUTSIDE_SCOPE": "PUBLISHED_APPLICATION_DATE_OUTSIDE_FIXED_SCOPE",
}


def kospi_boundary(form, body):
    if form not in {"68054.htm", "68060.htm", "99807.htm", "99808.htm", "99810.htm"}:
        return None
    headings = list(re.finditer(r"1\.\s*종목명 ", body))
    if len(headings) == 1:
        body = body[headings[0].start():]
    fields = kospi_halt_dates(form, body, SCOPE[:2]) or {}
    for key, label in KOSPI_BOUNDARIES.items():
        matches = re.findall(
            rf"{label}\s+(\d{{4}})[년-]\s*(\d{{2}})[월-]\s*(\d{{2}})일?"
            r"(?:\s+(\d{2}:\d{2}|-)|(?=\s+부터))",
            body)
        if len(matches) != 1:
            continue
        year, month, day, clock = matches[0]
        applied = date(int(year), int(month), int(day)).isoformat()
        fields[key + "Date"] = applied
        if clock and clock != "-":
            fields[key + "TimeKst"] = utc(f"{applied}T{clock}:00+09:00").astimezone(KST).isoformat()
    if fields:
        status = ("HALT_TIMES_SHARE_CLASS_UNCONFIRMED" if any(key.endswith("TimeKst") for key in fields)
                  else "HALT_DATES_SHARE_CLASS_UNCONFIRMED")
        boundaries = [value for key, value in fields.items() if key.endswith("Date")]
        if all(not SCOPE[0] <= value <= SCOPE[1] for value in boundaries):
            status = "APPLIED_DATE_OUTSIDE_SCOPE"
        target = re.findall(r"1\.\s*종목명 (.+?) 2\.", body)
        remarks = re.findall(r"7\. 기타 투자판단과 관련한 중요사항 (.+?) ※ 관련공시", body)
        if len(target) == 1:
            fields["publishedTarget"] = target[0]
        if len(remarks) == 1:
            fields["remarksDisplay"] = remarks[0]
        return {**fields, "status": status, "reason": REASONS[status]}
    return None


def market_dividend_notice(form, body):
    if form not in {"99329.htm", "99342.htm"}:
        return None
    dates = re.findall(r"\d\. 적용일\s*:\s*(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})", body)
    if len(dates) != 1:
        return None
    applied = date(*map(int, dates[0])).isoformat()
    fields = {"appliedDate": applied}
    match = re.search(r"배당락 종목\(\d+개사 (\d+)종목\) - (.+?) 2\. 기준가격", body)
    if match:
        total, names = match.groups()
        targets = [name.strip() for name in names.split(",")]
        if len(set(targets)) == int(total) == len(targets) and all(targets):
            fields["publishedTargets"] = targets
    status = "MARKET_DIVIDEND_LIST_VERIFIED" if "publishedTargets" in fields else "MARKET_DIVIDEND_DATE_ONLY"
    reason = ("LIST_HAS_NO_SECURITY_CODES_OR_SHARE_CLASSES" if "publishedTargets" in fields
              else "FULL_SECURITY_LIST_NOT_IN_BODY")
    if not SCOPE[0] <= applied <= SCOPE[1]:
        status, reason = "APPLIED_DATE_OUTSIDE_SCOPE", REASONS["APPLIED_DATE_OUTSIDE_SCOPE"]
    return fields | {"status": status, "reason": reason}


def review_body(notice, header, form, body):
    market, role = notice["market"], notice["role"]
    # Corrected documents can put the comparison table ahead of the action form.
    heading = ACTION_HEADINGS.get(role)
    headings = list(re.finditer(heading, body)) if heading else []
    if len(headings) == 1:
        body = body[headings[0].end():]
    if (market, role) == ("KOSPI", "DIVIDEND_OR_COMBINED"):
        market_notice = market_dividend_notice(form, body)
        if market_notice:
            return market_notice
    if header is None:
        return {"status": "BODY_SCOPE_OR_FIELDS_UNCONFIRMED", "reason": "VIEWER_ISSUER_OR_SYMBOL_MISSING"}
    issuer, symbol = header
    aliases = [issuer]
    aliases.extend(member["name"] for member in notice["membership"]["candidates"]
                   if member["symbol"] == symbol)
    alias_keys = {name_key(name) for name in aliases}
    mixed = MIXED_HALT_TARGET.search(body) if market == "KOSDAQ" and role in ACTION_HEADINGS else None
    published_classes = {"publishedShareClasses": mixed[1]} if mixed else {}
    if mixed:
        body = body[:mixed.start(1)] + "보통주" + body[mixed.end(1):]
    expiry = re.search(r"나\.\s*만료일시 (.+?) 4\.\s*근거규정", body) if form == "70797.htm" else None
    cause = re.search(r"2\.\s*(?:정지|해제)사유 (.+?) 3\.", body) if form in {"70797.htm", "70799.htm"} else None
    same_layout = {("KOSPI", "99335.htm"): "99311.htm", ("KOSDAQ", "73100.htm"): "70767.htm"}
    rights_form = same_layout.get((market, form), form)
    fields = next((result for name in dict.fromkeys(aliases)
                   if (result := body_fields(market, role, rights_form, body, name, symbol)
                       or extra_fields(market, role, form, body, name, symbol))), None)
    if fields and "appliedDate" in fields:
        status = ("EXCHANGE_NOTICE_FIELDS_VERIFIED" if SCOPE[0] <= fields["appliedDate"] <= SCOPE[1]
                  else "APPLIED_DATE_OUTSIDE_SCOPE")
        result = {**fields, **published_classes, "status": status, "symbol": symbol, "shareClass": "COMMON",
                  "reason": REASONS.get(status)}
        if expiry:
            result["expiryDisplay"] = expiry[1]
        if cause:
            result["publishedCause"] = cause[1]
        return result
    if market == "KOSPI" and role in ACTION_HEADINGS:
        boundary = kospi_boundary(form, body)
        if boundary:
            return boundary
        if all(re.search(label + r"\s+-\s+-", body) for label in KOSPI_BOUNDARIES.values()):
            return {"status": "BODY_SCOPE_OR_FIELDS_UNCONFIRMED",
                    "reason": "NO_HALT_OR_REOPENING_DATE_IN_BODY"}
    if market == "KOSDAQ" and role == "HALT_BOUNDARY_REVIEW" and form == "70798.htm":
        periods = PERIOD_CHANGE.findall(body)
        if len(periods) == 1:
            target, cause, before, after = periods[0]
            status = "HALT_PERIOD_CHANGE_FIELDS"
            result = {**published_classes, "status": status, "publishedIssuer": target, "shareClass": "COMMON",
                      "publishedCause": cause, "previousDurationDisplay": before,
                      "updatedDurationDisplay": after, "reason": REASONS[status]}
            if name_key(target) in alias_keys:
                result["symbol"] = symbol
            else:
                result["viewerSymbol"] = symbol
                result["identityReason"] = "HISTORICAL_BODY_NAME_DIFFERS_FROM_VIEWER"
            return result
    if market == "KOSDAQ" and (role, form) in {("HALT", "70797.htm"), ("REOPENING", "70799.htm")}:
        target = re.search(rf"1\.\s*대상종목 (.+?) (KDR|{PREFERRED_ONLY}) 2\.", body)
        dates = re.findall(r"(?:정지|해제)일시 (\d{4}-\d{2}-\d{2}) (?:\d{2}:\d{2}:\d{2}|-)", body)
        if target and len(dates) == 1:
            status = "NON_COMMON_SECURITY_ONLY" if target[2] == "KDR" else "PREFERRED_SHARES_ONLY"
            return {"status": status, "publishedIssuer": target[1], "publishedShareClasses": target[2],
                    "appliedDate": dates[0], "reason": "OUTSIDE_COMMON_SHARE_SCOPE"}
    if market == "KOSPI" and role in {"RIGHTS", "DIVIDEND_OR_COMBINED"}:
        preferred = re.search(
            r"1\. 회사명 (.+?) 2\. (?:주식의 종류|주권종류)와 가격 주권종류 기준가격\(원\) (.+?) "
            r"3\. 사유 .+? 4\. 적용일 (\d{4}-\d{2}-\d{2})", body)
        if preferred and name_key(preferred[1]) in alias_keys:
            if re.fullmatch(rf"{PREFERRED_ONLY}\s+[\d,]+", preferred[2]):
                return {"status": "PREFERRED_SHARES_ONLY", "shareClass": "PREFERRED",
                        "appliedDate": preferred[3], "reason": "OUTSIDE_COMMON_SHARE_SCOPE"}
            other = re.fullmatch(r"(종류주식\d*)\s+[\d,]+", preferred[2])
            if other:
                return {"status": "NON_COMMON_SECURITY_ONLY", "publishedShareClasses": other[1],
                        "appliedDate": preferred[3], "reason": "OUTSIDE_COMMON_SHARE_SCOPE"}
    if market == "KOSDAQ" and rights_form in {"70766.htm", "70767.htm"}:
        coded_targets = re.findall(rf"6\. 사유 (.+?) 보통주식 A{symbol} ", body)
        if len(coded_targets) == 1:
            published = body_fields(market, role, rights_form, body, coded_targets[0], symbol)
            if published:
                status = ("EXCHANGE_NOTICE_FIELDS_VERIFIED" if SCOPE[0] <= published["appliedDate"] <= SCOPE[1]
                          else "APPLIED_DATE_OUTSIDE_SCOPE")
                return {**published, "status": status, "publishedIssuer": coded_targets[0],
                        "symbol": symbol, "shareClass": "COMMON", "reason": REASONS.get(status)}
        other = re.fullmatch(rf".+?6\. 사유 (.+?) DR A{symbol} [\d,]+ (\d{{4}}-\d{{2}}-\d{{2}}) .+", body)
        if other:
            return {"status": "NON_COMMON_SECURITY_ONLY", "publishedIssuer": other[1],
                    "publishedShareClasses": "DR", "appliedDate": other[2], "reason": "OUTSIDE_COMMON_SHARE_SCOPE"}
    target_pattern = KOSDAQ_TARGET if market == "KOSDAQ" else KOSPI_RIGHTS_TARGET
    targets = target_pattern.findall(body)
    if len(targets) == 1 and name_key(targets[0]) not in alias_keys:
        published = body_fields(market, role, rights_form, body, targets[0], symbol)
        if published:
            result = {**published, **published_classes, "status": "BODY_TARGET_IDENTITY_UNCONFIRMED",
                      "publishedIssuer": targets[0], "shareClass": "COMMON", "viewerSymbol": symbol,
                      "reason": "HISTORICAL_BODY_NAME_DIFFERS_FROM_VIEWER"}
            if expiry:
                result["expiryDisplay"] = expiry[1]
            if cause:
                result["publishedCause"] = cause[1]
            return result
    return {"status": "BODY_SCOPE_OR_FIELDS_UNCONFIRMED",
            "reason": "BODY_FORM_TARGET_OR_APPLICATION_FIELDS_UNVERIFIED"}


def compare_pair(original, corrected):
    old, new = original["review"], corrected["review"]
    fields = ("symbol", "shareClass", "appliedDate", "noticeTimeKst", "haltDate", "reopeningDate",
              "haltTimeKst", "reopeningTimeKst", "previousDurationDisplay", "updatedDurationDisplay",
              "referencePriceKrw", "publishedCause", "expiryDisplay", "publishedTarget", "remarksDisplay",
              "publishedShareClasses")
    return {"original": original["document"], "corrected": corrected["document"],
            "bodyTextChanged": original["contentSha256"] != corrected["contentSha256"],
            "verifiedFieldChanges": {field: {"before": old[field], "after": new[field]}
                                     for field in fields if field in old and field in new
                                     and old[field] != new[field]},
            "unavailableFields": [field for field in fields if (field in old) != (field in new)]}


def compare_versions(versions):
    if len(versions) == 1:
        return {"status": "CORRECTION_ORIGINAL_UNAVAILABLE"}
    if any("contentSha256" not in version for version in versions):
        return {"status": "VERSION_BODY_UNAVAILABLE"}
    originals = [version for version in versions if not version["correctionMarked"]]
    if len(originals) == 1:
        comparisons = [compare_pair(originals[0], corrected) for corrected in versions if corrected["correctionMarked"]]
        if len(comparisons) == 1:
            return {"status": "ORIGINAL_CORRECTION_PAIR_COMPARED", **comparisons[0]}
        return {"status": "DISPLAYED_VERSIONS_CAPTURED_REVISION_ORDER_UNVERIFIED",
                "comparisonsWithOriginal": comparisons}
    return {"status": "DISPLAYED_VERSIONS_CAPTURED_REVISION_ORDER_UNVERIFIED"}


def review_month(manifest, artifacts, job):
    raw = read_bytes(manifest)
    spec = read_json(raw)
    report = build_expansion(manifest, artifacts, job)
    version_pins = spec["versionReceipts"]
    used = set()
    at = utc(report["knownAt"])

    def read_version(stage, document, request):
        key = f"proof-v{stage}-{document}"
        if key not in version_pins:
            return None, None
        used.add(key)
        return capture(job, version_pins, key, request, at)

    for notice in report["notices"]:
        receipt = notice["receipt"]
        viewer_url = VIEWER + f"?acptno={receipt}&method=search"
        notice["viewerUrl"] = viewer_url
        status = notice["status"]
        if len(notice["evidence"]) < 3 and status != "NOTICE_VERSION_REVIEW":
            notice["reason"] = REASONS[status]
            continue
        folder = job / "captures"
        viewer = checked_read(folder / f"proof-viewer-{receipt}" / "raw.bin",
                              notice["evidence"][0]["bodySha256"])
        headlines = [node.text() for node in html(viewer).walk("h1")]
        match = re.fullmatch(r"(.+) \(([0-9A-Z]{6})\)", headlines[0]) if len(headlines) == 1 else None
        header = match.groups() if match else None
        if status != "NOTICE_VERSION_REVIEW":
            body = notice["evidence"][-1]
            document = checked_read(folder / f"proof-body-{receipt}" / "raw.bin", body["bodySha256"])
            review = review_body(notice, header, body["sourceUrl"].rsplit("/", 1)[-1], text(document))
            if status in {"BODY_SCOPE_OR_FIELDS_UNCONFIRMED", "HALT_PERIOD_CHANGE_FIELDS",
                          "HALT_DATES_SHARE_CLASS_UNCONFIRMED", "HALT_TIMES_SHARE_CLASS_UNCONFIRMED"}:
                notice.update(review)
            else:
                notice["reason"] = REASONS.get(status)
                for field in ("expiryDisplay", "publishedCause"):
                    if field in review:
                        notice[field] = review[field]
            continue

        versions = []
        for version in viewer_documents(viewer):
            document = version["document"]
            route, route_proof = read_version("route", document, {
                "url": VIEWER, "method": "POST", "parameters": {"method": "searchContents", "docNo": document}})
            item = version | {"evidence": [route_proof] if route_proof else [], "reason": "VERSION_ROUTE_UNAVAILABLE"}
            versions.append(item)
            if route is None:
                continue
            try:
                url = body_path(route, document)
            except ResearchError:
                item["reason"] = "VERSION_ROUTE_UNVERIFIED"
                continue
            body, body_proof = read_version("body", document, {"url": url, "method": "GET", "parameters": None})
            if body is None:
                item["reason"] = "VERSION_BODY_UNAVAILABLE"
                continue
            normalized = text(body)
            item.update(contentSha256=digest(normalized.encode()), reason=None,
                        review=review_body(notice, header, url.rsplit("/", 1)[-1], normalized))
            item["evidence"].append(body_proof)
        revision = compare_versions(versions)
        notice.update(versions=versions, revision=revision, status=revision["status"])
    require(used == set(version_pins), "MONTHLY_VERSION_CAPTURE_SCOPE")
    report.update(schemaVersion=SCHEMA, manifestSha256=digest(raw),
                  statusCounts=dict(Counter(notice["status"] for notice in report["notices"])))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "audit"))
    for name in ("manifest", "artifacts", "job"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = review_month(args.manifest, args.artifacts, args.job)
    output = args.report or args.job / "monthly-review.json"
    immutable_json(output, report, require_existing=args.action == "audit")
    print(report["publicationWindow"], report["candidateCount"], report["statusCounts"])


if __name__ == "__main__":
    main()
