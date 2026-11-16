#!/usr/bin/env python3
"""Generic, manual zooo1 code updater. Standard library only; never installs dependencies."""
import argparse
import ast
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
            # cmdline is sufficient: refuse any zooo1/Muse/launcher owned by this user.
            # Do not inspect cwd of unrelated protected desktop/system processes.
            if ("OpenMuse" in cmd or "openmuse" in cmd or
                re.search(r"(?:^| )-m zooo1(?: |\.|$)", cmd) or
                "LAUNCH" in cmd or "zooo1/web.py" in cmd):
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
        if sd.exists() and any(p.name != "device.json" for p in sd.iterdir()):
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
        sd.mkdir(mode=0o700, exist_ok=True)
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
        data = {n: public_source(n, safe_path(root, n).read_bytes()) for n in inventory(root)}
        files = {n: digest(raw) for n, raw in data.items()}
        if sum(len(raw) for raw in data.values()) > LIMIT:
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
                    import io
                    member = tarfile.TarInfo(n)
                    member.size = len(data[n])
                    member.mode = 0o600
                    tar.addfile(member, io.BytesIO(data[n]))
        print("Prepared candidate ONLY. Test on Pi 1 before approving for Pi 2.")
        print("Version:", version)
        print("SHA256:", digest(output.read_bytes()))
        print("Candidate strips the device address. Review all source and bench-test before approving publication.")

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

def device_identity(source):
    # Existing package embeds headset identity in controller.py. Do not transplant it.
    names = {"ADDRESS", "NAME", "MUSE_ADDRESS", "HEADSET_ADDRESS", "HEADSET_NAME"}
    values = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in names:
                    values[target.id] = ast.dump(node.value, include_attributes=False)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id in names:
                values[node.target.id] = ast.dump(node.value, include_attributes=False)
    return values


# Only this reviewed expression can resolve an on-device headset address in releases.
DEVICE_EXPR = "json.loads((Path(__file__).resolve().parent.parent / '.local' / 'zooo1-updater' / 'device.json').read_text())['muse_address']"

def address_assignment(source):
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "ADDRESS" for t in node.targets):
            return node
    return None

def valid_address(value):
    if not isinstance(value, str) or not re.fullmatch(r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", value):
        fail("This device needs its own valid Muse address before installing a release.")
    return value

def saved_address(root):
    return valid_address(json.loads((state_dir(root) / "device.json").read_text())["muse_address"])


def configure_device(root, address):
    address = valid_address(address)
    with stopped(root):
        sd = state_dir(root)
        path = sd / "device.json"
        if path.exists():
            if saved_address(root) != address:
                fail("Device settings already exist; preserve them and review changes separately.")
            print("This device is already configured.")
            return
        node = address_assignment((root / "zooo1/controller.py").read_bytes())
        if node is None:
            fail("Unknown controller configuration.")
        if isinstance(node.value, ast.Constant) and node.value.value != address:
            fail("Address differs from this Pi's existing controller; use capture-device.")
        if not isinstance(node.value, ast.Constant) and ast.dump(node.value) != ast.dump(ast.parse(DEVICE_EXPR, mode="eval").body):
            fail("Unknown controller device expression.")
        sd.mkdir(mode=0o700, exist_ok=True)
        dump(path, {"format": 1, "muse_address": address})
        print("Saved this Pi's headset address locally; existing settings were not overwritten.")


def capture_device(root):
    with stopped(root):
        state = load_state(root)
        check_clean(root, state)
        source = (root / "zooo1/controller.py").read_bytes()
        node = address_assignment(source)
        if node is None:
            fail("Cannot locate this device's existing headset address.")
        if isinstance(node.value, ast.Constant):
            address = valid_address(node.value.value)
        elif ast.dump(node.value) == ast.dump(ast.parse(DEVICE_EXPR, mode="eval").body):
            address = saved_address(root)
        else:
            fail("Unknown device address configuration. Preserve and review it manually.")
        path = state_dir(root) / "device.json"
        if path.exists():
            if saved_address(root) != address:
                fail("Existing device settings disagree with the installed controller.")
        else:
            dump(path, {"format": 1, "muse_address": address})
        print("Preserved this Pi's headset settings locally. No device address uploaded.")

def effective_identity(root, source):
    values = device_identity(source)
    node = address_assignment(source)
    if node is not None and ast.dump(node.value) == ast.dump(ast.parse(DEVICE_EXPR, mode="eval").body):
        values["ADDRESS"] = ast.dump(ast.Constant(value=saved_address(root)))
    return values

def public_source(name, source):
    if name == "zooo1/controller.py":
        node = address_assignment(source)
        if node is None:
            fail("Missing controller device configuration.")
        lines = source.decode().splitlines(keepends=True)
        lines[node.lineno - 1:node.end_lineno] = ["ADDRESS = " + DEVICE_EXPR + "\n"]
        source = "".join(lines).encode()
    source = re.sub(rb"MuseS-[A-Fa-f0-9]{4}", b"your assigned Muse headset", source)
    # Keep any other inline device addresses out of public source; review instead of guessing.
    addresses = set(re.findall(rb"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", source))
    approved = {b"00:55:DA:B9:EC:25", b"00:55:DA:B9:EC:29"}
    if addresses and (name != "zooo1/controller.py" or addresses - approved):
        fail("Unapproved inline device address remains in source: " + name)
    return source


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
        controller = "zooo1/controller.py"
        if controller not in data:
            fail("Release must retain the device controller.")
        if effective_identity(root, (root / controller).read_bytes()) != effective_identity(root, data[controller]):
            fail("Embedded headset configuration differs; keep this device identity unchanged.")
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
                                    "environment": manifest["environment"], "artifact_sha256": sha})
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


