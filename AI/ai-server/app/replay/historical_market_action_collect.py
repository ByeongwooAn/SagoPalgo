"""Capture public KIND evidence for one H05 publication month."""

import argparse
from calendar import monthrange
from datetime import date
from pathlib import Path
from time import monotonic, sleep

from .corporate_action_outcomes import VIEWER, checked_read, require
from .dataset import digest, read_bytes, read_json
from .historical_market_action_expansion import SCHEMA, select_rows
from .history import atomic_json, job_lock, now
from .kind_membership_evidence import Transport
from .models import ResearchError
from .session_notice_inventory import body_path, viewer_documents


def collect_month(month, baseline, artifacts, job, transport):
    first = date.fromisoformat(month + "-01")
    spec = read_json(read_bytes(baseline))
    inventory, sample = (read_json(checked_read(artifacts / spec[name]["path"], spec[name]["sha256"]))
                         for name in ("inventory", "sample"))
    end = first.replace(day=monthrange(first.year, first.month)[1]).isoformat()
    window = {"from": first.isoformat(), "through": min(end, inventory["scope"]["publicationThrough"])}
    rows = select_rows(inventory, sample, window["from"], window["through"])
    require(bool(rows) and month != "2023-12", "MONTHLY_COLLECTION_WINDOW")
    captures = {}
    last_attempt = 0.0

    def fetch(stage, key, request):
        nonlocal last_attempt
        name = f"proof-{stage}-{key}"
        folder = job / "captures" / name
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "receipt.json"
        if path.exists():
            saved_raw = read_bytes(path)
            saved = read_json(saved_raw)
            require(saved["request"] == request, "MONTHLY_REQUEST_CHANGED")
            if saved["status"] == "CAPTURED":
                raw = checked_read(folder / "raw.bin", saved["sha256"])
                captures[name] = digest(saved_raw)
                return raw
        sleep(max(0, 0.5 - (monotonic() - last_attempt)))
        last_attempt = monotonic()
        receipt = {"schemaVersion": "SAGOPALGO_H05_CAPTURE_V1", "status": "RESERVED",
                   "request": request, "startedAt": now()}
        try:
            raw = transport.fetch(request)
            (folder / "raw.bin").write_bytes(raw)
            receipt.update(status="CAPTURED", sha256=digest(raw))
        except ResearchError as exc:
            receipt.update(status="FAILED", diagnostic=str(exc))
            raise
        finally:
            receipt["capturedAt"] = now()
            atomic_json(path, receipt)
        captures[name] = digest(read_bytes(path))
        return raw

    job.mkdir(parents=True, exist_ok=True)
    with job_lock(job):
        errors = 0
        for row in rows:
            receipt = row["receipt"]
            try:
                raw = fetch("viewer", receipt, {"url": row["sourceUrl"], "method": "GET", "parameters": None})
                versions = viewer_documents(raw)
                revised = len(versions) != 1 or versions[0]["correctionMarked"] or row["titleCorrectionFlag"]
                for version in versions:
                    document = version["document"]
                    key, prefix = (document, "v") if revised else (receipt, "")
                    route = fetch(prefix + "route", key, {"url": VIEWER, "method": "POST",
                                  "parameters": {"method": "searchContents", "docNo": document}})
                    fetch(prefix + "body", key, {"url": body_path(route, document),
                          "method": "GET", "parameters": None})
                errors = 0
            except ResearchError as exc:
                if str(exc) == "MONTHLY_REQUEST_CHANGED" or str(exc) == "INPUT_HASH":
                    raise
                print(receipt, str(exc), flush=True)
                if "HTTP_FAILED" in str(exc):
                    errors += 1
                    if errors >= 3:
                        break
        version_pins = {name: pin for name, pin in captures.items()
                        if name.startswith(("proof-vroute-", "proof-vbody-"))}
        manifest = {"schemaVersion": SCHEMA, "reviewedAt": now(), "publicationWindow": window,
                    "inventory": spec["inventory"], "sample": spec["sample"],
                    "receipts": {name: pin for name, pin in captures.items() if name not in version_pins},
                    "versionReceipts": version_pins}
        output = job / "review-manifest.json"
        if output.exists():
            saved = read_json(read_bytes(output))
            if saved == manifest | {"reviewedAt": saved["reviewedAt"]}:
                return len(rows), len(captures)
        atomic_json(output, manifest)
    return len(rows), len(captures)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("month", help="Publication month in YYYY-MM format")
    for name in ("baseline", "artifacts", "job"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    candidates, captures = collect_month(args.month, args.baseline, args.artifacts, args.job, Transport())
    print(args.month, candidates, captures)


if __name__ == "__main__":
    main()
