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
for name in ish-bridge-v2.py ish-failover-coordinator.py ish-code-runner.py test-ish-code-runner.py test-ish-failover-coordinator.py actions-failure-diagnostic.py test-actions-failure-diagnostic.py actions-run-probe.py test-actions-run-probe.py; do
  curl -fsSL --max-time 35 "$BASE/$name" -o "$STAGE/$name"
done
python3 -m py_compile "$STAGE/ish-bridge-v2.py" "$STAGE/ish-failover-coordinator.py" "$STAGE/ish-code-runner.py" "$STAGE/test-ish-code-runner.py" "$STAGE/test-ish-failover-coordinator.py" "$STAGE/actions-failure-diagnostic.py" "$STAGE/test-actions-failure-diagnostic.py" "$STAGE/actions-run-probe.py" "$STAGE/test-actions-run-probe.py"
python3 "$STAGE/test-ish-code-runner.py"
# Coordinator imports the installed underscore-named bridge; provide it in staging.
cp "$STAGE/ish-bridge-v2.py" "$STAGE/ish_bridge_v2.py"
python3 "$STAGE/test-ish-failover-coordinator.py"
python3 "$STAGE/test-actions-failure-diagnostic.py"
python3 "$STAGE/test-actions-run-probe.py"
# Only after syntax and regression checks pass, install the complete release.
mv "$STAGE/ish-bridge-v2.py" /root/ish_bridge_v2.py
mv "$STAGE/ish-failover-coordinator.py" /root/ish-failover-coordinator.py
mv "$STAGE/ish-code-runner.py" /root/ish-code-runner.py
mv "$STAGE/actions-failure-diagnostic.py" /root/actions-failure-diagnostic.py
mv "$STAGE/actions-run-probe.py" /root/actions-run-probe.py
chmod 600 /root/ish_bridge_v2.py /root/ish-failover-coordinator.py /root/ish-code-runner.py /root/actions-failure-diagnostic.py /root/actions-run-probe.py
echo "iSH V4 pinned release $COMMIT: syntax and regression tests passed"
python3 /root/ish-failover-coordinator.py &
COORD_PID=$!
python3 /root/ish_bridge_v2.py
