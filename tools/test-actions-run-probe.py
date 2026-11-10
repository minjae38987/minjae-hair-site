#!/usr/bin/env python3
from importlib.machinery import SourceFileLoader
from pathlib import Path
import unittest
from unittest.mock import patch
import datetime

path=Path(__file__).with_name("actions-run-probe.py")
mod=SourceFileLoader("actions_run_probe_test",str(path)).load_module()

def iso(second):
    return datetime.datetime.fromtimestamp(second,datetime.timezone.utc).isoformat()

def run(ident,when=1010,path=".github/workflows/dual-runner.yml",conclusion="failure"):
    return {"id":ident,"created_at":iso(when),"path":path,"event":"issue_comment",
            "status":"completed","conclusion":conclusion}

class ProbeTests(unittest.TestCase):
    def test_no_candidate_is_unverified(self):
        api=lambda method,path,token:{"workflow_runs":[]}
        x=mod.probe(api,"token",1010,"general")
        self.assertEqual(x["category"],"UNVERIFIED")
        self.assertEqual(x["evidence"],"no_candidate")

    def test_multiple_candidates_are_ambiguous(self):
        api=lambda method,path,token:{"workflow_runs":[run(1),run(2)]}
        x=mod.probe(api,"token",1010,"general")
        self.assertEqual(x["evidence"],"ambiguous_candidates")
        self.assertNotIn("run_id",x)

    def test_one_candidate_never_confirms_quota(self):
        def api(method,path,token):
            if "/jobs?" in path: return {"jobs":[]}
            return {"workflow_runs":[run(3)]}
        x=mod.probe(api,"token",1010,"general")
        self.assertEqual(x["category"],"RUN_FAILED_UNCLASSIFIED")
        self.assertEqual(x["association"],"TIME_PROXIMITY_ONLY")
        self.assertFalse(x["quota_confirmed"])

    def test_different_workflow_not_attributed(self):
        api=lambda method,path,token:{"workflow_runs":[run(1,path=".github/workflows/code-verification-dual.yml")]}
        self.assertEqual(mod.probe(api,"token",1010,"general")["evidence"],"no_candidate")

    def test_far_time_not_attributed(self):
        api=lambda method,path,token:{"workflow_runs":[run(1,when=1100)]}
        self.assertEqual(mod.probe(api,"token",1010,"general")["evidence"],"no_candidate")

    def test_unknown_task_never_calls_api(self):
        def bad(*args): raise AssertionError("must not call")
        x=mod.probe(bad,"token",1010,"SHELL")
        self.assertEqual(x["category"],"UNVERIFIED")

    def test_jobs_failure_step_used(self):
        def api(method,path,token):
            if "/jobs?" in path:return {"jobs":[{"steps":[{"conclusion":"failure"}]}]}
            return {"workflow_runs":[run(9,path=".github/workflows/code-verification-dual.yml")]}
        x=mod.probe(api,"token",1010,"code")
        self.assertEqual(x["category"],"STEP_FAILED_UNCLASSIFIED")

    def test_no_raw_details_leak(self):
        def api(method,path,token):
            if "/jobs?" in path:return {"jobs":[{"steps":[{"name":"secret abc123","conclusion":"failure"}]}]}
            return {"workflow_runs":[run(9)]}
        x=mod.probe(api,"token",1010,"general")
        self.assertNotIn("secret abc123",str(x))

if __name__=="__main__":
    unittest.main(verbosity=2)
