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
        self.assertEqual(set(code.TASKS),{"PYTHON_SYNTAX","NODE_DUAL_TEST","NODE_SYNTAX"})

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

    def test_node_version_gate(self):
        with patch.object(code,"exec_fixed",return_value={"code":0,"output":"v14.21.3"}):
            self.assertFalse(code.node_test_supported())
        with patch.object(code,"exec_fixed",return_value={"code":0,"output":"v22.1.0"}):
            self.assertTrue(code.node_test_supported())
        self.assertEqual(code.TASKS["NODE_SYNTAX"][0][:2],["node","--check"])

    def test_node_core_syntax_targets_are_explicit(self):
        self.assertEqual(len(code.NODE_SYNTAX_FILES),10)
        self.assertEqual(len(set(code.NODE_SYNTAX_FILES)),10)
        self.assertTrue(all(name.startswith(("scripts/","tests/")) and
                            name.endswith(".mjs") for name in code.NODE_SYNTAX_FILES))

    def test_node_core_syntax_short_circuits_on_failure(self):
        calls=[]
        def command(argv,**kwargs):
            calls.append(argv)
            return {"code": 1 if len(calls)==2 else 0,
                    "output":"SyntaxError" if len(calls)==2 else "",
                    "truncated":False}
        with patch.object(code,"exec_fixed",side_effect=command):
            result=code.check_node_files(Path("/tmp/test_worktree"))
        self.assertEqual(result["code"],1)
        self.assertEqual(len(calls),2)
        self.assertEqual(calls[0][:2],["node","--check"])

    def test_node_core_syntax_all_files_are_checked(self):
        calls=[]
        def command(argv,**kwargs):
            calls.append(argv)
            return {"code":0,"output":"","truncated":False}
        with patch.object(code,"exec_fixed",side_effect=command):
            result=code.check_node_files(Path("/tmp/test_worktree"))
        self.assertEqual(result["code"],0)
        self.assertEqual(len(calls),len(code.NODE_SYNTAX_FILES))

    def test_transient_network_retry_is_bounded(self):
        with TemporaryDirectory() as folder:
            with patch.object(code,"STATE",Path(folder)/"jobs.sqlite3"),patch.object(
                    code,"verify_repo",side_effect=["GIT_NETWORK","SHA_NOT_APPROVED"]) as check,patch.object(
                    code.time,"sleep") as sleeper:
                out=code.perform(job("case_retry_001"))
                self.assertEqual(out["status"],"SHA_NOT_APPROVED")
                self.assertEqual(check.call_count,2)
                self.assertEqual(sleeper.call_count,1)

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

    def test_failure_classification_and_counts(self):
        meta=code.error_metadata({"code":1,"output":chr(10).join(["not ok 2 - assertion","# pass 13","# fail 1",""])})
        self.assertEqual(meta["error_category"],"ASSERTION_FAILED")
        self.assertEqual(meta["tests_passed"],13)
        self.assertEqual(meta["tests_failed"],1)
        self.assertRegex(meta["diagnostic_fingerprint"],r"^[0-9a-f]{12}$")

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
