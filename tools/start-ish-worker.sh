#!/bin/sh
# Update and supervise both restricted iSH worker and failover coordinator.
# No secrets are downloaded; tokens remain stored locally in iSH.
set -eu
BASE='https://raw.githubusercontent.com/minjae38987/minjae-hair-site/ish-worker-stable/tools'
BRIDGE='/root/ish_bridge_v2.py'
COORD='/root/ish-failover-coordinator.py'
TB='/root/.ish_bridge_v2_download.py'
TC='/root/.ish_failover_download.py'
umask 077
cleanup() {
  if [ -n "${COORD_PID:-}" ]; then
    kill "$COORD_PID" 2>/dev/null || true
    wait "$COORD_PID" 2>/dev/null || true
  fi
  rm -f "$TB" "$TC"
}
trap cleanup EXIT HUP INT TERM
curl -fsSL --max-time 35 "$BASE/ish-bridge-v2.py" -o "$TB"
curl -fsSL --max-time 35 "$BASE/ish-failover-coordinator.py" -o "$TC"
python3 -m py_compile "$TB" "$TC"
mv "$TB" "$BRIDGE"
mv "$TC" "$COORD"
chmod 600 "$BRIDGE" "$COORD"
echo 'iSH worker and failover coordinator verified by Python compilation'
python3 "$COORD" &
COORD_PID=$!
python3 "$BRIDGE"
