#!/usr/bin/env python3
"""iSH-side bounded coordinator for read-only GitHub Actions -> iSH failover.

Issue #22 is the durable event log. Only owner-authored AUTO requests are valid.
No passwords, arbitrary code, URLs, or customer data enter the protocol.
iSH must remain running; this is not an iPadOS background service.
"""
import datetime
import fcntl
import json
import os
import re
import sys
import time
import urllib.error

# The colocated bridge owns token retrieval, the fixed repository and API client.
from importlib.machinery import SourceFileLoader
from pathlib import Path

BRIDGE_PATH = Path(__file__).with_name("ish_bridge_v2.py")
bridge = SourceFileLoader("ish_bridge_v2", str(BRIDGE_PATH)).load_module()
OWNER = "minjae38987"
ISSUE_PATH = "/repos/minjae38987/-2/issues/22/comments"
AUTO = "MINJAE_AUTO_V1 "
FINAL = "MINJAE_AUTO_RESULT_V1 "
ACTIONS = "MINJAE_JOB_V1 "
ACTIONS_RESULT = "MINJAE_RESULT_V1 "
ISH = "ISH_V3_REQUEST "
ISH_RESULT = "ISH_V3_RESULT "
TASKS = {"HEALTH_CHECK": "PING", "LUMI_PUBLIC": "LUMI_PUBLIC"}
ID = re.compile(r"^[A-Za-z0-9._-]{4,64}$")
ACTIONS_WAIT = 180
ISH_WAIT = 240
MAX_AGE = 1800
CODE_AUTO = "MINJAE_CODE_AUTO_V1 "
CODE_ACTIONS = "MINJAE_CODE_ACTIONS_REQUEST_V1 "
CODE_ACTIONS_RESULT = "MINJAE_CODE_ACTIONS_RESULT_V1 "
CODE_ISH = "ISH_CODE_REQUEST_V1 "
CODE_ISH_RESULT = "ISH_CODE_RESULT_V1 "
CODE_FINAL = "MINJAE_CODE_AUTO_RESULT_V1 "
CODE_TASKS = frozenset(("PYTHON_SYNTAX", "NODE_DUAL_TEST"))
SHA = re.compile(r"^[a-f0-9]{40}$")
CODE_ID = re.compile(r"^[A-Za-z0-9._-]{4,50}$")
CODE_ACTIONS_WAIT = 180
CODE_ISH_WAIT = 420


def utc_seconds(value):
    try:
        return datetime.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (ValueError, AttributeError, TypeError):
        return 0.0

def read_events(token):
    # Read the entire event log to reconstruct state after a restart.
    result = []
    for page in range(1, 21):
        batch = bridge.api("GET", ISSUE_PATH + "?per_page=100&page=" + str(page), token)
        if not isinstance(batch, list):
            raise ValueError("invalid_issue_comments")
        result.extend(batch)
        if len(batch) < 100:
            return sorted(result, key=lambda e: int(e.get("id", 0)))
    raise RuntimeError("issue_event_limit")

def event_data(entry, prefix):
    body = entry.get("body") or ""
    if not isinstance(body, str) or len(body) > 1500 or not body.startswith(prefix):
        return None
    try:
        obj = json.loads(body[len(prefix):])
        return obj if isinstance(obj, dict) else None
    except (ValueError, TypeError):
        return None

def author(entry):
    return (entry.get("user") or {}).get("login", "").lower()

def emit(token, prefix, obj):
    body = prefix + json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
    bridge.api("POST", ISSUE_PATH, token, {"body": body})

def index_events(events):
    requests = {}
    actions_jobs = set()
    ish_jobs = set()
    actions_results = {}
    ish_results = {}
    finals = set()
    for entry in events:
        who = author(entry)
        raw = event_data(entry, AUTO)
        if raw and who == OWNER and set(raw) == {"request_id", "task"}:
            rid = raw.get("request_id")
            if isinstance(rid, str) and ID.fullmatch(rid) and raw.get("task") in TASKS:
                requests.setdefault(rid, (raw["task"], utc_seconds(entry.get("created_at"))))
        raw = event_data(entry, ACTIONS)
        if raw and who == OWNER and raw.get("runner") == "actions":
            actions_jobs.add(raw.get("request_id"))
        raw = event_data(entry, ISH)
        if raw and who == OWNER and raw.get("action") in TASKS.values():
            ish_jobs.add(raw.get("request_id"))
        raw = event_data(entry, ACTIONS_RESULT)
        if raw and who in ("github-actions[bot]", OWNER) and raw.get("runner") == "actions":
            actions_results[raw.get("request_id")] = raw
        raw = event_data(entry, ISH_RESULT)
        if raw and who == OWNER and raw.get("action") in TASKS.values():
            ish_results[raw.get("request_id")] = raw
        raw = event_data(entry, FINAL)
        if raw and who == OWNER and isinstance(raw.get("request_id"), str):
            finals.add(raw["request_id"])
    return requests, actions_jobs, ish_jobs, actions_results, ish_results, finals

def result(token, rid, task, status, runner, reason):
    emit(token, FINAL, {"request_id": rid, "task": task, "status": status,
                        "runner": runner, "reason": reason})

