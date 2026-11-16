import fcntl
import importlib.util
import io
import json
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

if __name__ == "__main__":
    unittest.main()
