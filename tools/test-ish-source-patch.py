#!/usr/bin/env python3
from importlib.machinery import SourceFileLoader
from pathlib import Path
import base64
import hashlib
import urllib.error
import unittest

m=SourceFileLoader("ish_source_patch",str(Path(__file__).with_name("ish-source-patch.py"))).load_module()
BASE="a"*40
BLOB="b"*40
PATH="scripts/dual_runner_protocol.mjs"
ORIGINAL="export const a = 1;\n"
NEW="export const a = 2;\n"
def payload(rid="patch_test01",**kwargs):
    data={"request_id":rid,"action":m.ACTION,"base_sha":BASE,"path":PATH,
          "expected_blob_sha":BLOB,"old_text":"a = 1","new_text":"a = 2",
          "target_sha256":hashlib.sha256(NEW.encode()).hexdigest()}
    data.update(kwargs)
    return data

class API:
    def __init__(self):
        self.calls=[]
        self.main=BASE
        self.branch_sha=None
        self.branch_content=None
        self.writes=0
    def __call__(self,method,path,token,data=None):
        self.calls.append((method,path,data))
        if path.endswith("/git/ref/heads/main"): return {"object":{"sha":self.main}}
        if path.endswith("/git/refs") and method=="POST":
            if self.branch_sha is not None:
                raise urllib.error.HTTPError(path,422,"existing",None,None)
            self.branch_sha=data["sha"]
            return {"object":{"sha":self.branch_sha}}
        if "/git/ref/heads/ish-code-" in path:
            if self.branch_sha is None:raise urllib.error.HTTPError(path,404,"absent",None,None)
            return {"object":{"sha":self.branch_sha}}
        if "/contents/" in path and method=="GET":
            if "ref="+BASE in path:
                data=ORIGINAL
            else:
                data=self.branch_content if self.branch_content is not None else ORIGINAL
            return {"type":"file","sha":BLOB,
                    "content":base64.b64encode(data.encode()).decode()}
        if "/contents/" in path and method=="PUT":
            self.writes+=1
            self.branch_content=base64.b64decode(data["content"]).decode()
            self.branch_sha="c"*40
            return {"commit":{"sha":self.branch_sha}}
        raise AssertionError((method,path))

class Tests(unittest.TestCase):
    def test_success(self):
        api=API()
        value=m.run(api,"secret",payload())
        self.assertEqual((value["status"],value["reason"]),("OK","COMMIT_VERIFIED"))
        self.assertEqual(api.writes,1)
        self.assertEqual(api.branch_content,NEW)
        self.assertFalse(any(x[0]=="PUT" and x[1].endswith("/main") for x in api.calls))

    def test_identical_replay(self):
        api=API()
        self.assertEqual(m.run(api,"secret",payload())["status"],"OK")
        self.assertEqual(m.run(api,"secret",payload())["reason"],"ALREADY_COMMITTED")
        self.assertEqual(api.writes,1)

    def test_conflict_existing_branch(self):
        api=API()
        api.branch_sha=BASE
        self.assertEqual(m.run(api,"secret",payload())["reason"],"EXISTING_BRANCH_CONFLICT")
        self.assertEqual(api.writes,0)

    def test_reject_unapproved_file(self):
        for x in ("tools/ish-bridge-v2.py",".github/workflows/test.yml",
                  "../secret",".env","scripts/unknown.mjs"):
            with self.assertRaises(ValueError):
                m.validate(payload(path=x))

    def test_reject_additional_fields(self):
        with self.assertRaises(ValueError):
            m.validate(payload(shell="cat /etc/passwd"))

    def test_reject_stale_main(self):
        api=API()
        api.main="d"*40
        self.assertEqual(m.run(api,"secret",payload())["reason"],"BASE_SHA_MOVED")
        self.assertEqual(api.writes,0)

    def test_reject_wrong_blob(self):
        api=API()
        self.assertEqual(m.run(api,"secret",payload(expected_blob_sha="e"*40))["reason"],
                         "ORIGINAL_BLOB_MISMATCH")
        self.assertEqual(api.writes,0)

    def test_reject_bad_digest(self):
        api=API()
        self.assertEqual(m.run(api,"secret",payload(target_sha256="0"*64))["reason"],
                         "TARGET_DIGEST_MISMATCH")
        self.assertEqual(api.writes,0)

    def test_reject_nonunique_edit(self):
        api=API()
        self.assertEqual(m.run(api,"secret",payload(old_text="export"))["reason"],
                         "TARGET_DIGEST_MISMATCH")
        self.assertEqual(api.writes,0)
        with self.assertRaises(ValueError):
            m.patch("repeat repeat","repeat","other")

    def test_reject_large_edit_and_noop(self):
        for x in (payload(new_text="x"*1001),payload(old_text=""),
                  payload(new_text="a = 1")):
            with self.assertRaises(ValueError):m.validate(x)

    def test_no_token_in_result(self):
        api=API()
        self.assertNotIn("secret",str(m.run(api,"secret",payload())))

    def test_unapproved_ref_read_not_before_creation(self):
        api=API()
        m.run(api,"secret",payload())
        posts=[i for i,(method,path,_) in enumerate(api.calls) if method=="POST"]
        self.assertEqual(len(posts),1)
        self.assertFalse(any("/git/ref/heads/ish-code-" in path
                             for method,path,_ in api.calls[:posts[0]]))

    def test_403_stage_sanitized(self):
        api=API()
        def denied(method,path,token,data=None):
            if path.endswith("/git/ref/heads/main"):
                raise urllib.error.HTTPError(path,403,"forbidden",None,None)
            return api(method,path,token,data)
        with self.assertRaises(m.PermissionDenied) as e:
            m.run(denied,"secret",payload())
        self.assertEqual(e.exception.phase,"READ_MAIN_REF")

if __name__=="__main__": unittest.main(verbosity=2)
