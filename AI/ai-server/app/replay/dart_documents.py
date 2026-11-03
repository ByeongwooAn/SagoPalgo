"""One selected original ZIP, bound to an audited historical disclosure index."""
import argparse
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
from zipfile import BadZipFile, ZipFile

from .dart_history import Transport
from .dataset import canonical, digest, read_bytes, read_json
from .history import atomic_json, job_lock, now
from .models import ResearchError, utc


def inspect_zip(raw):
    try:
        with ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            names = [v.filename for v in entries]
            if not 1 <= len(entries) <= 32 or len(set(names)) != len(names) or sum(v.file_size for v in entries) > 32 * 1024 * 1024:
                raise ResearchError("DART_DOCUMENT_ARCHIVE_LIMIT")
            result = []
            for entry in entries:
                path = PurePosixPath(entry.filename)
                if (entry.orig_filename != entry.filename or entry.is_dir() or path.is_absolute() or ".." in path.parts or "\\" in entry.filename or ":" in entry.filename
                        or len(entry.filename) > 200 or entry.flag_bits & 1 or entry.file_size > 8 * 1024 * 1024):
                    raise ResearchError("DART_DOCUMENT_ENTRY_INVALID")
                # Reading validates CRC, bounds are checked before decompression. Never extracts or executes XML.
                body = archive.read(entry)
                result.append({"name": entry.filename, "bytes": len(body), "sha256": digest(body)})
            return result
    except (BadZipFile, RuntimeError, NotImplementedError, OSError, EOFError):
        raise ResearchError("DART_DOCUMENT_ZIP_INVALID") from None


def audit_document(folder: Path):
    value = read_json(read_bytes(folder / "capture.json"))
    if (not isinstance(value, dict) or value.get("schemaVersion") != "SAGOPALGO_DART_ORIGINAL_V1"
            or value.get("status") != "ORIGINAL_CAPTURED" or not re.fullmatch(r"[0-9]{14}", value.get("receiptNumber", ""))):
        raise ResearchError("DART_DOCUMENT_CAPTURE_INCOMPLETE")
    utc(value["capturedAt"])
    raw = read_bytes(folder / "original.zip")
    if digest(raw) != value.get("zipSha256") or inspect_zip(raw) != value.get("entries"):
        raise ResearchError("DART_DOCUMENT_TAMPERED")
    return value


def capture_document(index: Path, receipt: str, output: Path, transport):
    if not re.fullmatch(r"[0-9]{14}", receipt):
        raise ResearchError("DART_DOCUMENT_RECEIPT_INVALID")
    with job_lock(index):
        # Index audit takes its own lock; call the locked implementation here.
        from .dart_history import audit_locked
        report = audit_locked(index)
        if report["status"] != "DISCLOSURE_INDEX_COLLECTED":
            raise ResearchError("DART_DOCUMENT_INDEX_INCOMPLETE")
        records = [read_json(line) for line in read_bytes(index / "disclosures.jsonl").splitlines()]
        selected = [v for v in records if v["receiptNumber"] == receipt]
        if len(selected) != 1:
            raise ResearchError("DART_DOCUMENT_NOT_IN_INDEX")
        binding = {"schemaVersion": "SAGOPALGO_DART_ORIGINAL_V1", "indexPlanId": report["planId"],
                   "indexRecordsSha256": report["recordsSha256"], "stockCode": report["stockCode"],
                   "corpCode": report["corpCode"], "receiptNumber": receipt, "maxRequests": 1,
                   "indexInstrumentScope": selected[0]["instrumentScope"]}
        try:
            output.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            value = audit_document(output)
            if any(value.get(k) != v for k, v in binding.items()):
                raise ResearchError("DART_DOCUMENT_BINDING_MISMATCH")
            return value, True
        reservation = {**binding, "status": "RESERVED", "startedAt": now()}
        atomic_json(output / "capture.json", reservation)
        try:
            raw = transport.fetch("document", {"rcept_no": receipt})
            (output / "original.zip").write_bytes(raw)
            entries = inspect_zip(raw)
            result = {**reservation, "status": "ORIGINAL_CAPTURED", "capturedAt": now(), "zipSha256": digest(raw),
                      "entries": entries, "effectiveEventConfirmed": False, "referenceEventsEmitted": 0}
            atomic_json(output / "capture.json", result)
            return result, False
        except Exception as exc:
            reservation.update(status="FAILED", diagnostic=str(exc) if isinstance(exc, ResearchError) else "DART_DOCUMENT_FAILED")
            atomic_json(output / "capture.json", reservation)
            raise ResearchError(reservation["diagnostic"]) from None


def main(argv=None):
    parser = argparse.ArgumentParser(description="Explicit single original-document capture and offline audit")
    commands = parser.add_subparsers(dest="command", required=True)
    capture = commands.add_parser("capture")
    capture.add_argument("--index", required=True, type=Path)
    capture.add_argument("--receipt", required=True)
    capture.add_argument("--output", required=True, type=Path)
    commands.add_parser("audit").add_argument("--capture", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "audit":
            result = audit_document(args.capture)
            cached = True
        else:
            client = Transport(os.getenv("SAGOPALGO_OPEN_DART_API_KEY"), os.getenv("SAGOPALGO_OPEN_DART_ENABLED", "false").lower() == "true")
            result, cached = capture_document(args.index, args.receipt, args.output, client)
        print(json.dumps({"status": result["status"], "receiptNumber": result["receiptNumber"], "cached": cached,
                          "entryCount": len(result["entries"]), "indexInstrumentScope": result["indexInstrumentScope"],
                          "effectiveEventConfirmed": False}, ensure_ascii=False))
        return 0
    except ResearchError as exc:
        code = str(exc)
    except (ValueError, TypeError, KeyError, UnicodeError):
        code = "DART_DOCUMENT_INPUT_INVALID"
    except OSError:
        code = "DART_DOCUMENT_FILE_FAILED"
    print(json.dumps({"status": "FAILED", "code": code}), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
