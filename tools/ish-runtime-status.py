#!/usr/bin/env python3
"""Read-only, bounded release/process observability for the local iSH worker.

No file contents, paths, tokens, environment variables, logs or arbitrary shell
are exposed. The response is a fixed-schema summary of known worker modules.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import time

ROOT = Path.home()
CONFIG = ROOT / ".config" / "minjae-ish-bridge"
RELEASE = CONFIG / "release.json"
HEARTBEAT = CONFIG / "coordinator-heartbeat.json"
SHA = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
MODULES = {
    "bridge": ROOT / "ish_bridge_v2.py",
    "coordinator": ROOT / "ish-failover-coordinator.py",
    "code_runner": ROOT / "ish-code-runner.py",
    "failure_diagnostic": ROOT / "actions-failure-diagnostic.py",
    "run_probe": ROOT / "actions-run-probe.py",
}

def digest(path):
    try:
        h=hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda:f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except (OSError, ValueError):
        return None

def small_json(path):
    try:
        if path.stat().st_size > 8192:
            return None
        obj=json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj,dict) else None
    except (OSError, ValueError, UnicodeError):
        return None

def live_pid(pid):
    if not isinstance(pid,int) or isinstance(pid,bool) or pid<=1:
        return False
    try:
        os.kill(pid,0)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False

def snapshot(loaded_bridge_digest, now=None):
    now=time.time() if now is None else now
    installed={name:path.is_file() for name,path in MODULES.items()}
    release=small_json(RELEASE)
    valid_release=bool(release and isinstance(release.get("sha"),str) and SHA.fullmatch(release["sha"]))
    expected=(release.get("digests") or {}) if valid_release else {}
    verified={name:(installed[name] and bool(DIGEST.fullmatch(expected.get(name,""))) and
                    digest(path)==expected[name])
              for name,path in MODULES.items()}
    bridge_loaded=bool(DIGEST.fullmatch(loaded_bridge_digest or ""))
    bridge_matches=bool(bridge_loaded and verified["bridge"] and loaded_bridge_digest == expected["bridge"])
    beat=small_json(HEARTBEAT) or {}
    beat_age=now-beat.get("timestamp",0) if isinstance(beat.get("timestamp"),(int,float)) else float("inf")
    recent=0<=beat_age<=90
    running=bool(recent and live_pid(beat.get("pid")) and
                 bool(DIGEST.fullmatch(beat.get("coordinator_digest",""))) and
                 verified["coordinator"] and beat["coordinator_digest"] == expected["coordinator"])
    return {
        "protocol": "ISH_RUNTIME_STATUS_V1",
        "release_sha": release["sha"] if valid_release else None,
        "release_manifest_valid": valid_release,
        "modules_installed": installed,
        "modules_verified": verified,
        "bridge_loaded_matches_release": bridge_matches,
        "coordinator_heartbeat_recent": recent,
        "coordinator_process_alive": live_pid(beat.get("pid")) if recent else False,
        "coordinator_matches_release": running,
        "status": "CURRENT" if valid_release and all(verified.values()) and bridge_matches and running else "UNVERIFIED",
    }
