"""One acquisition owner. Browser requests never own Bluetooth or writer lifetime."""
from collections import deque
from datetime import date
import json
import os
from pathlib import Path
import threading
import time
import uuid
from .muse import MuseSource, DependencyUnavailable
from .storage import LocalTestStorage

ADDRESS = json.loads((Path(__file__).resolve().parent.parent / '.local' / 'zooo1-updater' / 'device.json').read_text())['muse_address']
ACTIVE = {'recording', 'saving'}

# Public device choices explicitly approved by the lab owner. Selected default stays local.
HEADSET_CHOICES = (
    {"address": "00:55:DA:B9:EC:25", "label": "Muse EC25"},
    {"address": "00:55:DA:B9:EC:29", "label": "Muse EC29"},
)

def selected_address(root):
    path = Path(root) / '.local' / 'zooo1-updater' / 'device.json'
    if not path.exists():
        return ADDRESS
    value = json.loads(path.read_text()).get('muse_address')
    if value not in {h['address'] for h in HEADSET_CHOICES}:
        raise ValueError('The local headset setting is not one of the approved Muse devices.')
    return value


class AcquisitionCancel:
    """Cancel a connection on shutdown or selection, without creating another owner."""
    def __init__(self, stop, switch):
        self.stop, self.switch = stop, switch

    def is_set(self):
        return self.stop.is_set() or self.switch.is_set()

    def wait(self, timeout):
        deadline = time.monotonic() + timeout
        while not self.is_set():
            left = deadline - time.monotonic()
            if left <= 0:
                return False
            self.stop.wait(min(.05, left))
        return True




def validate_form(data):
    """Provisional fields; identifiers stay only in this request, never in storage."""
    if set(data) != {'name', 'dob', 'uin', 'gender', 'handedness'}:
        raise ValueError('Please complete the participant information.')
    if not isinstance(data['name'], str) or not 1 <= len(data['name'].strip()) <= 150:
        raise ValueError('Enter a full name.')
    try:
        born = date.fromisoformat(data['dob'])
        today = date.today()
        age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
        if born > today or age > 120:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError('Enter a valid date of birth.') from None
    if not isinstance(data['uin'], str) or (data['uin'] and not (data['uin'].isascii() and data['uin'].isdigit() and len(data['uin']) == 9)):
        raise ValueError('Check the UIN or leave it blank.')
    if data['gender'] not in ('Male', 'Female', 'Other', 'Prefer not to say'):
        raise ValueError('Select a gender option.')
    if data['handedness'] not in ('Left', 'Right', 'Ambidextrous'):
        raise ValueError('Select a handedness option.')
    return age


class BenchWriter:
    """Tiny writer contract: begin, append, event, finalize, close + confirmed_count.

    No participant metadata is accepted. Replace at the composition boundary for
    reviewed production storage. A durable append acknowledges only fsync'd rows.
    """
    def __init__(self, root):
        self.sink = LocalTestStorage(root)
        self.confirmed_count = 0

    def begin(self, metadata, channels):
        self.sink.preflight(self.sink.root)
        self.sink.begin(metadata, channels)
        self.sink.sync()
        self._sync_directory()

    def _sync_directory(self):
        for path in (self.sink.path, self.sink.root):
            fd = os.open(str(path), os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)

    def append(self, samples, sensors=None, start_mono=None):
        self.sink.append(samples)
        if sensors is not None:
            batches, issues = sensors
            self.sink.append_sensors(batches, issues, start_mono)
        self.sink.sync()
        self.confirmed_count = self.sink.count

    def event(self, event):
        self.sink.event(event)
        self.sink.sync()

    def finalize(self, outcome):
        self.sink.finalize(outcome)
        self._sync_directory()

    def close(self):
        self.sink.close()


