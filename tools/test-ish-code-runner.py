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
        self.assertEqual(set(code.TASKS),{"PYTHON_SYNTAX","NODE_DUAL_TEST","NODE_SYNTAX","NODE_CORE_SYNTAX"})

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

    def test_only_previously_verified_exact_sha_is_eligible_for_offline_reuse(self):
        with TemporaryDirectory() as folder:
            with patch.object(code,"STATE",Path(folder)/"jobs.sqlite3"),patch.object(
                    code,"REPO",Path(folder)):
                # No known-good record: fail closed without trusting local SHA.
                self.assertFalse(code.locally_verified_commit(SHA))
                code.mark_verified_commit(SHA)
                with patch.object(code,"exec_fixed",return_value={"code":0,"output":""}) as check:
                    self.assertTrue(code.locally_verified_commit(SHA))
                    self.assertFalse(code.locally_verified_commit(SHA2))
                    self.assertEqual(check.call_count,1)

    def test_offline_reuse_requires_existing_git_object(self):
        with TemporaryDirectory() as folder:
            with patch.object(code,"STATE",Path(folder)/"jobs.sqlite3"),patch.object(
                    code,"REPO",Path(folder)):
                code.mark_verified_commit(SHA)
                with patch.object(code,"exec_fixed",return_value={"code":1,"output":""}):
                    self.assertFalse(code.locally_verified_commit(SHA))

    def test_upgrade_uses_prior_pass_but_not_prior_failure(self):
        with TemporaryDirectory() as folder:
            base=Path(folder)
            with patch.object(code,"STATE",base/"legacy.sqlite3"),patch.object(
                    code,"REPO",base),patch.object(
                    code,"exec_fixed",return_value={"code":0,"output":""}):
                db=code.open_db()
                db.execute("INSERT INTO jobs VALUES(?,?,?,?,?)",
                           ("old_success",SHA,"NODE_CORE_SYNTAX",
                            __import__("json").dumps(code.result("old_success",SHA,
                               "NODE_CORE_SYNTAX","OK","PASS",code=0)),123))
                db.execute("INSERT INTO jobs VALUES(?,?,?,?,?)",
                           ("old_failure",SHA2,"NODE_CORE_SYNTAX",
                            __import__("json").dumps(code.result("old_failure",SHA2,
                               "NODE_CORE_SYNTAX","TEST_FAILED","TEST_FAILED",code=1)),124))
                db.commit()
                db.close()
                self.assertTrue(code.locally_verified_commit(SHA))
                self.assertFalse(code.locally_verified_commit(SHA2))

    def test_cached_sha_skips_network_fetch(self):
        with TemporaryDirectory() as folder:
            base=Path(folder)
            (base/".git").mkdir()
            actions=[]
            def fake(argv,**kwargs):
                actions.append(argv)
                if argv[-3:]==["remote","get-url","origin"]:
                    return {"code":0,"output":"https://github.com/minjae38987/-2.git"}
                if argv[-3:]==["cat-file","-e",SHA+"^{commit}"]:
                    return {"code":0,"output":""}
                raise AssertionError("Unexpected remote Git fetch on trusted SHA")
            with patch.object(code,"STATE",base/"trust.sqlite3"),patch.object(
                    code,"REPO",base),patch.object(code,"exec_fixed",side_effect=fake):
                code.mark_verified_commit(SHA)
                self.assertEqual(code.verify_repo(SHA),"OK_CACHED")
            self.assertFalse(any("fetch" in argv for argv in actions))

    def test_validated_cache_used_only_after_fetch_failure(self):
        with TemporaryDirectory() as folder:
            base=Path(folder)
            (base/".git").mkdir()
            original="https://github.com/minjae38987/-2.git"
            counter=[0]
            def fake(argv,**kwargs):
                counter[0]+=1
                if argv[-3:] == ["remote","get-url","origin"]:
                    return {"code":0,"output":original}
                if "fetch" in argv:
                    return {"code":1,"output":""}
                return {"code":0,"output":""}
            with patch.object(code,"STATE",base/"verified.sqlite3"),patch.object(
                    code,"REPO",base),patch.object(code,"exec_fixed",side_effect=fake):
                self.assertEqual(code.verify_repo(SHA),"GIT_NETWORK")
                code.mark_verified_commit(SHA)
                self.assertEqual(code.verify_repo(SHA),"OK_CACHED")
                self.assertEqual(code.verify_repo(SHA2),"GIT_NETWORK")

    def test_transient_network_retry_is_bounded(self):
        calls=[]
        def fake(argv, **kwargs):
            calls.append(list(argv))
            return {"code":1,"output":"Could not resolve host"}
        with patch.object(code,"exec_fixed",side_effect=fake),patch.object(code.time,"sleep") as sleep:
            self.assertEqual(code.fetch_main_with_retry(),"GIT_NETWORK")
        self.assertEqual(len(calls),3)
        self.assertEqual(sleep.call_count,2)
        self.assertEqual([c.args[0] for c in sleep.call_args_list],[2,4])
        self.assertTrue(all("fetch" in c and "origin" in c and "main" in c for c in calls))

    def test_fetch_error_classification_has_no_raw_log_in_public_result(self):
        self.assertEqual(code.fetch_failure_kind("fatal: Could not resolve host: github.com"),
                         "TRANSIENT_NETWORK")
        self.assertEqual(code.fetch_failure_kind("remote: Permission to repository denied"),
                         "AUTH_OR_PERMISSION")
        self.assertEqual(code.fetch_failure_kind("unexpected internal error"),
                         "UNKNOWN_GIT_FAILURE")

    def test_network_recovery_second_attempt(self):
        with patch.object(code,"exec_fixed",side_effect=[
                {"code":1,"output":"connection reset"},
                {"code":0,"output":""}]) as run,patch.object(code.time,"sleep") as sleep:
            self.assertEqual(code.fetch_main_with_retry(),"OK")
        self.assertEqual(run.call_count,2)
        self.assertEqual(sleep.call_count,1)

    def test_auth_failure_does_not_retry(self):
        with patch.object(code,"exec_fixed",return_value={
                "code":128,"output":"fatal: Authentication failed"}) as run,patch.object(
                code.time,"sleep") as sleep:
            self.assertEqual(code.fetch_main_with_retry(),"GIT_AUTH")
        self.assertEqual(run.call_count,1)
        sleep.assert_not_called()

    def test_missing_git_does_not_retry(self):
        with patch.object(code,"exec_fixed",return_value={"code":127,"output":"","missing":True}) as run:
            self.assertEqual(code.fetch_main_with_retry(),"GIT_MISSING")
        self.assertEqual(run.call_count,1)

    def test_worker_does_not_duplicate_repo_verification_retries(self):
        with TemporaryDirectory() as folder:
            with patch.object(code,"STATE",Path(folder)/"jobs.sqlite3"),patch.object(
                    code,"verify_repo",return_value="GIT_NETWORK") as check,patch.object(
                    code.time,"sleep") as sleeper:
                out=code.perform(job("case_retry_001"))
                self.assertEqual(out["status"],"GIT_UNAVAILABLE")
                self.assertEqual(out["reason"],"GIT_NETWORK")
                self.assertEqual(check.call_count,1)
                sleeper.assert_not_called()

    def test_auth_error_remains_sanitized(self):
        with TemporaryDirectory() as folder:
            with patch.object(code,"STATE",Path(folder)/"jobs.sqlite3"),patch.object(
                    code,"verify_repo",return_value="GIT_AUTH"):
                out=code.perform(job("case_auth_001"))
                self.assertEqual(out["status"],"GIT_UNAVAILABLE")
                self.assertEqual(out["reason"],"GIT_AUTH")
                self.assertNotIn("token",str(out).lower())

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
