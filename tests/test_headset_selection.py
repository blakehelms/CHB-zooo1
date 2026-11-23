"""Acquisition safety tests. Fake sources only; no Bluetooth or real recordings."""
import ast
import csv
import http.client
import importlib.util
import json
from pathlib import Path
from queue import Empty, Queue
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
APP = Path(__file__).parents[1] / "app"
pkg = types.ModuleType("zooo1")
pkg.__path__ = [str(APP / "zooo1")]
sys.modules.setdefault("zooo1", pkg)
# Substitute only the on-device default lookup for an explicit synthetic test fixture.
source = APP / "zooo1/controller.py"
tree = ast.parse(source.read_bytes())
for node in tree.body:
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "ADDRESS" for t in node.targets):
        node.value = ast.Constant(value="00:55:DA:B9:EC:25")
ast.fix_missing_locations(tree)
ctl = types.ModuleType("zooo1.controller")
ctl.__file__ = str(source)
ctl.__package__ = "zooo1"
sys.modules["zooo1.controller"] = ctl
exec(compile(tree, str(source), "exec"), ctl.__dict__)
from zooo1.web import make_server
from zooo1.acquisition import Sample, SensorBatch
from zooo1.muse import MuseSource

A, B = [x["address"] for x in ctl.HEADSET_CHOICES]

class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.settings = self.root / ".local/zooo1-updater/device.json"
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text(json.dumps({"format":1,"muse_address":A,"other_local_setting":"retain"}))
        self.c = ctl.Controller(self.root, source_factory=lambda: None)

    def test_both_headsets_are_offered_and_default_is_local(self):
        self.settings.write_text(json.dumps({"muse_address":B}))
        c = ctl.Controller(self.root, source_factory=lambda: None)
        self.assertEqual(c.snapshot()["headset_address"], B)
        self.assertEqual({h["address"] for h in c.snapshot()["headset_options"]}, {A,B})

    def test_recording_and_saving_never_switch(self):
        before = self.settings.read_bytes()
        for state in ("recording","saving"):
            self.c.state = state
            with self.assertRaisesRegex(ValueError, "recording"):
                self.c.choose_headset(B)
            self.assertFalse(self.c.switch_requested.is_set())
        self.assertEqual(self.settings.read_bytes(), before)

    def test_unknown_device_is_rejected(self):
        with self.assertRaises(ValueError):
            self.c.choose_headset("00:00:00:00:00:00")

    def test_selection_clears_freshness_and_prevents_begin(self):
        self.c.headset="connected";self.c.last=time.monotonic()
        self.c.points.append([1,2])
        self.c.choose_headset(B)
        self.assertFalse(self.c.snapshot()["can_start"])
        self.assertFalse(self.c.snapshot()["eeg_fresh"])
        self.assertEqual(self.c.snapshot()["points"], [])
        self.assertEqual(self.c.address, A) # New identity not claimed before cleanup.
        with self.assertRaisesRegex(ValueError, "Wait"):
            self.c.choose_headset(A)

    def test_worker_closes_old_owner_before_persisting_new_identity(self):
        seen=[]
        class Old:
            def close(inner):
                seen.append(json.loads(self.settings.read_text())["muse_address"])
        self.c.source=Old()
        self.c.choose_headset(B)
        self.assertTrue(self.c._apply_headset_choice())
        self.assertEqual(seen,[A])
        self.assertEqual(self.c.address,B)
        self.assertEqual(json.loads(self.settings.read_text())["other_local_setting"],"retain")
        self.assertEqual(json.loads(self.settings.read_text())["muse_address"],B)
        self.assertFalse(self.c.switch_requested.is_set())

    def test_cleanup_failure_never_transplants_identity_or_starts_another_owner(self):
        class Broken:
            def close(inner): raise RuntimeError("close failed")
        before=self.settings.read_bytes()
        self.c.source=Broken()
        self.c.choose_headset(B)
        self.assertFalse(self.c._apply_headset_choice())
        self.assertEqual(self.c.address,A)
        self.assertEqual(self.settings.read_bytes(),before)
        self.assertEqual(self.c.connection_issue,"cleanup")

    def test_setting_write_failure_blocks_reconnect(self):
        self.c.choose_headset(B)
        before=self.settings.read_bytes()
        with patch.object(ctl.json,"dump",side_effect=OSError("disk")):
            self.assertFalse(self.c._apply_headset_choice())
        self.assertEqual(self.c.address,A)
        self.assertEqual(self.settings.read_bytes(),before)

    def test_cancel_facade_handles_shutdown_and_selection(self):
        stop=threading.Event();switch=threading.Event()
        cancel=ctl.AcquisitionCancel(stop,switch)
        self.assertFalse(cancel.wait(.001))
        switch.set()
        self.assertTrue(cancel.is_set());self.assertTrue(cancel.wait(1))
        switch.clear();stop.set()
        self.assertTrue(cancel.is_set())

    def test_switch_cancels_inflight_connection_before_new_source(self):
        entered=threading.Event();created=[];closed=[]
        c=self.c
        class Fake:
            def __init__(inner):
                inner.address=c.address;created.append(inner.address)
            def connect(inner,cancel):
                if inner.address==A:
                    entered.set()
                    cancel.wait(2)
                    raise RuntimeError("cancelled")
                return ["EEG"]
            def read(inner,cancel):
                cancel.wait(.01);return []
            def close(inner):
                closed.append(inner.address)
        c.source_factory=Fake
        worker=threading.Thread(target=c.run)
        worker.start()
        try:
            self.assertTrue(entered.wait(1))
            c.choose_headset(B)
            deadline=time.monotonic()+2
            while time.monotonic()<deadline and c.headset!="connected":
                time.sleep(.01)
            self.assertEqual(c.address,B)
            self.assertEqual(c.headset,"connected")
            self.assertEqual(created,[A,B])
            self.assertIn(A,closed)
        finally:
            c.stop.set();worker.join(3)
        self.assertFalse(worker.is_alive())

    def test_recording_metadata_uses_current_selected_identity(self):
        metadata=[]
        class Writer:
            def begin(inner,data,channels): metadata.append(data)
            def event(inner,e): pass
            def close(inner): pass
        self.c.choose_headset(B);self.assertTrue(self.c._apply_headset_choice())
        self.c.writer_factory=Writer;self.c.headset="connected";self.c.last=time.monotonic()
        self.c.begin({"name":"Fictional fixture","dob":"2000-01-01","uin":"","gender":"Other","handedness":"Right"})
        self.assertEqual(metadata[0]["headset_id"],B)

class RouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.c=ctl.Controller(self.root, source_factory=lambda:None)
        self.server=make_server(root=self.root,port=0,controller=self.c)
        self.server.access.configure("fixture-only-passphrase",persist=False)
        self.token=self.server.access.login("fixture-only-passphrase")
        self.csrf=self.server.access.session("zooo1="+self.token)[1]
        self.worker=threading.Thread(target=self.server.serve_forever,daemon=True);self.worker.start()
        self.addCleanup(self.close)
    def close(self):
        self.server.shutdown();self.worker.join(2);self.server.server_close()
    def post(self, cookie=True, csrf=True, origin=True):
        con=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=2)
        headers={"Content-Type":"application/json"}
        if origin:headers["Origin"]="http://127.0.0.1:"+str(self.server.server_port)
        if cookie:headers["Cookie"]="zooo1="+self.token
        if csrf:headers["X-CSRF"]=self.csrf
        con.request("POST","/api/headset",json.dumps({"address":B}),headers)
        response=con.getresponse();status=response.status;response.read();con.close()
        return status
    def test_wrong_origin_is_refused(self):
        self.assertEqual(self.post(origin=False),403)
        self.assertFalse(self.c.switch_requested.is_set())
    def test_authentication_and_csrf_are_required(self):
        self.assertEqual(self.post(cookie=False),401)
        self.assertEqual(self.post(csrf=False),403)
        self.assertFalse(self.c.switch_requested.is_set())
    def test_authenticated_selection_is_queued(self):
        self.assertEqual(self.post(),200)
        self.assertTrue(self.c.switch_requested.is_set())
    def test_recording_route_is_refused(self):
        self.c.state="recording"
        self.assertEqual(self.post(),409)
        self.assertFalse(self.c.switch_requested.is_set())


