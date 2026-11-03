"""Small, explicitly scoped KIND case studies, never a complete market universe."""
from pathlib import Path
from decimal import Decimal
from typing import Literal
import re
from urllib import request

from pydantic import Field, ValidationError, model_validator

from .dataset import canonical, digest, read_bytes, read_json
from .distribution_facts import Node, XForms
from .history import NoRedirect, atomic_json, day, now
from .models import ResearchError, StrictModel, utc
from .reference import ReferencePack, combine, references_as_of
from .session_evidence import LIMIT, validate_url

LAYOUTS = {"IPO": ("70760", "신규상장"), "DELISTING": ("70769", "상장폐지"),
           "SPLIT": ("70764", "변경상장(액면변경)"), "SUSPENSION": ("70797", "주권매매거래정지"),
           "RESUMPTION": ("70799", "주권매매거래정지해제")}


class Case(StrictModel):
    caseId: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,80}$")
    stockCode: str = Field(pattern=r"^[0-9]{6}$")
    issuerName: str = Field(min_length=1, max_length=100)
    market: Literal["KOSDAQ"]
    kind: Literal["IPO", "DELISTING", "SPLIT", "SUSPENSION", "RESUMPTION"]
    url: str

    @model_validator(mode="after")
    def source(self):
        validate_url(self.url)
        if not self.url.endswith("/" + LAYOUTS[self.kind][0] + ".htm"):
            raise ValueError("case kind and reviewed KIND form must agree")
        return self


class CaseScope(StrictModel):
    schemaVersion: Literal["SAGOPALGO_KIND_CASE_SCOPE_V1"]
    startDate: str
    endDate: str
    purpose: Literal["PERSONAL_LOCAL_REFERENCE_RESEARCH"]
    cases: list[Case] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def bounds(self):
        if day(self.startDate) > day(self.endDate):
            raise ValueError("scope reversed")
        if any(len(set(values)) != len(values) for values in [
                [v.caseId for v in self.cases], [v.url for v in self.cases],
                [(v.stockCode, v.kind) for v in self.cases]]):
            raise ValueError("duplicate case, source or stock/kind")
        identities = {}
        for case in self.cases:
            if case.stockCode in identities and identities[case.stockCode] != case.issuerName:
                raise ValueError("conflicting reviewed issuer mapping")
            identities[case.stockCode] = case.issuerName
        return self


def load_scope(path):
    return CaseScope.model_validate(read_json(read_bytes(path)))


def compact(value):
    return re.sub(r"\s+", "", value)


def document_rows(raw, case):
    if len(raw) > LIMIT:
        raise ResearchError("KIND_CASE_RESPONSE_LIMIT")
    # These five reviewed forms declare UTF-8. Do not guess encodings or fetch DTD/scripts.
    value = raw.decode("utf-8-sig")
    value = re.sub(r'\A\s*<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1\.0 Transitional//EN" '
                   r'"http://www\.w3\.org/TR/xhtml1/DTD/xhtml1-transitional\.dtd">', "", value, count=1)
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)", value, re.I):
        raise ResearchError("KIND_CASE_DECLARATION_UNSUPPORTED")
    parser = XForms()
    parser.feed(value)
    parser.close()
    if len(parser.stack) != 1 or len(list(parser.root.walk("html"))) != 1:
        raise ResearchError("KIND_CASE_HTML_INVALID")
    titles = [v.text() for v in parser.root.walk("a") if v.attrs.get("name") == "#2"]
    if titles != [LAYOUTS[case.kind][1]]:
        raise ResearchError("KIND_CASE_TITLE_MISMATCH")
    if "정정신고" in compact(parser.root.text()) or "정정공시" in compact(parser.root.text()):
        raise ResearchError("KIND_CASE_CORRECTION_UNSUPPORTED")
    tables = []
    for table in parser.root.walk("table"):
        rows = [[v.text() for v in tr.children if isinstance(v, Node) and v.tag in {"td", "th"}]
                for tr in table.walk("tr")]
        if rows and rows[0] and compact(rows[0][0]) in {"1.회사명", "1.대상종목"}:
            if list(table.walk("table")) or len(rows) > 1000:
                raise ResearchError("KIND_CASE_TABLE_UNSUPPORTED")
            tables.append(rows)
    if len(tables) != 1:
        raise ResearchError("KIND_CASE_TABLE_AMBIGUOUS")
    rows = tables[0]
    name = rows[0][-1] if case.kind == "IPO" else rows[0][1]
    if compact(name) != compact(case.issuerName):
        raise ResearchError("KIND_CASE_ISSUER_MISMATCH")
    codes = re.findall(r"(?<![A-Za-z0-9])A([0-9]{6})(?![A-Za-z0-9])", " ".join(" ".join(row) for row in rows))
    if case.kind in {"IPO", "DELISTING", "SPLIT"}:
        if codes != [case.stockCode]:
            raise ResearchError("KIND_CASE_CODE_MISMATCH")
        stock_rows = [row for row in rows if "A" + case.stockCode in row]
        if len(stock_rows) != 1 or stock_rows[0][0] != "보통주":
            raise ResearchError("KIND_CASE_SHARE_CLASS_UNSUPPORTED")
    elif codes or rows[0][-1] != "보통주":
        raise ResearchError("KIND_CASE_SHARE_CLASS_UNSUPPORTED")
    if case.kind in {"SUSPENSION", "RESUMPTION"} and not any("코스닥시장" in " ".join(row) for row in rows):
        raise ResearchError("KIND_CASE_MARKET_MISMATCH")
    return rows


