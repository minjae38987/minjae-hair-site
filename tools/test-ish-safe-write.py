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
            if self.branch is not None:
                raise urllib.error.HTTPError(path,422,"already exists",None,None)
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
        self.assertEqual(m.execute(api,"secret",req())["reason"],"EXISTING_BRANCH_WITHOUT_PROOF")
        self.assertEqual(api.writes,0)
    def test_conflicting_existing_proof_fails(self):
        api=FakeAPI()
        api.branch="b"*40
        api.content=b"malicious"
        self.assertEqual(m.execute(api,"secret",req())["reason"],"EXISTING_PROOF_CONFLICT")
        self.assertEqual(api.writes,0)
    def test_new_branch_never_gets_ref_before_post(self):
        api=FakeAPI()
        self.assertEqual(m.execute(api,"secret",req())["status"],"OK")
        calls=api.calls
        created=next(i for i,c in enumerate(calls) if c[0]=="POST" and c[1].endswith("/git/refs"))
        self.assertFalse(any(c[0]=="GET" and "/git/ref/heads/ish-proof-" in c[1]
                             for c in calls[:created]))

    def test_existing_422_never_overwrites_even_if_same_base(self):
        api=FakeAPI()
        api.branch=SHA
        result=m.execute(api,"secret",req())
        self.assertEqual(result["reason"],"EXISTING_BRANCH_WITHOUT_PROOF")
        self.assertEqual(api.writes,0)

    def test_permission_denied_at_existing_ref_is_reported(self):
        api=FakeAPI()
        api.branch=SHA
        orig=api.__call__
        def forbidden(method,path,token,payload=None):
            if method=="GET" and "/git/ref/heads/ish-proof-" in path:
                raise urllib.error.HTTPError(path,403,"forbidden",None,None)
            return orig(method,path,token,payload)
        with self.assertRaises(m.WriteAccessDenied) as err:
            m.execute(forbidden,"secret",req())
        self.assertEqual(err.exception.phase,"READ_PROOF_REF")
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
        with self.assertRaises(m.WriteAccessDenied) as err:
            m.execute(denied,"secret",req())
        self.assertEqual(err.exception.phase,"WRITE_PROOF_CONTENT")
    def test_main_read_permission_denied_has_safe_phase(self):
        api=FakeAPI()
        orig=api.__call__
        def denied(method,path,token,payload=None):
            if path.endswith("/git/ref/heads/main"):
                raise urllib.error.HTTPError(path,403,"forbidden",None,None)
            return orig(method,path,token,payload)
        with self.assertRaises(m.WriteAccessDenied) as err:
            m.execute(denied,"secret",req())
        self.assertEqual(err.exception.phase,"READ_MAIN_REF")
        self.assertEqual(api.writes,0)

    def test_branch_creation_denied_has_safe_phase(self):
        api=FakeAPI()
        orig=api.__call__
        def denied(method,path,token,payload=None):
            if method=="POST" and path.endswith("/git/refs"):
                raise urllib.error.HTTPError(path,403,"forbidden",None,None)
            return orig(method,path,token,payload)
        with self.assertRaises(m.WriteAccessDenied) as err:
            m.execute(denied,"secret",req())
        self.assertEqual(err.exception.phase,"CREATE_PROOF_REF")
        self.assertEqual(api.writes,0)

    def test_payload_deterministic(self):
        self.assertEqual(m.payload(RID,SHA),m.payload(RID,SHA))

if __name__=="__main__":
    unittest.main(verbosity=2)
