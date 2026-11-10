#!/bin/sh
# Fail-closed installer and supervisor for iSH code verification.
# Verify the entire candidate release before replacing running files.
set -eu
# Freeze all files to one immutable approved commit to avoid mixed releases.
METADATA=$(curl -fsSL --max-time 35 'https://api.github.com/repos/minjae38987/minjae-hair-site/git/ref/heads/ish-worker-stable')
COMMIT=$(printf '%s' "$METADATA" | python3 -c 'import sys,json,re; x=json.load(sys.stdin)["object"]["sha"]; assert re.fullmatch("[0-9a-f]{40}",x); print(x)')
BASE="https://raw.githubusercontent.com/minjae38987/minjae-hair-site/$COMMIT/tools"
STAGE=$(mktemp -d /root/ish-release.XXXXXX)
COORD_PID=''
umask 077
cleanup() {
  if [ -n "$COORD_PID" ]; then
    kill "$COORD_PID" 2>/dev/null || true
    wait "$COORD_PID" 2>/dev/null || true
  fi
  rm -rf "$STAGE"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP
for name in ish-bridge-v2.py ish-failover-coordinator.py ish-code-runner.py test-ish-code-runner.py test-ish-failover-coordinator.py actions-failure-diagnostic.py test-actions-failure-diagnostic.py actions-run-probe.py test-actions-run-probe.py ish-runtime-status.py test-ish-runtime-status.py ish-safe-write.py test-ish-safe-write.py; do
  curl -fsSL --max-time 35 "$BASE/$name" -o "$STAGE/$name"
done
python3 -m py_compile "$STAGE/ish-bridge-v2.py" "$STAGE/ish-failover-coordinator.py" "$STAGE/ish-code-runner.py" "$STAGE/test-ish-code-runner.py" "$STAGE/test-ish-failover-coordinator.py" "$STAGE/actions-failure-diagnostic.py" "$STAGE/test-actions-failure-diagnostic.py" "$STAGE/actions-run-probe.py" "$STAGE/test-actions-run-probe.py" "$STAGE/ish-runtime-status.py" "$STAGE/test-ish-runtime-status.py" "$STAGE/ish-safe-write.py" "$STAGE/test-ish-safe-write.py"
python3 "$STAGE/test-ish-code-runner.py"
# Coordinator imports the installed underscore-named bridge; provide it in staging.
cp "$STAGE/ish-bridge-v2.py" "$STAGE/ish_bridge_v2.py"
python3 "$STAGE/test-ish-failover-coordinator.py"
python3 "$STAGE/test-actions-failure-diagnostic.py"
python3 "$STAGE/test-actions-run-probe.py"
python3 "$STAGE/test-ish-runtime-status.py"
python3 "$STAGE/test-ish-safe-write.py"
# Only after syntax and regression checks pass, install the complete release.
mv "$STAGE/ish-bridge-v2.py" /root/ish_bridge_v2.py
mv "$STAGE/ish-failover-coordinator.py" /root/ish-failover-coordinator.py
mv "$STAGE/ish-code-runner.py" /root/ish-code-runner.py
mv "$STAGE/actions-failure-diagnostic.py" /root/actions-failure-diagnostic.py
mv "$STAGE/actions-run-probe.py" /root/actions-run-probe.py
mv "$STAGE/ish-runtime-status.py" /root/ish-runtime-status.py
mv "$STAGE/ish-safe-write.py" /root/ish-safe-write.py
chmod 600 /root/ish_bridge_v2.py /root/ish-failover-coordinator.py /root/ish-code-runner.py /root/actions-failure-diagnostic.py /root/actions-run-probe.py /root/ish-runtime-status.py /root/ish-safe-write.py
# Write a manifest only after a fully validated, single-commit release
# has been installed. Old running processes cannot spoof the loaded digests.
python3 - "$COMMIT" <<'PY'
import hashlib, json, os, pathlib, sys, time
sha=sys.argv[1]
root=pathlib.Path("/root")
config=root/".config"/"minjae-ish-bridge"
config.mkdir(mode=0o700,parents=True,exist_ok=True)
files={"bridge":"ish_bridge_v2.py","coordinator":"ish-failover-coordinator.py",
       "code_runner":"ish-code-runner.py",
       "failure_diagnostic":"actions-failure-diagnostic.py",
       "run_probe":"actions-run-probe.py",
       "safe_write":"ish-safe-write.py"}
digests={k:hashlib.sha256((root/v).read_bytes()).hexdigest() for k,v in files.items()}
manifest={"sha":sha,"digests":digests,"installed_at":int(time.time())}
tmp=config/"release.json.tmp"
with open(tmp,"w",encoding="utf-8") as f:json.dump(manifest,f)
os.chmod(tmp,0o600)
os.replace(tmp,config/"release.json")
PY
echo "iSH V6 pinned release $COMMIT: syntax and regression tests passed"
python3 /root/ish-failover-coordinator.py &
COORD_PID=$!
python3 /root/ish_bridge_v2.py
