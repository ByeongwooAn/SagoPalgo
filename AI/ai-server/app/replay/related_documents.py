"""Single DART original explicitly linked by an audited originating disclosure."""
import argparse
import io
import json
import os
from pathlib import Path
import sys
from zipfile import ZipFile

from .corporate_facts import one
from .dart_documents import audit_document, inspect_zip
from .dart_history import Transport, audit_locked, cached, load_job
from .dataset import digest, read_bytes, read_json
from .distribution_facts import extract_distribution
from .history import atomic_json, job_lock, now
from .models import ResearchError, utc


def origin_binding(index, origin):
    report = audit_locked(index)
    source = audit_document(origin)
    if (report.get("status") != "DISCLOSURE_INDEX_COLLECTED" or source["indexPlanId"] != report["planId"]
            or source["indexRecordsSha256"] != report["recordsSha256"] or source["stockCode"] != report["stockCode"]
            or source["corpCode"] != report["corpCode"]):
        raise ResearchError("RELATED_INDEX_BINDING_MISMATCH")
    with ZipFile(io.BytesIO(read_bytes(origin / "original.zip"))) as archive:
        entry = one(v for v in archive.infolist() if v.filename.lower().endswith(".xml"))
        raw = archive.read(entry)
    rows = [read_json(line) for line in read_bytes(index / "disclosures.jsonl").splitlines()]
    selected = one(v for v in rows if v["receiptNumber"] == source["receiptNumber"])
    if selected["instrumentScope"] != source["indexInstrumentScope"]:
        raise ResearchError("RELATED_INDEX_BINDING_MISMATCH")
    _, _, journal = load_job(index)
    company_raw, _ = cached(index, journal, "company", {"corp_code": report["corpCode"]})
    company = read_json(company_raw)
    content = extract_distribution(raw, selected, [v for v in [company.get("stock_name"), company.get("corp_name")] if isinstance(v, str) and v])
    if content["kind"] != "SHARE_CANCELLATION_PLAN":
        raise ResearchError("RELATED_ORIGIN_UNSUPPORTED")
    return report, source, content["relatedDocuments"]


def capture_related(index: Path, origin: Path, receipt: str, output: Path, transport):
    with job_lock(index):
        report, source, links = origin_binding(index, origin)
        link = one(v for v in links if v["receiptNumber"] == receipt and v["role"] == "TREASURY_ACQUISITION_RESULT")
        binding = {"schemaVersion": "SAGOPALGO_DART_RELATED_ORIGINAL_V1", "indexPlanId": report["planId"],
                   "indexRecordsSha256": report["recordsSha256"], "stockCode": report["stockCode"], "corpCode": report["corpCode"],
                   "originReceiptNumber": source["receiptNumber"], "originZipSha256": source["zipSha256"],
                   "receiptNumber": receipt, "relationship": link, "maxRequests": 1}
        try:
            output.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            value = audit_related(index, origin, output, locked=True)
            if any(value.get(k) != v for k, v in binding.items()):
                raise ResearchError("RELATED_CAPTURE_BINDING_MISMATCH")
            return value, True
        reservation = {**binding, "status": "RESERVED", "startedAt": now()}
        atomic_json(output / "capture.json", reservation)
        try:
            raw = transport.fetch("document", {"rcept_no": receipt})
            (output / "original.zip").write_bytes(raw)
            value = {**reservation, "status": "RELATED_ORIGINAL_CAPTURED", "capturedAt": now(),
                     "zipSha256": digest(raw), "entries": inspect_zip(raw), "effectiveEventConfirmed": False}
            atomic_json(output / "capture.json", value)
            return value, False
        except Exception as exc:
            reservation.update(status="FAILED", diagnostic=str(exc) if isinstance(exc, ResearchError) else "RELATED_CAPTURE_FAILED")
            atomic_json(output / "capture.json", reservation)
            raise ResearchError(reservation["diagnostic"]) from None


def audit_related(index: Path, origin: Path, capture: Path, locked=False):
    if not locked:
        with job_lock(index):
            return audit_related(index, origin, capture, locked=True)
    report, source, links = origin_binding(index, origin)
    value = read_json(read_bytes(capture / "capture.json"))
    if (not isinstance(value, dict) or value.get("schemaVersion") != "SAGOPALGO_DART_RELATED_ORIGINAL_V1"
            or value.get("status") != "RELATED_ORIGINAL_CAPTURED" or value.get("maxRequests") != 1
            or value.get("effectiveEventConfirmed") is not False):
        raise ResearchError("RELATED_CAPTURE_INCOMPLETE")
    utc(value["capturedAt"])
    if utc(value["capturedAt"]) < utc(source["capturedAt"]):
        raise ResearchError("RELATED_CAPTURE_TIME_INVALID")
    expected = {"indexPlanId": report["planId"], "indexRecordsSha256": report["recordsSha256"],
                "stockCode": report["stockCode"], "corpCode": report["corpCode"], "originReceiptNumber": source["receiptNumber"],
                "originZipSha256": source["zipSha256"]}
    if (any(value.get(k) != v for k, v in expected.items()) or value.get("relationship") not in links
            or value["receiptNumber"] != value["relationship"]["receiptNumber"] or value["relationship"]["role"] != "TREASURY_ACQUISITION_RESULT"):
        raise ResearchError("RELATED_CAPTURE_BINDING_MISMATCH")
    raw = read_bytes(capture / "original.zip")
    if digest(raw) != value.get("zipSha256") or inspect_zip(raw) != value.get("entries"):
        raise ResearchError("RELATED_CAPTURE_TAMPERED")
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description="Explicit related acquisition result original capture/audit")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ["capture", "audit"]:
        command = commands.add_parser(name)
        command.add_argument("--index", required=True, type=Path)
        command.add_argument("--origin", required=True, type=Path)
        command.add_argument("--output" if name == "capture" else "--capture", required=True, type=Path)
        if name == "capture": command.add_argument("--receipt", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "capture":
            client = Transport(os.getenv("SAGOPALGO_OPEN_DART_API_KEY"), os.getenv("SAGOPALGO_OPEN_DART_ENABLED", "false").lower() == "true")
            value, cached = capture_related(args.index, args.origin, args.receipt, args.output, client)
        else:
            value, cached = audit_related(args.index, args.origin, args.capture), True
        print(json.dumps({"status": value["status"], "receiptNumber": value["receiptNumber"], "cached": cached,
                          "originReceiptNumber": value["originReceiptNumber"], "relationshipRole": value["relationship"]["role"]}))
        return 0
    except ResearchError as exc:
        code = str(exc)
    except (ValueError, TypeError, KeyError, UnicodeError):
        code = "RELATED_INPUT_INVALID"
    except OSError:
        code = "RELATED_FILE_FAILED"
    print(json.dumps({"status": "FAILED", "code": code}), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
