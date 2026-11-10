#!/bin/sh
# Fail-closed installer and supervisor for iSH code verification.
# Verify the entire candidate release before replacing running files.
set -eu
BASE='https://raw.githubusercontent.com/minjae38987/minjae-hair-site/ish-worker-stable/tools'
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
for name in ish-bridge-v2.py ish-failover-coordinator.py ish-code-runner.py test-ish-code-runner.py; do
  curl -fsSL --max-time 35 "$BASE/$name" -o "$STAGE/$name"
done
python3 -m py_compile "$STAGE/ish-bridge-v2.py" "$STAGE/ish-failover-coordinator.py" "$STAGE/ish-code-runner.py" "$STAGE/test-ish-code-runner.py"
python3 "$STAGE/test-ish-code-runner.py"
# Only after syntax and regression checks pass, install the complete release.
mv "$STAGE/ish-bridge-v2.py" /root/ish_bridge_v2.py
mv "$STAGE/ish-failover-coordinator.py" /root/ish-failover-coordinator.py
mv "$STAGE/ish-code-runner.py" /root/ish-code-runner.py
chmod 600 /root/ish_bridge_v2.py /root/ish-failover-coordinator.py /root/ish-code-runner.py
echo 'iSH V4 release verified: Python syntax and code-runner regression suite passed'
python3 /root/ish-failover-coordinator.py &
COORD_PID=$!
python3 /root/ish_bridge_v2.py
