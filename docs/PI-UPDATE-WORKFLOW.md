# zooo1: click to update from GitHub

## What the button does

When clicked, **Update zooo1**:
1. Requires the app, recording, acquisition and optional Muse viewer to be fully stopped.
2. Checks this public GitHub repository for the highest stable zooo1 version marked
   ZOOO1_APPROVED_RELEASE=1 by its publisher; drafts/prereleases/unapproved releases
   and unfinished commits are ignored.
3. Downloads the code-only release asset and verifies GitHub's SHA256 asset digest.
4. Checks local source, dependencies, runtime, storage and per-device headset identity.
5. Displays the release and asks you to type INSTALL vX.Y.Z, then saves the old code,
   installs, verifies and automatically restores code if verification fails.

You no longer need to find a file, version or checksum yourself.
If the same release is already installed it reports "already up to date".
If the network is unavailable or a check fails, no application update is applied.
It refuses downgrade and refuses changed bytes published under an installed version.
Nothing updates automatically, during boot or in the background during an experiment.

The repository is public by the owner's choice. Only reviewed application source,
tooling and compatibility versions are public. Device settings, authentication,
password hashes, recordings, journals and environments remain private on the Pis.
Anonymous HTTPS gives both Pis read-only public downloads; no keys/tokens/account
access are needed. GitHub's standard TLS checks remain enabled.

## Existing Pi 1 installation: one-time setup or updater upgrade

Pi 1's working directory is ~/Downloads/zooo1-raspberry-pi. The working source was
compared file-by-file with the inspected package: all 14 managed files matched.
That tested source is the baseline. Do not extract an old ZIP over the live install.

End any recording, let saving finish, stop the foreground app with Ctrl+C, close the
optional viewer and all separate Muse streams. Use the ordinary Pi lab user, not root.
Disable any custom automatic restart of zooo1 before migration.
Always launch the app through the existing LAUNCH.sh, which uses the startup gate.

The tooling lives separately at ~/src/CHB-zooo1. For a new clone:

    mkdir -p ~/src
    git clone https://github.com/blakehelms/CHB-zooo1.git ~/src/CHB-zooo1

For an existing clone, first inspect git status and preserve any edits, then fetch and
check out a reviewed commit containing this change. Do not reset/clean the application:

    git -C ~/src/CHB-zooo1 fetch origin main
    git -C ~/src/CHB-zooo1 checkout --detach origin/main

Keep a private backup on the Pi before the first setup. The destination must not exist;
choose a unique name and enough disk space. It contains private credentials/data.
Never upload it or copy it onto another device:

    umask 077
    cp -a ~/Downloads/zooo1-raspberry-pi ~/Downloads/zooo1-raspberry-pi-before-github-updater

For a fresh ZIP installation only, initialize the updater:

    python3 ~/src/CHB-zooo1/tools/update_zooo1.py bootstrap

If the offline updater was initialized previously, do not bootstrap again.
Capture this Pi's current embedded headset address into its own private updater state:

    python3 ~/src/CHB-zooo1/tools/update_zooo1.py capture-device

This reads the existing controller's reviewed literal address. It does not scan, connect
Bluetooth, change authentication or transplant settings from Pi 1 to Pi 2.
An existing device setting is never silently overwritten.
The shared application code loads this value from .local/zooo1-updater/device.json.

For a new desktop launcher:

    python3 ~/src/CHB-zooo1/tools/update_zooo1.py desktop

For a previously installed offline desktop launcher, preserve a copy outside the Desktop,
then edit only its Exec line, changing its final word interactive to github:

    mkdir -p ~/.local/share/zooo1-launcher-backups
    cp -p ~/Desktop/Update-zooo1.desktop ~/.local/share/zooo1-launcher-backups/Update-zooo1-before-github.desktop
    python3 - <<'PY'
    from pathlib import Path
    p=Path.home()/'Desktop/Update-zooo1.desktop'
    s=p.read_text()
    assert s.count('" interactive\n')==1, 'Inspect the existing launcher before changing it'
    p.write_text(s.replace('" interactive\n','" github\n'))
    p.chmod(0o700)
    PY

