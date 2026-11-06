import contextlib
import io
import json
from pathlib import Path
import subprocess
import shutil
import unittest
import uuid
from unittest.mock import patch

import check_public_tick_readiness as check


@contextlib.contextmanager
def workspace_temp():
    base=(Path(__file__).resolve().parents[1]/"Back/spring-server/build-codex-tick-readiness/tests").resolve()
    folder=base/uuid.uuid4().hex
    folder.mkdir(parents=True)
    try:yield folder
    finally:
        # Resolve and verify the exact owned target before recursive cleanup.
        assert folder.resolve().parent==base and folder.name.isalnum()
        shutil.rmtree(folder)


class PublicTickReadinessTest(unittest.TestCase):
    def inputs(self):
        return ({"STORAGE_025":2,"STORAGE_026":4},
                {"enabled":False,"rightsConfirmed":False,"positiveSubscriptionBudget":False,"kisCredentialsPresent":True},
                {"http":200,"body":{"success":True,"data":{"schemaVersion":"SAGOPALGO_STORED_EXPORT_V1",
                    "readOnly":True,"usableForTrading":False,"streamCoverage":"OBSERVED_ONLY",
                    "streamEvents":[{"type":"TRADE"},{"type":"QUOTE"}]}}},
                {"http":200,"body":{"success":True,"data":{"contractVersion":"KIS_KRX_STREAM_V1",
                    "usableForTrading":False,"state":"DISABLED"}}})

    def test_disabled_continuous_collection_can_have_valid_persisted_sample(self):
        report=check.summarize(*self.inputs())
        self.assertTrue(report["storageAndExportReady"])
        self.assertTrue(report["persistedSampleAvailable"])
        self.assertFalse(report["continuousCollectionConfigurationDeclared"])
        self.assertIn("COLLECTION_DISABLED",report["blockers"])

    def test_each_missing_migration_blocks_readiness(self):
        for key, code in [("STORAGE_025","STORAGE_025_REQUIRED"),("STORAGE_026","STORAGE_026_REQUIRED")]:
            a=list(self.inputs());a[0][key]=0;r=check.summarize(*a)
            self.assertFalse(r["storageAndExportReady"]);self.assertIn(code,r["blockers"])

    def test_502_and_empty_200_are_different(self):
        a=list(self.inputs());a[2]={"http":502,"body":{"success":False,"error":{"code":"EXTERNAL_DATA_ERROR"}}}
        self.assertIn("EXPORT_API_UNAVAILABLE",check.summarize(*a)["blockers"])
        a=list(self.inputs());a[2]["body"]["data"]["streamEvents"]=[];r=check.summarize(*a)
        self.assertTrue(r["storageAndExportReady"]);self.assertFalse(r["persistedSampleAvailable"])
        self.assertIn("NO_PERSISTED_TICK_SAMPLE",r["blockers"])

    def test_one_stream_type_does_not_pass_as_complete_sample(self):
        a=list(self.inputs());a[2]["body"]["data"]["streamEvents"]=[{"type":"TRADE"}]
        self.assertFalse(check.summarize(*a)["persistedSampleAvailable"])

    def test_wrong_contract_flags_and_unknown_event_fail(self):
        edits=[{"readOnly":False},{"usableForTrading":True},{"schemaVersion":"OTHER"},
               {"streamEvents":[{"type":"ACCOUNT_FILL"}]},{"streamEvents":"not-list"}]
        for edit in edits:
            a=list(self.inputs());a[2]["body"]["data"].update(edit)
            self.assertFalse(check.summarize(*a)["storageAndExportReady"])

    def test_empty_configuration_cannot_be_declared_ready(self):
        a=list(self.inputs());a[1]={}
        self.assertFalse(check.summarize(*a)["continuousCollectionConfigurationDeclared"])

    def test_untrusted_origin_and_window_rejected_before_access(self):
        for base in ["http://user:secret@localhost", "file:///x", "http://localhost/api", "http://localhost?x=1"]:
            with self.assertRaises(check.CheckError):check.validate_window(base,"2026-11-05T00:00:00Z","2026-11-05T00:01:00Z")
        for a,b in [("2026-11-05T00:00:01Z","2026-11-05T00:01:00Z"),
                    ("2026-11-05T00:00:00","2026-11-05T00:01:00"),
                    ("2026-11-05T00:00:00Z","2026-11-07T00:00:00Z")]:
            with self.assertRaises(check.CheckError):check.validate_window("http://localhost",a,b)

    def test_sql_uses_binary_lf_and_rejects_missing_result(self):
        with patch.object(check,"run",return_value=b"STORAGE_025\t2\nSTORAGE_026\t4\n") as run:
            self.assertEqual(check.database_checks()["STORAGE_026"],4)
            script=run.call_args.kwargs["input"]
            self.assertIsInstance(script,bytes);self.assertNotIn(b"\r",script)
            self.assertTrue(script.endswith(b"\nSQL\n"))
        with patch.object(check,"run",return_value=b"STORAGE_025\t2\n"):
            with self.assertRaises(check.CheckError):check.database_checks()

    def test_credential_values_do_not_escape_configuration_summary(self):
        env=["SAGOPALGO_KIS_APP_KEY=private-key", "SAGOPALGO_KIS_APP_SECRET=private-secret", "SAGOPALGO_DB_PASSWORD=private-password"]
        with patch.object(check,"run",return_value=json.dumps([{"Config":{"Env":env}}]).encode()):
            r=check.configuration_checks();self.assertTrue(r["kisCredentialsPresent"])
            self.assertNotIn("private",json.dumps(r));self.assertTrue(all(isinstance(v,bool) for v in r.values()))

    def test_command_failures_do_not_echo_raw_stderr(self):
        fake=subprocess.CompletedProcess([],1,stdout=b"",stderr=b"private-credential")
        with patch.object(check.subprocess,"run",return_value=fake):
            with self.assertRaisesRegex(check.CheckError,"^LOCAL_COMMAND_FAILED$"):check.run(["docker"])

    def test_cli_only_reads_and_preserves_existing_report(self):
        db,config,export,stream=self.inputs()
        with workspace_temp() as folder:
            path=Path(folder)/"report.json"
            args=["--from","2026-11-05T00:00:00Z","--to","2026-11-05T00:01:00Z","--output",str(path)]
            with patch.object(check,"database_checks",return_value=db),patch.object(check,"configuration_checks",return_value=config),patch.object(check,"public_get",side_effect=[export,stream]) as get,contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(check.main(args),0)
                self.assertEqual(get.call_count,2)
                self.assertIn("/api/v1/research/dataset-export?",get.call_args_list[0].args[0])
            before=path.read_bytes()
            with patch.object(check,"database_checks") as access,contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(check.main(args),1);access.assert_not_called()
            self.assertEqual(path.read_bytes(),before)


if __name__=="__main__":unittest.main()
