# Installed by the generic updater; keep this startup safety gate.
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