REPO = "blakehelms/CHB-zooo1"
STABLE = re.compile(r"v([0-9]+)\.([0-9]+)\.([0-9]+)\Z")

def stable_key(version):
    match = STABLE.fullmatch(version)
    if not match:
        fail("Approved GitHub versions must be stable vX.Y.Z releases.")
    return tuple(map(int, match.groups()))

def github_bytes(url, limit):
    from urllib.request import Request, build_opener, HTTPRedirectHandler
    from urllib.parse import urlsplit
    from urllib.error import HTTPError, URLError
    hosts = {"api.github.com", "github.com", "release-assets.githubusercontent.com",
             "objects.githubusercontent.com"}
    def validate(address):
        p = urlsplit(address)
        if p.scheme != "https" or p.hostname not in hosts or p.username or p.password or p.port not in (None, 443):
            fail("Unexpected GitHub download destination.")
    class Redirects(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            validate(newurl)
            return super().redirect_request(req, fp, code, msg, headers, newurl)
    validate(url)
    req = Request(url, headers={"User-Agent":"zooo1-manual-updater",
                               "Accept":"application/vnd.github+json" if url.startswith("https://api.github.com/") else "application/octet-stream"})
    try:
        with build_opener(Redirects()).open(req, timeout=30) as response:
            validate(response.geturl())
            raw = response.read(limit + 1)
            if len(raw) > limit:
                fail("GitHub response exceeds size limit.")
            return raw
    except (HTTPError, URLError, TimeoutError) as exc:
        fail("Cannot retrieve approved release from GitHub. No application files changed. " + str(exc))

def approved_github_release():
    approved = []
    for page in range(1, 11):
        items = json.loads(github_bytes(
            "https://api.github.com/repos/" + REPO + "/releases?per_page=100&page=" + str(page),
            2 * 1024 * 1024))
        if not isinstance(items, list):
            fail("Unexpected GitHub release response.")
        for release in items:
            if release.get("draft") or release.get("prerelease"):
                continue
            tag = release.get("tag_name", "")
            if not tag.startswith("zooo1-") or not STABLE.fullmatch(tag[6:]):
                continue
            if "ZOOO1_APPROVED_RELEASE=1" not in (release.get("body") or "").splitlines():
                continue
            version = tag[6:]
            wanted = "zooo1-" + version + ".tar.gz"
            assets = [a for a in release.get("assets", []) if a.get("name") == wanted]
            if len(assets) != 1:
                fail("Approved release is missing its unique application asset: " + version)
            asset = assets[0]
            if asset.get("state") != "uploaded" or not 0 < asset.get("size", 0) <= LIMIT:
                fail("Approved release asset is incomplete or too large.")
            checksum = asset.get("digest") or ""
            if not re.fullmatch(r"sha256:[a-f0-9]{64}", checksum):
                fail("GitHub release asset has no valid SHA256 digest.")
            expected = "https://github.com/" + REPO + "/releases/download/" + tag + "/" + wanted
            if asset.get("browser_download_url") != expected:
                fail("Unexpected release asset location.")
            approved.append((stable_key(version), version, asset, checksum[7:]))
        if len(items) < 100:
            break
    else:
        fail("Release list exceeds limit; cannot establish newest approved version.")
    if not approved:
        fail("No approved zooo1 application release is published on GitHub yet.")
    approved.sort(key=lambda item: item[0], reverse=True)
    if len(approved) > 1 and approved[0][0] == approved[1][0]:
        fail("Duplicate approved version.")
    return approved[0][1:]

def github_update(root):
    # Refuse before networking when acquiring, recording or an interrupted update exists.
    with stopped(root):
        if (state_dir(root) / "pending.json").exists():
            fail("Incomplete update. Run recover first.")
        state = load_state(root)
        check_clean(root, state)
    print("Checking GitHub for the newest approved zooo1 release...", flush=True)
    version, asset, sha = approved_github_release()
    current = state["version"]
    if current != "zip-baseline":
        if stable_key(version) < stable_key(current):
            fail("GitHub version is older than this device. Use explicit local rollback if needed.")
        if version == current:
            if state.get("artifact_sha256") != sha:
                fail("Published bytes changed under an existing version. Refusing replacement.")
            print("zooo1 is already up to date:", current)
            return
    print("Approved release:", version, "| installed:", current)
    with tempfile.TemporaryDirectory(prefix="zooo1-github-") as td:
        artifact = Path(td) / asset["name"]
        raw = github_bytes(asset["browser_download_url"], LIMIT)
        if len(raw) != asset["size"] or digest(raw) != sha:
            fail("Downloaded GitHub release failed integrity verification.")
        artifact.write_bytes(raw)
        # apply rechecks stopped state and local source after download before any code write.
        apply(root, artifact, version, sha)


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
                    'Exec=python3 "' + str(script) + '" --root "' + str(root) + '" github\n'
                    'Icon=system-software-update\nCategories=Utility;\n')
    path.chmod(0o700)
    print("Created", path)

def main():
    os.umask(0o077)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=Path.home() / "Downloads/zooo1-raspberry-pi")
    sub = p.add_subparsers(dest="command", required=True)
    for cmd in ("bootstrap", "desktop", "recover", "rollback", "interactive", "github", "capture-device"):
        sub.add_parser(cmd)
    c = sub.add_parser("configure-device")
    c.add_argument("address")
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
        elif args.command == "configure-device":
            configure_device(root, args.address)
        elif args.command == "capture-device":
            capture_device(root)
        elif args.command == "github":
            github_update(root)
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
        if args.command in ("interactive", "github"):
            input("Press Enter to close.")
        return 1
    if args.command in ("interactive", "github"):
        input("Press Enter to close.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
