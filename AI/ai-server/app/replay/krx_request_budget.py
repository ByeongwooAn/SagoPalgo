"""Shared local-key daily request reservations; cannot observe other applications."""
from datetime import datetime, timezone
import time

from .dataset import digest, read_bytes, read_json
from .history import KST, job_lock
from .krx_storage import atomic_json
from .models import ResearchError, utc


class Budget:
    def __init__(self, root, key, limit=8000, prior_requests=0, interval_seconds=0.5, clock=None, sleep=None):
        if not key or not 1 <= limit <= 10000 or not 0 <= prior_requests <= limit or not 0.5 <= interval_seconds <= 10:
            raise ResearchError("KRX_BUDGET_CONFIG_INVALID")
        self.folder = root / digest(key.encode())
        self.limit, self.prior, self.interval = limit, prior_requests, interval_seconds
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.sleep = sleep or time.sleep

    def reserve(self, request_id):
        self.folder.mkdir(parents=True, exist_ok=True)
        with job_lock(self.folder):
            at = self.clock()
            stamp = at.astimezone(KST).date().isoformat()
            path = self.folder / (stamp + ".json")
            value = read_json(read_bytes(path)) if path.exists() else {
                "schemaVersion": "SAGOPALGO_KRX_LOCAL_DAILY_BUDGET_V1", "localDay": stamp,
                "limit": self.limit, "externalReservations": self.prior, "reservations": []}
            if (not isinstance(value, dict) or set(value) != {"schemaVersion", "localDay", "limit", "externalReservations", "reservations"}
                    or value["schemaVersion"] != "SAGOPALGO_KRX_LOCAL_DAILY_BUDGET_V1" or value["localDay"] != stamp
                    or type(value["limit"]) is not int or not 1 <= value["limit"] <= 10000
                    or type(value["externalReservations"]) is not int or not 0 <= value["externalReservations"] <= value["limit"]
                    or not isinstance(value["reservations"], list)):
                raise ResearchError("KRX_BUDGET_LEDGER_INVALID")
            entries = value["reservations"]
            seen = set()
            for entry in entries:
                if (not isinstance(entry, dict) or set(entry) != {"requestId", "reservedAt"}
                        or not isinstance(entry["requestId"], str) or entry["requestId"] in seen
                        or utc(entry["reservedAt"]).astimezone(KST).date().isoformat() != stamp):
                    raise ResearchError("KRX_BUDGET_LEDGER_INVALID")
                seen.add(entry["requestId"])
            if any(v["requestId"] == request_id for v in entries):
                raise ResearchError("KRX_BUDGET_REQUEST_ALREADY_RESERVED")
            ceiling = min(self.limit, value["limit"])
            value["limit"] = ceiling
            if len(entries) + value["externalReservations"] >= ceiling:
                raise ResearchError("KRX_DAILY_REQUEST_BUDGET_EXHAUSTED")
            if entries:
                elapsed = (at - utc(entries[-1]["reservedAt"])).total_seconds()
                if elapsed < 0:
                    raise ResearchError("KRX_BUDGET_CLOCK_REGRESSION")
                wait = self.interval - elapsed
                if wait > 0:
                    self.sleep(wait)
            reserved = self.clock()
            if reserved.astimezone(KST).date().isoformat() != stamp:
                raise ResearchError("KRX_BUDGET_DAY_CHANGED_RETRY_EXPLICITLY")
            entries.append({"requestId": request_id, "reservedAt": reserved.isoformat()})
            atomic_json(path, value)
            return {"localDay": stamp, "used": len(entries) + value["externalReservations"], "limit": ceiling}
