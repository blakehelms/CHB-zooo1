# Pi setup and approved releases

## Scope and what has been inspected

The existing Mac ZIP package was inspected read-only before this implementation.
The working Pi 1 directory is ~/Downloads/zooo1-raspberry-pi. The package launches
with LAUNCH.sh, Python -m zooo1, Python 3.13 on Linux aarch64, an existing .venv,
.local/service.lock, .local/viewer.lock, .local/auth.json, .local/session.json
and bench-recordings. The previously tested Pi may contain changes absent from
that ZIP. **Pi 1's working source is the baseline; do not replace it with that ZIP.**

The GitHub repository was observed as public and initially contained README and
.gitignore. The owner chose to keep it public and upload generic tooling only.
No application source or live data has been uploaded. No new account permissions,
tokens, private repository or deploy keys have been created.

This tool supports the inspected package layout, not arbitrary software.
The source allowlist is visible as MANAGED in tools/update_zooo1.py.
It intentionally excludes zooo1/__main__.py (a fixed startup safety gate),
LAUNCH.sh, INSTALL.sh, every unknown file and all device data.
Adding a managed source path or changing startup/dependencies needs a separate
reviewed updater/provisioning change. A release cannot change those implicitly.

## 1. Get the generic updater on Pi 1

Run these commands **on Pi 1**, logged in as yamauchipi1. They are instructions,
not commands already executed on the hardware.

End any recording using the app, wait for saving to finish, stop the foreground
server with Ctrl+C, close the optional viewer, and stop any separate OpenMuse stream.
Do not kill a live recording to make the update proceed.
Disable any previously configured automatic restart of zooo1 before migration.
Do not use sudo for the updater.

Clone this public tooling repository outside the live app:

    mkdir -p ~/src
    git clone https://github.com/blakehelms/CHB-zooo1.git ~/src/CHB-zooo1
    cd ~/src/CHB-zooo1
    git rev-parse HEAD

Review that commit and the script before initial use. Clone does not install or run
the application. There is no Git repository inside the live ZIP installation.

Keep a private, local backup of the tested installation before modifying its entrypoint.
This backup contains credentials/data: keep it on protected local storage; never upload it.

    umask 077
    cp -a ~/Downloads/zooo1-raspberry-pi ~/Downloads/zooo1-raspberry-pi-before-updater

If the backup directory already exists, stop and select a new unique name rather than
merging backups. Check disk space first; if recordings are large, use an approved
private backup destination with sufficient space.

Initialize and create the desktop launcher:

    python3 ~/src/CHB-zooo1/tools/update_zooo1.py bootstrap
    python3 ~/src/CHB-zooo1/tools/update_zooo1.py desktop

Bootstrap verifies the existing environment without installing anything. It records a
local source/runtime baseline, saves the original __main__.py inside
.local/zooo1-updater/original-main.py, and installs a startup gate there.
Every normal LAUNCH.sh -> python -m zooo1 startup holds a shared update lock for
its lifetime. The updater needs an exclusive lock, plus the service and viewer locks.
It also checks /proc for surviving zooo1/OpenMuse processes.

The supported app entrypoint remains bash LAUNCH.sh. Do not bypass the safety gate
with direct web.py calls, custom launch scripts, another user, or a second OS namespace.
Stop all legacy launch paths before bootstrap. Advisory locking cannot constrain
arbitrary commands run by a user deliberately bypassing it.

The tool creates no scheduled task or service. Existing device data remains at its
original paths. It does not reset authentication or copy auth from another Pi.
Desktop environments may ask you to mark the new launcher as trusted/allow launching.
The launcher uses a terminal and requests a local approved package, version and digest.
A cancelled or failed update stays stopped.

## 2. Capture the existing Pi 1 source without uploading it

After bootstrap and a successful ordinary bench test, prepare the first local candidate:

    mkdir -p ~/zooo1-candidates
    python3 ~/src/CHB-zooo1/tools/update_zooo1.py release v0.1.1 ~/zooo1-candidates/zooo1-v0.1.1.tar.gz

This packages only the fixed source allowlist and a manifest. It prints a SHA256
integrity digest. It never packages .local, recordings, local configuration, venv,
startup scripts or __main__.py. Check the archive inventory and review the source
before sharing even a candidate:

    tar -tzf ~/zooo1-candidates/zooo1-v0.1.1.tar.gz