def one_row(rows, label):
    values = [row for row in rows if row and compact(row[0]) == compact(label)]
    if len(values) != 1:
        raise ResearchError("KIND_CASE_FIELD_AMBIGUOUS")
    return values[0]


def iso_date(value):
    if re.fullmatch(r"[0-9]{4}년 [0-9]{2}월 [0-9]{2}일", value):
        value = value.replace("년 ", "-").replace("월 ", "-").replace("일", "")
    day(value)
    return value


def scalar_date(rows, label):
    row = one_row(rows, label)
    if len(row) != 2:
        raise ResearchError("KIND_CASE_DATE_AMBIGUOUS")
    return iso_date(row[1])


def case_fact(raw, case, captured_at):
    utc(captured_at)
    rows = document_rows(raw, case)
    details = {}
    if case.kind == "IPO":
        date = scalar_date(rows, "10.상장일(매매개시일)")
        basis = "FIRST_LISTING_DATE"
    elif case.kind == "DELISTING":
        date = scalar_date(rows, "7.상장폐지일")
        basis = "DELISTING_DATE"
        details["originalListingDate"] = iso_date(next(row for row in rows if "A" + case.stockCode in row)[-1])
    elif case.kind == "SPLIT":
        if one_row(rows, "3.변경상장사유")[1:] != ["액면분할"]:
            raise ResearchError("KIND_CASE_SPLIT_REASON_UNSUPPORTED")
        row = one_row(rows, "4.액면변경내역")
        if len(row) != 5 or compact(row[1]) != "변경전액면가(원)" or compact(row[3]) != "변경후액면가(원)":
            raise ResearchError("KIND_CASE_SPLIT_FIELDS_INVALID")
        if any(not re.fullmatch(r"(?:[1-9][0-9]{0,8}|[1-9][0-9]{0,2}(?:,[0-9]{3}){1,2})", v) for v in [row[2], row[4]]):
            raise ResearchError("KIND_CASE_SPLIT_VALUES_INVALID")
        before, after = (Decimal(v.replace(",", "")) for v in [row[2], row[4]])
        if before <= after or before % after:
            raise ResearchError("KIND_CASE_SPLIT_RATIO_UNSUPPORTED")
        details.update(faceValueBefore=str(before), faceValueAfter=str(after), ratio=str(before / after))
        date = scalar_date(rows, "6.상장일")
        basis = "CHANGED_LISTING_DATE_NOT_LEGAL_EFFECTIVE_DATE"
    elif case.kind == "SUSPENSION":
        row = one_row(rows, "3.정지기간")
        if len(row) != 4 or compact(row[1]) != "가.정지일시" or row[-1] != "-":
            raise ResearchError("KIND_CASE_INTRADAY_SUSPENSION_UNSUPPORTED")
        date = iso_date(row[2])
        details["endCondition"] = " ".join(one_row(rows, "나.만료일시")[1:])
        basis = "SUSPENSION_START_DATE"
    else:
        row = one_row(rows, "3.해제일시")
        if len(row) != 3 or row[-1] != "-":
            raise ResearchError("KIND_CASE_INTRADAY_RESUMPTION_UNSUPPORTED")
        date = iso_date(row[1])
        basis = "RESUMPTION_DATE"
    return {"caseId": case.caseId, "stockCode": case.stockCode, "issuerName": case.issuerName,
            "market": case.market, "kind": case.kind, "date": date, "dateBasis": basis,
            "knownAt": captured_at, "knowledgeBasis": "FETCH_TIME_ONLY", "precision": "DATE_ONLY",
            "identityBasis": "SOURCE_CODE" if case.kind in {"IPO", "DELISTING", "SPLIT"} else "REVIEWED_ISSUER_MAPPING",
            "sourceUrl": case.url, "sourceSha256": digest(raw), "details": details}


