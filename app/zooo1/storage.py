"""Checked, local TEST storage. Never a production archive."""
import csv
import json
import os
from pathlib import Path
import time
import uuid
from functools import wraps

from .acquisition import AUXILIARY_STREAMS

def checked(method):
    """A storage error poisons the session: it can never be marked finalized."""
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except Exception:
            self.failed = True
            raise
    return wrapped

class LocalTestStorage:
    def __init__(self, root):
        self.root = Path(root)
        self.handles = []
        self.path = None
        self.count = 0
        self.failed = False
        self.sensor_csvs = {}

    @staticmethod
    def preflight(root):
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ('.write-check-' + uuid.uuid4().hex)
        try:
            with probe.open('x') as f:
                f.write('local test storage check\n')
                f.flush()
                os.fsync(f.fileno())
        finally:
            if probe.exists():
                probe.unlink()

    @checked
    def begin(self, metadata, channels):
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / (time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:12])
        self.path.mkdir(exist_ok=False)
        self.meta = dict(metadata, schema_version=1, channels=channels, status='incomplete',
                         samples=0, storage_purpose='LOCAL TEST ONLY',
                         units='microvolts' if metadata['synthetic'] else 'upstream EEG stream units; verify on hardware')
        if self.meta.pop('capture_muse_sensors', False):
            self.meta.update(schema_version=2, sensor_streams={
                name: dict(file=None, samples=0, channels=None, nominal_rate_hz=None,
                           first_source_time=None, last_source_time=None, non_increasing_timestamps=0,
                           issue=None, status='not_observed')
                for name in AUXILIARY_STREAMS
            }, timing={
                'source_time': 'OpenMuse timestamps in the local LSL clock domain, in seconds',
                'received_monotonic_s': 'Local monotonic time when a chunk was pulled',
                'events_lsl_time': 'Local LSL clock at the event, in seconds',
                'alignment': 'Join source times across streams; inter-stream accuracy has not been bench measured',
            })
        self._manifest('manifest.incomplete.json', self.meta)
        self.raw = (self.path / 'raw.csv').open('x', newline='')
        self.handles.append(self.raw)
        self.events = (self.path / 'events.jsonl').open('x')
        self.handles.append(self.events)
        self.csv = csv.writer(self.raw)
        self.csv.writerow(['synthetic', 'source_time', 'received_monotonic_s'] + channels)
        self.last_sync = time.monotonic()

    def _manifest(self, name, data):
        temp = self.path / (name + '.tmp')
        with temp.open('w') as f:
            json.dump(data, f, indent=2, allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        temp.replace(self.path / name)

    @checked
    def append(self, samples):
        for sample in samples:
            self.csv.writerow([self.meta['synthetic'], sample.source_time,
                               sample.received_mono] + list(sample.values))
            self.count += 1
        if time.monotonic() - self.last_sync >= 1:
            self.sync()

    @checked
    def event(self, event):
        self.events.write(json.dumps(event, allow_nan=False) + '\n')

    @checked
    def append_sensors(self, batches, issues, start_mono):
        streams = self.meta['sensor_streams']
        for name, batch in batches.items():
            stream = streams[name]
            samples = [s for s in batch.samples if s.received_mono >= start_mono]
            if not samples:
                continue
            channels = list(batch.channels)
            if name not in self.sensor_csvs:
                filename = name + '.csv'
                handle = (self.path / filename).open('x', newline='')
                self.handles.append(handle)
                writer = self.sensor_csvs[name] = csv.writer(handle)
                writer.writerow(['synthetic', 'source_time', 'received_monotonic_s', *channels])
                stream.update(file=filename, channels=channels, nominal_rate_hz=batch.rate_hz,
                              first_source_time=samples[0].source_time, status='recorded')
            if channels != stream['channels'] or batch.rate_hz != stream['nominal_rate_hz']:
                raise ValueError('Sensor schema changed within the recording.')
            writer = self.sensor_csvs[name]
            for sample in samples:
                last = stream['last_source_time']
                if last is not None and sample.source_time <= last:
                    stream['non_increasing_timestamps'] += 1
                writer.writerow([self.meta['synthetic'], sample.source_time,
                                 sample.received_mono, *sample.values])
                stream['samples'] += 1
                stream['last_source_time'] = sample.source_time
        for name, issue in issues.items():
            streams[name].update(status='stream_error', issue=issue)

    @checked
    def sync(self):
        for f in self.handles:
            f.flush()
            os.fsync(f.fileno())
        self.last_sync = time.monotonic()

    def finalize(self, outcome, reason=''):
        if self.failed:
            raise OSError('Earlier storage operation failed; files remain incomplete')
        self.sync()
        self.close()
        manifest = dict(self.meta, status=outcome, reason=reason, samples=self.count,
                        ended_utc=time.time())
        self._manifest('manifest.json', manifest)
        (self.path / 'manifest.incomplete.json').unlink()
        return str(self.path)

    def close(self):
        error = None
        for f in self.handles:
            if not f.closed:
                try:
                    f.close()
                except OSError as exc:
                    error = exc
        if error:
            raise error
