#!/usr/bin/env python3
"""Offline regression for safe, immutable iSH runtime status reporting."""
import hashlib
from importlib.machinery import SourceFileLoader
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

mod=SourceFileLoader("ish_runtime_status_test",str(Path(__file__).with_name("ish-runtime-status.py"))).load_module()

class RuntimeStatusTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        root=Path(self.tmp.name)
        self.release=root/"release.json"
        self.heartbeat=root/"heartbeat.json"
        self.files={name:root/(name+".py") for name in mod.MODULES}
        for name,path in self.files.items():
            path.write_text("version-"+name, encoding="utf-8")
        self.digests={name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in self.files.items()}
        self.release.write_text(json.dumps({"sha":"a"*40,"digests":self.digests}))
        self.heartbeat.write_text(json.dumps({"pid":111,"timestamp":1000,
            "coordinator_digest":self.digests["coordinator"]}))
        self.patches=[
            patch.object(mod,"MODULES",self.files),
            patch.object(mod,"RELEASE",self.release),
            patch.object(mod,"HEARTBEAT",self.heartbeat),
            patch.object(mod,"live_pid",return_value=True),
        ]
        for p in self.patches:p.start()

    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()

    def test_valid_running_release(self):
        d=mod.snapshot(self.digests["bridge"],now=1020)
        self.assertEqual(d["status"],"CURRENT")
        self.assertEqual(d["release_sha"],"a"*40)
        self.assertTrue(d["coordinator_matches_release"])

    def test_old_bridge_process_not_current(self):
        d=mod.snapshot("f"*64,now=1020)
        self.assertEqual(d["status"],"UNVERIFIED")
        self.assertFalse(d["bridge_loaded_matches_release"])

    def test_stale_coordinator_heartbeat_not_current(self):
        d=mod.snapshot(self.digests["bridge"],now=1200)
        self.assertFalse(d["coordinator_heartbeat_recent"])
        self.assertEqual(d["status"],"UNVERIFIED")

    def test_dead_process_not_current(self):
        with patch.object(mod,"live_pid",return_value=False):
            d=mod.snapshot(self.digests["bridge"],now=1020)
        self.assertFalse(d["coordinator_matches_release"])

    def test_missing_diagnostic_file(self):
        self.files["failure_diagnostic"].unlink()
        d=mod.snapshot(self.digests["bridge"],now=1020)
        self.assertFalse(d["modules_installed"]["failure_diagnostic"])
        self.assertFalse(d["modules_verified"]["failure_diagnostic"])
        self.assertEqual(d["status"],"UNVERIFIED")

    def test_modified_coordinator_not_current(self):
        self.files["coordinator"].write_text("modified")
        d=mod.snapshot(self.digests["bridge"],now=1020)
        self.assertFalse(d["modules_verified"]["coordinator"])
        self.assertEqual(d["status"],"UNVERIFIED")

    def test_malformed_manifest_fails_closed(self):
        self.release.write_text(json.dumps({"sha":"a"*40,"digests":["bad"]}))
        d=mod.snapshot(self.digests["bridge"],now=1020)
        self.assertEqual(d["status"],"UNVERIFIED")

    def test_manifest_has_no_token_or_path_leak(self):
        self.files["bridge"].write_text("TOKEN=secret_token_value")
        d=mod.snapshot(self.digests["bridge"],now=1020)
        result=json.dumps(d)
        self.assertNotIn("secret_token_value",result)
        self.assertNotIn(self.tmp.name,result)

    def test_invalid_heartbeat_and_sha(self):
        self.heartbeat.write_text("garbled")
        self.release.write_text(json.dumps({"sha":"not_sha","digests":self.digests}))
        d=mod.snapshot(self.digests["bridge"],now=1020)
        self.assertIsNone(d["release_sha"])
        self.assertFalse(d["coordinator_matches_release"])

    def test_missing_manifest_fails_closed(self):
        self.release.unlink()
        d=mod.snapshot(self.digests["bridge"],now=1020)
        self.assertEqual(d["status"],"UNVERIFIED")

if __name__=="__main__":
    unittest.main(verbosity=2)
