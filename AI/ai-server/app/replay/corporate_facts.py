"""Offline, source-bound declared facts. Plans never become automatic economic effects."""
import argparse
import io
import json
from pathlib import Path
import re
import sys
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from .dart_documents import audit_document
from .dart_history import audit_locked
from .dataset import canonical, digest, read_bytes, read_json
from .history import day, job_lock
from .models import ResearchError, utc


def compact(value):
    return re.sub(r"\s+", "", value)


def text(element):
    return " ".join("".join(element.itertext()).split())


def one(nodes):
    values = list(nodes)
    if len(values) != 1:
        raise ResearchError("FACT_FIELD_AMBIGUOUS")
    return values[0]


def integer(value):
    value = value.strip()
    if value == "-":
        return None
    if not re.fullmatch(r"(?:0|[1-9][0-9]*|[1-9][0-9]{0,2}(?:,[0-9]{3})+)", value):
        raise ResearchError("FACT_NUMBER_INVALID")
    number = value.replace(",", "")
    if len(number) > 18:
        raise ResearchError("FACT_NUMBER_LIMIT")
    return number


def parse_xml(raw):
    if len(raw) > 8 * 1024 * 1024:
        raise ResearchError("FACT_XML_LIMIT")
    value = raw.decode("utf-8-sig")
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)", value, re.I):
        raise ResearchError("FACT_XML_DECLARATION_FORBIDDEN")
    # DART originals can contain bare '&' in prose. Preserve raw bytes and record this lexical repair.
    normalized, repairs = re.subn(r"&(?!(?:amp|lt|gt|apos|quot|#[0-9]+|#x[0-9a-fA-F]+);)", "&amp;", value)
    try:
        root = ET.fromstring(normalized)
    except ET.ParseError:
        raise ResearchError("FACT_XML_INVALID") from None
    if root.tag != "DOCUMENT" or sum(1 for _ in root.iter()) > 50000:
        raise ResearchError("FACT_DOCUMENT_INVALID")
    return root, {"bareAmpersandEscapes": repairs, "normalizedXmlSha256": digest(normalized.encode("utf-8"))}


def field(scope, tag, attribute, code):
    element = one(e for e in scope.iter(tag) if e.get(attribute) == code)
    return element, {"tag": tag, "attribute": attribute, "code": code, "sourceText": text(element)}


def date_fact(scope, code, role):
    element, evidence = field(scope, "TU", "AUNIT", code)
    value, displayed = element.get("AUNITVALUE"), text(element)
    if value == "-" and displayed == "-":
        return {"role": role, "value": None, "precision": "DATE", "evidence": evidence}
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{8}", value):
        raise ResearchError("FACT_DATE_INVALID")
    stamp = value[:4] + "-" + value[4:6] + "-" + value[6:]
    day(stamp)
    shown = re.fullmatch(r"([0-9]{4})년\s*([0-9]{1,2})월\s*([0-9]{1,2})일", displayed)
    if not shown or tuple(map(int, shown.groups())) != tuple(map(int, stamp.split("-"))):
        raise ResearchError("FACT_DATE_DISPLAY_CONFLICT")
    return {"role": role, "value": stamp, "precision": "DATE", "evidence": evidence}


def number_fact(scope, code, role, share_class, unit):
    _, evidence = field(scope, "TE", "ACODE", code)
    return {"role": role, "shareClass": share_class, "unit": unit,
            "value": integer(evidence["sourceText"]), "evidence": evidence}


def normalized_title(value):
    return compact(re.sub(r"^(?:\[[^\]]+\])+", "", value))


def correction_facts(root, selected, rows, numbers):
    sections = list(root.iter("CORRECTION"))
    if len(sections) > 1:
        raise ResearchError("FACT_CORRECTION_AMBIGUOUS")
    base = {"present": bool(sections), "indexCorrectionIndicated": selected["correctionIndicated"],
            "indexWithdrawalIndicated": selected["withdrawalIndicated"], "originalSubmissionDate": None,
            "candidateReceiptNumbers": [], "directParentReceiptNumber": None, "changes": [], "unparsedChangeRows": 0,
            "chainStatus": "NOT_ESTABLISHED"}
    if not sections:
        return base
    section = sections[0]
    dates = re.findall(r"최초제출일\s*:\s*([0-9]{4})년\s*([0-9]{1,2})월\s*([0-9]{1,2})일", text(section))
    if len(dates) != 1:
        raise ResearchError("FACT_CORRECTION_DATE_AMBIGUOUS")
    stamp = "-".join([dates[0][0], dates[0][1].zfill(2), dates[0][2].zfill(2)])
    day(stamp)
    candidates = sorted(v["receiptNumber"] for v in rows if v["receiptNumber"] != selected["receiptNumber"]
                        and v["receiptDate"] == stamp and normalized_title(v["reportName"]) == normalized_title(selected["reportName"]))
    base.update(originalSubmissionDate=stamp, candidateReceiptNumbers=candidates,
                chainStatus="AMBIGUOUS" if len(candidates) > 1 else "CANDIDATE_ONLY" if candidates else "UNRESOLVED")
    for tr in section.iter("TR"):
        cells = [text(e) for e in tr if e.tag == "TD"]
        if len(cells) != 4:
            continue
        if "1일매수주문수량한도" not in compact(cells[0]):
            base["unparsedChangeRows"] += 1
            continue
        before = re.fullmatch(r"기타주식\s*:\s*([0-9,]+)", cells[2])
        after = re.fullmatch(r"기타주식\s*:\s*([0-9,]+)", cells[3])
        if not before or not after or base["changes"]:
            raise ResearchError("FACT_CORRECTION_CHANGE_AMBIGUOUS")
        old, new = integer(before[1]), integer(after[1])
        current = [v["value"] for v in numbers if v["role"] == "DAILY_ORDER_LIMIT" and v["shareClass"] == "OTHER"]
        if current != [new]:
            raise ResearchError("FACT_CORRECTION_MAIN_CONFLICT")
        base["changes"].append({"role": "DAILY_ORDER_LIMIT", "shareClass": "OTHER", "before": old,
                                "after": new, "mainFieldMatched": True})
    return base


