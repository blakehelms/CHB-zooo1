"""Optional desktop-only LSL viewer. Never connects Bluetooth or owns acquisition."""
import fcntl
import os
from pathlib import Path
import subprocess
import sys
import time

from .controller import ADDRESS
from .muse import MuseSource

ROOT = Path(__file__).resolve().parent.parent


def graphical_session():
    if sys.platform == 'darwin':
        return not (os.environ.get('SSH_CONNECTION') or os.environ.get('SSH_TTY'))
    return sys.platform.startswith('linux') and bool(
        os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))


def launch_desktop_viewer(root=ROOT):
    """Fire and forget; even a broken viewer cannot delay browser/acquisition."""
    try:
        if not graphical_session():
            return
        root = Path(root)
        logs = root / 'local-logs'
        logs.mkdir(mode=0o700, exist_ok=True)
        with (logs / 'viewer.log').open('a') as log:
            subprocess.Popen(
                [sys.executable, '-m', 'zooo1.viewer'], cwd=root,
                stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                start_new_session=True, close_fds=True)
    except Exception:
        # Optional display only. Never propagate a launch failure into the service.
        pass


def run_viewer(root=ROOT, wait_seconds=300):
    """One launch per request, with a shared lock while waiting AND viewing."""
    if not graphical_session():
        print('Viewer skipped: no desktop session.', flush=True)
        return
    root = Path(root)
    (root / '.local').mkdir(mode=0o700, exist_ok=True)
    with (root / '.local' / 'viewer.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('Viewer already open or waiting for EEG.', flush=True)
            return
        # Reuse the existing reviewed dependency/provenance check, never connect().
        executable, _inlet, resolve = MuseSource(ADDRESS)._dependencies()
        deadline = time.monotonic() + wait_seconds
        print('Waiting up to 300 seconds for the existing EEG LSL stream.', flush=True)
        while time.monotonic() < deadline:
            matches = resolve(timeout=0.5, source_id=ADDRESS + '_eeg', minimum=2)
            matches = [s for s in matches if s.source_id == ADDRESS + '_eeg']
            if len(matches) > 1:
                raise RuntimeError('Ambiguous EEG stream; viewer not opened.')
            if matches and matches[0].stype == 'EEG':
                # Inherit the lock as well: a surviving GUI still excludes duplicates
                # if this supervisor is unexpectedly killed. No restart loop.
                process = subprocess.Popen(
                    [str(executable), 'view', '--address', ADDRESS],
                    stdin=subprocess.DEVNULL, pass_fds=(lock.fileno(),))
                code = process.wait()
                print(f'Viewer closed (exit {code}); reopen separately if needed.', flush=True)
                return
            time.sleep(1)
        print('No EEG stream found. Turn on headset and reopen the viewer separately.', flush=True)


def main():
    os.umask(0o077)
    try:
        run_viewer()
    except Exception as exc:
        print(f'Viewer unavailable: {exc} Backend/recording are independent.', flush=True)


if __name__ == '__main__':
    main()
