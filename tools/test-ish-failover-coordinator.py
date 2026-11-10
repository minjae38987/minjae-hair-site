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

class FastFailoverTests(unittest.TestCase):
    def capture(self, events, now):
        outputs=[]
        with patch.object(mod,"emit",side_effect=lambda token,prefix,payload:outputs.append((prefix,payload))):
            with patch.object(mod,"read_events",return_value=events):
                mod.tick("unused",now=now)
        return outputs

    def basic(self, created=1000, dispatch=1010):
        return [
            event("MINJAE_AUTO_V1",{"request_id":"probe-101","task":"HEALTH_CHECK"},created),
            event("MINJAE_JOB_V1",{"request_id":"probe-101-actions","runner":"actions",
                "task":"HEALTH_CHECK"},dispatch)]

    def test_probe_waits_from_actions_dispatch_not_creation(self):
        self.assertEqual(self.capture(self.basic(),1049),[])
        out=self.capture(self.basic(),1050)
        self.assertEqual(len(out),1)
        self.assertEqual(out[0][0],mod.ISH)
        self.assertEqual(out[0][1]["request_id"],"probe-101-ish")

    def test_probe_explicit_failure_falls_back_without_delay(self):
        events=self.basic()
        events.append(event("MINJAE_RESULT_V1",
            {"request_id":"probe-101-actions","runner":"actions","task":"HEALTH_CHECK",
             "status":"RUNNER_ERROR"},1015))
        out=self.capture(events,1020)
        self.assertEqual(len(out),1)
        self.assertEqual(out[0][0],mod.ISH)

    def test_probe_success_prioritized_after_expiration(self):
        events=self.basic()
        events.append(event("MINJAE_RESULT_V1",
            {"request_id":"probe-101-actions","runner":"actions","task":"HEALTH_CHECK",
             "status":"OK"},1100))
        out=self.capture(events,4000)
        self.assertEqual(len(out),1)
        self.assertEqual(out[0][1]["status"],"OK")
        self.assertEqual(out[0][1]["runner"],"actions")

    def test_probe_ish_timeout_from_actual_dispatch(self):
        events=self.basic()
        events.append(event("ISH_V3_REQUEST",
            {"request_id":"probe-101-ish","action":"PING"},1500))
        self.assertEqual(self.capture(events,1510),[])
        out=self.capture(events,1740)
        self.assertEqual(len(out),1)
        self.assertEqual(out[0][1]["status"],"TIMED_OUT")

    def test_probe_wrong_task_error_does_not_fail_fast(self):
        events=self.basic()
        events.append(event("MINJAE_RESULT_V1",
            {"request_id":"probe-101-actions","runner":"actions","task":"LUMI_PUBLIC",
             "status":"RUNNER_ERROR"},1015))
        self.assertEqual(self.capture(events,1020),[])

    def test_code_waits_90s_from_actual_dispatch(self):
        records=[
            event("MINJAE_CODE_AUTO_V1",{"request_id":RID,"sha":SHA,
                "task":"PYTHON_SYNTAX"},1000),
            event("MINJAE_CODE_ACTIONS_REQUEST_V1",{"request_id":RID+"-actions",
                "sha":SHA,"task":"PYTHON_SYNTAX"},1050)]
        out=[]
        with patch.object(mod,"emit",side_effect=lambda token,prefix,payload:out.append((prefix,payload))):
            mod.code_tick("unused",records,now=1139)
        self.assertEqual(out,[])
        with patch.object(mod,"emit",side_effect=lambda token,prefix,payload:out.append((prefix,payload))):
            mod.code_tick("unused",records,now=1140)
        self.assertEqual(out[-1][0],mod.CODE_ISH)

    def test_existing_final_never_reemits(self):
        events=self.basic()
        events.append(event("MINJAE_AUTO_RESULT_V1",
            {"request_id":"probe-101","task":"HEALTH_CHECK",
             "status":"OK","runner":"actions","reason":"ACTIONS_CONFIRMED"},1020))
        self.assertEqual(self.capture(events,4000),[])


class IntegrationDiagnosticTests(unittest.TestCase):
    def test_failed_diagnostic_cannot_block_failover(self):
        events=[
            event("MINJAE_AUTO_V1",{"request_id":"diag-probe-001","task":"HEALTH_CHECK"},1000),
            event("MINJAE_JOB_V1",{"request_id":"diag-probe-001-actions",
                  "runner":"actions","task":"HEALTH_CHECK"},1010)]
        emitted=[]
        with patch.object(mod,"read_events",return_value=events):
            with patch.object(mod,"emit",side_effect=lambda token,prefix,obj:emitted.append((prefix,obj))):
                with patch.object(mod,"observe_actions_failure",side_effect=RuntimeError("diagnostic offline")):
                    # A separate observer failure happens after an iSH request was emitted.
                    with self.assertRaises(RuntimeError):
                        mod.tick("token",now=1050)
        self.assertEqual(emitted[0][0],mod.ISH)

    def test_observer_swallows_network_errors(self):
        mod._probe_attempted.clear()
        with patch.object(mod,"SourceFileLoader",side_effect=OSError("offline")):
            mod.observe_actions_failure("token","diag-002-actions",1010,"general")
        self.assertIn("diag-002-actions",mod._probe_attempted)

    def test_observer_only_probes_once_per_process(self):
        mod._probe_attempted.clear()
        with patch.object(mod,"SourceFileLoader",side_effect=OSError("offline")) as loader:
            mod.observe_actions_failure("token","diag-003-actions",1010,"general")
            mod.observe_actions_failure("token","diag-003-actions",1010,"general")
        self.assertEqual(loader.call_count,1)

if __name__=="__main__":
    unittest.main(verbosity=2)