def reference_pack(facts):
    observed = max((v["knownAt"] for v in facts), key=utc)
    pack = {"schemaVersion": "SAGOPALGO_MARKET_REFERENCE_V1", "provider": "KRX_KIND_CASE_STUDIES",
            "provenance": "PROVIDER_OBSERVATIONS", "reference": "Selected common-share cases; FETCH_TIME_ONLY; incomplete market coverage",
            "observedAt": observed, "calendar": [], "sessions": [], "listings": [], "actions": [], "coverage": []}
    for fact in facts:
        base = {"eventId": "kind-case:" + fact["caseId"], "stockCode": fact["stockCode"], "effectiveDate": fact["date"],
                "knownAt": fact["knownAt"], "evidence": fact["sourceUrl"] + "; raw-sha256:" + fact["sourceSha256"]
                + "; " + fact["dateBasis"] + "; knowledge=FETCH_TIME_ONLY"}
        if fact["kind"] in {"IPO", "DELISTING"}:
            pack["listings"].append({**base, "eligible": fact["kind"] == "IPO"})
        else:
            pack["actions"].append({**base, "kind": "OTHER" if fact["kind"] == "RESUMPTION" else fact["kind"],
                                    "ratio": fact["details"].get("ratio")})
    return ReferencePack.model_validate(pack)


def build_report(scope, cache):
    facts, missing = [], []
    for case in scope.cases:
        folder = cache / digest(case.url.encode())
        if not folder.exists():
            missing.append(case.caseId)
            continue
        receipt = audit_source(folder, case.url)
        fact = case_fact(read_bytes(folder / "body.html"), case, receipt["capturedAt"])
        if not scope.startDate <= fact["date"] <= scope.endDate:
            raise ResearchError("KIND_CASE_OUTSIDE_SCOPE")
        facts.append(fact)
    # Date-only stop/restart references require another source in this exact scope to verify their code.
    for fact in facts:
        if fact["identityBasis"] == "REVIEWED_ISSUER_MAPPING" and not any(
                other["identityBasis"] == "SOURCE_CODE" and other["stockCode"] == fact["stockCode"]
                and other["issuerName"] == fact["issuerName"] for other in facts):
            raise ResearchError("KIND_CASE_CODE_ANCHOR_MISSING")
    pack = reference_pack(facts) if facts else None
    if pack:
        combine([pack])
    return {"schemaVersion": "SAGOPALGO_KIND_CASE_REPORT_V1", "scopeSha256": digest(canonical(scope.model_dump(mode="json"))),
            "startDate": scope.startDate, "endDate": scope.endDate, "targetCaseCount": len(scope.cases),
            "verifiedCaseCount": len(facts), "missingCaseIds": missing,
            "verifiedCompanyCount": len({v["stockCode"] for v in facts}), "verifiedKinds": sorted({v["kind"] for v in facts}),
            "verifiedMarkets": sorted({v["market"] for v in facts}), "caseStudyComplete": not missing,
            "marketUniverseComplete": False, "corporateActionsComplete": False, "calendarComplete": False,
            "usableForTraining": False, "usableForTrading": False, "priceAdjustmentApplied": False,
            "facts": facts, "referencePack": pack.model_dump(mode="json") if pack else None}


def audit_report(scope, cache, path):
    report = build_report(scope, cache)
    if read_bytes(path) != canonical(report):
        raise ResearchError("KIND_CASE_REPORT_TAMPERED")
    return report


def as_of(report, stock, at, business_date):
    instant = utc(at)
    day(business_date)
    if not re.fullmatch(r"[0-9]{6}", stock) or not report["startDate"] <= business_date <= report["endDate"]:
        raise ResearchError("KIND_CASE_QUERY_OUTSIDE_SCOPE")
    pack = ReferencePack.model_validate(report["referencePack"]) if report["referencePack"] else None
    visible = [v for v in report["facts"] if v["stockCode"] == stock and utc(v["knownAt"]) <= instant]
    restrictions = [v for v in visible if v["kind"] in {"SUSPENSION", "RESUMPTION"} and v["date"] <= business_date]
    latest = max((v["date"] for v in restrictions), default=None)
    selected = [v for v in restrictions if v["date"] == latest]
    if len(selected) > 1:
        raise ResearchError("KIND_CASE_RESTRICTION_AMBIGUOUS")
    return {"stockCode": stock, "asOf": at, "businessDate": business_date,
            **references_as_of([pack] if pack else [], stock, instant, business_date, "KOSDAQ"),
            "visibleFacts": visible,
            "lastAnnouncedRestriction": selected[0] if selected else None,
            "actualTradabilityConfirmed": False, "usableForTrading": False, "priceAdjustmentApplied": False}


