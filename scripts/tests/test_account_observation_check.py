"""Exercise the PowerShell live-check client against a local HTTP fake; no KB calls."""
import copy
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


SCRIPT = Path(__file__).resolve().parents[1] / "check-account-observation.ps1"
POWERSHELL = os.environ.get("SAGOPALGO_TEST_POWERSHELL") or shutil.which("pwsh") or shutil.which("powershell")
ROOT = "/api/v1/kb/accounts/primary/observations"
APIS = ["SSQM1801", "SSQM2932", "SSQM2952", "SSQM2341"]


@unittest.skipUnless(POWERSHELL, "PowerShell is required")
class ObservationCheckTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.receipt = Path(self.directory.name) / "receipt.json"
        self.requests = []
        self.data = None
        self.lose_post = False
        self.partial = False
        self.pending = False
        self.mismatch = False
        self.storage_error = False
        self.collection_enabled = False
        self.live_order_enabled = False
        self.owner_recorded = False
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def reply(self, data, status=200):
                body = json.dumps({"success": status == 200, "data": data}).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                owner.requests.append(("GET", self.path))
                if self.path == ROOT + "/collection":
                    self.reply({"enabled": owner.collection_enabled, "personalModeEnabled": True,
                                "accountEnabled": True, "connectionConfigured": True,
                                "state": "NOT_STARTED", "readOnly": True, "usableForTrading": False})
                elif self.path == "/api/v1/orders/readiness":
                    self.reply({"checks": [{"code": code, "passed": passed} for code, passed in [
                        ("ORDER_PRECHECK_SWITCH", False), ("LIVE_ORDER_SWITCH", owner.live_order_enabled),
                        ("ACCOUNT_SWITCH", True), ("CREDENTIALS", True),
                        ("HTTPS_ENDPOINT", True), ("OFFICIAL_ORDER_ENDPOINT", True)]]})
                elif self.path == ROOT + "?limit=20":
                    self.reply({"items": [] if owner.data is None else [{"requestId": owner.data["requestId"]}]},
                               status=503 if owner.storage_error else 200)
                else:
                    data = copy.deepcopy(owner.data)
                    if owner.mismatch:
                        data["orderDate"] = "20261101"
                    self.reply(data)

            def do_POST(self):
                owner.requests.append(("POST", self.path))
                request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                owner.owner_recorded = json.loads(owner.receipt.read_text())["requestId"] == request["requestId"]
                owner.data = {**request, "readOnly": True, "storageState": "COMPLETED",
                              "observationId": request["requestId"], "snapshotStatus": "SUCCESS",
                              "observation": {"contractVersion": "KB_ACCOUNT_OBSERVATION_V1",
                                  "provider": "KB", "accountAlias": "primary", "atomic": False,
                                  "usableForTrading": False, "observationId": request["requestId"],
                                  "status": "SUCCESS", "sections": [
                                      {"api": api, "status": "SUCCESS", "completeness": "COMPLETE",
                                       "pagesRead": 1, "receivedRowCount": 1, "scope": {"orderDate": request["orderDate"]},
                                       "summary": {"tfnd": "PRIVATE_BALANCE"}, "issues": [],
                                       "rows": [{"fields": {"hld_q_p6": "0.123456", "now_prc": None}}]}
                                      for api in APIS]}}
                if owner.partial:
                    owner.data["snapshotStatus"] = "PARTIAL"
                    owner.data["observation"]["status"] = "PARTIAL"
                    section = owner.data["observation"]["sections"][0]
                    section.update(status="FAILED", completeness="UNKNOWN", pagesRead=0,
                                   receivedRowCount=0, rows=[], issues=[{"code": "LOOKUP_FAILED"}])
                if owner.pending:
                    owner.data = {**request, "readOnly": True, "storageState": "PENDING"}
                if owner.lose_post:
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.connection.close()
                    return
                self.reply(owner.data)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.directory.cleanup()

    def run_check(self, capture=True, receipt=None, date="20261103"):
        result = subprocess.run([POWERSHELL, "-NoLogo", "-NoProfile", "-NonInteractive", "-File", str(SCRIPT),
                                 "-ApiBaseUrl", self.base, "-ReceiptPath", str(receipt or self.receipt),
                                 "-OrderDate", date, *(["-Capture"] if capture else [])],
                                capture_output=True, text=True, encoding="utf-8", timeout=25)
        self.assertNotIn("PRIVATE_BALANCE", result.stdout + result.stderr)
        self.assertNotIn("0.123456", result.stdout + result.stderr)
        return result, json.loads(result.stdout)

    def test_capture_records_before_single_post_and_verifies_stored_detail(self):
        result, report = self.run_check()
        self.assertEqual(result.returncode, 0, report)
        self.assertTrue(self.owner_recorded)
        self.assertEqual(report["result"], "API_OBSERVATION_VERIFIED")
        self.assertEqual(report["kbAppComparison"], "NOT_PERFORMED")
        self.assertEqual([path for method, path in self.requests if method == "POST"], [ROOT])
        self.assertEqual([s["api"] for s in report["sections"]], APIS)
        self.assertNotIn("PRIVATE_BALANCE", self.receipt.read_text() + Path(str(self.receipt) + ".report.json").read_text())

    def test_lost_post_response_recovers_only_with_get(self):
        self.lose_post = True
        result, report = self.run_check()
        self.assertEqual(result.returncode, 0, report)
        self.assertEqual([m for m, _ in self.requests].count("POST"), 1)
        self.assertEqual(report["postHttpStatus"], 0)
        self.requests.clear()
        result, report = self.run_check(capture=False)
        self.assertEqual(result.returncode, 0, report)
        self.assertEqual([m for m, _ in self.requests], ["GET", "GET"])

    def test_existing_receipt_blocks_second_capture(self):
        self.run_check()
        previous = Path(str(self.receipt) + ".report.json").read_text()
        self.requests.clear()
        result, report = self.run_check()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(report["failureCode"], "RECEIPT_ALREADY_EXISTS_USE_GET")
        self.assertEqual(self.requests, [])
        self.assertEqual(Path(str(self.receipt) + ".report.json").read_text(), previous)

    def test_partial_is_not_promoted_to_success(self):
        self.partial = True
        result, report = self.run_check()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(report["failureCode"], "OBSERVATION_NOT_FULLY_SUCCESSFUL")
        self.assertTrue(report["storageVerified"])
        self.assertEqual(report["sections"][0]["issues"], ["LOOKUP_FAILED"])
        self.assertEqual([m for m, _ in self.requests].count("POST"), 1)

    def test_pending_is_preserved_without_new_post(self):
        self.pending = True
        _, report = self.run_check()
        self.assertEqual(report["failureCode"], "OBSERVATION_NOT_COMPLETED")
        self.requests.clear()
        _, report = self.run_check(capture=False)
        self.assertEqual(report["storageState"], "PENDING")
        self.assertEqual([m for m, _ in self.requests], ["GET"])

    def test_mismatched_detail_fails_without_retry(self):
        self.mismatch = True
        result, report = self.run_check()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(report["failureCode"], "DETAIL_RECEIPT_MISMATCH")
        self.assertEqual([m for m, _ in self.requests].count("POST"), 1)

    def test_collection_or_live_order_enabled_blocks_capture(self):
        for flag in ["collection_enabled", "live_order_enabled"]:
            with self.subTest(flag=flag):
                setattr(self, flag, True)
                result, _ = self.run_check()
                self.assertEqual(result.returncode, 1)
                self.assertFalse(self.receipt.exists())
                self.assertNotIn("POST", [m for m, _ in self.requests])
                setattr(self, flag, False)

    def test_storage_failure_or_unwritable_receipt_blocks_post(self):
        self.storage_error = True
        _, report = self.run_check()
        self.assertEqual(report["failureCode"], "HISTORY_PREFLIGHT_FAILED")
        self.storage_error = False
        result, _ = self.run_check(receipt=self.receipt.parent / "absent" / "receipt.json")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("POST", [m for m, _ in self.requests])

    def test_invalid_date_and_missing_receipt_do_not_call_api(self):
        _, report = self.run_check(date="20260230")
        self.assertEqual(report["failureCode"], "ORDER_DATE_INVALID")
        _, report = self.run_check(capture=False)
        self.assertEqual(report["failureCode"], "RECEIPT_REQUIRED")
        self.assertEqual(self.requests, [])


if __name__ == "__main__":
    unittest.main()
