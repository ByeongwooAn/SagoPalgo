"""Venue-specific historical evidence; a market transfer is not a global delisting."""
import argparse
import json
import re
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from .dataset import canonical, digest, read_bytes, read_json
from .distribution_facts import Node, parse_html
from .history import atomic_json, day
from .kind_cases import Case, audit_source, capture_source, compact, document_rows, one_row, scalar_date
from .models import ResearchError, StrictModel, utc
from .session_evidence import validate_url


class Transfer(StrictModel):
    caseId: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,80}$")
    stockCode: str = Field(pattern=r"^[0-9]{6}$")
    sourceIssuerName: str = Field(min_length=1, max_length=100)
    destinationIssuerName: str = Field(min_length=1, max_length=100)
    fromMarket: Literal["KOSDAQ"]
    toMarket: Literal["KOSPI"]
    exitUrl: str
    entryUrl: str

    @model_validator(mode="after")
    def sources(self):
        for url, form in [(self.exitUrl, "70769"), (self.entryUrl, "99343")]:
            validate_url(url)
            if not url.endswith("/" + form + ".htm"):
                raise ValueError("unsupported reviewed transfer source")
        return self


class MergerDelisting(StrictModel):
    caseId: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,80}$")
    stockCode: str = Field(pattern=r"^[0-9]{6}$")
    issuerName: str = Field(min_length=1, max_length=100)
    survivingIssuerName: str = Field(min_length=1, max_length=100)
    market: Literal["KOSDAQ"]
    url: str

    @model_validator(mode="after")
    def source(self):
        validate_url(self.url)
        if not self.url.endswith("/70769.htm"):
            raise ValueError("unsupported reviewed merger source")
        return self


class Scope(StrictModel):
    schemaVersion: Literal["SAGOPALGO_UNIVERSE_EVENT_SCOPE_V1"]
    startDate: str
    endDate: str
    transfers: list[Transfer] = Field(default_factory=list, max_length=8)
    mergerDelistings: list[MergerDelisting] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def bounds(self):
        cases = [*self.transfers, *self.mergerDelistings]
        if day(self.startDate) > day(self.endDate) or not cases:
            raise ValueError("nonempty bounded scope required")
        for values in [[v.caseId for v in cases], [v.stockCode for v in cases], self.urls()]:
            if len(values) != len(set(values)):
                raise ValueError("duplicate case, stock or source")
        return self

    def urls(self):
        return [url for case in self.transfers for url in [case.exitUrl, case.entryUrl]] + [v.url for v in self.mergerDelistings]


def load_scope(path):
    return Scope.model_validate(read_json(read_bytes(path)))


def delisting_case(stock, name, case_id, url):
    case = Case.model_validate({"caseId": case_id, "stockCode": stock, "issuerName": name,
                                "market": "KOSDAQ", "kind": "DELISTING", "url": url})
    return case


def source(cache, url):
    folder = cache / digest(url.encode())
    receipt = audit_source(folder, url)
    return read_bytes(folder / "body.html"), {"url": url, "sha256": receipt["bodySha256"], "knownAt": receipt["capturedAt"]}


