#!/usr/bin/env python3
"""Offline regression checks for the iSH pinned code runner (Python >=3.9)."""
from importlib.machinery import SourceFileLoader
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import sys
import unittest
from unittest.mock import patch

code=SourceFileLoader("ish_code_runner",str(Path(__file__).with_name("ish-code-runner.py"))).load_module()
SHA="a"*40
SHA2="b"*40
def job(id="case_001",task="PYTHON_SYNTAX",sha=SHA):
    return {"request_id":id,"sha":sha,"task":task}

class CodeRunnerTests(unittest.TestCase):
    def test_allowlist_rejects_arbitrary_execution(self):
        with self.assertRaisesRegex(ValueError,"UNAPPROVED_TASK"):
            code.validate(job(task="SHELL"))
        with self.assertRaisesRegex(ValueError,"INVALID_FIELDS"):
            code.validate(dict(job(),command="rm -rf /"))
        with self.assertRaisesRegex(ValueError,"INVALID_SHA"):
            code.validate(job(sha="main"))
        self.assertEqual(set(code.TASKS),{"PYTHON_SYNTAX","NODE_DUAL_TEST"})

    def test_one_id_is_only_executed_once(self):
        with TemporaryDirectory() as folder:
            with patch.object(code,"STATE",Path(folder)/"jobs.sqlite3"),patch.object(
                    code,"verify_repo",return_value="SHA_NOT_APPROVED") as check:
                first=code.perform(job())
                second=code.perform(job())
                self.assertEqual(first["status"],"SHA_NOT_APPROVED")
                self.assertFalse(first["cached"])
                self.assertTrue(second["cached"])
                self.assertEqual(check.call_count,1)

    def test_id_conflict_does_not_reuse_wrong_result(self):
        with TemporaryDirectory() as folder:
            with patch.object(code,"STATE",Path(folder)/"jobs.sqlite3"),patch.object(
                    code,"verify_repo",return_value="SHA_NOT_APPROVED"):
                code.perform(job())
                conflict=code.perform(job(sha=SHA2))
                self.assertEqual(conflict["reason"],"REQUEST_ID_CONFLICT")
                self.assertEqual(conflict["status"],"EXECUTION_ERROR")

    def test_missing_runtime_fails_closed(self):
        with TemporaryDirectory() as folder:
            with patch.object(code,"STATE",Path(folder)/"jobs.sqlite3"),patch.object(
                    code,"verify_repo",return_value="OK"),patch.object(
                    code.shutil,"which",return_value=None):
                outcome=code.perform(job())
                self.assertEqual(outcome["status"],"DEPENDENCY_MISSING")
                self.assertEqual(outcome["exit_code"],127)

    def test_env_does_not_expose_sensitive_variables(self):
        with patch.dict(os.environ,{"GH_TOKEN":"sample-secret","MY_PASSWORD":"secret",
                                     "MY_API_KEY":"secret","PATH":"/bin"}):
            env=code.clean_env()
            self.assertNotIn("GH_TOKEN",env)
            self.assertNotIn("MY_PASSWORD",env)
            self.assertNotIn("MY_API_KEY",env)
            self.assertEqual(env["CI"],"1")

    def test_remote_url_is_fixed_owner_repo(self):
        with TemporaryDirectory() as folder:
            base=Path(folder)
            (base/".git").mkdir()
            def malicious(argv,**kwargs):
                return {"code":0,"output":"https://github.com/other/repository.git","truncated":False}
            with patch.object(code,"REPO",base),patch.object(code,"exec_fixed",side_effect=malicious):
                self.assertEqual(code.verify_repo(SHA),"GIT_UNAVAILABLE")

    def test_no_credentials_or_logs_in_result(self):
        out=code.result("case_002",SHA,"PYTHON_SYNTAX","OK","PASS",code=0)
        self.assertEqual(out["logs_exported"],False)
        self.assertEqual(out["video_executed"],False)
        self.assertEqual(out["runner"],"ish")

if __name__=="__main__":
    unittest.main(verbosity=2)