def tick(token, now=None):
    now = time.time() if now is None else now
    events = read_events(token)
    requests, aj, ij, ar, ir, finals = index_events(events)
    for rid, (task, created) in requests.items():
        if rid in finals:
            continue
        aid = rid + "-actions"
        iid = rid + "-ish"
        if now - created > MAX_AGE:
            result(token, rid, task, "TIMED_OUT", "none", "REQUEST_EXPIRED")
            continue
        if aid not in aj:
            emit(token, ACTIONS, {"request_id": aid, "runner": "actions", "task": task})
            print("Dispatched Actions:", rid, flush=True)
            continue
        a = ar.get(aid)
        if a and a.get("task") == task and a.get("status") == "OK":
            result(token, rid, task, "OK", "actions", "ACTIONS_CONFIRMED")
            continue
        # Only idempotent, read-only tasks are eligible. Absence of a result
        # is not proof of quota exhaustion. A late Actions run is harmless.
        if now - created < ACTIONS_WAIT and not (a and a.get("status") != "OK"):
            continue
        if iid not in ij:
            emit(token, ISH, {"request_id": iid, "action": TASKS[task]})
            print("Failover to iSH:", rid, flush=True)
            continue
        i = ir.get(iid)
        if i and i.get("status") == "OK" and i.get("action") == TASKS[task]:
            data = i.get("data") or {}
            if (task == "HEALTH_CHECK" and data.get("bridge") == "online") or (
                    task == "LUMI_PUBLIC" and data.get("http_status") == 200):
                result(token, rid, task, "OK", "ish", "ACTIONS_UNCONFIRMED_OR_FAILED")
                continue
        if now - created >= ACTIONS_WAIT + ISH_WAIT:
            result(token, rid, task, "TIMED_OUT", "ish", "NO_CONFIRMED_SUCCESS")
    code_tick(token, events, now)
    return len(requests)

def code_tick(token, events, now):
    """Event-sourced, read-only code verification using one pinned SHA."""
    jobs, actions_sent, ish_sent, ar, ir, finals = {}, set(), set(), {}, {}, set()
    for e in events:
        who = author(e)
        raw = event_data(e, CODE_AUTO)
        if raw and who == OWNER and set(raw) == {"request_id","sha","task"}:
            rid, sha, task = raw.get("request_id"), raw.get("sha"), raw.get("task")
            if isinstance(rid,str) and CODE_ID.fullmatch(rid) and (
                    isinstance(sha,str) and SHA.fullmatch(sha)) and task in CODE_TASKS:
                jobs.setdefault(rid,(sha,task,utc_seconds(e.get("created_at"))))
        raw = event_data(e, CODE_ACTIONS)
        if raw and who == OWNER: actions_sent.add(raw.get("request_id"))
        raw = event_data(e, CODE_ISH)
        if raw and who == OWNER: ish_sent.add(raw.get("request_id"))
        raw = event_data(e, CODE_ACTIONS_RESULT)
        if raw and who in (OWNER,"github-actions[bot]"):
            ar[raw.get("request_id")] = raw
        raw = event_data(e, CODE_ISH_RESULT)
        if raw and who == OWNER:
            ir[raw.get("request_id")] = raw
        raw = event_data(e, CODE_FINAL)
        if raw and who == OWNER and raw.get("request_id"):
            finals.add(raw["request_id"])
    for rid, (sha, task, created) in jobs.items():
        if rid in finals: continue
        aid, iid = rid+"-actions", rid+"-ish"
        def valid(x, runner):
            return (isinstance(x,dict) and x.get("request_id") == (aid if runner=="actions" else iid)
                    and x.get("sha")==sha and x.get("task")==task
                    and x.get("runner")==runner)
        def done(status, runner, reason):
            emit(token,CODE_FINAL,{"request_id":rid,"sha":sha,"task":task,
                                  "status":status,"runner":runner,"reason":reason})
        if now-created>MAX_AGE:
            done("TIMED_OUT","none","REQUEST_EXPIRED")
            continue
        if aid not in actions_sent:
            emit(token,CODE_ACTIONS,{"request_id":aid,"sha":sha,"task":task})
            continue
        a=ar.get(aid)
        if valid(a,"actions") and a.get("status")=="OK":
            done("OK","actions","ACTIONS_CONFIRMED")
            continue
        if now-created<CODE_ACTIONS_WAIT and not valid(a,"actions"):
            continue
        if iid not in ish_sent:
            emit(token,CODE_ISH,{"request_id":iid,"sha":sha,"task":task})
            continue
        i=ir.get(iid)
        if valid(i,"ish") and i.get("status") in (
            "OK","TEST_FAILED","DEPENDENCY_MISSING","SHA_NOT_APPROVED",
            "GIT_UNAVAILABLE","EXECUTION_ERROR","RUNNER_TIMEOUT"):
            done(i["status"],"ish",i.get("reason","ISH_COMPLETED"))
            continue
        if now-created>CODE_ACTIONS_WAIT+CODE_ISH_WAIT:
            done("TIMED_OUT","ish","NO_MATCHING_RESULT")

def main():
    # One active coordinator per iSH installation. A second launcher must not
    # dispatch duplicate jobs while the first process is still running.
    lock_path = Path.home() / ".config" / "minjae-ish-bridge" / "coordinator.lock"
    lock_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock = open(lock_path, "a+")
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("Coordinator already running; duplicate disabled", flush=True)
        return
    token = bridge.token_get()
    print("Dual runner coordinator active; iSH foreground required", flush=True)
    while True:
        try:
            tick(token)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError,
                ValueError, RuntimeError) as exc:
            print("Coordinator retry:", type(exc).__name__, flush=True)
        if "--once" in sys.argv:
            break
        time.sleep(20)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
