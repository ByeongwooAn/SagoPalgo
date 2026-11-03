"""GET-only collection operation checks; all HTTP is a local fake."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SCRIPT = Path(__file__).resolve().parents[1] / "check-account-collection.ps1"
POWERSHELL = os.environ.get("SAGOPALGO_TEST_POWERSHELL") or shutil.which("pwsh") or shutil.which("powershell")
ROOT = "/api/v1/kb/accounts/primary/observations"
ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
OTHER_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


@unittest.skipUnless(POWERSHELL, "PowerShell is required")
class CollectionCheckTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.report = Path(self.directory.name) / "report.json"
        self.baseline = Path(self.directory.name) / "baseline.json"
        self.requests = []
        self.data = {"enabled": False, "state": "NOT_STARTED", "intervalSeconds": 900,
                     "personalModeEnabled": True, "accountEnabled": True, "connectionConfigured": True,
                     "readOnly": True, "usableForTrading": False}
        self.detail = {"requestId": ID, "readOnly": True, "storageState": "COMPLETED", "snapshotStatus": "PARTIAL",
                       "observation": {"contractVersion": "KB_ACCOUNT_OBSERVATION_V1", "atomic": False,
                                       "usableForTrading": False, "status": "PARTIAL",
                                       "summary": {"cash": "PRIVATE_CASH_AMOUNT"}}}
        self.ids = [OTHER_ID]
        self.order_enabled = False
        self.no_store = True
        self.fail_http = False
        self.malformed_history = False
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_GET(self):
                owner.requests.append(("GET", self.path))
                if self.path == ROOT + "/collection":
                    data = owner.data
                elif self.path == "/api/v1/orders/readiness":
                    data = {"checks": [{"code": "ORDER_PRECHECK_SWITCH", "passed": owner.order_enabled},
                                       {"code": "LIVE_ORDER_SWITCH", "passed": False}]}
                elif self.path == ROOT + "/" + ID:
                    data = owner.detail
                elif self.path == ROOT + "?limit=100":
                    data = {"items": [{"requestId": value} for value in owner.ids]}
                    if owner.malformed_history:
                        data = {}
                else:
                    raise AssertionError(self.path)
                body = json.dumps({"success": not owner.fail_http, "data": data,
                                   "error": {"message": "PRIVATE_UPSTREAM_MESSAGE"}}).encode()
                self.send_response(503 if owner.fail_http else 200)
                if owner.no_store:
                    self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                owner.requests.append(("POST", self.path))
                self.send_error(405)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.directory.cleanup()

    def paused(self, state="PAUSED"):
        self.data.update(state=state, lastRequestId=ID, lastStorageState="COMPLETED", lastSnapshotStatus="PARTIAL")
        if state == "PAUSED":
            self.data["failureCode"] = "SNAPSHOT_PARTIAL"
        self.ids = [ID, OTHER_ID]

    def run_check(self, *arguments):
        result = subprocess.run([POWERSHELL, "-NoLogo", "-NoProfile", "-NonInteractive", "-File", str(SCRIPT),
                                 "-ApiBaseUrl", self.base, "-ReportPath", str(self.report), *arguments],
                                capture_output=True, text=True, encoding="utf-8", timeout=25)
        report = json.loads(result.stdout)
        for secret in ["PRIVATE_CASH_AMOUNT", "PRIVATE_UPSTREAM_MESSAGE"]:
            self.assertNotIn(secret, result.stdout + result.stderr + self.report.read_text())
        self.assertNotIn("POST", [method for method, _ in self.requests])
        return result.returncode, report

    def test_default_checks_off_using_local_get_only(self):
        status, report = self.run_check("-ExpectedState", "NOT_STARTED")
        self.assertEqual(status, 0, report)
        self.assertEqual(report["result"], "CHECK_PASSED")
        self.assertTrue(report["getOnly"])
        self.assertEqual(len(self.requests), 3)

    def test_paused_terminal_receipt_and_idle_after_resume_are_valid(self):
        for state in ["PAUSED", "IDLE"]:
            with self.subTest(state=state):
                self.data.pop("failureCode", None)
                self.paused(state)
                status, report = self.run_check("-ExpectedState", state)
                self.assertEqual(status, 0, report)
                self.assertTrue(report["lastReceiptVerified"])
                self.assertEqual(report["lastSnapshotStatus"], "PARTIAL")

    def test_active_is_unconfirmed_and_never_released(self):
        self.data.update(state="ACTIVE", activeRequestId=ID)
        status, report = self.run_check()
        self.assertEqual(status, 1)
        self.assertEqual(report["failureCode"], "ACTIVE_RESULT_UNCONFIRMED")
        self.assertEqual(len(self.requests), 2)

    def test_pending_mismatched_or_trading_usable_receipt_is_rejected(self):
        self.paused()
        for change in [{"storageState": "PENDING"}, {"requestId": OTHER_ID},
                       {"snapshotStatus": "SUCCESS"}, {"readOnly": False}]:
            with self.subTest(change=change):
                original = self.detail.copy()
                self.detail.update(change)
                status, report = self.run_check()
                self.assertEqual(status, 1)
                self.assertEqual(report["failureCode"], "TERMINAL_RECEIPT_MISMATCH")
                self.detail = original
        self.detail["observation"]["usableForTrading"] = True
        self.assertEqual(self.run_check()[0], 1)

    def test_baseline_detects_state_or_history_change_and_is_not_overwritten(self):
        self.paused("IDLE")
        self.assertEqual(self.run_check()[0], 0)
        baseline = self.report.read_text()
        self.baseline.write_text(baseline)
        arguments = ["-PreviousReport", str(self.baseline), "-RequireUnchanged"]
        self.assertEqual(self.run_check(*arguments)[0], 0)
        self.ids.append("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
        _, report = self.run_check(*arguments)
        self.assertEqual(report["failureCode"], "STATUS_OR_HISTORY_CHANGED")
        self.assertEqual(self.baseline.read_text(), baseline)

    def test_settings_and_expected_state_must_match(self):
        self.data["enabled"] = True
        self.assertEqual(self.run_check()[1]["failureCode"], "ENABLED_STATE_MISMATCH")
        self.order_enabled = True
        self.assertEqual(self.run_check("-ExpectedEnabled", "ON")[1]["failureCode"], "ORDER_SWITCH_NOT_OFF")
        self.order_enabled = False
        self.assertEqual(self.run_check("-ExpectedEnabled", "ON", "-ExpectedState", "PAUSED")[1]["failureCode"],
                         "EXPECTED_STATE_MISMATCH")

    def test_unknown_contract_or_http_and_cache_errors_fail_closed(self):
        self.data["failureCode"] = "PRIVATE_UPSTREAM_MESSAGE"
        self.assertEqual(self.run_check()[1]["failureCode"], "COLLECTION_CONTRACT_INVALID")
        del self.data["failureCode"]
        self.malformed_history = True
        self.assertEqual(self.run_check()[1]["failureCode"], "HISTORY_CONTRACT_INVALID")
        self.malformed_history = False
        self.no_store = False
        self.assertEqual(self.run_check()[1]["failureCode"], "API_UNCONFIRMED")
        self.no_store = True
        self.fail_http = True
        self.assertEqual(self.run_check()[1]["failureCode"], "API_UNCONFIRMED")


if __name__ == "__main__":
    unittest.main()
