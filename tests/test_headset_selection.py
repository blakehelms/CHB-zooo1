"""Headset selection safety tests. Fake sources only; no Bluetooth or real recording."""
import ast
import http.client
import importlib.util
import json
from pathlib import Path
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
    def post(self, cookie=True, csrf=True):
        con=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=2)
        headers={"Content-Type":"application/json"}
        if cookie:headers["Cookie"]="zooo1="+self.token
        if csrf:headers["X-CSRF"]=self.csrf
        con.request("POST","/api/headset",json.dumps({"address":B}),headers)
        response=con.getresponse();status=response.status;response.read();con.close()
        return status
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

if __name__=="__main__":
    unittest.main()
