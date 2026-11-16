#!/bin/sh
# Run on the Pi as the regular lab user, from an extracted copy on its local disk.
set -eu
umask 077
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$ROOT"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONNOUSERSITE=1
PYTHON_BIN=${PYTHON_BIN:-python3}
fail() { printf '%s\n' "$*" >&2; exit 1; }
[ "$(uname -s)" = Linux ] || fail 'Run INSTALL.sh on the Raspberry Pi, not on the Mac.'
[ "$(id -u)" -ne 0 ] || fail 'Run as the lab user: bash INSTALL.sh (do not sudo the whole script).'
[ -f /etc/rpi-issue ] || [ -f /proc/device-tree/model ] || fail 'Raspberry Pi OS / Raspberry Pi hardware was not detected.'
[ "$(uname -m)" = aarch64 ] || fail 'This package targets 64-bit Raspberry Pi OS (aarch64); 32-bit OS is not qualified.'
"$PYTHON_BIN" - <<'PY'
import platform, struct, sys
if sys.version_info[:2] != (3, 13) or struct.calcsize('P') != 8:
    raise SystemExit('Use the Pi\'s 64-bit Python 3.13 interpreter. Expected lab version: 3.13.5.')
print('Python:', sys.version.split()[0], '| architecture:', platform.machine())
print('C library:', *platform.libc_ver())
PY
[ ! -L .venv ] || fail '.venv must not be a symbolic link.'
if [ -d .venv ] && [ ! -f .venv/pyvenv.cfg ]; then
    fail 'An unrecognized .venv directory already exists; choose a fresh deployment directory.'
fi
printf '%s\n' 'Installing Pi OS packages (Internet and sudo access required)...'
sudo apt-get update
sudo apt-get install -y python3-venv python3-dev bluez dbus rfkill ca-certificates \
    build-essential cmake libboost-system-dev libpugixml-dev \
    libgl1 libegl1 libopengl0 libfontconfig1 libdbus-1-3 \
    libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-image0 \
    libxcb-keysyms1 libxcb-render-util0 libxcb-xinerama0 libxcb-xkb1
if [ ! -f .venv/pyvenv.cfg ]; then
    "$PYTHON_BIN" -m venv .venv
fi
.venv/bin/python - <<'PY'
import sys
if sys.version_info[:2] != (3, 13) or sys.prefix == sys.base_prefix:
    raise SystemExit('Existing .venv is incompatible; use a fresh deployment directory.')
PY
.venv/bin/python -m pip install --upgrade pip setuptools wheel
.venv/bin/python -m pip install -r requirements.txt
# Native Qt is optional. Its ARM64 wheels require a newer glibc; the existing
# browser monitor can show EEG without Qt. Do not build Qt from source here.
if "$PYTHON_BIN" - <<'PY'
import platform, sys
libc, version = platform.libc_ver()
sys.exit(0 if libc == 'glibc' and tuple(map(int, version.split('.')[:2])) >= (2, 39) else 1)
PY
then
    if ! .venv/bin/python -m pip install --only-binary=:all: -r requirements-viewer.txt; then
        printf '%s\n' 'Optional Qt install failed. Use the browser monitor; see docs/DEPENDENCIES.md.' >&2
    fi
else
    printf '%s\n' 'Optional Qt wheels skipped (glibc below 2.39). Use the existing browser EEG monitor.'
fi
.venv/bin/python -m pip check
.venv/bin/python scripts/check-runtime.py
mkdir -p .local
.venv/bin/python -m pip freeze > .local/dependency-versions.txt
chmod 600 .local/dependency-versions.txt
if ! systemctl is-active --quiet bluetooth; then
    sudo systemctl start bluetooth
fi
printf '\n%s\n' 'Installation complete. No zooo1 service or boot task was installed.' \
    'Power on your assigned Muse headset, then run: bash LAUNCH.sh' \
    'If Bluetooth is blocked, inspect: rfkill list bluetooth' \
    'The install checks do not prove real EEG acquisition; follow README.md.'