An allowlist is not a secret scanner: secrets hard-coded into an allowed source
file must be removed and replaced by existing per-device configuration before any
publication. Do not treat a private research directory as safe to git add.

Hashes of passwords/authentication must never enter Git. Release integrity digests
are a different concept; this tool uses SHA256 locally to verify exact approved bytes.
This public repository stores no per-device or application-release digest snapshots.

## 3. Develop and test on Pi 1

Keep the tested deployment and original backup. Use a separate private development
directory on Pi 1. A complete local copy preserves the tested source/environment:

    cp -a ~/Downloads/zooo1-raspberry-pi ~/Downloads/zooo1-development

The destination must be new. This copies credentials/data only locally; never turn
this whole directory into a public repository. Python venv scripts can contain absolute
paths, so do not run INSTALL.sh or pip in this copied environment. For development,
invoke its .venv/bin/python explicitly; if any dependencies or native executables
resolve incorrectly, stop and separately provision/qualify the dev environment.

Edit the application source in ~/Downloads/zooo1-development using the Pi editor.
Never run the development app and production app simultaneously against the headset.
Use only non-research bench sessions in the development copy.
The new gate is installed in its __main__.py and resolves the dev directory correctly.

    cd ~/Downloads/zooo1-development
    bash LAUNCH.sh

Bench-check login, automatic headset connection, real/synthetic status, start/end,
fresh EEG, CSV saving, partial-session recovery and optional viewer behavior.
Confirm saving finishes, stop the app and viewer, then package a NEW version:

    python3 ~/src/CHB-zooo1/tools/update_zooo1.py --root ~/Downloads/zooo1-development release v0.1.2 ~/zooo1-candidates/zooo1-v0.1.2.tar.gz

The release command permits development source changes but still requires the startup
gate, no pending transaction, stopped acquisition and successful runtime checks.
Do not overwrite an existing version's artifact.

Install that candidate back onto the clean Pi 1 deployment to test the actual update
path. Use its printed digest in the desktop launcher or:

    python3 ~/src/CHB-zooo1/tools/update_zooo1.py install ~/zooo1-candidates/zooo1-v0.1.2.tar.gz v0.1.2 APPROVED_SHA256

Replace APPROVED_SHA256 with the full 64 lowercase hex digits supplied independently
by the approving researcher. The tool also requires typing INSTALL v0.1.2.
If local deployment source changed after initialization, it refuses to overwrite it:
develop in the separate directory instead, or restore the trusted source from your
private backup after preserving the edits. Do not delete state.json to bypass this.

Perform another bench test on Pi 1 after installation before approving Pi 2.
Record approval privately: version, full digest, tester, date, device/OS/Python/package
versions, bench outcomes, known limitations and previous release.
Approval is a human decision; generating an artifact does not approve it.
Never approve a release solely because automated tests pass.

## 4. Pi 2 installation and approved updates

Use Pi 2's own lab username/home. It must already have an independently provisioned
and bench-qualified installation of the same package layout at
~/Downloads/zooo1-raspberry-pi, with its own authentication/configuration and .venv.
Do not copy Pi 1's .local, auth, password hashes, recordings or entire deployment
to Pi 2. For a new Pi, provision the existing reviewed installer/application through
an approved private transfer, then configure and bench-test that Pi independently.
This public repository does not contain that installer/application.

Clone the generic tooling to ~/src/CHB-zooo1 as above, inspect the approved tooling
commit, make Pi 2's own private baseline backup, and run bootstrap and desktop.
Bootstrap never pulls Pi 1's code or installs a dependency.

The candidate manifest requires exact Python patch version, architecture, OS,
libc version and installed distribution versions to match Pi 1's tested release.
The two requirements files must also match Pi 2's baseline byte-for-byte.
The inspected app also embeds headset identity in controller.py. The updater compares
its ADDRESS/NAME and related headset assignments and refuses a candidate that would
transplant another device's identity. If Pi 2 has different inline headset settings,
prepare a separate Pi 2 candidate privately on Pi 1 retaining Pi 2's exact reviewed
assignments; bench-qualify it on Pi 2 before research use. Do not copy Pi 1's identity
to make this check pass. Moving identity into local configuration would require a
separately reviewed application change; this generic tool does not redesign the app.
If they differ, the updater refuses. Resolve differences in a separate qualified
environment; never run pip install or the legacy INSTALL.sh over the working Pi
just to force an update. Dependency-changing releases are deliberately out of scope.