class Controller:
    def __init__(self, root, source_factory=None, writer_factory=None):
        self.root = Path(root)
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.address = selected_address(self.root)
        self.requested_address = None
        self.switch_requested = threading.Event()
        self.connection_cancel = AcquisitionCancel(self.stop, self.switch_requested)
        self.source_factory = source_factory or (lambda: MuseSource(self.address))
        self.writer_factory = writer_factory
        self.writer = None
        self.source = None
        self.state = 'ready'
        self.headset = 'unavailable'
        self.connection_issue = None
        self.detail = 'Headset unavailable. Waiting for a verified EEG stream.'
        self.storage = 'not_ready' if writer_factory is None else 'bench_ready'
        self.session_id = None
        self.started = None
        self.ended = None
        self.last = None
        self.last_source = None
        self.received = 0
        self.confirmed = 0
        self.channels = []
        self.points = deque(maxlen=768)
        self.events = deque(maxlen=30)
        self.retry_at = 0
        self.journal = self.root / '.local' / 'session.json'
        self.root.joinpath('.local').mkdir(mode=0o700, exist_ok=True)
        if self.journal.exists():
            saved = json.loads(self.journal.read_text())
            self.session_id = saved.get('session_id')
            self.state = saved.get('state', 'ready')
            self.received = saved.get('received', 0)
            self.confirmed = saved.get('confirmed', 0)
            self.started = saved.get('started')
            self.events.extend(saved.get('events', []))
            self.ended = saved.get('ended')
            self.storage = saved.get('storage', self.storage)
            if self.state in ACTIVE:
                self.state = 'interrupted'
                self.storage = 'incomplete'
                self.ended = time.time()
                self._event('service_restart')
                self._persist()

    def _persist(self):
        data = {k: getattr(self, k) for k in ('state', 'session_id', 'started', 'ended', 'received', 'confirmed', 'storage')}
        data['events'] = list(self.events)
        temp = self.journal.with_suffix('.tmp')
        with temp.open('w') as f:
            json.dump(data, f)
            f.flush()
            os.fsync(f.fileno())
        temp.replace(self.journal)
        fd = os.open(str(self.journal.parent), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def _event(self, kind):
        event = {'kind': kind, 'utc': time.time(), 'received_monotonic': time.monotonic()}
        event_clock = getattr(self.source, 'event_time', None)
        if event_clock is not None:
            event['lsl_time'] = event_clock()
        self.events.append(event)
        if self.writer:
            self.writer.event(event)

    def snapshot(self):
        with self.lock:
            now = time.time()
            fresh = not self.switch_requested.is_set() and self.last is not None and time.monotonic() - self.last < 3
            return dict(state=self.state, headset=self.headset, detail=self.detail,
                        headset_address=self.address, headset_options=list(HEADSET_CHOICES),
                        headset_requested=self.requested_address,
                        can_switch_headset=self.state not in ACTIVE and not self.switch_requested.is_set() and self.connection_issue != 'cleanup',
                        eeg_fresh=fresh, connection_issue=self.connection_issue,
                        storage=self.storage, session_id=self.session_id,
                        elapsed=max(0, (self.ended or now) - self.started) if self.started else 0,
                        sample_age=round(time.monotonic()-self.last, 1) if self.last else None,
                        received=self.received, confirmed=self.confirmed,
                        can_start=self.state == 'ready' and self.writer_factory is not None and fresh and self.headset == 'connected',
                        channels=self.channels, points=list(self.points) if fresh else [],
                        events=list(self.events), battery=None, bench_only=True)

    def begin(self, form):
        validate_form(form)  # Age calculated silently; no identifiers retained in bench mode.
        with self.lock:
            if not self.snapshot()['can_start']:
                raise ValueError('Session cannot start until the headset and recording storage are ready.')
            self.session_id = uuid.uuid4().hex
            self.started = time.time()
            self.start_mono = time.monotonic()
            self.ended = None
            self.received = self.confirmed = 0
            self.events.clear()
            self.writer = self.writer_factory()
            try:
                # Journal before opening any output, so service restart never claims completion.
                self.state = 'recording'
                self.storage = 'opening'
                self._persist()
                self.writer.begin(dict(session_id=self.session_id, started_utc=self.started,
                                       headset_id=self.address, synthetic=False, purpose='NO PARTICIPANTS: BENCH ONLY',
                                       capture_muse_sensors=hasattr(self.source, 'read_sensors')), self.channels)
                self._event('manual_start')
                self.storage = 'writing'
                self._persist()
            except Exception:
                self._storage_failed()
                raise ValueError('Storage could not begin. Recording has not been confirmed.') from None

    def _storage_failed(self):
        self.state = 'storage_failure'
        self.storage = 'failed'
        self.ended = time.time()
        if self.writer:
            try:
                self.writer.close()
            except Exception:
                pass
        self.writer = None
        try:
            self._persist()
        except OSError:
            pass

    def _finish(self, outcome, event):
        if self.state != 'recording':
            raise ValueError('There is no active recording to end.')
        self.state = 'saving'
        self.ended = time.time()
        try:
            self._persist()
            self._event(event)
            self.writer.finalize(outcome)
            self.writer = None
            self.state = outcome
            self.storage = 'saved_bench' if outcome == 'complete' else 'partial_bench'
            self._persist()
        except Exception:
            self._storage_failed()

    def end(self):
        with self.lock:
            self._finish('complete', 'manual_end')

    def marker(self):
        with self.lock:
            if self.state != 'recording':
                raise ValueError('Markers require an active recording.')
            try:
                self._event('researcher_marker')
            except Exception:
                self._storage_failed()

    def reset(self):
        with self.lock:
            if self.state in ACTIVE:
                raise ValueError('End the session before preparing a new one.')
            if self.state == 'ready':
                return
            self.state = 'ready'
            self.session_id = self.started = self.ended = None
            self.received = self.confirmed = 0
            self.events.clear()
            self.storage = 'bench_ready' if self.writer_factory else 'not_ready'
            self._persist()

    def _lost(self):
        self.headset = 'unavailable'
        self.detail = 'Headset data lost. Check power, fit, and Bluetooth range.'
        self.points.clear()
        if self.state == 'recording':
            self._finish('interrupted', 'headset_data_lost')
        else:
            self._event('headset_data_lost')

    def _close_source(self):
        if self.source:
            self.source.close()
            self.source = None


    def choose_headset(self, address):
        if address not in {h['address'] for h in HEADSET_CHOICES}:
            raise ValueError('Choose one of the two approved Muse headsets.')
        with self.lock:
            if self.state in ACTIVE or self.writer is not None:
                raise ValueError('End the recording and wait for saving before changing headsets.')
            if self.connection_issue == 'cleanup':
                raise ValueError('Restart zooo1 before changing headsets after a cleanup failure.')
            if self.switch_requested.is_set():
                raise ValueError('Wait for the current headset change to finish.')
            if address == self.address:
                return
            self.requested_address = address
            self.switch_requested.set()
            self.headset = 'switching'
            self.last = self.last_source = None
            self.points.clear()
            self.detail = 'Changing headset. Waiting for the previous connection to stop.'

    def _apply_headset_choice(self):
        """Acquisition worker only: close owned source before persisting/using a new address."""
        with self.lock:
            if self.state in ACTIVE or self.writer is not None:
                raise RuntimeError('Refusing headset change while a writer is active.')
            try:
                self._close_source()
                path = self.root / '.local' / 'zooo1-updater' / 'device.json'
                settings = json.loads(path.read_text()) if path.exists() else {'format': 1}
                settings['muse_address'] = self.requested_address
                path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                temp = path.with_suffix('.tmp')
                with temp.open('w') as f:
                    os.chmod(temp, 0o600)
                    json.dump(settings, f)
                    f.flush()
                    os.fsync(f.fileno())
                temp.replace(path)
                fd = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
                self.address = self.requested_address
                self.requested_address = None
                self.channels = []
                self.last = self.last_source = None
                self.points.clear()
                self.headset = 'unavailable'
                self.connection_issue = None
                self.detail = 'Headset selected. Waiting for a verified EEG stream.'
                self.switch_requested.clear()
                return True
            except Exception:
                self.headset = 'unavailable'
                self.connection_issue = 'cleanup'
                self.detail = 'Headset change could not finish safely. Restart zooo1 before reconnecting.'
                return False


    def run(self):
        attempts = 0
        while not self.stop.is_set():
            if self.switch_requested.is_set():
                if not self._apply_headset_choice():
                    return
                attempts = 0
            if self.source is None:
                with self.lock:
                    self.connection_issue = None
                    self.headset = 'connecting'
                    self.detail = 'Looking for the known Muse headset.'
                candidate = self.source_factory()
                try:
                    channels = candidate.connect(self.connection_cancel)
                    with self.lock:
                        if self.switch_requested.is_set() or self.stop.is_set():
                            candidate.close()
                            continue
                        self.source = candidate
                        self.channels = channels
                        self.connection_issue = None
                        self.headset = 'connected'
                        self.detail = 'Receiving real EEG samples.'
                        self.last_source = None
                        self.points.clear()
                        self._event('headset_connected')
                    attempts = 0
                except Exception as exc:
                    try:
                        candidate.close()
                    except Exception:
                        with self.lock:
                            self.headset = 'unavailable'
                            self.connection_issue = 'cleanup'
                            self.detail = 'Headset cleanup failed. Restart the service before reconnecting.'
                        return  # Never create a competing Bluetooth owner.
                    if self.switch_requested.is_set():
                        continue
                    attempts += 1
                    with self.lock:
                        self.headset = 'unavailable'
                        self.connection_issue = 'dependencies' if isinstance(exc, DependencyUnavailable) else 'connection'
                        self.detail = ('Headset connection software is unavailable. Ask the researcher to check the reviewed OpenMuse environment. Retrying automatically.'
                                       if self.connection_issue == 'dependencies' else
                                       'Headset not connected. Check power, Bluetooth and range. Retrying automatically.')
                    self.connection_cancel.wait(min(60, 5 * 2 ** min(attempts, 4)))
                    continue
            try:
                samples = self.source.read(self.connection_cancel)
                read_sensors = getattr(self.source, 'read_sensors', None)
                sensors = read_sensors(self.connection_cancel) if read_sensors else None
                sensor_samples = sensors is not None and any(batch.samples for batch in sensors[0].values())
                with self.lock:
                    if self.switch_requested.is_set():
                        continue
                    if samples:
                        # Gaps / backward clocks terminate the current recording. Never concatenate recovery.
                        times = [s.source_time for s in samples]
                        previous = self.last_source
                        gap = any(b <= a or b-a > .1 for a, b in zip(([previous] if previous is not None else []) + times, times if previous is not None else times[1:]))
                        if gap and self.state == 'recording':
                            self._finish('interrupted', 'sample_gap_or_clock_reset')
                        self.last_source = times[-1]
                        self.last = time.monotonic()
                        self.points.extend([[s.source_time, *s.values] for s in samples])
                    elif self.last is not None and time.monotonic() - self.last > 3:
                        raise ConnectionError('No fresh samples')
                    if self.state == 'recording' and (samples or sensor_samples):
                        samples = [s for s in samples if s.received_mono >= self.start_mono]
                        self.received += len(samples)
                        try:
                            if sensors is None:
                                self.writer.append(samples)
                            else:
                                self.writer.append(samples, sensors, self.start_mono)
                            self.confirmed = self.writer.confirmed_count
                            if samples:
                                self._persist()
                        except Exception:
                            self._storage_failed()
                self.stop.wait(.02)
            except Exception:
                if self.switch_requested.is_set():
                    continue
                with self.lock:
                    self._lost()
                try:
                    self._close_source()
                except Exception:
                    with self.lock:
                        self.connection_issue = 'cleanup'
                        self.detail = 'Headset cleanup failed. Restart the service before reconnecting.'
                    return
                self.last = None
                self.stop.wait(5)
        with self.lock:
            if self.state == 'recording':
                self._finish('interrupted', 'service_stop')
        try:
            self._close_source()
        except Exception:
            pass
