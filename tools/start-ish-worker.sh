#!/bin/sh
# Fixed-source updater/launcher for the allowlisted iSH worker.
# All credentials remain in ~/.config/minjae-ish-bridge; never download token files.
set -eu
BASE='https://raw.githubusercontent.com/minjae38987/minjae-hair-site/ish-worker-stable/tools'
DEST='/root/ish_bridge_v2.py'
TMP='/root/.ish_bridge_v2_download.py'
umask 077
trap 'rm -f "$TMP"' EXIT HUP INT TERM
curl -fsSL --max-time 35 "$BASE/ish-bridge-v2.py" -o "$TMP"
python3 -m py_compile "$TMP"
mv "$TMP" "$DEST"
chmod 600 "$DEST"
echo 'iSH bridge source verified by Python compilation; starting worker'
exec python3 "$DEST"