class SensorCaptureTests(unittest.TestCase):
    FORM = {"name": "Fictional fixture", "dob": "2000-01-01", "uin": "",
            "gender": "Other", "handedness": "Right"}

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def test_session_records_native_rate_streams_and_keeps_eeg_format(self):
        chunks = Queue()

        class FakeMuse:
            sensors = ({}, {})

            def connect(self, cancel):
                return ["TP9", "AF7", "AF8", "TP10"]

            def read(self, cancel):
                try:
                    samples, self.sensors = chunks.get(timeout=0.01)
                    return samples
                except Empty:
                    self.sensors = ({}, {})
                    return []

            def read_sensors(self, cancel):
                return self.sensors

            def event_time(self):
                return 101.25

            def close(self):
                pass

        controller = ctl.Controller(self.root, source_factory=FakeMuse,
                                    writer_factory=lambda: ctl.BenchWriter(self.root / "bench-recordings"))
        worker = threading.Thread(target=controller.run)
        worker.start()
        try:
            chunks.put(([Sample(100.0, (1, 2, 3, 4), time.monotonic())], ({}, {})))
            self.wait_until(lambda: controller.snapshot()["can_start"])
            controller.begin(self.FORM)
            now = time.monotonic()
            sensor_batches = {
                "accgyro": SensorBatch(("AX", "AY", "AZ", "GX", "GY", "GZ"), 52.0, [
                    Sample(100.01, (0, 0, 0, 0, 0, 0), now - 10),
                    Sample(100.02, (1, 2, 3, 4, 5, 6), now),
                    Sample(100.04, (6, 5, 4, 3, 2, 1), now),
                ]),
                "optics": SensorBatch(("NIR1", "NIR2", "IR1", "IR2"), 64.0, [
                    Sample(100.02, (0.1, 0.2, 0.3, 0.4), now),
                ]),
            }
            chunks.put(([Sample(100.04, (5, 6, 7, 8), now)], (sensor_batches, {})))
            self.wait_until(lambda: controller.snapshot()["confirmed"] == 1)
            chunks.put(([Sample(100.07, (8, 7, 6, 5), time.monotonic())],
                        ({}, {"optics": "stream_read_failed"})))
            self.wait_until(lambda: controller.snapshot()["confirmed"] == 2)
            controller.marker()
            controller.end()
        finally:
            controller.stop.set()
            worker.join(3)
        self.assertFalse(worker.is_alive())
        recording, = (self.root / "bench-recordings").iterdir()
        with (recording / "raw.csv").open(newline="") as f:
            header, *eeg = list(csv.reader(f))
        self.assertEqual(header, ["synthetic", "source_time", "received_monotonic_s",
                                  "TP9", "AF7", "AF8", "TP10"])
        self.assertEqual([row[1] for row in eeg], ["100.04", "100.07"])
        with (recording / "accgyro.csv").open(newline="") as f:
            header, *motion = list(csv.reader(f))
        self.assertEqual(header[3:], ["AX", "AY", "AZ", "GX", "GY", "GZ"])
        self.assertEqual([row[1] for row in motion], ["100.02", "100.04"])
        manifest = json.loads((recording / "manifest.json").read_text())
        self.assertEqual(manifest["status"], "complete")
        self.assertEqual(manifest["schema_version"], 2)
        self.assertEqual(manifest["samples"], len(eeg))
        self.assertEqual(manifest["sensor_streams"]["accgyro"]["samples"], len(motion))
        self.assertEqual(manifest["sensor_streams"]["optics"]["samples"], 1)
        self.assertEqual(manifest["sensor_streams"]["optics"]["issue"], "stream_read_failed")
        self.assertEqual(manifest["sensor_streams"]["battery"]["status"], "not_observed")
        self.assertFalse((recording / "battery.csv").exists())
        events = [json.loads(line) for line in (recording / "events.jsonl").read_text().splitlines()]
        self.assertEqual([e["kind"] for e in events], ["manual_start", "researcher_marker", "manual_end"])
        self.assertTrue(all(e["lsl_time"] == 101.25 for e in events))

    def wait_until(self, ready):
        deadline = time.monotonic() + 2
        while not ready() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(ready())

    def test_uses_pinned_openmuse_sensor_arguments_and_closes_inlets(self):
        source = MuseSource(A)
        source_id = A + "_eeg"
        info = types.SimpleNamespace(source_id=source_id, stype="EEG", n_channels=4, sfreq=256.0)
        motion_info = types.SimpleNamespace(source_id=A + "_accgyro", stype="ACCGYRO",
                                            n_channels=6, sfreq=52.0)
        unrelated = types.SimpleNamespace(source_id=B + "_accgyro")
        eeg = self.fake_inlet(["TP9", "AF7", "AF8", "TP10"], (1, 2, 3, 4))
        motion = self.fake_inlet(["AX", "AY", "AZ", "GX", "GY", "GZ"], (0, 1, 0, 0, 5, 0))
        process = types.SimpleNamespace(poll=lambda: None, terminate=lambda: None, wait=lambda **k: None)
        outlets = {}

        def resolve(*, source_id, **kwargs):
            return outlets.get(source_id, [])

        def start(*args, **kwargs):
            outlets[source_id] = [info]
            outlets[motion_info.source_id] = [unrelated, motion_info]
            return process

        with patch.object(source, "_dependencies", return_value=(
            "/fixture/OpenMuse", lambda info, **kw: eeg if info.stype == "EEG" else motion,
            resolve, lambda: 99.0,
        )), patch("zooo1.muse.subprocess.Popen", side_effect=start) as popen:
            source.connect(threading.Event())
            try:
                self.assertEqual(popen.call_args.args[0][4:9],
                                 ["--sensors", "EEG", "ACCGYRO", "OPTICS", "BATTERY"])
                self.assertEqual(source.event_time(), 99.0)
                batches, issues = source.read_sensors(threading.Event())
                self.assertEqual(issues, {})
                self.assertEqual(batches["accgyro"].rate_hz, 52.0)
                self.assertEqual(batches["accgyro"].samples[0].source_time, 100.0)
            finally:
                source.close()
        self.assertTrue(eeg.closed)
        self.assertTrue(motion.closed)
        self.assertEqual(source.sensor_inlets, {})

    def test_malformed_optional_data_leaves_eeg_available(self):
        source = MuseSource(A)
        motion = self.fake_inlet(["AX", "AY", "AZ", "GX", "GY", "GZ"], (0, 1))
        source.sensor_inlets["accgyro"] = (motion, ("AX", "AY", "AZ", "GX", "GY", "GZ"), 52.0)
        source.inlet = self.fake_inlet(["EEG"], (12.3,))
        source.channels = ["EEG"]
        source.process = types.SimpleNamespace(poll=lambda: 0)
        source.next_sensor_check = time.monotonic() + 5
        try:
            batches, issues = source.read_sensors(threading.Event())
            self.assertEqual(batches, {})
            self.assertEqual(issues, {"accgyro": "stream_read_failed"})
            source.process.poll = lambda: None
            self.assertEqual(source.read(threading.Event())[0].values, (12.3,))
        finally:
            source.process.poll = lambda: 0
            source.close()

    @staticmethod
    def fake_inlet(channels, values):
        class Inlet:
            closed = False

            def open_stream(self, timeout):
                pass

            def get_sinfo(self, timeout):
                return types.SimpleNamespace(get_channel_names=lambda: channels)

            def pull_chunk(self, **kwargs):
                return [values], [100.0]

            def close_stream(self):
                self.closed = True

        return Inlet()


if __name__=="__main__":
    unittest.main()
