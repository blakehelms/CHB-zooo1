#!/usr/bin/env python3
"""Build code-only zooo1 release from reviewed Git source, never a device directory."""
import argparse
import gzip
import importlib.util
import io
import json
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("updater", ROOT / "tools/update_zooo1.py")
u = importlib.util.module_from_spec(spec)
spec.loader.exec_module(u)

def build(version, output):
    u.stable_key(version)
    app = ROOT / "app"
    data = {}
    for name in sorted(u.MANAGED):
        path = u.safe_path(app, name)
        if not path.is_file():
            u.fail("Missing reviewed source: " + name)
        data[name] = u.public_source(name, path.read_bytes())
        if name.endswith(".py"):
            compile(data[name], name, "exec")
    # Refuse nested auth/data/env files even though they could not be added to the package.
    extras = [str(p.relative_to(app)) for p in app.rglob("*")
              if p.is_file() and str(p.relative_to(app)) not in u.MANAGED
              and str(p.relative_to(app)) not in {"LAUNCH.sh", "INSTALL.sh", "zooo1/__main__.py"}]
    if extras:
        u.fail("Unexpected application source tree members: " + ", ".join(extras))
    files = {name:u.digest(raw) for name,raw in data.items()}
    manifest = {"format":1, "version":version, "files":files,
                "environment":json.loads((ROOT / "release/qualified-runtime.json").read_text()),
                "dependencies":{n:files[n] for n in ("requirements.txt","requirements-viewer.txt")}}
    data["release.json"] = json.dumps(manifest, sort_keys=True).encode()
    if sum(map(len, data.values())) > u.LIMIT:
        u.fail("Release exceeds size limit.")
    output.parent.mkdir(parents=True, exist_ok=True)
    # Deterministic archive. Never overwrite an existing local build or published version.
    with output.open("xb") as f:
        with gzip.GzipFile(filename="", fileobj=f, mode="wb", mtime=0) as gz:
            with tarfile.open(fileobj=gz, mode="w") as tar:
                for name, raw in sorted(data.items()):
                    member = tarfile.TarInfo(name)
                    member.size = len(raw)
                    member.mode = 0o600
                    tar.addfile(member, io.BytesIO(raw))
    u.read_release(output, version, u.digest(output.read_bytes()))
    print(output)
    print("SHA256:", u.digest(output.read_bytes()))

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("version")
    p.add_argument("output",type=Path)
    a=p.parse_args()
    build(a.version, a.output)
