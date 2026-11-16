"""Deployment dependency checks only: no scan, BLE connection, or EEG recording."""
from importlib import metadata
import json
from pathlib import Path
import platform
import subprocess
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
REVISION = 'a9be252188321e269537eabf609bc207be293f8c'


def main():
    if platform.system() != 'Linux' or sys.version_info[:2] != (3, 13):
        raise RuntimeError('Run with the Pi Python 3.13 virtual environment.')
    from zooo1.controller import ADDRESS
    from zooo1.muse import MuseSource
    executable, _, _ = MuseSource(ADDRESS)._dependencies()
    dist = metadata.distribution('OpenMuse')
    source = json.loads(dist.read_text('direct_url.json') or '{}')
    url = urlsplit(source.get('url', ''))
    if (url.scheme != 'https' or url.hostname not in ('github.com', 'codeload.github.com')
            or '/DominiqueMakowski/OpenMuse/' not in url.path or REVISION not in url.path):
        raise RuntimeError('OpenMuse must come from the exact GitHub revision in requirements.txt.')
    import bleak
    from bleak.backends.bluezdbus.client import BleakClientBlueZDBus
    from mne_lsl.lsl import StreamInlet, resolve_streams, local_clock
    import numpy, pandas, matplotlib, vispy
    if not callable(StreamInlet) or not callable(resolve_streams) or local_clock() <= 0:
        raise RuntimeError('Native LSL runtime is unavailable.')
    for command, flags in [('stream', ('--address', '--sensors', '--clock')),
                           ('view', ('--address',))]:
        result = subprocess.run([str(executable), command, '--help'], capture_output=True,
                                text=True, timeout=30, check=True)
        if any(flag not in result.stdout for flag in flags):
            raise RuntimeError('Installed OpenMuse CLI does not match the existing adapter.')
    print('PASS: OpenMuse 0.1.8, exact source revision, CLI, BlueZ backend, and native LSL imports.')
    try:
        from PyQt6 import QtCore, QtWidgets
        print('Optional PyQt:', QtCore.PYQT_VERSION_STR, '| Qt:', QtCore.QT_VERSION_STR)
    except (ImportError, OSError):
        print('Optional PyQt6 unavailable. Use the existing browser EEG monitor.')
    print('PASS here means software imports only. Bluetooth acquisition and GUI rendering are not tested.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'Runtime check failed: {exc}', file=sys.stderr)
        raise SystemExit(1)
