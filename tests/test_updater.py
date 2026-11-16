import fcntl
import importlib.util
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("updater", Path(__file__).parents[1] / "tools/update_zooo1.py")
u = importlib.util.module_from_spec(spec)
spec.loader.exec_module(u)

class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "app"
        self.root.mkdir()
        for n in u.MANAGED:
            p = self.root / n
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("# baseline\n")
        (self.root / "zooo1/__main__.py").write_text(u.GATE)
        self.sd = u.state_dir(self.root)
        self.sd.mkdir(parents=True)
        self.env = {"python": [3,13,5], "packages": [["example","1"]]}
        self.state = {"version": "zip-baseline", "files": u.inventory(self.root), "environment": self.env}
        u.dump(self.sd / "state.json", self.state)
        self.protected = {n: b"private-device-data" for n in [
            ".local/auth.json", ".local/session.json", "bench-recordings/raw.csv",
            "config.json", "zooo1/config.py", ".venv/marker"]}
        for n, value in self.protected.items():
            p = self.root / n
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(value)

    def artifact(self, malicious=None):
        data = {n: (self.root / n).read_bytes() for n in u.MANAGED}
        data["zooo1/web.py"] = b"# new code\n"
        files = {n: u.digest(v) for n,v in data.items()}
        manifest = {"format":1, "version":"v0.1.1", "files":files, "environment":self.env,
                    "dependencies":{n:files[n] for n in ("requirements.txt","requirements-viewer.txt")}}
        path = Path(self.tmp.name) / "release.tar.gz"
        with tarfile.open(path, "w:gz") as t:
            entries = {"release.json":json.dumps(manifest).encode(), **data}
            if malicious:
                entries[malicious] = b"bad"
            for n,v in entries.items():
                m = tarfile.TarInfo(n)
                m.size = len(v)
                t.addfile(m, io.BytesIO(v))
        return path, u.digest(path.read_bytes())

    def install(self, verify=None):
        path, sha = self.artifact()
        with patch.object(u, "proc_check"), patch.object(u, "environment", return_value=self.env), \
             patch.object(u, "verify", side_effect=verify), patch("builtins.input", return_value="INSTALL v0.1.1"):
            u.apply(self.root, path, "v0.1.1", sha)

    def assert_protected(self):
        for n, value in self.protected.items():
            self.assertEqual((self.root / n).read_bytes(), value)

    def test_install_and_rollback_preserve_data_and_environment(self):
        self.install()
        self.assertEqual((self.root / "zooo1/web.py").read_bytes(), b"# new code\n")
        self.assertEqual(u.load_state(self.root)["version"], "v0.1.1")
        with patch.object(u, "proc_check"), patch.object(u, "verify"), \
             patch.object(u, "environment", return_value=self.env):
            u.recover(self.root, rollback=True)
        self.assertEqual(u.inventory(self.root), self.state["files"])
        self.assert_protected()

    def test_failed_verification_automatically_restores(self):
        with self.assertRaises(RuntimeError):
            self.install(verify=[RuntimeError("bad runtime"), None])
        self.assertEqual(u.inventory(self.root), self.state["files"])
        self.assertFalse((self.sd / "pending.json").exists())
        self.assert_protected()

    def test_interrupted_update_recovers(self):
        u.snapshot(self.root, self.state, set(self.state["files"]))
        (self.root / "zooo1/web.py").write_text("# partial")
        with patch.object(u, "proc_check"), patch.object(u, "verify"):
            u.recover(self.root)
        self.assertEqual(u.inventory(self.root), self.state["files"])
        self.assert_protected()

    def test_bad_digest_refused(self):
        path, _ = self.artifact()
        with self.assertRaisesRegex(RuntimeError, "digest mismatch"):
            u.read_release(path, "v0.1.1", "0"*64)

    def test_wrong_version_refused(self):
        path, sha = self.artifact()
        with self.assertRaisesRegex(RuntimeError, "Version/format"):
            u.read_release(path, "v0.2.0", sha)

    def test_data_and_traversal_paths_refused(self):
        for n in ("../escape.py", ".local/auth.json", "bench-recordings/raw.csv",
                  "zooo1/config.py", "zooo1/__main__.py", ".venv/bin/python"):
            with self.subTest(n=n):
                path, sha = self.artifact(n)
                with self.assertRaisesRegex(RuntimeError, "Disallowed"):
                    u.read_release(path, "v0.1.1", sha)

    def test_symlink_refused(self):
        p = self.root / "zooo1/web.py"
        p.unlink()
        p.symlink_to(self.root / ".local/auth.json")
        with self.assertRaisesRegex(RuntimeError, "Symlink"):
            u.safe_path(self.root, "zooo1/web.py")

    def test_local_edits_refused(self):
        (self.root / "zooo1/web.py").write_text("# pi edits")
        with patch.object(u, "environment", return_value=self.env):
            with self.assertRaisesRegex(RuntimeError, "Local application edits"):
                u.check_clean(self.root, self.state)

    def test_dependency_drift_refused(self):
        with patch.object(u, "environment", return_value={}):
            with self.assertRaisesRegex(RuntimeError, "drift"):
                u.check_clean(self.root, self.state)

    def test_live_service_lock_refused(self):
        with (self.root / ".local/service.lock").open("a") as f:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(RuntimeError, "running"):
                with u.stopped(self.root, legacy=False):
                    self.fail("Should not enter")

    def test_startup_shared_gate_excludes_updates(self):
        with (self.root / ".local/update.lock").open("a") as f:
            fcntl.flock(f, fcntl.LOCK_SH | fcntl.LOCK_NB)
            with self.assertRaisesRegex(RuntimeError, "running"):
                with u.stopped(self.root, legacy=False):
                    self.fail("Should not enter")

    def test_pending_transaction_refused(self):
        u.dump(self.sd / "pending.json", {})
        with self.assertRaisesRegex(RuntimeError, "Incomplete transaction"):
            self.install()

    def test_dependency_change_refused(self):
        path, sha = self.artifact()
        state = dict(self.state)
        state["files"] = dict(state["files"], **{"requirements.txt":"different"})
        u.dump(self.sd / "state.json", state)
        with patch.object(u, "proc_check"), patch.object(u, "check_clean"):
            with self.assertRaisesRegex(RuntimeError, "Dependency changes"):
                u.apply(self.root, path, "v0.1.1", sha)

    def test_unapproved_confirmation_cancels(self):
        path, sha = self.artifact()
        with patch.object(u, "proc_check"), patch.object(u, "environment", return_value=self.env), \
             patch("builtins.input", return_value="yes"):
            with self.assertRaisesRegex(RuntimeError, "Cancelled"):
                u.apply(self.root, path, "v0.1.1", sha)
        self.assertEqual(u.inventory(self.root), self.state["files"])

    def test_process_check_does_not_inspect_unrelated_cwd(self):
        proc = Path(self.tmp.name) / "proc"
        entry = proc / "99999999"
        entry.mkdir(parents=True)
        (entry / "cmdline").write_bytes(b"/usr/bin/dbus-daemon\\0")
        (proc / "self").mkdir()
        (proc / "self/cmdline").write_bytes(b"python3")
        real_path = Path
        def fake_path(value):
            return proc if value == "/proc" else proc / "self/cmdline"
        with patch.object(u, "Path", side_effect=fake_path), \
             patch.object(real_path, "resolve", side_effect=PermissionError("protected cwd")):
            u.proc_check(self.root)
        (entry / "cmdline").write_bytes(b"python3 -m zooo1 --no-browser")
        with patch.object(u, "Path", side_effect=fake_path):
            with self.assertRaisesRegex(RuntimeError, "Close zooo1"):
                u.proc_check(self.root)

    def test_embedded_device_identity_is_not_transplanted(self):
        path, sha = self.artifact()
        (self.root / "zooo1/controller.py").write_text("ADDRESS = 'device-two'\n")
        state = dict(self.state, files=u.inventory(self.root))
        u.dump(self.sd / "state.json", state)
        with patch.object(u, "proc_check"), patch.object(u, "environment", return_value=self.env):
            with self.assertRaisesRegex(RuntimeError, "headset configuration differs"):
                u.apply(self.root, path, "v0.1.1", sha)
        self.assertEqual((self.root / "zooo1/controller.py").read_text(), "ADDRESS = 'device-two'\n")
        self.assert_protected()

    def test_links_and_duplicates_refused(self):
        for link in (True, False):
            path = Path(self.tmp.name) / "bad.tar.gz"
            with tarfile.open(path, "w:gz") as t:
                for _ in range(1 if link else 2):
                    m = tarfile.TarInfo("release.json")
                    if link:
                        m.type = tarfile.SYMTYPE
                        m.linkname = "../escape"
                        t.addfile(m)
                    else:
                        m.size = 2
                        t.addfile(m, io.BytesIO(b"{}"))
            with self.assertRaisesRegex(RuntimeError, "Duplicate"):
                u.read_release(path, "v0.1.1", u.digest(path.read_bytes()))


    def github_record(self, version="v0.1.1", **changes):
        tag = "zooo1-" + version
        record = {"draft":False, "prerelease":False, "tag_name":tag,
                  "body":"ZOOO1_APPROVED_RELEASE=1",
                  "assets":[{"name":tag+".tar.gz","state":"uploaded","size":100,
                             "digest":"sha256:"+"a"*64,
                             "browser_download_url":"https://github.com/"+u.REPO+"/releases/download/"+tag+"/"+tag+".tar.gz"}]}
        record.update(changes)
        return record

    def test_github_selects_newest_approved_stable(self):
        records = [self.github_record("v0.2.0"), self.github_record("v0.10.0"),
                   self.github_record("v9.0.0", draft=True),
                   self.github_record("v8.0.0", prerelease=True),
                   self.github_record("v7.0.0", body="not approved")]
        with patch.object(u, "github_bytes", return_value=json.dumps(records).encode()):
            self.assertEqual(u.approved_github_release()[0], "v0.10.0")

    def test_github_does_not_install_arbitrary_main_or_unapproved_release(self):
        with patch.object(u, "github_bytes", return_value=json.dumps([self.github_record(body="not approved")]).encode()):
            with self.assertRaisesRegex(RuntimeError, "No approved"):
                u.approved_github_release()

    def test_github_rejects_asset_url_and_digest(self):
        record = self.github_record()
        record["assets"][0]["browser_download_url"] = "https://example.com/evil"
        with patch.object(u, "github_bytes", return_value=json.dumps([record]).encode()):
            with self.assertRaisesRegex(RuntimeError, "Unexpected release"):
                u.approved_github_release()
        record = self.github_record()
        record["assets"][0]["digest"] = None
        with patch.object(u, "github_bytes", return_value=json.dumps([record]).encode()):
            with self.assertRaises((RuntimeError, TypeError)):
                u.approved_github_release()

    def test_github_running_app_refuses_before_network(self):
        with (self.root / ".local/update.lock").open("a") as f:
            fcntl.flock(f, fcntl.LOCK_SH | fcntl.LOCK_NB)
            with patch.object(u, "github_bytes") as network:
                with self.assertRaisesRegex(RuntimeError, "running"):
                    u.github_update(self.root)
                network.assert_not_called()

    def test_github_bad_download_never_applies(self):
        with patch.object(u, "proc_check"), patch.object(u, "environment", return_value=self.env), \
             patch.object(u, "approved_github_release", return_value=("v0.1.1",self.github_record()["assets"][0],"a"*64)), \
             patch.object(u, "github_bytes", return_value=b"bad"), patch.object(u, "apply") as apply:
            with self.assertRaisesRegex(RuntimeError, "integrity"):
                u.github_update(self.root)
            apply.assert_not_called()
        self.assert_protected()

    def test_github_download_hands_verified_package_to_transaction(self):
        artifact, sha = self.artifact()
        raw = artifact.read_bytes()
        asset = {"name":"zooo1-v0.1.1.tar.gz","size":len(raw),"browser_download_url":"https://github.com/test"}
        with patch.object(u, "proc_check"), patch.object(u, "environment", return_value=self.env), \
             patch.object(u, "approved_github_release", return_value=("v0.1.1",asset,sha)), \
             patch.object(u, "github_bytes", return_value=raw), \
             patch.object(u, "verify"), patch("builtins.input", return_value="INSTALL v0.1.1"):
            u.github_update(self.root)
        self.assertEqual(u.load_state(self.root)["version"], "v0.1.1")
        self.assertEqual(u.load_state(self.root)["artifact_sha256"], sha)
        self.assert_protected()

    def test_device_config_survives_universal_release_and_rollback(self):
        controller = self.root / "zooo1/controller.py"
        controller.write_text("ADDRESS = '00:00:00:00:00:01'\n")
        state = dict(self.state, files=u.inventory(self.root))
        u.dump(self.sd / "state.json", state)
        with patch.object(u, "proc_check"), patch.object(u, "environment", return_value=self.env):
            u.capture_device(self.root)
        settings = (self.sd / "device.json").read_bytes()
        shared = u.public_source("zooo1/controller.py", controller.read_bytes())
        self.assertNotIn(b"00:00:00:00:00:01", shared)
        self.assertEqual(u.effective_identity(self.root, controller.read_bytes()),
                         u.effective_identity(self.root, shared))
        u.write_code(self.root, {"zooo1/controller.py":shared}, set())
        self.assertEqual((self.sd / "device.json").read_bytes(), settings)
        self.assert_protected()

    def test_unknown_device_address_expression_is_not_evaluated(self):
        (self.root / "zooo1/controller.py").write_text("ADDRESS = dangerous_function()\n")
        u.dump(self.sd / "state.json", dict(self.state, files=u.inventory(self.root)))
        with patch.object(u, "proc_check"), patch.object(u, "environment", return_value=self.env):
            with self.assertRaisesRegex(RuntimeError, "Unknown device"):
                u.capture_device(self.root)

    def test_github_up_to_date_no_download(self):
        u.dump(self.sd / "state.json", dict(self.state, version="v0.1.1", artifact_sha256="a"*64))
        with patch.object(u, "proc_check"), patch.object(u, "environment", return_value=self.env), \
             patch.object(u, "approved_github_release", return_value=("v0.1.1",{},"a"*64)), \
             patch.object(u, "github_bytes") as network:
            u.github_update(self.root)
            network.assert_not_called()

    def test_github_same_version_changed_bytes_refuses(self):
        u.dump(self.sd / "state.json", dict(self.state, version="v0.1.1", artifact_sha256="a"*64))
        with patch.object(u, "proc_check"), patch.object(u, "environment", return_value=self.env), \
             patch.object(u, "approved_github_release", return_value=("v0.1.1",{},"b"*64)):
            with self.assertRaisesRegex(RuntimeError, "Published bytes changed"):
                u.github_update(self.root)

    def test_github_older_release_refuses(self):
        u.dump(self.sd / "state.json", dict(self.state, version="v0.2.0", artifact_sha256="a"*64))
        with patch.object(u, "proc_check"), patch.object(u, "environment", return_value=self.env), \
             patch.object(u, "approved_github_release", return_value=("v0.1.1",{},"b"*64)):
            with self.assertRaisesRegex(RuntimeError, "older"):
                u.github_update(self.root)

if __name__ == "__main__":
    unittest.main()
