"""Experimental OpenMuse 0.1.8 adapter. Bench testing only; no participant use.

No hardware or optional packages are accessed merely by importing this module.
"""
import importlib.metadata
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit


class DependencyUnavailable(RuntimeError):
    """The reviewed streaming environment is unavailable; no scan was started."""


class MuseSource:
    synthetic = False
    label = "MUSE BENCH TEST — real device data"
    sample_rate = 256

    def __init__(self, address, timeout=15):
        self.address = address.strip()
        if not re.fullmatch(r"[A-Za-z0-9:._-]{4,80}", self.address):
            raise ValueError("Enter the exact headset address from the verified lab setup.")
        self.timeout = max(1.0, min(float(timeout), 12.0))
        self.process = None
        self.inlet = None
        self.channels = []
        self.pending = []

    def _dependencies(self):
        try:
            return self._load_dependencies()
        except Exception as exc:
            raise DependencyUnavailable(str(exc)) from exc

    def _load_dependencies(self):
        if sys.version_info < (3, 12):
            raise RuntimeError("Muse streaming needs Python 3.12+.")
        try:
            dist = importlib.metadata.distribution("OpenMuse")
            if dist.version != "0.1.8":
                raise RuntimeError("Muse bench mode requires reviewed OpenMuse version 0.1.8.")
            provenance = dist.read_text("direct_url.json")
            if not provenance:
                raise RuntimeError("OpenMuse source provenance missing; use the reviewed GitHub install.")
            url = urlsplit(json.loads(provenance).get("url", "").lower())
            repo = "/dominiquemakowski/openmuse"
            valid_path = (url.path == repo or url.path == repo + ".git"
                          or url.path.startswith(repo + "/"))
            if not (url.scheme == "https" and url.hostname in
                    ("github.com", "codeload.github.com") and valid_path):
                raise RuntimeError("OpenMuse installed source is not the reviewed EEG project.")
            from mne_lsl.lsl import StreamInlet, resolve_streams
        except (ImportError, importlib.metadata.PackageNotFoundError) as exc:
            raise RuntimeError("Optional EEG OpenMuse / mne-lsl dependencies are missing. See docs/OPENMUSE.md.") from exc
        executable = Path(sys.prefix) / "bin" / "OpenMuse"
        if not executable.is_file():
            raise RuntimeError("OpenMuse executable missing in this Python environment.")
        return executable, StreamInlet, resolve_streams

    def connect(self, cancel):
        """Two bounded attempts; returns channel names only after receiving samples."""
        if self.process is not None or self.inlet is not None:
            raise RuntimeError("Muse source is already connected or connecting.")
        executable, inlet_class, resolve = self._dependencies()
        if cancel.is_set():
            raise RuntimeError("Connection cancelled.")
        source_id = self.address + "_eeg"
        # Reject an already-running stream rather than attach to someone else's job.
        if resolve(timeout=0.5, source_id=source_id, minimum=2):
            raise RuntimeError("An EEG stream for this address already exists. Stop it before starting zooo1.")
        last_error = "No verified EEG samples arrived."
        for _attempt in range(2):
            deadline = time.monotonic() + self.timeout
            try:
                if cancel.is_set():
                    raise RuntimeError("Connection cancelled.")
                self.process = subprocess.Popen(
                    [str(executable), "stream", "--address", self.address,
                     "--sensors", "EEG", "--clock", "windowed"],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                while time.monotonic() < deadline and not cancel.is_set():
                    if self.process.poll() is not None:
                        raise RuntimeError("OpenMuse exited before a verified stream arrived; check address, Bluetooth and environment.")
                    matches = resolve(timeout=0.5, source_id=source_id, minimum=2)
                    matches = [s for s in matches if s.source_id == source_id]
                    if len(matches) > 1:
                        raise RuntimeError("Ambiguous EEG stream identity; close other streamers.")
                    if not matches:
                        continue
                    info = matches[0]
                    if (info.stype != "EEG" or info.n_channels not in (4, 8)
                            or not math.isclose(float(info.sfreq), 256.0)):
                        raise RuntimeError("EEG metadata does not match the reviewed Muse adapter.")
                    self.inlet = inlet_class(info, max_buffered=5, recover=False,
                                             processing_flags=None)
                    self.inlet.open_stream(timeout=min(1.0, max(0.01, deadline-time.monotonic())))
                    full_info = self.inlet.get_sinfo(timeout=min(1.0, max(0.01, deadline-time.monotonic())))
                    channels = full_info.get_channel_names()
                    if not channels or len(channels) != info.n_channels or any(not c for c in channels):
                        raise RuntimeError("EEG channel labels missing; refusing to guess channel order.")
                    self.channels = list(channels)
                    while time.monotonic() < deadline and not cancel.is_set():
                        self.pending = self._pull()
                        if self.pending:
                            return list(self.channels)
                        if self.process.poll() is not None:
                            raise RuntimeError("OpenMuse exited before delivering EEG samples.")
                        cancel.wait(0.05)
                    break
                raise RuntimeError("Muse connection timed out or was cancelled; no recording started.")
            except Exception as exc:
                last_error = str(exc)
                self.close()
                if cancel.is_set():
                    break
        raise RuntimeError(last_error)

    def _pull(self):
        from .acquisition import Sample
        values, timestamps = self.inlet.pull_chunk(timeout=0.0, max_samples=1024)
        if len(values) != len(timestamps):
            raise RuntimeError("EEG sample/timestamp count mismatch.")
        received = time.monotonic()
        result = []
        for timestamp, row in zip(timestamps, values):
            row = tuple(float(v) for v in row)
            timestamp = float(timestamp)
            if (len(row) != len(self.channels) or not math.isfinite(timestamp)
                    or not all(math.isfinite(v) for v in row)):
                raise RuntimeError("Invalid EEG data received; recording stopped.")
            result.append(Sample(timestamp, row, received))
        return result

    def read(self, cancel):
        if cancel.is_set():
            return []
        if self.inlet is None or self.process is None:
            raise RuntimeError("Muse is not connected.")
        if self.process.poll() is not None:
            raise RuntimeError("Muse streaming process stopped; partial recording retained.")
        if self.pending:
            result, self.pending = self.pending, []
            return result
        result = self._pull()
        if not result:
            cancel.wait(0.02)
        return result

    def close(self):
        """Idempotently close inlet and stop only our owned subprocess."""
        inlet, self.inlet = self.inlet, None
        process, self.process = self.process, None
        self.pending = []
        error = None
        if process is not None:
            try:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=0.5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=0.5)
            except Exception as exc:
                error = exc
        if inlet is not None:
            # The native API offers no timeout. Keep the owned process cleanup
            # independent and never block the controller indefinitely on it.
            closed = threading.Event()
            inlet_errors = []

            def close_inlet():
                try:
                    inlet.close_stream()
                except Exception as exc:
                    inlet_errors.append(exc)
                finally:
                    closed.set()

            threading.Thread(target=close_inlet, name="muse-inlet-cleanup",
                             daemon=True).start()
            if not closed.wait(0.5):
                error = RuntimeError("Native LSL inlet cleanup timed out.")
            elif inlet_errors:
                error = inlet_errors[0]
        if error is not None:
            raise RuntimeError("Muse cleanup failed; verify headset streaming has stopped.") from error
