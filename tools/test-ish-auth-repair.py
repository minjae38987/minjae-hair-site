#!/usr/bin/env python3
"""Offline tests for on-device token repair; never use real credentials."""
from importlib.machinery import SourceFileLoader
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import stat
import unittest
import urllib.error
from unittest.mock import patch

m=SourceFileLoader("ish_auth_repair",str(Path(__file__).with_name("ish-auth-repair.py"))).load_module()
TOKEN="ghp_example_not_real"

def fake_api(path, token):
    if path=="/user": return {"login":"minjae38987"}
    if path=="/repos/minjae38987/-2/git/ref/heads/main":
        return {"object":{"sha":"a"*40}}
    raise AssertionError(path)

class AuthRepairTests(unittest.TestCase):
    def test_valid_token_reads_only_fixed_endpoints(self):
        calls=[]
        def get(path,token):
            calls.append(path)
            return fake_api(path,token)
        self.assertEqual(m.check(TOKEN,get),"READ_VERIFIED")
        self.assertEqual(calls,["/user","/repos/minjae38987/-2/git/ref/heads/main"])

    def test_account_mismatch_fails(self):
        self.assertEqual(m.check(TOKEN,lambda p,t: {"login":"other"}),
                         "ACCOUNT_MISMATCH")

    def test_ref_permission_denied_keeps_old_file(self):
        with TemporaryDirectory() as root:
            path=Path(root)/"github_token"
            path.write_text("old_token\n")
            def fail(path,token):
                if path=="/user":return {"login":"minjae38987"}
                raise urllib.error.HTTPError(path,403,"Forbidden",None,None)
            self.assertEqual(m.check(TOKEN,fail),"TOKEN_OR_REPOSITORY_PERMISSION_403")
            self.assertEqual(path.read_text(),"old_token\n")

    def test_atomic_save_has_private_mode(self):
        with TemporaryDirectory() as root:
            path=Path(root)/".config"/"github_token"
            m.store(TOKEN,path)
            self.assertEqual(path.read_text(),TOKEN+"\n")
            self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)
            self.assertFalse(path.with_name("github_token.new").exists())

    def test_unsupported_whitespace(self):
        self.assertEqual(m.check("not a token",fake_api),"TOKEN_FORMAT_INVALID")

    def test_no_public_token_logging(self):
        with TemporaryDirectory() as root:
            with patch.object(m,"TOKEN_FILE",Path(root)/"github_token"),patch.object(
                    m.getpass,"getpass",return_value=TOKEN),patch.object(
                    m,"check",return_value="READ_VERIFIED"),patch("builtins.print") as printed:
                self.assertEqual(m.main(),0)
                self.assertNotIn(TOKEN,str(printed.call_args_list))

    def test_failed_check_never_overwrites_existing(self):
        with TemporaryDirectory() as root:
            path=Path(root)/"github_token"
            path.write_text("oldsecret\n")
            with patch.object(m,"TOKEN_FILE",path),patch.object(
                    m.getpass,"getpass",return_value=TOKEN),patch.object(
                    m,"check",return_value="TOKEN_OR_REPOSITORY_PERMISSION_403"):
                self.assertEqual(m.main(),1)
            self.assertEqual(path.read_text(),"oldsecret\n")

if __name__=="__main__":
    unittest.main(verbosity=2)
