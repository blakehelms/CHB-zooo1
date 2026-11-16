# CHB-zooo1 — manual release updater

This public repository contains **only generic deployment tooling, tests and instructions**.
It does not contain the lab application, credentials, password hashes, headset settings,
research recordings, journals, virtual environments or application release artifacts.

Pi 1 develops and bench-tests candidates. Pi 2 installs only an explicitly approved,
versioned candidate. There is no automatic update, boot task, service, cron job or
"pull latest" operation. Neither Pi has been accessed or modified by this change.

Start with [the Pi setup and release guide](docs/PI-UPDATE-WORKFLOW.md).

The updater preserves the existing ZIP installation in place. It manages a fixed list
of application source paths, blocks while the application/viewer is running, rejects
unapproved digests and dependency drift, and retains code backups for rollback.
It never runs INSTALL.sh, apt, pip install, git reset or git clean against a deployment.

**Publication boundary:** while this repository remains public and application source
is not approved for public release, application synchronization through this repository
is intentionally unavailable. Transfer candidate packages privately between Pis, or
use a separately authorized private release repository. A public GitHub Release asset
is public too. Do not upload lab packages here.

Software safety tests run in GitHub Actions with synthetic fixtures. Passing them is
not qualification of Bluetooth, acquisition, signal quality, hardware or power-loss
recovery on a lab Pi.
