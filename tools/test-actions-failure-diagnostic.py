#!/usr/bin/env python3
from importlib.machinery import SourceFileLoader
from pathlib import Path
import unittest
import json
import subprocess
import sys

mod=SourceFileLoader("actions_failure_diagnostic",str(Path(__file__).with_name("actions-failure-diagnostic.py"))).load_module()

class DiagnosticTests(unittest.TestCase):
    def base(self, conclusion="failure", status="completed"):
        return {"id": 42834621311, "status": status, "conclusion": conclusion}

    def test_fast_failure_without_logs_is_not_quota(self):
        x=mod.classify(self.base(), log_state="unavailable")
        self.assertEqual(x["category"], "RUN_FAILED_UNCLASSIFIED")
        self.assertFalse(x["quota_confirmed"])

    def test_quota_requires_explicit_marker(self):
        x=mod.classify(self.base(),log_text="The account has exceeded its spending limit.",log_state="available")
        self.assertEqual(x["category"], "QUOTA_CONFIRMED")
        self.assertTrue(x["quota_confirmed"])

    def test_success_takes_precedence(self):
        x=mod.classify(self.base("success"), log_text="exceeded its spending limit",log_state="available")
        self.assertEqual(x["category"], "SUCCESS")
        self.assertFalse(x["failover_eligible"])

    def test_running_is_not_failure(self):
        x=mod.classify(self.base(None,"in_progress"))
        self.assertEqual(x["category"],"RUN_IN_PROGRESS")
        self.assertFalse(x["failover_eligible"])

    def test_failed_step_without_logs(self):
        jobs=[{"steps":[{"name":"verify","conclusion":"failure"}]}]
        self.assertEqual(mod.classify(self.base(),jobs)["category"],"STEP_FAILED_UNCLASSIFIED")

    def test_missing_logs_do_not_override_explicit_step(self):
        jobs=[{"steps":[{"conclusion":"failure"}]}]
        self.assertFalse(mod.classify(self.base(),jobs,log_state="forbidden")["quota_confirmed"])

    def test_known_workflow_parse_failure(self):
        self.assertEqual(mod.classify(self.base(), log_text="Invalid workflow file",log_state="available")["category"],"WORKFLOW_CONFIG_ERROR")

    def test_known_network_failure(self):
        self.assertEqual(mod.classify(self.base(),log_text="Could not resolve host",log_state="available")["category"],"NETWORK_ERROR")

    def test_no_raw_log_leakage(self):
        x=mod.classify(self.base(),log_text="token=VERY_SECRET_VALUE",log_state="available")
        self.assertNotIn("VERY_SECRET_VALUE",json.dumps(x))

    def test_cancelled_not_eligible(self):
        x=mod.classify(self.base("cancelled"))
        self.assertEqual(x["category"],"CANCELLED")
        self.assertFalse(x["failover_eligible"])

    def test_wrong_payload_and_log_state_rejected(self):
        with self.assertRaises(TypeError): mod.classify(None)
        with self.assertRaises(ValueError): mod.classify(self.base(),log_state="bad")

    def test_cli_json_output(self):
        p=subprocess.run([sys.executable,str(Path(__file__).with_name("actions-failure-diagnostic.py"))],
            input=json.dumps({"run":self.base(),"log_state":"unavailable"}),text=True,capture_output=True,check=True)
        self.assertEqual(json.loads(p.stdout)["category"],"RUN_FAILED_UNCLASSIFIED")

if __name__=="__main__":
    unittest.main(verbosity=2)