def transfer_fact(case, cache):
    raw, old = source(cache, case.exitUrl)
    rows = document_rows(raw, delisting_case(case.stockCode, case.sourceIssuerName, case.caseId, case.exitUrl))
    if one_row(rows, "5.상장폐지사유")[1:] != ["유가증권시장 상장"]:
        raise ResearchError("UNIVERSE_TRANSFER_EXIT_REASON_MISMATCH")
    date = scalar_date(rows, "7.상장폐지일")
    raw, new = source(cache, case.entryUrl)
    root = parse_html(raw)
    titles = [v.text() for v in root.walk("div") if v.attrs.get("class") == "xforms_title"]
    if titles != ["주권 등 신규상장 기준가격 안내 (이전상장)"]:
        raise ResearchError("UNIVERSE_TRANSFER_ENTRY_TITLE_MISMATCH")
    if "정정신고" in compact(root.text()) or "정정공시" in compact(root.text()):
        raise ResearchError("UNIVERSE_TRANSFER_CORRECTION_UNSUPPORTED")
    tables = [v for v in root.walk("table") if v.attrs.get("id") == "XFormD1_Form0_RepeatTable1"]
    if len(tables) != 1 or list(tables[0].walk("table")):
        raise ResearchError("UNIVERSE_TRANSFER_ENTRY_TABLE_AMBIGUOUS")
    rows = [[v.text() for v in tr.children if isinstance(v, Node) and v.tag == "td"] for tr in tables[0].walk("tr")]
    if one_row(rows, "1.회사명")[1:] != [case.destinationIssuerName] or one_row(rows, "3.사유")[1:] != ["이전상장"]:
        raise ResearchError("UNIVERSE_TRANSFER_ENTRY_IDENTITY_MISMATCH")
    coded = [row for row in rows if "A" + case.stockCode in row]
    codes = re.findall(r"(?<![A-Za-z0-9])A([0-9]{6})(?![A-Za-z0-9])", " ".join(" ".join(row) for row in rows))
    if codes != [case.stockCode] or len(coded) != 1 or len(coded[0]) != 3 or coded[0][0] != "보통주식":
        raise ResearchError("UNIVERSE_TRANSFER_ENTRY_CODE_MISMATCH")
    if "유가증권시장업무규정" not in compact(" ".join(one_row(rows, "5.근거규정"))):
        raise ResearchError("UNIVERSE_TRANSFER_ENTRY_MARKET_MISMATCH")
    if date != scalar_date(rows, "4.적용일"):
        raise ResearchError("UNIVERSE_TRANSFER_DATES_CONFLICT")
    return {"caseId": case.caseId, "stockCode": case.stockCode, "issuerName": case.sourceIssuerName,
            "destinationIssuerName": case.destinationIssuerName, "kind": "MARKET_TRANSFER", "date": date,
            "dateBasis": "MATCHED_MARKET_EXIT_AND_ENTRY_APPLICATION_DATE", "fromMarket": case.fromMarket, "toMarket": case.toMarket,
            "knownAt": max([old["knownAt"], new["knownAt"]], key=utc), "sources": [old, new],
            "knowledgeBasis": "FETCH_TIME_ONLY", "precision": "DATE_ONLY"}


def merger_fact(case, cache):
    raw, evidence = source(cache, case.url)
    rows = document_rows(raw, delisting_case(case.stockCode, case.issuerName, case.caseId, case.url))
    if one_row(rows, "5.상장폐지사유")[1:] != ["피흡수합병(스팩소멸합병)"]:
        raise ResearchError("UNIVERSE_MERGER_REASON_MISMATCH")
    description = compact(" ".join(one_row(rows, "9.기타")[1:]))
    if compact(case.survivingIssuerName) not in description or "흡수합병" not in description:
        raise ResearchError("UNIVERSE_MERGER_SURVIVOR_MISMATCH")
    return {"caseId": case.caseId, "stockCode": case.stockCode, "issuerName": case.issuerName,
            "survivingIssuerName": case.survivingIssuerName, "kind": "MERGER_DELISTING", "date": scalar_date(rows, "7.상장폐지일"),
            "dateBasis": "EXCHANGE_DELISTING_DATE_NOT_LEGAL_MERGER_DATE", "fromMarket": case.market, "toMarket": None,
            "knownAt": evidence["knownAt"], "sources": [evidence], "knowledgeBasis": "FETCH_TIME_ONLY", "precision": "DATE_ONLY",
            "legalMergerCompletionConfirmed": False, "survivorListingConfirmed": False, "exchangeRatio": None}


