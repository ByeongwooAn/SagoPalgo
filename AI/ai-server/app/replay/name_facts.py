"""Reviewed exchange name-change forms; listing dates never imply corporate legal effectiveness."""
from collections import Counter
import re
import unicodedata

from . import name_disclosures as capture
from .dataset import canonical, digest, read_bytes
from .distribution_facts import Node
from .kind_cases import compact, one_row, iso_date
from .models import ResearchError, utc


def name_key(value):
    # Remove only explicit Korean corporate markers and whitespace; do not transliterate.
    value = unicodedata.normalize("NFC", value)
    return re.sub(r"\s+|\(주\)|㈜|주식회사", "", value)


def name_matches(source_name, observed_name, market, source_isin=None):
    left, right = name_key(source_name), name_key(observed_name)
    return left == right or (market == "KOSPI" and source_isin is not None and left.endswith("보통주")
                             and not right.endswith("보통주") and left.removesuffix("보통주") == right)


def parse(raw, url, market, corrected=False):
    capture.public.validate_url(url)
    form = url.rsplit("/", 1)[1].removesuffix(".htm")
    root = capture.public.html(raw)
    text = root.text()
    if form == "70765" and market == "KOSDAQ":
        titles = [v.text() for v in root.walk("div") if v.attrs.get("class") == "xforms_title"]
        titles += [v.text() for v in root.walk("a") if v.attrs.get("name") == "#2"]
        expected = ["정정신고(보고)", "변경상장(상호변경)"] if corrected else ["변경상장(상호변경)"]
        if [compact(v) for v in titles] != expected:
            raise ResearchError("NAME_FACT_TITLE_OR_CORRECTION_REVIEW")
        tables = []
        for table in root.walk("table"):
            rows = [[v.text() for v in tr.children if isinstance(v, Node) and v.tag in {"td", "th"}] for tr in table.walk("tr")]
            if rows and rows[0] and compact(rows[0][0]) == "1.변경전상호":
                if list(table.walk("table")):
                    raise ResearchError("NAME_FACT_TABLE_AMBIGUOUS")
                tables.append(rows)
        if len(tables) != 1:
            raise ResearchError("NAME_FACT_TABLE_AMBIGUOUS")
        rows = tables[0]
        before = one_row(rows, "1.변경전상호")
        reason = one_row(rows, "2.변경상장사유")
        after = one_row(rows, "3.변경후상호")
        date_row = one_row(rows, "4.상장일")
        abbreviated = [r for r in rows if len(r) == 3 and r[:2] == ["약명", "한글"]]
        if (len(before) != 2 or reason != [reason[0], "상호변경"] or len(after) != 4
                or after[1:3] != ["정식명", "한글"] or len(date_row) != 2 or len(abbreviated) > 1):
            raise ResearchError("NAME_FACT_FIELDS_INVALID")
        stamp = iso_date(date_row[1])
        return {"form": form, "beforeName": before[1], "afterName": after[3], "date": stamp,
                "afterAbbreviatedName": abbreviated[0][2] if abbreviated else None,
                "dateBasis": "EXCHANGE_NAME_CHANGE_LISTING_DATE", "sourceIsin": None, "sourceStockCode": None,
                "marketBasis": "REVIEWED_KOSDAQ_NAME_CHANGE_FORM", "sourceTextSha256": digest(text.encode())}
    combined = False
    if form == "68151" and market == "KOSPI":
        if "정정" in text:
            raise ResearchError("NAME_FACT_COMBINED_NOTICE_REVIEW")
        sections = [v for v in text.split("◎") if "변경상장(상호변경)" in v]
        if len(sections) != 1 or corrected:
            raise ResearchError("NAME_FACT_COMBINED_NOTICE_REVIEW")
        text = sections[0].strip()
        combined = True
    if form in {"68155", "68151"} and market == "KOSPI":
        if text.count("변경상장(상호변경)") != 1 or (not corrected and ("정정" in text)):
            raise ResearchError("NAME_FACT_TITLE_OR_CORRECTION_REVIEW")
        matches = re.findall(r"㉮\s*상장종목\s*\(영문명\)\s*-\s*(.*?)\s*\(영문명\s*:.*?\)\s*→\s*(.*?)\s*\(영문명\s*:.*?\)\s*㉯", text)
        dates = re.findall(r"[⑤⑥]\s*변경상장일\s*:\s*([0-9]{4})년\s*([0-9]{1,2})월\s*([0-9]{1,2})일", text)
        identities = re.findall(r"보통주\s*표준코드\s*:\s*([A-Z]{2}[A-Z0-9]{10})\s*\(단축코드\s*:\s*A([A-Z0-9]{6})\)", text)
        if len(matches) != 1 or len(dates) != 1 or len(identities) != 1 or "기명식 보통주" not in text:
            raise ResearchError("NAME_FACT_KOSPI_FIELDS_INVALID")
        stamp = "%04d-%02d-%02d" % tuple(map(int, dates[0]))
        iso_date(stamp)
        return {"form": form, "beforeName": matches[0][0], "afterName": matches[0][1], "date": stamp,
                "dateBasis": "EXCHANGE_NAME_CHANGE_LISTING_DATE", "sourceIsin": identities[0][0], "sourceStockCode": identities[0][1],
                "marketBasis": "REVIEWED_KOSPI_NAME_CHANGE_FORM", "sourceTextSha256": digest(text.encode()),
                "combinedNotice": combined, "otherCorporateActionsConfirmed": False}
    raise ResearchError("NAME_FACT_FORM_REVIEW_REQUIRED")