Now double-click **Update zooo1**. Your desktop may request "Allow launching" once.
For a terminal check that performs the same action:

    python3 ~/src/CHB-zooo1/tools/update_zooo1.py github

The app remains stopped afterward. Open the normal zooo1 launcher and perform a
non-research acceptance check before experiments. This setup does not start a recording.

## Raspberry Pi 2

Pi 2 needs its own independently provisioned and bench-qualified zooo1 installation
at ~/Downloads/zooo1-raspberry-pi, with its own auth, configuration and environment.
Never copy Pi 1's whole install, .local, password hashes, recordings or venv to Pi 2.

For a completely new Pi 2 only, clone the repo and copy app/ into a NEW deployment
directory (never over an existing working installation):

    cp -a ~/src/CHB-zooo1/app ~/Downloads/zooo1-raspberry-pi

Configure Pi 2's actual headset address before installing/importing this public source.
Replace PI2_HEADSET_ADDRESS below with that headset's Bluetooth address; do not use Pi 1's:

    python3 ~/src/CHB-zooo1/tools/update_zooo1.py configure-device PI2_HEADSET_ADDRESS
    cd ~/Downloads/zooo1-raspberry-pi
    bash INSTALL.sh

INSTALL.sh is the existing reviewed one-time provisioner for 64-bit Pi OS/Python 3.13.
It requires Internet and OS-package administration, and is never run by Update zooo1.
Before qualifying this NEW Pi 2 environment, match the reviewed dependency versions:

    .venv/bin/python -m pip install --no-deps -r ~/src/CHB-zooo1/release/requirements-pi-qualified.txt
    .venv/bin/python -m pip check
    .venv/bin/python scripts/check-runtime.py

This is initial provisioning only. Do not run these package-changing commands on Pi 1
or an existing working Pi 2. If OS/Python/libc differ, stop and provision a compatible
OS/environment separately rather than overriding the updater checks.

Then bootstrap, create the desktop launcher, and run the normal launcher to establish
Pi 2's own login and bench-qualify it before research. No existing auth is copied.

For an already working Pi 2 ZIP installation, run the same clone, private backup,
bootstrap, capture-device and desktop setup steps,
logged into Pi 2 as its own lab user. Commands use that user's home automatically.
Pi 2 gets exactly the same GitHub-connected button and anonymous read-only download.
It never publishes code and requires no GitHub sign-in, write key or account token.

The dependency environment must match the approved release's qualified runtime:
Linux aarch64, Python 3.13.5, glibc 2.41 and the recorded distribution versions.
The requirements inputs must also match byte-for-byte. Changes require separately
qualified provisioning, not pip install over a working experiment system.
The current updater never runs INSTALL.sh, apt or pip install.
Keep Pi 2 stopped until setup is complete and perform its own acceptance test.
Pi 2 has not been connected or modified merely by preparing these instructions.

## Developing and publishing from Pi 1

Pi 1 remains the development/test device. Pi 2 receives only approved releases.
Keep the last tested deployment and a private backup. Use a separate Pi 1 development
copy. Do not run two acquisition owners against the same headset.
Python venv scripts may retain absolute paths: qualify the development environment
separately if copying it changes dependency/native executable behavior.

Develop reviewed source under app/ in the GitHub clone or copy only explicitly reviewed
managed source from a private dev directory into app/. Never git add the whole live
deployment or .local. The default-deny .gitignore helps; git add -f bypasses it.
The public controller must use the reviewed local-settings expression instead of an
inline headset address. The updater release command can prepare a sanitized local
candidate for source inspection and Pi 1 testing:

    python3 ~/src/CHB-zooo1/tools/update_zooo1.py --root ~/Downloads/zooo1-development release v0.1.2 ~/zooo1-candidates/zooo1-v0.1.2.tar.gz

Review all source for credentials/configuration before publication; a path allowlist
and MAC-address check cannot detect every hard-coded secret.
Only copy reviewed code into app/. Participant fields in the code are not participant data.

