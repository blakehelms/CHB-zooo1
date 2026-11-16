#!/bin/sh
# Foreground launch: keep this terminal open; Ctrl+C stops the acquisition owner.
set -eu
umask 077
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$ROOT"
[ "$(uname -s)" = Linux ] || { echo 'Run this launcher on the Raspberry Pi.' >&2; exit 1; }
[ "$(id -u)" -ne 0 ] || { echo 'Launch as the lab user, not root.' >&2; exit 1; }
[ -x .venv/bin/python ] || { echo 'Run bash INSTALL.sh first.' >&2; exit 1; }
export PYTHONDONTWRITEBYTECODE=1
export PYTHONNOUSERSITE=1
# Today's direct, on-Pi bench test uses the existing local settings only.
export ZOOO1_BIND=127.0.0.1
export ZOOO1_PORT=8765
unset ZOOO1_TLS_CERT ZOOO1_TLS_KEY ZOOO1_HOSTS ZOOO1_APPROVED_NETWORK
export ZOOO1_BENCH_RECORDING=${ZOOO1_BENCH_RECORDING:-yes}
export QT_API=pyqt6
export VISPY_APP=pyqt6
printf '%s\n' 'zooo1: http://127.0.0.1:8765 (open in the Pi browser)' \
    'Headset: configured Muse for this Pi' \
    "Existing bench recorder: $ZOOO1_BENCH_RECORDING; recording starts only when Begin is pressed." \
    'Keep this terminal open. End any recording in the browser before Ctrl+C.'
exec .venv/bin/python -m zooo1 "$@"
