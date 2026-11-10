#!/usr/bin/env python3
"""Pinned, allowlisted code verification for iSH (Python 3.9+).

No caller-controlled commands, paths, branches or URLs. Only an explicitly
approved commit reachable from the trusted repository main may be executed.
Run only diagnostic tests on an isolated detached worktree. No videos, no
deployments, no data mutations. Fail closed on missing dependencies.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time

REPO = Path("/root/minjae-ai-hub")
STATE = Path.home() / ".config" / "minjae-ish-bridge" / "code_jobs.sqlite3"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
ID_RE = re.compile(r"^[A-Za-z0-9._-]{4,64}$")
TASKS = {
    "PYTHON_SYNTAX": (["python3", "-m", "compileall", "-q", "scripts", "tests"], 75),
    "NODE_DUAL_TEST": (["node", "--test",
                        "tests/dual_runner_protocol.test.mjs",
                        "tests/dual_runner_router.test.mjs",
                        "tests/dual_runner_coordinator.test.mjs"], 110),
}
# These tests must never write to external services. An explicit profile is
# required to add other suites after review.
MAX_OUTPUT = 180000
TRANSIENT = {"GIT_NETWORK", "RUNNER_TIMEOUT"}
VALID_STATES = {"OK", "TEST_FAILED", "DEPENDENCY_MISSING", "GIT_UNAVAILABLE",
                "SHA_NOT_APPROVED", "RUNNER_TIMEOUT", "EXECUTION_ERROR"}

def exec_fixed(argv, cwd=None, timeout=35, env=None):
    if not isinstance(argv, list) or not argv or any(not isinstance(x, str) for x in argv):
        raise ValueError("invalid_fixed_argv")
    try:
        run = subprocess.run(argv, cwd=str(cwd) if cwd else None,
                             stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             timeout=timeout, env=env, check=False)
        return {"code": run.returncode,
                "output": run.stdout[:MAX_OUTPUT].decode("utf-8", "replace"),
                "truncated": len(run.stdout) > MAX_OUTPUT}
    except subprocess.TimeoutExpired:
        return {"code": 124, "output": "", "truncated": False, "timeout": True}
    except FileNotFoundError:
        return {"code": 127, "output": "", "truncated": False, "missing": True}

def clean_env():
    # Never pass personal GitHub credentials or authentication tokens to
    # scripts checked out from the repository.
    deny = ("TOKEN", "SECRET", "PASSWORD", "COOKIE", "KEY", "AUTH", "CREDENTIAL")
    env = {k: v for k, v in os.environ.items()
           if not any(word in k.upper() for word in deny)}
    env.update({"GIT_TERMINAL_PROMPT": "0", "CI": "1",
                "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
                "PIP_NO_INDEX": "1", "NPM_CONFIG_OFFLINE": "true"})
    return env

def error_metadata(raw):
    """Return stable, low-information diagnostics; never expose raw log lines."""
    data = raw.get("output","") if isinstance(raw,dict) else ""
    patterns = (
        ("MODULE_MISSING", ("modulenotfounderror", "cannot find module", "err_module_not_found")),
        ("SYNTAX_ERROR", ("syntaxerror", "indentationerror", "invalid syntax")),
        ("ASSERTION_FAILED", ("assertionerror", "not ok", "failed assertion")),
        ("DEPENDENCY_ERROR", ("no module named", "command not found")),
    )
    lower = data.lower()
    category = next((name for name, words in patterns if any(w in lower for w in words)), "TEST_FAILURE")
    # No raw stdout, paths, user inputs, environment variables or tokens.
    # Categorization and bounded counters are enough to choose a repair path.
    passed = re.search(r"(?m)^# pass (\d+)\s*$",data)
    failed = re.search(r"(?m)^# fail (\d+)\s*$",data)
    return {"error_category":category,
            "diagnostic_fingerprint":hashlib.sha256(
                (category+"|"+str(raw.get("code"))+"|"+re.sub(r"[0-9]+","#",data[:500])).encode()).hexdigest()[:12],
            "tests_passed":int(passed.group(1)) if passed else None,
            "tests_failed":int(failed.group(1)) if failed else None}

def result(rid, sha, task, status, reason, code=None, elapsed=0, cached=False, metadata=None):
    return {"request_id": rid, "sha": sha, "task": task,
            "status": status, "reason": reason,
            "exit_code": code if isinstance(code, int) else None,
            "duration_ms": max(0, int(elapsed * 1000)),
            "cached": bool(cached), "runner": "ish",
            "logs_exported": False, "video_executed": False,
            "diagnostics": metadata or {}}

def open_db():
    STATE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    db = sqlite3.connect(str(STATE), timeout=10)
    db.execute("""CREATE TABLE IF NOT EXISTS jobs(
        request_id TEXT PRIMARY KEY, sha TEXT NOT NULL, task TEXT NOT NULL,
        result_json TEXT NOT NULL, completed_at INTEGER NOT NULL)""")
    db.commit()
    return db

def validate(req):
    if not isinstance(req, dict) or set(req) != {"request_id", "sha", "task"}:
        raise ValueError("INVALID_FIELDS")
    rid, sha, task = req["request_id"], req["sha"], req["task"]
    if not isinstance(rid, str) or not ID_RE.fullmatch(rid):
        raise ValueError("INVALID_ID")
    if not isinstance(sha, str) or not SHA_RE.fullmatch(sha):
        raise ValueError("INVALID_SHA")
    if task not in TASKS:
        raise ValueError("UNAPPROVED_TASK")
    return rid, sha, task

def verify_repo(sha):
    if not (REPO / ".git").exists():
        return "GIT_UNAVAILABLE"
    # Check origin URL, not just its name: an attacker must not substitute a
    # different remote. SSH and HTTPS are permitted for the fixed owner/repo.
    remote = exec_fixed(["git", "-C", str(REPO), "remote", "get-url", "origin"])
    allowed = ("https://github.com/minjae38987/-2",
               "https://github.com/minjae38987/-2.git",
               "git@github.com:minjae38987/-2.git")
    if remote["code"] != 0 or remote["output"].strip() not in allowed:
        return "GIT_UNAVAILABLE"
    # Fetch trusted branch, then require requested commit to be its ancestor.
    fetch = exec_fixed(["git", "-C", str(REPO), "fetch", "--no-tags",
                        "--depth=1000", "origin", "main"], timeout=50, env=clean_env())
    if fetch.get("timeout") or fetch["code"] != 0:
        return "GIT_NETWORK"
    ref = exec_fixed(["git", "-C", str(REPO), "rev-parse", "FETCH_HEAD"])
    if ref["code"] != 0 or not SHA_RE.fullmatch(ref["output"].strip()):
        return "GIT_UNAVAILABLE"
    parent = exec_fixed(["git", "-C", str(REPO), "merge-base", "--is-ancestor",
                         sha, ref["output"].strip()])
    return "OK" if parent["code"] == 0 else "SHA_NOT_APPROVED"

def perform(req):
    rid, sha, task = validate(req)
    db = open_db()
    try:
        row = db.execute("SELECT sha, task, result_json FROM jobs WHERE request_id=?",
                         (rid,)).fetchone()
        if row:
            if row[0] != sha or row[1] != task:
                return result(rid, sha, task, "EXECUTION_ERROR", "REQUEST_ID_CONFLICT")
            stored = json.loads(row[2])
            stored["cached"] = True
            return stored
        start = time.monotonic()
        repo_status = verify_repo(sha)
        # Only one bounded retry for transient transport failure. A failing
        # test or rejected SHA is deterministic and must never be retried
        # blindly under the same request.
        if repo_status == "GIT_NETWORK":
            time.sleep(2)
            repo_status = verify_repo(sha)
        if repo_status != "OK":
            status = "SHA_NOT_APPROVED" if repo_status == "SHA_NOT_APPROVED" else "GIT_UNAVAILABLE"
            outcome = result(rid, sha, task, status, repo_status, elapsed=time.monotonic()-start)
        else:
            argv, timeout = TASKS[task]
            if shutil.which(argv[0]) is None:
                outcome = result(rid, sha, task, "DEPENDENCY_MISSING",
                                 "RUNTIME_NOT_INSTALLED", code=127, elapsed=time.monotonic()-start)
            else:
                with tempfile.TemporaryDirectory(prefix="minjae-code-", dir="/tmp") as folder:
                    path = Path(folder) / "workspace"
                    added = exec_fixed(["git", "-C", str(REPO), "worktree", "add",
                                        "--detach", str(path), sha], timeout=40, env=clean_env())
                    if added["code"] != 0:
                        outcome = result(rid, sha, task, "EXECUTION_ERROR",
                                         "WORKTREE_FAILED", code=added["code"],
                                         elapsed=time.monotonic()-start)
                    else:
                        try:
                            run = exec_fixed(argv, cwd=path, timeout=timeout, env=clean_env())
                            status = ("RUNNER_TIMEOUT" if run.get("timeout") else
                                      "DEPENDENCY_MISSING" if run.get("missing") else
                                      "OK" if run["code"] == 0 else "TEST_FAILED")
                            outcome = result(rid, sha, task, status,
                                             "PASS" if status == "OK" else status,
                                             code=run["code"], elapsed=time.monotonic()-start,
                                             metadata=error_metadata(run) if status!="OK" else {})
                        finally:
                            exec_fixed(["git", "-C", str(REPO), "worktree", "remove",
                                        "--force", str(path)], timeout=30, env=clean_env())
        # Terminal states are cached: never run the same ID twice, even if a
        # network response was lost or the process restarted.
        db.execute("INSERT INTO jobs VALUES(?,?,?,?,?)",
                   (rid, sha, task, json.dumps(outcome, separators=(",", ":")), int(time.time())))
        db.commit()
        return outcome
    finally:
        db.close()