def extract_content(raw, selected, rows, corp_code):
    root, normalization = parse_xml(raw)
    name = one(root.iter("DOCUMENT-NAME"))
    company = one(root.iter("COMPANY-NAME"))
    if company.get("AREGCIK") != corp_code:
        raise ResearchError("FACT_ISSUER_MISMATCH")
    doc_type = name.get("ACODE")
    version = text(one(root.iter("FORMULA-VERSION")))
    if (doc_type, version) not in {("11332", "1.5"), ("11314", "1.3")}:
        raise ResearchError("FACT_FORM_VERSION_UNSUPPORTED")
    if normalized_title(text(name)) != normalized_title(selected["reportName"]):
        raise ResearchError("FACT_INDEX_TITLE_CONFLICT")
    numbers, dates = [], []
    if doc_type == "11332" and "자기주식취득결정" in compact(text(name)):
        scope = one(e for e in root.iter("TABLE-GROUP") if e.get("ACLASS") == "TBL_ACQ_STK")
        kind = "TREASURY_ACQUISITION_PLAN"
        for share_class, prefix in [("COMMON", "OSTK"), ("OTHER", "ESTK")]:
            numbers.extend([number_fact(scope, "ACQ_" + prefix, "PLANNED_ACQUISITION", share_class, "SHARES"),
                            number_fact(scope, "ACQ_" + prefix + "_PRC", "PLANNED_ACQUISITION_AMOUNT", share_class, "KRW"),
                            number_fact(scope, "BUY_" + prefix + "_LMT", "DAILY_ORDER_LIMIT", share_class, "SHARES")])
        dates = [date_fact(scope, code, role) for code, role in [("ACQ_DATE", "DECISION_DATE"), ("ACQ_BGN", "PLANNED_START"), ("ACQ_END", "PLANNED_END")]]
        _, method = field(scope, "TE", "ACODE", "ACQ_MTH")
        if compact(method["sourceText"]) != "유가증권시장을통한장내매수":
            raise ResearchError("FACT_MARKET_METHOD_UNSUPPORTED")
        instrument = {"scope": "DOMESTIC_EQUITY_PROGRAM", "market": "KOSPI", "methodEvidence": method,
                      "otherShareClassStockCode": None}
    elif doc_type == "11314" and "해외증권시장주권등상장폐지결정" in compact(text(name)):
        scope = one(e for e in root.iter("TABLE-GROUP") if e.get("ACLASS") == "TBL1")
        kind = "OVERSEAS_DELISTING_PLAN"
        numbers = [number_fact(scope, "DEL_CST_CNT", "DECLARED_DELISTING_SHARE_COUNT", "COMMON", "ISSUER_REPORTED_SHARES"),
                   number_fact(scope, "DEL_PST_CNT", "DECLARED_DELISTING_SHARE_COUNT", "OTHER", "ISSUER_REPORTED_SHARES")]
        dates = [date_fact(scope, code, role) for code, role in [("DRC_DT", "DECISION_DATE"), ("APP_DT", "PLANNED_APPLICATION"), ("DELS_EXP_DT", "PLANNED_DELISTING")]]
        _, exchange = field(scope, "TE", "ACODE", "LST_MKT")
        if not exchange["sourceText"] or exchange["sourceText"] == "-" or "한국거래소" in exchange["sourceText"]:
            raise ResearchError("FACT_OVERSEAS_EXCHANGE_INVALID")
        instrument = {"scope": "OVERSEAS_SECURITIES", "exchangeEvidence": exchange, "otherShareClassStockCode": None}
    else:
        raise ResearchError("FACT_DOCUMENT_TYPE_UNSUPPORTED")
    values = [v["value"] for v in dates]
    known_dates = [v for v in values if v is not None]
    if values[0] is None or known_dates != sorted(known_dates):
        raise ResearchError("FACT_DATE_ORDER_INVALID")
    correction = correction_facts(root, selected, rows, numbers)
    return {"documentType": doc_type, "formulaVersion": version, "kind": kind, "dates": dates, "numbers": numbers,
            "instrument": instrument, "correction": correction, "normalization": normalization}