def main(argv=None):
    import argparse
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ["capture", "build", "audit", "as-of"]:
        p = sub.add_parser(command)
        p.add_argument("--scope", type=Path, required=True)
        p.add_argument("--cache", type=Path, required=True)
        if command == "capture":
            p.add_argument("--max-new-requests", type=int, default=1, choices=range(0, 17))
        else:
            p.add_argument("--report", type=Path, required=True)
        if command == "as-of":
            p.add_argument("--stock", required=True)
            p.add_argument("--at", required=True)
            p.add_argument("--date", required=True)
    args = parser.parse_args(argv)
    try:
        scope = load_scope(args.scope)
        if args.command == "capture":
            needed = sum(not (args.cache / digest(case.url.encode())).exists() for case in scope.cases)
            if needed > args.max_new_requests:
                raise ResearchError("KIND_CASE_REQUEST_BUDGET_EXCEEDED")
            # Audit every existing reservation before starting any new request.
            for case in scope.cases:
                folder = args.cache / digest(case.url.encode())
                if folder.exists():
                    audit_source(folder, case.url)
            reused = sum(capture_source(case.url, args.cache)[2] for case in scope.cases)
            result = {"capturedSources": len(scope.cases) - reused, "reusedSources": reused}
        elif args.command == "build":
            result = build_report(scope, args.cache)
            if args.report.exists():
                audit_report(scope, args.cache, args.report)
            else:
                args.report.parent.mkdir(parents=True, exist_ok=True)
                atomic_json(args.report, result)
        else:
            result = audit_report(scope, args.cache, args.report)
            if args.command == "as-of":
                result = as_of(result, args.stock, args.at, args.date)
        if args.command in {"build", "audit"}:
            result = {key: value for key, value in result.items() if key not in {"facts", "referencePack"}}
        print(json.dumps(result, ensure_ascii=True, sort_keys=True))
        return 0
    except (ResearchError, ValueError, ValidationError, OSError):
        # Input, transport and filesystem details may contain private local paths or response data.
        import sys
        error = sys.exc_info()[1]
        print(json.dumps({"diagnostic": str(error) if isinstance(error, ResearchError) else "KIND_CASE_INVALID_INPUT"}))
        return 2


def capture_source(url, cache, opener=None):
    validate_url(url)
    folder = cache / digest(url.encode())
    folder.parent.mkdir(parents=True, exist_ok=True)
    try:
        folder.mkdir()
    except FileExistsError:
        return audit_source(folder, url), folder, True
    receipt = {"schemaVersion": "SAGOPALGO_KIND_CASE_CAPTURE_V1", "url": url,
               "status": "IN_FLIGHT", "startedAt": now(), "maxGetRequests": 1,
               "knowledgeBasis": "FETCH_TIME_ONLY"}
    atomic_json(folder / "receipt.json", receipt)
    try:
        client = opener or request.build_opener(NoRedirect())
        req = request.Request(url, headers={"Accept": "text/html", "User-Agent": "SagoPalgo-local-research/1"}, method="GET")
        with client.open(req, timeout=20) as response:
            raw = response.read(LIMIT + 1)
        if len(raw) > LIMIT:
            raise ResearchError("KIND_CASE_RESPONSE_LIMIT")
        (folder / "body.html").write_bytes(raw)
        receipt.update(status="COMPLETE", bodySha256=digest(raw), capturedAt=now())
        atomic_json(folder / "receipt.json", receipt)
        return receipt, folder, False
    except Exception as exc:
        code = str(exc) if isinstance(exc, ResearchError) else "KIND_CASE_CAPTURE_FAILED"
        receipt.update(status="FAILED", diagnostic=code, finishedAt=now())
        atomic_json(folder / "receipt.json", receipt)
        raise ResearchError(code) from None


def audit_source(folder, url):
    validate_url(url)
    receipt = read_json(read_bytes(folder / "receipt.json")) if (folder / "receipt.json").is_file() else {}
    if not isinstance(receipt, dict) or receipt.get("status") != "COMPLETE":
        raise ResearchError("KIND_CASE_CAPTURE_RESERVED")
    if (set(receipt) != {"schemaVersion", "url", "status", "startedAt", "maxGetRequests", "knowledgeBasis", "bodySha256", "capturedAt"}
            or receipt["schemaVersion"] != "SAGOPALGO_KIND_CASE_CAPTURE_V1" or receipt["url"] != url
            or type(receipt["maxGetRequests"]) is not int or receipt["maxGetRequests"] != 1
            or receipt["knowledgeBasis"] != "FETCH_TIME_ONLY"
            or utc(receipt["startedAt"]) > utc(receipt["capturedAt"])):
        raise ResearchError("KIND_CASE_CACHE_TAMPERED")
    raw = read_bytes(folder / "body.html")
    if len(raw) > LIMIT or digest(raw) != receipt["bodySha256"]:
        raise ResearchError("KIND_CASE_CACHE_TAMPERED")
    return receipt


if __name__ == "__main__":
    raise SystemExit(main())