Transfer the approved artifact privately, for example using existing authorized SSH
between the Pis or approved removable storage. This tool does not set up SSH access.
Use a fresh local download path on Pi 2. Obtain the approved version and full digest
from the researcher through a separate trusted channel.
Double-click Update zooo1, supply those three values, then explicitly confirm.

The launcher does not fetch a branch, install latest, start the app, connect BLE or
record. Run the normal launcher afterward and perform a non-research acceptance
check before any experiment.

## 5. GitHub publication from Pi 1

**Current public-repository policy:** only update this generic tooling repository
from Pi 1. Do not publish application source, candidate tarballs, release.json,
dependency fingerprints or private approval records here. The default-deny
.gitignore prevents accidental inclusion, but git add -f bypasses it.

For a generic tooling change, using the owner's already authorized Git identity:

    cd ~/src/CHB-zooo1
    git switch -c tooling/my-reviewed-change
    # Edit only generic files in the allowlist.
    python3 -m unittest discover -s tests -v
    git add tools/update_zooo1.py tests/test_updater.py docs/PI-UPDATE-WORKFLOW.md
    git diff --cached --stat
    git diff --cached
    git commit -m "Describe the reviewed updater change"
    git push origin HEAD

Open a pull request in GitHub, inspect the complete diff and GitHub test result,
then merge only after review. Do not save credentials in repository URLs, scripts,
shell history or screenshots. No write credential is needed on Pi 2.

There is deliberately NO application publish command targeting this public repository.
To distribute application releases through GitHub, a separately authorized private
repository or explicit clearance to publish sanitized application source is still
required. A Release marked draft is not a substitute for a private repository
once published. This implementation does not create either permission.

If an authorized private release repository is provided later, use distinct read-only
deploy keys for each Pi, restricted to that one repository; do not grant Pi 2 account
access, account SSH keys, a write-capable key, an account-wide PAT, agent forwarding
or an embedded token. Do not reuse Pi 1's publishing credential on Pi 2.
An administrator must authorize that setup separately. A key should have its own
SSH host alias and IdentitiesOnly yes, and GitHub's host key must be verified using
official GitHub fingerprints rather than disabling host-key checking.
The currently public generic-tooling clone uses anonymous HTTPS and needs no key.

Official reference: https://docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys

The current desktop updater accepts a privately obtained local artifact, not a
GitHub download URL. That is intentional while no private release source is authorized.
GitHub holds and tests the generic workflow now; full application sync remains gated
by the publication boundary.

## 6. Verification, rollback and interrupted updates

Preflight checks platform, current source integrity, startup gate, environment,
archive digest/version, fixed source paths, archive structure/size, available space,
locks and legacy process presence. Package symlinks, traversal paths, duplicate members,
unexpected files and changes to dependency inputs are rejected before code writes.

The updater writes a durable pending journal and code-only backup first. During an
update the startup gate cannot launch the app. If software verification fails,
the prior source is restored; if recovery also fails the pending journal remains,
blocking supported startups. Dependencies/data are never rolled back or edited.

After installation it runs pip check, the existing dependency/provenance runtime
checker, and source compilation without writing bytecode. It does not start the
server, modify authentication, scan Bluetooth or prove hardware behavior.

If a bench check fails after a successful install, stop the app/viewer, then:

    python3 ~/src/CHB-zooo1/tools/update_zooo1.py rollback

If power/process interruption leaves a pending update, stop all processes, then:

    python3 ~/src/CHB-zooo1/tools/update_zooo1.py recover

Recover is repeatable and restores the saved code baseline without requiring network.
A successful rollback restores the previous release and consumes the rollback marker.
Backups remain private under .local/zooo1-updater/backup-* and are not automatically
pruned. The tool deliberately does not delete or reinterpret interrupted session
journals; inspect them in the existing app after recovery.
Reboot/power-loss behavior must still be qualified on Pi 1 before lab deployment.

To undo the bootstrap itself, fully stop the app, retain all device data, and restore
only the original zooo1/__main__.py from the private pre-updater backup. Do not
delete .local, clear auth, replace .venv or extract an old ZIP over the live app.

Keep the original private installation backup until bench acceptance and lab
retention policy permit its removal.
