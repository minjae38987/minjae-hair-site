#!/usr/bin/env python3
"""Evidence-based GitHub Actions run failure classification.

Offline, read-only and deliberately conservative. A failed run or a missing
log is NEVER sufficient evidence of billing exhaustion.
"""
from __future__ import annotations
import json
import re
import sys

QUOTA_MARKERS = (
    "billing and plans",
    "spending limit",
    "actions minutes quota",
    "included minutes have been used",
    "account has exceeded its spending limit",
    "usage limit for github actions",
)
PERMISSION_MARKERS = ("resource not accessible by integration", "permission denied", "http 403")
CONFIG_MARKERS = ("invalid workflow file", "workflow is not valid", "unknown workflow", "yaml parse")
TIMEOUT_MARKERS = ("the job has exceeded the maximum execution time", "the operation was canceled due to timeout")
NETWORK_MARKERS = ("connection timed out", "could not resolve host", "temporary failure in name resolution")


def classify(run, jobs=None, log_text=None, log_state="unavailable"):
    """Return conservative machine-readable diagnosis of one Actions run.

    'log_state' is one of available/unavailable/forbidden. Do not pass
    credentials, secrets, or raw logs into the output.
    """
    if not isinstance(run, dict):
        raise TypeError("run must be a JSON object")
    if log_state not in ("available", "unavailable", "forbidden"):
        raise ValueError("invalid log_state")
    jobs = jobs if isinstance(jobs, list) else []
    status, conclusion = run.get("status"), run.get("conclusion")
    text = log_text.lower()[:300000] if isinstance(log_text, str) else ""
    categories = [
        ("QUOTA_CONFIRMED", QUOTA_MARKERS),
        ("PERMISSION_ERROR", PERMISSION_MARKERS),
        ("WORKFLOW_CONFIG_ERROR", CONFIG_MARKERS),
        ("EXECUTION_TIMEOUT", TIMEOUT_MARKERS),
        ("NETWORK_ERROR", NETWORK_MARKERS),
    ]
    reason = "UNKNOWN"
    evidence = "insufficient_evidence"
    if status in ("queued", "pending", "waiting", "requested", "in_progress"):
        reason, evidence = "RUN_IN_PROGRESS", "run_status"
    elif conclusion == "success":
        reason, evidence = "SUCCESS", "run_conclusion"
    elif conclusion in ("cancelled", "skipped", "timed_out"):
        reason, evidence = {
            "cancelled": "CANCELLED",
            "skipped": "SKIPPED",
            "timed_out": "EXECUTION_TIMEOUT",
        }[conclusion], "run_conclusion"
    else:
        for name, markers in categories:
            if any(marker in text for marker in markers):
                reason, evidence = name, "explicit_log_marker"
                break
        if reason == "UNKNOWN":
            failed_steps = [s for j in jobs if isinstance(j, dict)
                            for s in (j.get("steps") or [])
                            if isinstance(s, dict) and s.get("conclusion") == "failure"]
            if failed_steps:
                reason, evidence = "STEP_FAILED_UNCLASSIFIED", "job_step_conclusion"
            elif conclusion == "failure":
                reason, evidence = "RUN_FAILED_UNCLASSIFIED", "run_conclusion_only"
    return {
        "run_id": run.get("id") if isinstance(run.get("id"), int) else None,
        "status": status,
        "conclusion": conclusion,
        "category": reason,
        "evidence": evidence,
        "logs": log_state,
        "quota_confirmed": reason == "QUOTA_CONFIRMED",
        "failover_eligible": reason in (
            "QUOTA_CONFIRMED", "PERMISSION_ERROR", "WORKFLOW_CONFIG_ERROR",
            "RUN_FAILED_UNCLASSIFIED", "STEP_FAILED_UNCLASSIFIED",
            "NETWORK_ERROR", "EXECUTION_TIMEOUT"
        ),
    }


def main():
    """Input: JSON with run, jobs, log_text, log_state. Output: sanitized JSON."""
    payload = json.load(sys.stdin)
    if not isinstance(payload, dict):
        raise ValueError("expected object")
    result = classify(payload.get("run"), payload.get("jobs"),
                      payload.get("log_text"), payload.get("log_state", "unavailable"))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
