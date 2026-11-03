"""Issuer-reported acquisition outcome, explicitly linked to a cancellation decision."""
import argparse
import io
import json
from pathlib import Path
import re
import sys
from zipfile import ZipFile

from .corporate_facts import as_of, compact, date_fact, derive as derive_plan, field, integer, one, parse_xml, text
from .dataset import canonical, digest, read_bytes
from .history import job_lock
from .models import ResearchError, utc
from .related_documents import audit_related


def parse_result(raw, corp_code):
    root, normalization = parse_xml(raw)
    name, version, company = one(root.iter("DOCUMENT-NAME")), one(root.iter("FORMULA-VERSION")), one(root.iter("COMPANY-NAME"))
    if (name.get("ACODE") != "00681" or text(version) != "6.0" or compact(text(name)) != "자기주식취득결과보고서"
            or company.get("AREGCIK") != corp_code):
        raise ResearchError("OUTCOME_FORM_ISSUER_UNSUPPORTED")
    period = one(v for v in root.iter("TABLE-GROUP") if v.get("ACLASS") == "ACT_BGN_DT")
    dates = [date_fact(period, code, role) for code, role in [("ACT_BGN_DT", "REPORTED_ACTUAL_START"), ("ACT_END_DT", "REPORTED_ACTUAL_END")]]
    start, end = [v["value"] for v in dates]
    if start is None or end is None or start > end:
        raise ResearchError("OUTCOME_PERIOD_INVALID")
    table = one(v for v in root.iter("TABLE-GROUP") if v.get("ACLASS") == "ACT_DT")
    entries = []
    totals = {key: {"orders": 0, "shares": 0, "amount": 0} for key in ["COMMON", "OTHER"]}
    for index, row in enumerate(table.iter("TR")):
        if not any(v.get("ACODE") == "ACT_CNT" for v in row.iter("TE")):
            continue
        date = date_fact(row, "ACT_DT", "REPORTED_ACQUISITION_DATE")["value"]
        kind, _ = field(row, "TU", "AUNIT", "STK_KND")
        classes = {"6": ("COMMON", "보통주식"), "7": ("OTHER", "기타주식")}
        cls, label = classes.get(kind.get("AUNITVALUE"), (None, None))
        if cls is None or text(kind) != label or date is None or not start <= date <= end:
            raise ResearchError("OUTCOME_ROW_CLASS_DATE_INVALID")
        values = {}
        for code, target in [("ORD_CNT", "orders"), ("ACT_CNT", "shares"), ("PCQ_AMT", "amount")]:
            element, _ = field(row, "TE", "ACODE", code)
            values[target] = integer(text(element))
        if any(v is None for v in values.values()) or int(values["shares"]) > int(values["orders"]):
            raise ResearchError("OUTCOME_ROW_QUANTITY_INVALID")
        broker, _ = field(row, "TE", "ACODE", "CNS_CRP")
        if not re.fullmatch(r"[0-9]{8}", text(broker)):
            raise ResearchError("OUTCOME_BROKER_INVALID")
        for target, value in values.items():
            totals[cls][target] += int(value)
        entries.append({"rowIndex": index, "date": date, "shareClass": cls, "brokerCorpCode": text(broker), **values})
    if not 1 <= len(entries) <= 5000 or min(v["date"] for v in entries) != start or max(v["date"] for v in entries) != end:
        raise ResearchError("OUTCOME_ROWS_PERIOD_MISMATCH")
    for code, key in [("SUM_ORD_CNT", "orders"), ("SUM_ACT_CNT", "shares"), ("ACQ_AMT", "amount")]:
        element, _ = field(table, "TE", "ACODE", code)
        if integer(text(element)) != str(sum(v[key] for v in totals.values())):
            raise ResearchError("OUTCOME_TOTAL_MISMATCH")
    for values in totals.values():
        for value in values.values(): integer(str(value))
    return {"kind": "TREASURY_ACQUISITION_REPORTED_OUTCOME", "documentType": "00681", "formulaVersion": "6.0",
            "dates": dates, "reportedRows": entries, "totalsByShareClass": {key: {k: str(v) for k, v in values.items()} for key, values in totals.items()},
            "normalization": normalization, "roundedUnitPriceUsedForAmount": False}


def derive_result(index, origin, capture):
    with job_lock(index):
        source = audit_related(index, origin, capture, locked=True)
        with ZipFile(io.BytesIO(read_bytes(capture / "original.zip"))) as archive:
            entry = one(v for v in archive.infolist() if v.filename.lower().endswith(".xml"))
            raw = archive.read(entry)
        content = parse_result(raw, source["corpCode"])
        value = {"schemaVersion": "SAGOPALGO_TREASURY_OUTCOME_V1", "stage": "REPORTED_OUTCOME", "receiptNumber": source["receiptNumber"],
                 "stockCode": source["stockCode"], "corpCode": source["corpCode"], "availability": "OBSERVED_AT",
                 "knownAt": source["capturedAt"], "actualAcquisitionReported": True, "automaticEffectAllowed": False,
                 "effectiveDate": None, "referenceEventsEmitted": 0, "priceAdjustmentApplied": False, "usableForTraining": False,
                 "source": {"indexPlanId": source["indexPlanId"], "indexRecordsSha256": source["indexRecordsSha256"],
                            "originReceiptNumber": source["originReceiptNumber"], "originZipSha256": source["originZipSha256"],
                            "zipSha256": source["zipSha256"], "xmlSha256": digest(raw), "xmlEntry": entry.filename}, **content}
        value["factId"] = digest(canonical(value))
        return value