Commit changes on a branch using the owner's already authorized GitHub publishing
identity; do not embed a credential in a URL or script:

    cd ~/src/CHB-zooo1
    git switch -c development/my-change
    python3 -m unittest discover -s tests -v
    git add app tools tests docs release/qualified-runtime.json
    git diff --cached
    git commit -m "Describe the tested change"
    git push origin HEAD

Open a pull request and inspect the full diff and GitHub safety checks. Only merge
after review. This does NOT release or update a Pi.

Run hardware acceptance checks on Pi 1 before research use. You can test a local
candidate or install the published release first. Check login, headset identity,
real/synthetic status, connection, fresh EEG, begin/end, saved CSV,
interrupted-session handling and the optional viewer. Confirm saving finishes and
stop acquisition.
If dependencies changed, separately qualify them and update only the reviewed package
versions in release/qualified-runtime.json. Do not upload pip configuration/direct URL
credentials, whole dependency snapshots from private projects or any environment.

After source review, open the release workflow in an authorized GitHub session:

https://github.com/blakehelms/CHB-zooo1/actions/workflows/publish-release.yml

Choose **Run workflow**, branch main, a NEW stable version (for example v0.1.2),
and approval text exactly APPROVE v0.1.2. This is the explicit release approval.
The workflow runs safety tests, packages only the fixed app source allowlist, and
publishes an approved GitHub Release with its code asset and integrity digest.
The workflow's built-in token has only this repository's release-write permission;
no credential is installed on either Pi or added to source.
It will not run on push, a schedule or an experiment.

Do not replace an existing tag/version's asset. Software checks verify packaging
and updater behavior. Hardware acceptance checks verify acquisition on the Pis.
Both desktop buttons can now find this approved version. Each Pi must be stopped and
the operator must confirm installation. Test device behavior before research use.

GitHub API/asset reference:
https://docs.github.com/en/rest/releases/releases
https://docs.github.com/en/rest/releases/assets

## Rollback and recovery

Each update preserves source backups under .local/zooo1-updater/backup-*.
Only managed code is replaced/removed. Unknown/local files, configuration, auth,
device settings, recordings, session journals and .venv are not overwritten or pruned.

After a successful install whose acceptance check fails, fully stop the app/viewer:

    python3 ~/src/CHB-zooo1/tools/update_zooo1.py rollback

After an interrupted update/power loss:

    python3 ~/src/CHB-zooo1/tools/update_zooo1.py recover

The startup gate blocks normal launches while a pending update exists. Recovery is
repeatable and needs no network. Do not clear auth/journals or delete pending state
to bypass a failure. Preserve the private pre-updater backup.

Tests use synthetic fixtures for update/rollback, interrupted recovery, data preservation,
active locks, source drift, dependency drift, archive attacks, device identity, GitHub
release selection, approved download integrity, unchanged-version tampering and downgrade.
They do not start BLE or prove EEG signal quality, viewer rendering or power-loss
behavior on hardware. Keep code updates separate from experiments.


## Selecting either lab Muse (v0.1.2 and later)

The owner explicitly requested publishing both Muse addresses as shared application
choices. Both Pis offer Muse EC25 and Muse EC29 in the authenticated application and
researcher monitor. Only these device identifiers are shared; credentials, authentication
hashes, recordings, journals and selected local defaults remain private.

Choose a headset and click Connect selected headset. The acquisition worker cancels
any pending connection, closes its old source, persists the new local default, and only
then starts the selected connection. It refuses a change during recording/saving or
a cleanup failure. It clears old traces/freshness, so Begin cannot use the prior stream.
New recording metadata identifies the selected headset. The optional LSL viewer follows
the newly selected stream after closing its old view.

When running two Pis together, choose different headsets. The same headset should not
be controlled by both acquisition owners at once. No automatic switch between devices
occurs when a headset disappears; the operator chooses the target explicitly.

Fresh Pi 2 installation still requires its own researcher-password setup on first launch.
Do not reuse or copy Pi 1's authentication file. No passwords belong in this repository.