def verify(parsed, target, context):
    if (parsed["sourceStockCode"] is not None and parsed["sourceStockCode"] != target["symbol"]
            or parsed["sourceIsin"] is not None and parsed["sourceIsin"] != target["isin"]):
        raise ResearchError("NAME_FACT_SOURCE_IDENTITY_MISMATCH")
    bindings = {}
    for side in ["before", "after"]:
        source = context[side]
        if ((source["symbol"], source["isin"], source["market"], source["name"])
                != (target["symbol"], target["isin"], target[side + "Market"], target[side + "Name"])
                or source["shareType"] != "보통주"):
            raise ResearchError("NAME_FACT_OBSERVED_NAME_OR_IDENTITY_MISMATCH")
        if name_matches(parsed[side + "Name"], source["name"], source["market"], parsed["sourceIsin"]):
            bindings[side] = "DECLARED_FORMAL_NAME_TO_KRX_NAME"
        elif (side == "after" and parsed.get("afterAbbreviatedName")
              and name_key(parsed["afterAbbreviatedName"]) == name_key(source["name"])):
            bindings[side] = "DECLARED_ABBREVIATED_NAME_TO_KRX_NAME"
        else:
            raise ResearchError("NAME_FACT_OBSERVED_NAME_OR_IDENTITY_MISMATCH")
        utc(source["knownAt"])
    if not target["observedFrom"] < parsed["date"] <= target["observedTo"]:
        raise ResearchError("NAME_FACT_DATE_CONFLICT")
    return {**parsed, "observationId": target["observationId"], "stockCode": target["symbol"], "historyIsin": target["isin"],
            "market": target["afterMarket"], "identityBasis": "FULL_CODE_VIEWER_AND_BOTH_OBSERVED_NAMES_AND_KRX_ISIN",
            "observedBeforeName": target["beforeName"], "observedAfterName": target["afterName"], "nameMatchBasis": bindings,
            "instrumentContext": context, "corporateLegalEffectiveDate": None, "legalMergerCompletionConfirmed": False,
            "exchangeRatio": None, "firstEverIpoConfirmed": False}


def transfer_fact(target, parent, context):
    # Only a known transfer and the explicit KOSPI common-share suffix explain this label change.
    if (target["beforeMarket"], target["afterMarket"]) != ("KOSDAQ", "KOSPI") or target["afterName"] != target["beforeName"] + "보통주":
        raise ResearchError("NAME_TRANSFER_LABEL_REVIEW_REQUIRED")
    for side in ["before", "after"]:
        c = context[side]
        if ((c["symbol"], c["isin"], c["market"], c["name"], c["shareType"])
                != (target["symbol"], target["isin"], target[side + "Market"], target[side + "Name"], "보통주")):
            raise ResearchError("NAME_TRANSFER_CONTEXT_MISMATCH")
    matches = []
    for row in parent["rows"]:
        o = row["observation"]
        if (o["kind"] == "MARKET_TRANSFER_OBSERVED" and row["resolution"] == "DISCLOSURE_MATCH"
                and row["membershipDateConfirmedByDisclosure"]
                and all(o[k] == target[k] for k in ["observedFrom", "observedTo"])
                and all(o[side]["symbol"] == target["symbol"] and o[side]["isin"] == target["isin"]
                        and o[side]["name"] == target[side + "Name"] and o[side]["market"] == target[side + "Market"] for side in ["before", "after"])):
            matches.append(row)
    if len(matches) != 1:
        raise ResearchError("NAME_TRANSFER_DISCLOSURE_CONTEXT_REQUIRED")
    return {"observationId": target["observationId"], "classification": "MARKET_TRANSFER_COMMON_SHARE_LABEL",
            "stockCode": target["symbol"], "historyIsin": target["isin"], "beforeName": target["beforeName"], "afterName": target["afterName"],
            "transferObservationId": matches[0]["observationId"], "transferEvidence": matches[0]["evidence"],
            "knownAt": max([matches[0]["knownAt"], *[context[s]["knownAt"] for s in ["before", "after"]]], key=utc),
            "date": matches[0]["exchangeMembershipDate"], "dateBasis": "OBSERVED_LABEL_AT_AUDITED_MARKET_TRANSFER",
            "instrumentContext": context, "corporateLegalEffectiveDate": None, "corporateNameChangeConfirmed": False}