def derive(index: Path, capture: Path):
    with job_lock(index):
        report = audit_locked(index)
        original = audit_document(capture)
        if (report["status"] != "DISCLOSURE_INDEX_COLLECTED" or original["indexPlanId"] != report["planId"]
                or original["indexRecordsSha256"] != report["recordsSha256"] or original["corpCode"] != report["corpCode"]
                or original["stockCode"] != report["stockCode"]):
            raise ResearchError("FACT_INDEX_BINDING_MISMATCH")
        rows = [read_json(line) for line in read_bytes(index / "disclosures.jsonl").splitlines()]
        selected = one(v for v in rows if v["receiptNumber"] == original["receiptNumber"])
        if original["indexInstrumentScope"] != selected["instrumentScope"]:
            raise ResearchError("FACT_INSTRUMENT_SCOPE_CONFLICT")
        with ZipFile(io.BytesIO(read_bytes(capture / "original.zip"))) as archive:
            entry = one(v for v in archive.infolist() if v.filename.lower().endswith(".xml"))
            raw = archive.read(entry)
        content = extract_content(raw, selected, rows, report["corpCode"])
        if content["instrument"]["scope"] == "DOMESTIC_EQUITY_PROGRAM" and selected["instrumentScope"] in {"OVERSEAS_SECURITIES", "SUBSIDIARY"}:
            raise ResearchError("FACT_INSTRUMENT_SCOPE_CONFLICT")
        known = max(utc(original["capturedAt"]), utc(selected["observedAt"]))
        value = {"schemaVersion": "SAGOPALGO_DISCLOSURE_FACTS_V1", "status": "DISCLOSURE_FACTS_EXTRACTED",
                 "stockCode": report["stockCode"], "corpCode": report["corpCode"], "receiptNumber": original["receiptNumber"],
                 "receiptDate": selected["receiptDate"], "knownAt": known.isoformat(), "availability": "OBSERVED_AT",
                 "stage": "DECLARED_PLAN", "effectiveDate": None, "automaticEffectAllowed": False,
                 "referenceEventsEmitted": 0, "priceAdjustmentApplied": False, "usableForTraining": False,
                 "source": {"historyPlanId": report["historyPlanId"], "dailySha256": report["dailySha256"],
                            "indexPlanId": report["planId"], "indexRecordsSha256": report["recordsSha256"],
                            "zipSha256": original["zipSha256"], "xmlSha256": digest(raw), "xmlEntry": entry.filename}, **content}
        value["factId"] = digest(canonical(value))
        return value


def extract(index, capture, output):
    value = derive(index, capture)
    with output.open("xb") as stream:
        stream.write(canonical(value))
    return value


def audit(index, capture, facts):
    value = derive(index, capture)
    if read_bytes(facts) != canonical(value):
        raise ResearchError("FACT_DERIVATION_TAMPERED")
    return value


def as_of(value, at):
    body = {key: item for key, item in value.items() if key != "factId"}
    if (value.get("factId") != digest(canonical(body)) or value.get("stage") != "DECLARED_PLAN"
            or value.get("automaticEffectAllowed") is not False or value.get("effectiveDate") is not None):
        raise ResearchError("FACT_SNAPSHOT_INVALID")
    cutoff = utc(at)
    return {"at": cutoff.isoformat(), "availability": "OBSERVED_AT", "automaticEffectAllowed": False,
            "facts": [value] if utc(value["knownAt"]) <= cutoff else []}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline declared corporate facts from audited original documents")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ["extract", "audit", "as-of"]:
        command = commands.add_parser(name)
        command.add_argument("--index", required=True, type=Path)
        command.add_argument("--capture", required=True, type=Path)
        command.add_argument("--output" if name == "extract" else "--facts", required=True, type=Path)
        if name == "as-of": command.add_argument("--at", required=True)
    args = parser.parse_args(argv)
    try:
        value = extract(args.index, args.capture, args.output) if args.command == "extract" else audit(args.index, args.capture, args.facts)
        if args.command == "as-of":
            result = as_of(value, args.at)
            result = {"at": result["at"], "visibleFacts": len(result["facts"]), "automaticEffectAllowed": False}
        else:
            result = {"status": value["status"], "factId": value["factId"], "kind": value["kind"],
                      "numberFacts": len(value["numbers"]), "dateFacts": len(value["dates"]),
                      "correctionChainStatus": value["correction"]["chainStatus"], "automaticEffectAllowed": False}
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except ResearchError as exc:
        code = str(exc)
    except (ValueError, TypeError, KeyError, UnicodeError):
        code = "FACT_INPUT_INVALID"
    except OSError:
        code = "FACT_FILE_FAILED"
    print(json.dumps({"status": "FAILED", "code": code}), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
