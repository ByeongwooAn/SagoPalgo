import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import patch

import capture_public_tick_sample as capture


def source():
    v={k:"test-only" for k in capture.COPY_KEYS}
    v.update(SAGOPALGO_KIS_BASE_URL="https://openapi.koreainvestment.com:9443",
             SAGOPALGO_KB_APP_KEY="private-account-key",SAGOPALGO_KB_ACCOUNT_NUMBER="private-account")
    return v


class CapturePublicSampleTest(unittest.TestCase):
    def test_only_public_credentials_and_db_are_copied(self):
        v=capture.isolated_environment(source(),"247540")
        self.assertNotIn("SAGOPALGO_KB_APP_KEY",v);self.assertNotIn("SAGOPALGO_KB_ACCOUNT_NUMBER",v)
        self.assertTrue(all(v[k]=="false" for k in capture.DISABLED))
        self.assertEqual(v["SAGOPALGO_MARKET_STREAM_APPROVED_SUBSCRIPTIONS"],"2")

    def test_active_owner_newlines_and_wrong_origin_rejected(self):
        for changes in [dict(SAGOPALGO_MARKET_STREAM_ENABLED="true"),dict(SAGOPALGO_DB_PASSWORD="bad\nentry"),
                        dict(SAGOPALGO_KIS_BASE_URL="https://example.test")]:
            v=source();v.update(changes)
            with self.assertRaises(ValueError):capture.isolated_environment(v,"247540")
        for stock in ["x","1234567","12345\n"]:
            with self.assertRaises(ValueError):capture.isolated_environment(source(),stock)

    def run_capture(self,available):
        clock=[0];calls=[]
        def docker(args,**kwargs):
            calls.append(args)
            if args[0]=="inspect":
                v={"Config":{"Env":[k+"="+v for k,v in source().items()],"Image":"test-local-image"},
                   "NetworkSettings":{"Networks":{"test-network":{}}},"Image":"sha256:test-local"}
                return subprocess.CompletedProcess([],0,stdout=json.dumps([v]).encode())
            if args[0]=="run":return subprocess.CompletedProcess([],0,stdout=b"a"*64)
            return subprocess.CompletedProcess([],0,stdout=b"")
        def get(url):
            if not available:raise ValueError("not ready")
            return {"http":200,"body":{"success":True,"data":{"state":"LIVE","connectionState":"CONNECTED",
                "diagnostic":None,"trade":{},"quote":{},"checkedAt":"synthetic"}}}
        def sleep(_):clock[0]+=10
        stdout=io.StringIO()
        with patch.object(capture,"docker",side_effect=docker),patch.object(capture,"public_get",side_effect=get),\
             patch.object(capture.time,"monotonic",side_effect=lambda:clock[0]),patch.object(capture.time,"sleep",side_effect=sleep),\
             contextlib.redirect_stdout(stdout):
            result=capture.main(["--stock-code","247540","--seconds","5","--personal-local-use-confirmed","--no-other-key-client-confirmed"])
        public=json.loads(stdout.getvalue());folder=Path(public["receipt"]).parent
        try:
            receipt=json.loads((folder/"receipt.json").read_bytes())
            self.assertFalse((folder/"capture.env.local").exists())
            self.assertEqual(receipt["containerLifetimeLimitSeconds"],55)
            self.assertEqual(receipt["containerHardLifetimeLimitSeconds"],60)
            self.assertEqual(calls[-1],["stop","--time","5","a"*64])
            run=next(c for c in calls if c[0]=="run")
            self.assertIn("--pull=never",run);self.assertIn("/usr/bin/timeout",run);self.assertIn("55s",run)
            self.assertNotIn("private-account",json.dumps(receipt))
            return result,receipt
        finally:
            base=Path(capture.__file__).resolve().parents[1]/"Back/spring-server/build-codex-quote-samples"
            assert folder.resolve().parent==base.resolve()
            shutil.rmtree(folder)

    def test_success_stops_owned_container_and_removes_environment(self):
        result,r=self.run_capture(True)
        self.assertEqual(result,0);self.assertEqual(r["status"],"OBSERVATION_COMPLETED")

    def test_startup_timeout_also_stops_and_preserves_safe_receipt(self):
        result,r=self.run_capture(False)
        self.assertEqual(result,1);self.assertEqual(r["failureCode"],"CAPTURE_STARTUP_TIMEOUT")


if __name__=="__main__":unittest.main()