def build(folder, parent, contexts):
    plan, journal, latest = capture.load(folder)
    facts, reviews = [], []
    if set(contexts) != {t["observationId"] for t in plan["targets"]}:
        raise ResearchError("NAME_FACT_CONTEXT_SCOPE_MISMATCH")
    for target in plan["targets"]:
        identity = target["observationId"]
        context = contexts[identity]
        _, _, completed, state = capture.inspect(folder, target, latest)
        versions = []
        try:
            if state == "TRANSFER_CONTEXT_REQUIRED":
                facts.append(transfer_fact(target, parent, context))
                continue
            if state != "BODIES_CAPTURED":
                raise ResearchError(state)
            selected = capture.candidates(completed.get("NOTICE_SEARCH", completed["SEARCH"]))
            for index, candidate in enumerate(selected):
                label = "V" + str(index)
                viewer = capture.viewer(completed[label + "_VIEWER"], target, candidate)
                entry = latest[(identity, label + "_BODY")]
                parsed = parse(completed[label + "_BODY"], entry["request"]["url"], target["afterMarket"], candidate["corrected"])
                versions.append({**candidate, **viewer, "parsed": parsed, "sourceUrl": entry["request"]["url"], "sourceSha256": entry["sha256"],
                                 "acquisitionHashes": {stage: latest[(identity, stage)]["sha256"] for stage in ["SEARCH", *(["NOTICE_SEARCH"] if "NOTICE_SEARCH" in completed else []), label + "_VIEWER", label + "_PATH", label + "_BODY"]}})
            valid = []
            diagnostics = []
            for version in versions:
                try:
                    fact = verify(version["parsed"], target, context)
                    valid.append((version, fact))
                except ResearchError as exc:
                    diagnostics.append(str(exc))
            if not valid:
                raise ResearchError(diagnostics[0] if len(set(diagnostics)) == 1 else "NAME_FACT_MULTIPLE_CANDIDATES_REVIEW")
            # A full viewer history must be present and all versions of that history must agree on the name fields/date.
            histories = {tuple(sorted(v["documents"])) for v, _ in valid}
            if len(histories) != 1:
                raise ResearchError("NAME_FACT_MULTIPLE_CANDIDATES_REVIEW")
            docs = set(next(iter(histories)))
            chain = [v for v in versions if v["document"] in docs]
            if (set(v["document"] for v in chain) != docs or len(chain) != len(docs)
                    or any(set(v["documents"]) != docs for v in chain)
                    or len([v for v in chain if not v["corrected"]]) != 1
                    or len(chain) > 1 and not all(v["corrected"] for v in chain[1:])):
                raise ResearchError("NAME_FACT_VERSION_LINEAGE_REVIEW")
            fields = ["beforeName", "afterName", "date", "sourceStockCode", "sourceIsin", "form"]
            if any(any(v["parsed"][k] != chain[0]["parsed"][k] for k in fields) for v in chain):
                raise ResearchError("NAME_FACT_CORRECTION_CHANGES_NAME_FIELDS")
            chosen = chain[-1]
            fact = verify(chosen["parsed"], target, context)
            stages = [stage for (key, stage) in latest if key == identity]
            known = max([latest[(identity, stage)]["capturedAt"] for stage in stages] + [context[s]["knownAt"] for s in ["before", "after"]], key=utc)
            facts.append({**fact, "classification": "EXCHANGE_NAME_CHANGE", "knownAt": known, "knowledgeBasis": "FETCH_TIME_ONLY",
                          "versions": chain, "otherCandidateReceipts": [v["receipt"] for v in versions if v not in chain],
                          "correctionPolicy": "FORMAL_NAMES_AND_LISTING_DATE_EQUAL_OTHER_CONTENT_RETAINED" if len(chain) > 1 else "NO_ADDITIONAL_VIEWER_VERSION",
                          "otherCorrectionContentInterpreted": False if len(chain) > 1 else None})
        except ResearchError as exc:
            times = [context[s]["knownAt"] for s in ["before", "after"]]
            times += [e.get("finishedAt", e.get("capturedAt", e["startedAt"])) for e in journal["attempts"] if e["targetId"] == identity]
            reviews.append({"observationId": identity, "symbol": target["symbol"], "beforeName": target["beforeName"], "afterName": target["afterName"],
                            "classification": "SAME_NORMALIZED_NAME_REVIEW" if name_key(target["beforeName"]) == name_key(target["afterName"]) else "NAME_CHANGE_REVIEW",
                            "knownAt": max(times, key=utc), "candidateVersions": versions, "diagnostic": str(exc)})
    return {"schemaVersion": "SAGOPALGO_NAME_FACTS_V1", "sourceKind": plan["sourceKind"], "planId": plan["planId"],
            "parentSha256": plan["parentSha256"], "targets": len(plan["targets"]), "facts": facts, "reviews": reviews,
            "verified": len(facts), "reviewRequired": len(reviews), "classificationCounts": dict(Counter(v["classification"] for v in facts)),
            "corporateLegalEffectiveDatesConfirmed": False, "allCorporateActionsConfirmed": False, "usableForTraining": False, "usableForTrading": False}
