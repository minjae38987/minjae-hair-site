#!/usr/bin/env python3
"""Bounded, best-effort GitHub Actions diagnosis for iSH failover.

Run association by workflow path and timestamp is heuristic only. Never
declare quota exhaustion or an exact request-to-run match from timestamps.
"""
import datetime
from importlib.machinery import SourceFileLoader
from pathlib import Path

DIAG = SourceFileLoader(
    "actions_failure_diagnostic_probe",
    str(Path(__file__).with_name("actions-failure-diagnostic.py"))
).load_module()

REPO = "/repos/minjae38987/-2"
PATHS = {
    "general": ".github/workflows/dual-runner.yml",
    "code": ".github/workflows/code-verification-dual.yml",
}
MAX_CLOCK_SKEW = 30


def parse_timestamp(value):
    try:
        return datetime.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (AttributeError, ValueError, TypeError):
        return None


def probe(api, token, dispatch_time, category):
    """Return sanitized observation; never assert exact job identity.

    Uses one bounded list request and at most one jobs request. Runs created
    within +/- 30 seconds are candidates, NOT verified matches.
    """
    if category not in PATHS or not isinstance(dispatch_time, (int, float)) or dispatch_time <= 0:
        return {"category": "UNVERIFIED", "evidence": "invalid_dispatch"}
    response = api("GET", REPO + "/actions/runs?event=issue_comment&per_page=40", token)
    if not isinstance(response, dict) or not isinstance(response.get("workflow_runs"), list):
        return {"category": "UNVERIFIED", "evidence": "invalid_runs_response"}
    matches = []
    for run in response["workflow_runs"][:40]:
        if not isinstance(run, dict):
            continue
        t = parse_timestamp(run.get("created_at"))
        if (run.get("event") == "issue_comment" and run.get("path") == PATHS[category]
                and t is not None and abs(t - dispatch_time) <= MAX_CLOCK_SKEW):
            matches.append(run)
    if len(matches) != 1:
        return {"category": "UNVERIFIED", "evidence": "no_candidate" if not matches else "ambiguous_candidates",
                "candidate_count": len(matches)}
    run = matches[0]
    details = []
    if isinstance(run.get("id"), int) and run.get("conclusion") == "failure":
        response = api("GET", REPO + "/actions/runs/" + str(run["id"]) + "/jobs?per_page=20", token)
        if isinstance(response, dict) and isinstance(response.get("jobs"), list):
            details = response["jobs"][:20]
    outcome = DIAG.classify(run, jobs=details, log_state="unavailable")
    # Even one run in the window is not uniquely linked to the request.
    return {
        "category": outcome["category"],
        "evidence": outcome["evidence"],
        "association": "TIME_PROXIMITY_ONLY",
        "run_id": outcome["run_id"],
        "quota_confirmed": False,
        "logs": "unavailable",
    }
