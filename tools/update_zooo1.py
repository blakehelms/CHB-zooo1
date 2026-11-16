#!/usr/bin/env python3
"""Generic, manual zooo1 code updater. Standard library only; never installs dependencies."""
import argparse
from contextlib import ExitStack, contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

VERSION = re.compile(r"v[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?\Z")
LIMIT = 32 * 1024 * 1024
GATE = '''# Installed by the generic updater; keep this startup safety gate.
import fcntl
import os
from pathlib import Path
_root = Path(__file__).resolve().parent.parent
_lock = (_root / ".local" / "update.lock").open("a")
try:
    fcntl.flock(_lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
except BlockingIOError:
    raise SystemExit("Update in progress. Close this window and try again later.")
if (_root / ".local" / "zooo1-updater" / "pending.json").exists():
    raise SystemExit("Incomplete update. Run updater recover before launching zooo1.")
from .web import main
main()
'''

def fail(message):
    raise RuntimeError(message)

def run(args, **kwargs):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")
    return subprocess.run([str(x) for x in args], check=True, text=True,
                          capture_output=True, timeout=120, env=env, **kwargs).stdout

def digest(data):
    return hashlib.sha256(data).hexdigest()

def dump(path, value):
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w") as f:
        json.dump(value, f, sort_keys=True, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

# Fixed source allowlist. Unknown files and device configuration are never managed.
MANAGED = frozenset("""
zooo1/__init__.py zooo1/acquisition.py zooo1/storage.py zooo1/experiments.py
zooo1/muse.py zooo1/controller.py zooo1/viewer.py zooo1/web.py
zooo1/static/index.html zooo1/static/app.js zooo1/static/style.css
scripts/check-runtime.py requirements.txt requirements-viewer.txt
""".split())

def allowed(name):
    return name in MANAGED


def safe_path(root, name):
    if not allowed(name):
        fail("Disallowed release path: " + name)
    p = root
    for part in PurePosixPath(name).parts:
        p = p / part
        if p.is_symlink():
            fail("Symlink in managed path: " + name)
    if p.exists() and not p.is_file():
        fail("Managed path is not a regular file: " + name)
    return p

def inventory(root):
    names = [str(p.relative_to(root)) for p in (root / "zooo1").rglob("*")
             if p.is_file() and allowed(str(p.relative_to(root)))]
    names += [n for n in ("scripts/check-runtime.py", "requirements.txt",
                         "requirements-viewer.txt") if (root / n).is_file()]
    return {n: digest(safe_path(root, n).read_bytes()) for n in sorted(names)}

def environment(root):
    py = root / ".venv/bin/python"
    if not py.is_file():
        fail("Missing existing .venv. Provision and qualify dependencies separately.")
    # Package names/versions only. Never capture direct URLs, credentials or pip configuration.
    code = ("import importlib.metadata as m,json,platform,sys;"
            "print(json.dumps({'python':list(sys.version_info[:3]),"
            "'machine':platform.machine(),'system':platform.system(),"
            "'libc':list(platform.libc_ver()),"
            "'packages':sorted((d.metadata['Name'].lower(),d.version) for d in m.distributions())},sort_keys=True))")
    return json.loads(run([py, "-I", "-c", code]))

def verify(root):
    py = root / ".venv/bin/python"
    run([py, "-m", "pip", "check"], cwd=root)
    run([py, "scripts/check-runtime.py"], cwd=root)
    # Compile without writing bytecode; no import that could create auth/session state.
    for name in inventory(root):
        if name.endswith(".py"):
            compile((root / name).read_bytes(), name, "exec")
    compile((root / "zooo1/__main__.py").read_bytes(), "__main__.py", "exec")

def state_dir(root):
    return root / ".local/zooo1-updater"

def load_state(root):
    return json.loads((state_dir(root) / "state.json").read_text())

def gate_ok(root):
    if (root / "zooo1/__main__.py").read_text() != GATE:
        fail("Startup gate missing or modified. Refusing update.")

def proc_check(root):
    # Legacy startup must be stopped as well as the new shared-lock launcher.
    if platform.system() != "Linux" or not Path("/proc/self/cmdline").exists():
        fail("This operation requires Linux /proc; cannot establish that acquisition is stopped.")
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            if entry.stat().st_uid != os.getuid():
                continue
            cmd = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
            try:
                cwd = (entry / "cwd").resolve(strict=True)
            except FileNotFoundError:
                continue
            if ("OpenMuse" in cmd or "openmuse" in cmd or
                re.search(r"(?:^| )-m zooo1(?: |\.|$)", cmd) or
                (cwd == root and ("LAUNCH" in cmd or "zooo1/web.py" in cmd))):
                fail("Close zooo1 and all Muse acquisition/viewer processes before updating.")
        except (FileNotFoundError, ProcessLookupError):
            continue
        except PermissionError:
            fail("Cannot inspect a process owned by this user; refusing update.")

@contextmanager
def stopped(root, legacy=True):
    root = root.resolve()
    local = root / ".local"
    if local.is_symlink():
        fail(".local must be a real directory.")
    local.mkdir(mode=0o700, exist_ok=True)
    with ExitStack() as stack:
        for name in ("update.lock", "service.lock", "viewer.lock"):
            p = local / name
            if p.is_symlink():
                fail("Lock path must not be a symlink.")
            f = stack.enter_context(p.open("a"))
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                fail("zooo1 is running or another update is in progress. Fully stop the app first.")
        if legacy:
            proc_check(root)
        yield

def check_clean(root, state):
    if inventory(root) != state["files"]:
        fail("Local application edits detected. Capture/test them on Pi 1; never overwrite silently.")
    gate_ok(root)
    if environment(root) != state["environment"]:
        fail("Dependency/runtime drift detected. Requalify the device; updater will not change .venv.")

def bootstrap(root):
    if platform.system() != "Linux" or os.getuid() == 0:
        fail("Run on the Pi as the ordinary lab user.")
    with stopped(root):
        sd = state_dir(root)
        if sd.exists():
            fail("Already initialized (or partial initialization). Inspect before proceeding.")
        for name in ("zooo1/__main__.py", "scripts/check-runtime.py", "LAUNCH.sh"):
            p = root / name
            if p.is_symlink() or not p.is_file():
                fail("Missing or unsafe baseline file: " + name)
        # Runtime check uses existing source and environment, never INSTALL.sh.
        verify(root)
        env = environment(root)
        if env["system"] != "Linux" or env["machine"] != "aarch64" or env["python"][:2] != [3, 13]:
            fail("Expected existing Linux aarch64 / Python 3.13 installation.")
        files = inventory(root)
        if not files:
            fail("No application source found.")
        sd.mkdir(mode=0o700)
        original = (root / "zooo1/__main__.py").read_bytes()
        (sd / "original-main.py").write_bytes(original)
        (root / "zooo1/__main__.py").write_text(GATE)
        dump(sd / "state.json", {"version": "zip-baseline", "files": files, "environment": env})
        dump(sd / "baseline.json", load_state(root))
        print("Initialized. Existing auth, configuration, data and .venv retained in place.")

def release(root, version, output):
    if not VERSION.fullmatch(version):
        fail("Use an explicit version such as v0.1.1.")
    with stopped(root):
        gate_ok(root)
        if (state_dir(root) / "pending.json").exists():
            fail("Recover incomplete transaction first.")
        verify(root)
        files = inventory(root)
        if sum((root / n).stat().st_size for n in files) > LIMIT:
            fail("Source package exceeds limit.")
        manifest = {"format": 1, "version": version, "files": files, "environment": environment(root)}
        # Dependency input text is part of the reviewed release. Devices require exact equality.
        manifest["dependencies"] = {n: files[n] for n in ("requirements.txt", "requirements-viewer.txt")}
        output = output.resolve()
        if output.exists():
            fail("Output already exists; never replace a release.")
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "release.json"
            dump(p, manifest)
            with tarfile.open(output, "w:gz") as tar:
                tar.add(p, arcname="release.json", recursive=False)
                for n in files:
                    tar.add(safe_path(root, n), arcname=n, recursive=False)
        print("Prepared candidate ONLY. Test on Pi 1 before approving for Pi 2.")
        print("Version:", version)
        print("SHA256:", digest(output.read_bytes()))
        print("Keep artifact and digest outside public Git until all source is cleared for publication.")

def read_release(path, version, sha):
    if not VERSION.fullmatch(version) or not re.fullmatch("[a-f0-9]{64}", sha):
        fail("Explicit version and independently approved SHA256 are required.")
    if path.stat().st_size > LIMIT:
        fail("Release archive exceeds limit.")
    raw = path.read_bytes()
    if digest(raw) != sha:
        fail("Release digest mismatch.")
    import io
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tar:
        members = tar.getmembers()
        if len(members) > 1000 or sum(m.size for m in members) > LIMIT:
            fail("Expanded archive exceeds limit.")
        names = [m.name for m in members]
        if len(names) != len(set(names)) or any(not m.isfile() for m in members):
            fail("Duplicate paths, links or non-files in release.")
        if "release.json" not in names or any(n != "release.json" and not allowed(n) for n in names):
            fail("Disallowed archive member.")
        manifest = json.loads(tar.extractfile("release.json").read())
        if manifest.get("format") != 1 or manifest.get("version") != version:
            fail("Version/format mismatch.")
        files = manifest["files"]
        if set(files) != set(names) - {"release.json"}:
            fail("Release inventory mismatch.")
        data = {n: tar.extractfile(n).read() for n in files}
        if any(digest(data[n]) != files[n] for n in files):
            fail("Release file integrity mismatch.")
        if not {"zooo1/web.py", "scripts/check-runtime.py", "requirements.txt",
                "requirements-viewer.txt"} <= set(files):
            fail("Incomplete release.")
        if manifest.get("dependencies") != {n: files[n] for n in (
                "requirements.txt", "requirements-viewer.txt")}:
            fail("Dependency manifest mismatch.")
        return manifest, data

def write_code(root, data, remove):
    for n in sorted(set(data) | set(remove)):
        p = safe_path(root, n)
        if n in data:
            p.parent.mkdir(parents=True, exist_ok=True)
            # Temporary file in same directory permits atomic replacement of each file.
            fd, tmp = tempfile.mkstemp(prefix=".zooo1-update-", dir=p.parent)
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(data[n])
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, p)
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)
        elif p.exists():
            p.unlink()
        fd = os.open(p.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

def snapshot(root, state, changed):
    sd = state_dir(root)
    backup = sd / ("backup-" + str(time.time_ns()))
    backup.mkdir(mode=0o700)
    for n in state["files"]:
        p = backup / n
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(safe_path(root, n), p)
        with p.open("rb") as f:
            os.fsync(f.fileno())
    dump(backup / "state.json", state)
    pending = {"backup": backup.name, "paths": sorted(changed)}
    dump(sd / "pending.json", pending)
    return backup

def restore(root, backup, paths):
    saved = json.loads((backup / "state.json").read_text())
    data = {n: (backup / n).read_bytes() for n in saved["files"]}
    if any(digest(data[n]) != saved["files"][n] for n in data):
        fail("Backup integrity check failed; app remains blocked.")
    write_code(root, data, set(paths) - set(data))
    dump(state_dir(root) / "state.json", saved)

def apply(root, artifact, version, sha):
    manifest, data = read_release(artifact, version, sha)
    with stopped(root):
        sd = state_dir(root)
        if (sd / "pending.json").exists():
            fail("Incomplete transaction. Run recover first.")
        state = load_state(root)
        check_clean(root, state)
        if manifest["environment"] != state["environment"]:
            fail("Release dependencies/runtime differ from this qualified device.")
        for n, value in manifest["dependencies"].items():
            if state["files"].get(n) != value:
                fail("Dependency changes require a separately qualified deployment.")
        paths = set(state["files"]) | set(data)
        for n in paths:
            safe_path(root, n)
        if shutil.disk_usage(root).free < 4 * LIMIT:
            fail("At least 128 MiB free space required.")
        answer = input("Type INSTALL " + version + " to install this explicitly approved release: ")
        if answer != "INSTALL " + version:
            fail("Cancelled.")
        backup = snapshot(root, state, paths)
        try:
            write_code(root, data, set(state["files"]) - set(data))
            verify(root)
            dump(sd / "state.json", {"version": version, "files": manifest["files"],
                                    "environment": manifest["environment"]})
            dump(sd / "previous.json", {"backup": backup.name, "paths": sorted(paths)})
            (sd / "pending.json").unlink()
        except BaseException:
            restore(root, backup, paths)
            verify(root)
            (sd / "pending.json").unlink()
            raise
        print("Installed", version, "Software checks passed; app remains stopped.")
        print("Perform a non-research bench test before use. Run rollback if it fails.")

def recover(root, rollback=False):
    with stopped(root):
        sd = state_dir(root)
        p = sd / ("previous.json" if rollback else "pending.json")
        if rollback:
            if (sd / "pending.json").exists():
                fail("Run recover before rollback.")
            check_clean(root, load_state(root))
        entry = json.loads(p.read_text())
        name = entry["backup"]
        if not re.fullmatch(r"backup-[0-9]+", name):
            fail("Invalid backup identifier.")
        # Recovery is repeatable after interruption; pending blocks all supported launches.
        if rollback:
            dump(sd / "pending.json", entry)
        restore(root, sd / name, entry["paths"])
        verify(root)
        (sd / "pending.json").unlink()
        if rollback:
            p.unlink()
        print("Restored", load_state(root)["version"], "; data and .venv untouched.")

def desktop(root, script):
    if '"' in str(root) or '"' in str(script) or "%" in str(root) or "%" in str(script):
        fail("Unsupported desktop path characters.")
    target = Path.home() / "Desktop"
    if not target.is_dir():
        fail("Desktop directory not found; install launcher manually on this desktop.")
    path = target / "Update-zooo1.desktop"
    if path.exists():
        fail("Desktop launcher already exists; inspect it before replacing.")
    path.write_text('[Desktop Entry]\nType=Application\nName=Update zooo1\nTerminal=true\n'
                    'Exec=python3 "' + str(script) + '" --root "' + str(root) + '" interactive\n'
                    'Icon=system-software-update\nCategories=Utility;\n')
    path.chmod(0o700)
    print("Created", path)

def main():
    os.umask(0o077)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=Path.home() / "Downloads/zooo1-raspberry-pi")
    sub = p.add_subparsers(dest="command", required=True)
    for cmd in ("bootstrap", "desktop", "recover", "rollback", "interactive"):
        sub.add_parser(cmd)
    r = sub.add_parser("release")
    r.add_argument("version")
    r.add_argument("output", type=Path)
    r = sub.add_parser("install")
    r.add_argument("artifact", type=Path)
    r.add_argument("version")
    r.add_argument("sha256")
    args = p.parse_args()
    root = args.root.expanduser().resolve()
    try:
        if platform.system() != "Linux" or os.getuid() == 0:
            fail("Run on Linux as the ordinary lab user.")
        if args.command == "bootstrap":
            bootstrap(root)
        elif args.command == "desktop":
            desktop(root, Path(__file__).resolve())
        elif args.command == "release":
            release(root, args.version, args.output)
        elif args.command == "install":
            apply(root, args.artifact, args.version, args.sha256)
        elif args.command in ("recover", "rollback"):
            recover(root, rollback=args.command == "rollback")
        else:
            print("End the recording, stop zooo1 and close the viewer first.")
            print("Only use a release explicitly approved after Pi 1 bench testing.")
            artifact = Path(input("Approved release file path: ").strip()).expanduser()
            version = input("Approved version (vX.Y.Z): ").strip()
            sha = input("Independently approved SHA256: ").strip()
            apply(root, artifact, version, sha)
    except (Exception, KeyboardInterrupt) as exc:
        print("Update refused or failed:", str(exc), file=sys.stderr)
        if args.command == "interactive":
            input("Press Enter to close.")
        return 1
    if args.command == "interactive":
        input("Press Enter to close.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
