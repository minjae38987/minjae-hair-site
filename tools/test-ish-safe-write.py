#!/usr/bin/env python3
from importlib.machinery import SourceFileLoader
from pathlib import Path
import base64
import json
import unittest
import urllib.error

m=SourceFileLoader("ish_safe_write",str(Path(__file__).with_name("ish-safe-write.py"))).load_module()
SHA="a"*40
RID="proof_abc1"

class FakeAPI:
    def __init__(self):
        self.calls=[]
        self.base=SHA
        self.branch=None
        self.content=None
        self.writes=0
    def __call__(self,method,path,token,payload=None):
        self.calls.append((method,path,payload))
        if path==m.REPO+"/git/ref/heads/main":return {"object":{"sha":self.base}}
        if path.startswith(m.REPO+"/git/ref/heads/ish-proof-"):
            if self.branch is None:raise urllib.error.HTTPError(path,404,"notfound",None,None)
            return {"object":{"sha":self.branch}}
        if method=="POST" and path==m.REPO+"/git/refs":
            self.branch=payload["sha"];return {"object":{"sha":self.branch}}
        if "/contents/" in path and method=="GET":
            if self.content is None:raise urllib.error.HTTPError(path,404,"notfound",None,None)
            return {"content":base64.b64encode(self.content).decode("ascii")}
        if "/contents/" in path and method=="PUT":
            self.writes+=1
            self.content=base64.b64decode(payload["content"])
            self.branch="b"*40
            return {"commit":{"sha":self.branch}}
        raise AssertionError((method,path))

def req(**kw):
    return dict({"request_id":RID,"base_sha":SHA,"action":"PROOF_COMMIT"},**kw)

class WriteTests(unittest.TestCase):
    def test_rejects_unauthorized_arbitrary_commands(self):
        for item in [dict(req(),shell="rm -rf /"),{"request_id":"../oops","base_sha":SHA,"action":"PROOF_COMMIT"},
                     {"request_id":RID,"base_sha":SHA,"action":"RUN_SHELL"}]:
            with self.assertRaises(ValueError):m.validate(item)
    def test_success_is_verified(self):
        api=FakeAPI()
        result=m.execute(api,"secret",req())
        self.assertEqual(result["status"],"OK")
        self.assertEqual(result["reason"],"COMMIT_VERIFIED")
        self.assertEqual(api.writes,1)
        self.assertEqual(api.content,m.payload(RID,SHA))
        self.assertFalse(any("/contents/README" in x[1] for x in api.calls))
    def test_exact_retry_no_second_write(self):
        api=FakeAPI()
        self.assertEqual(m.execute(api,"secret",req())["status"],"OK")
        self.assertEqual(m.execute(api,"secret",req())["reason"],"ALREADY_COMMITTED")
        self.assertEqual(api.writes,1)
    def test_idempotent_retry_after_main_advances(self):
        api=FakeAPI()
        self.assertEqual(m.execute(api,"secret",req())["status"],"OK")
        api.base="c"*40
        repeat=m.execute(api,"secret",req())
        self.assertEqual(repeat["reason"],"ALREADY_COMMITTED")
        self.assertEqual(api.writes,1)

    def test_stale_base_fails_closed(self):
        api=FakeAPI()
        api.base="b"*40
        self.assertEqual(m.execute(api,"secret",req())["reason"],"BASE_SHA_MISMATCH")
        self.assertEqual(api.writes,0)
    def test_existing_branch_not_owned_fails(self):
        api=FakeAPI()
        api.branch="b"*40
        self.assertEqual(m.execute(api,"secret",req())["reason"],"BRANCH_MOVED_BEFORE_WRITE")
        self.assertEqual(api.writes,0)
    def test_conflicting_existing_proof_fails(self):
        api=FakeAPI()
        api.branch="b"*40
        api.content=b"malicious"
        self.assertEqual(m.execute(api,"secret",req())["reason"],"EXISTING_PROOF_CONFLICT")
        self.assertEqual(api.writes,0)
    def test_branch_creation_uses_fixed_prefix(self):
        api=FakeAPI()
        m.execute(api,"secret",req())
        refs=[p for method,path,p in api.calls if method=="POST" and path.endswith("/git/refs")]
        self.assertEqual(refs[0]["ref"],"refs/heads/ish-proof-"+RID)
    def test_secret_never_in_output(self):
        api=FakeAPI()
        result=m.execute(api,"secret_token_abc",req())
        self.assertNotIn("secret_token_abc",json.dumps(result))
    def test_missing_write_permission_not_success(self):
        api=FakeAPI()
        original=api.__call__
        def denied(method,path,token,payload=None):
            if method=="PUT":raise urllib.error.HTTPError(path,403,"forbidden",None,None)
            return original(method,path,token,payload)
        result=m.execute(denied,"secret",req())
        self.assertEqual(result["reason"],"WRITE_FAILED_HTTP_403")
    def test_payload_deterministic(self):
        self.assertEqual(m.payload(RID,SHA),m.payload(RID,SHA))

if __name__=="__main__":
    unittest.main(verbosity=2)