def reconcile(index, origin, capture, decision):
    cancellation = derive_plan(index, origin)
    result = derive_result(index, origin, capture)
    plan = derive_plan(index, decision)
    links = cancellation.get("relatedDocuments", [])
    if (cancellation["kind"] != "SHARE_CANCELLATION_PLAN" or plan["kind"] != "TREASURY_ACQUISITION_PLAN"
            or not any(v["receiptNumber"] == plan["receiptNumber"] and v["role"] == "TREASURY_ACQUISITION_DECISION" for v in links)
            or not any(v["receiptNumber"] == result["receiptNumber"] and v["role"] == "TREASURY_ACQUISITION_RESULT" for v in links)
            or len({v["corpCode"] for v in [cancellation, result, plan]}) != 1):
        raise ResearchError("OUTCOME_EXPLICIT_RELATION_MISMATCH")
    planned_dates = {v["role"]: v["value"] for v in plan["dates"]}
    actual_dates = {v["role"]: v["value"] for v in result["dates"]}
    if (planned_dates["PLANNED_START"] is None or planned_dates["PLANNED_END"] is None
            or not planned_dates["PLANNED_START"] <= actual_dates["REPORTED_ACTUAL_START"] <= actual_dates["REPORTED_ACTUAL_END"] <= planned_dates["PLANNED_END"]):
        raise ResearchError("OUTCOME_PLAN_PERIOD_MISMATCH")
    comparisons = []
    for cls in ["COMMON", "OTHER"]:
        planned = one(v for v in plan["numbers"] if v["shareClass"] == cls and v["role"] == "PLANNED_ACQUISITION")["value"]
        cancel = one(v for v in cancellation["numbers"] if v["shareClass"] == cls and v["role"] == "PLANNED_CANCELLATION")["value"]
        actual = result["totalsByShareClass"][cls]["shares"]
        if planned is None or cancel is None or not int(cancel) <= int(actual) <= int(planned):
            raise ResearchError("OUTCOME_QUANTITY_RELATION_INVALID")
        comparisons.append({"shareClass": cls, "plannedAcquisition": planned, "reportedAcquisition": actual,
                            "plannedCancellation": cancel, "plannedQuantityFullyReported": planned == actual})
    value = {"schemaVersion": "SAGOPALGO_TREASURY_RECONCILIATION_V1", "status": "EXPLICIT_REPORTS_RECONCILED",
             "knownAt": max(utc(v["knownAt"]) for v in [plan, cancellation, result]).isoformat(), "availability": "OBSERVED_AT",
             "sourceFactIds": [v["factId"] for v in [plan, cancellation, result]], "comparisons": comparisons,
             "actualAcquisitionReported": True, "cancellationCompletionReported": False, "automaticEffectAllowed": False,
             "referenceEventsEmitted": 0, "priceAdjustmentApplied": False, "usableForTraining": False}
    value["reconciliationId"] = digest(canonical(value))
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description="Linked treasury acquisition outcome extraction/reconciliation")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ["extract", "audit", "as-of", "reconcile", "audit-reconciliation"]:
        command = commands.add_parser(name)
        for flag in ["index", "origin", "capture"]: command.add_argument("--" + flag, required=True, type=Path)
        command.add_argument("--output" if name in {"extract", "reconcile"} else "--facts", required=True, type=Path)
        if name in {"reconcile", "audit-reconciliation"}: command.add_argument("--decision", required=True, type=Path)
        if name == "as-of": command.add_argument("--at", required=True)
    args = parser.parse_args(argv)
    try:
        value = reconcile(args.index, args.origin, args.capture, args.decision) if args.command in {"reconcile", "audit-reconciliation"} else derive_result(args.index, args.origin, args.capture)
        if args.command in {"extract", "reconcile"}:
            with args.output.open("xb") as stream: stream.write(canonical(value))
        elif read_bytes(args.facts) != canonical(value):
            raise ResearchError("OUTCOME_DERIVATION_TAMPERED")
        if args.command == "as-of":
            result = {"status": "OUTCOME_AS_OF", "visibleFacts": len(as_of(value, args.at)["facts"]), "automaticEffectAllowed": False}
        else:
            result = {"status": value.get("status", "OUTCOME_FACTS_EXTRACTED"), "actualAcquisitionReported": True,
                      "automaticEffectAllowed": False,
                      "cancellationCompletionReported": value.get("cancellationCompletionReported", False)}
            if "reportedRows" in value: result["reportedRows"] = len(value["reportedRows"])
            if "comparisons" in value: result["reconciledShareClasses"] = len(value["comparisons"])
        print(json.dumps(result))
        return 0
    except ResearchError as exc:
        code = str(exc)
    except (ValueError, TypeError, KeyError, UnicodeError):
        code = "OUTCOME_INPUT_INVALID"
    except OSError:
        code = "OUTCOME_FILE_FAILED"
    print(json.dumps({"status": "FAILED", "code": code}), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
