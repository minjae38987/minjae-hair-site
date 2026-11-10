#!/usr/bin/env python3
"""Offline regression for failover timekeeping and terminal result precedence."""
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest.mock import patch
import datetime
import unittest

path=Path(__file__).with_name("ish-failover-coordinator.py")
mod=SourceFileLoader("ish_failover_coordinator_test",str(path)).load_module()
SHA="a"*40
RID="regression-v4-check-001"
def event(prefix,payload,seconds):
    return {"user":{"login":"minjae38987"},
            "created_at":datetime.datetime.fromtimestamp(seconds,datetime.timezone.utc).isoformat(),
            "body":prefix+" "+__import__("json").dumps(payload)}
def base(created=1000):
    return [
        event("MINJAE_CODE_AUTO_V1",{"request_id":RID,"sha":SHA,"task":"PYTHON_SYNTAX"},created),
        event("MINJAE_CODE_ACTIONS_REQUEST_V1",{"request_id":RID+"-actions","sha":SHA,"task":"PYTHON_SYNTAX"},created+10),
        event("ISH_CODE_REQUEST_V1",{"request_id":RID+"-ish","sha":SHA,"task":"PYTHON_SYNTAX"},created+600)]
class CoordinatorTests(unittest.TestCase):
    def test_ish_timeout_counts_from_dispatch(self):
        outputs=[]
        with patch.object(mod,"emit",side_effect=lambda token,prefix,payload:outputs.append((prefix,payload))):
            mod.code_tick("unused",base(),now=1610)
        self.assertEqual(outputs,[],"iSH must not time out ten seconds after dispatch")
    def test_ish_result_wins_over_elapsed_limit(self):
        events=base()
        events.append(event("ISH_CODE_RESULT_V1",
                            {"request_id":RID+"-ish","sha":SHA,"task":"PYTHON_SYNTAX",
                             "runner":"ish","status":"OK","reason":"PASS"},1800))
        outputs=[]
        with patch.object(mod,"emit",side_effect=lambda token,prefix,payload:outputs.append((prefix,payload))):
            mod.code_tick("unused",events,now=4000)
        self.assertEqual(len(outputs),1)
        self.assertEqual(outputs[0][1]["status"],"OK")
        self.assertEqual(outputs[0][1]["runner"],"ish")
    def test_expired_ish_dispatch_times_out(self):
        outputs=[]
        with patch.object(mod,"emit",side_effect=lambda token,prefix,payload:outputs.append((prefix,payload))):
            mod.code_tick("unused",base(),now=2100)
        self.assertEqual(len(outputs),1)
        self.assertEqual(outputs[0][1]["status"],"TIMED_OUT")
    def test_no_duplicate_if_final_exists(self):
        events=base()
        events.append(event("MINJAE_CODE_AUTO_RESULT_V1",
                            {"request_id":RID,"sha":SHA,"task":"PYTHON_SYNTAX",
                             "runner":"ish","status":"OK"},1800))
        outputs=[]
        with patch.object(mod,"emit",side_effect=lambda token,prefix,payload:outputs.append((prefix,payload))):
            mod.code_tick("unused",events,now=4000)
        self.assertEqual(outputs,[])
if __name__=="__main__":
    unittest.main(verbosity=2)