def build_report(scope, cache):
    facts, missing = [], []
    for case, urls, derive in [*[(v, [v.exitUrl, v.entryUrl], transfer_fact) for v in scope.transfers],
                                *[(v, [v.url], merger_fact) for v in scope.mergerDelistings]]:
        if any(not (cache / digest(url.encode())).exists() for url in urls):
            missing.append(case.caseId)
            continue
        fact = derive(case, cache)
        if not scope.startDate <= fact["date"] <= scope.endDate:
            raise ResearchError("UNIVERSE_EVENT_OUTSIDE_SCOPE")
        facts.append(fact)
    events = []
    for fact in facts:
        for market, eligible, role in [(fact["fromMarket"], False, "EXIT"), (fact["toMarket"], True, "ENTRY")]:
            if market is not None:
                events.append({"eventId": fact["caseId"] + ":" + role, "stockCode": fact["stockCode"], "market": market,
                               "eligible": eligible, "effectiveDate": fact["date"], "knownAt": fact["knownAt"], "sourceCaseId": fact["caseId"]})
    return {"schemaVersion": "SAGOPALGO_UNIVERSE_EVENT_REPORT_V1", "scopeSha256": digest(canonical(scope.model_dump(mode="json"))),
            "startDate": scope.startDate, "endDate": scope.endDate, "targetCaseCount": len(scope.transfers) + len(scope.mergerDelistings),
            "verifiedCaseCount": len(facts), "missingCaseIds": missing, "caseStudyComplete": not missing,
            "facts": facts, "venueEvents": events, "marketUniverseComplete": False,
            "usableForTraining": False, "usableForTrading": False, "priceAdjustmentApplied": False}


def audit_report(scope, cache, path):
    report = build_report(scope, cache)
    if read_bytes(path) != canonical(report):
        raise ResearchError("UNIVERSE_EVENT_REPORT_TAMPERED")
    return report


def as_of(report, stock, at, business_date):
    instant = utc(at)
    day(business_date)
    if not re.fullmatch(r"[0-9]{6}", stock) or not report["startDate"] <= business_date <= report["endDate"]:
        raise ResearchError("UNIVERSE_EVENT_QUERY_OUTSIDE_SCOPE")
    selected = []
    for market in ["KOSPI", "KOSDAQ"]:
        values = [v for v in report["venueEvents"] if v["stockCode"] == stock and v["market"] == market
                  and v["effectiveDate"] <= business_date and utc(v["knownAt"]) <= instant]
        latest = max((v["effectiveDate"] for v in values), default=None)
        values = [v for v in values if v["effectiveDate"] == latest]
        if len(values) > 1:
            raise ResearchError("UNIVERSE_EVENT_MEMBERSHIP_AMBIGUOUS")
        selected.extend(values)
    return {"stockCode": stock, "asOf": at, "businessDate": business_date, "venueMembership": selected,
            "allMarketsMembershipConfirmed": False, "actualTradabilityConfirmed": False,
            "usableForTrading": False, "priceAdjustmentApplied": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for cmd in ["capture", "build", "audit", "as-of"]:
        p = sub.add_parser(cmd)
        p.add_argument("--scope", type=Path, required=True)
        p.add_argument("--cache", type=Path, required=True)
        if cmd == "capture":
            p.add_argument("--max-new-requests", type=int, default=0, choices=range(0, 25))
        else:
            p.add_argument("--report", type=Path, required=True)
        if cmd == "as-of":
            for arg in ["stock", "at", "date"]:
                p.add_argument("--" + arg, required=True)
    args = parser.parse_args(argv)
    try:
        scope = load_scope(args.scope)
        if args.command == "capture":
            needed = sum(not (args.cache / digest(url.encode())).exists() for url in scope.urls())
            if needed > args.max_new_requests:
                raise ResearchError("UNIVERSE_EVENT_REQUEST_BUDGET_EXCEEDED")
            for url in scope.urls():
                folder = args.cache / digest(url.encode())
                if folder.exists():
                    audit_source(folder, url)
            reused = sum(capture_source(url, args.cache)[2] for url in scope.urls())
            result = {"capturedSources": len(scope.urls()) - reused, "reusedSources": reused}
        else:
            result = build_report(scope, args.cache) if args.command == "build" else audit_report(scope, args.cache, args.report)
            if args.command == "build":
                if args.report.exists():
                    audit_report(scope, args.cache, args.report)
                else:
                    args.report.parent.mkdir(parents=True, exist_ok=True)
                    atomic_json(args.report, result)
            if args.command == "as-of":
                result = as_of(result, args.stock, args.at, args.date)
            else:
                result = {key: value for key, value in result.items() if key not in {"facts", "venueEvents"}}
        print(json.dumps(result, ensure_ascii=True, sort_keys=True))
        return 0
    except (ValueError, OSError) as exc:
        print(json.dumps({"diagnostic": str(exc) if isinstance(exc, ResearchError) else "UNIVERSE_EVENT_INVALID_INPUT"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
