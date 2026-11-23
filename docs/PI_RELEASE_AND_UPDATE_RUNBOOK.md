# zooo1 Raspberry Pi releases

Repository: [blakehelms/CHB-zooo1](https://github.com/blakehelms/CHB-zooo1).
The confirmed deployment baseline as of November 23, 2026 is **v0.1.2** on both Pis.
Pi 1 is the development and bench-test device. Pi 2 is the second research device.
Both have **zooo1** and **Update zooo1** desktop shortcuts and use
`~/Downloads/zooo1-raspberry-pi/`. Either Pi can select Muse EC25 or Muse EC29.
Both have acquired real EEG. The last confirmed Pi 2 bench session finalized
with 20,736 EEG samples in `raw.csv` (20,737 lines including its header).

## Where the workflow lives

| Repository path | Role |
| --- | --- |
| `app/` | Reviewed application source |
| `app/LAUNCH.sh`, `app/zooo1/__main__.py` | Existing foreground launcher and startup lock |
| `app/INSTALL.sh` | Initial provisioning for a new installation |
| `tools/update_zooo1.py` | Desktop command, release validation, install, backup, recovery and rollback |
| `tools/build_release.py` | Builds the deterministic, code-only `zooo1-vX.Y.Z.tar.gz` |
| `release/qualified-runtime.json`, `app/requirements*.txt` | Qualified runtime and dependency inputs checked by the existing updater |
| `.github/workflows/updater-tests.yml` | Software tests and package smoke test on pushes and pull requests |
| `.github/workflows/publish-release.yml` | Manual publishing workflow on `main` |

Work in the GitHub checkout. Review the staged diff and candidate archive before
publishing. This repository and its releases are public. Keep passwords, tokens,
authentication files and hashes, private settings, venvs, journals, participant
information, and all recordings on the lab devices. The builder only accepts the
14 paths in the updater's `MANAGED` allowlist and packages them with
`release.json`. The archive excludes `INSTALL.sh`, `LAUNCH.sh`, and the
updater-installed startup gate. The build checks the source inventory and inline
device addresses. Review source for secrets separately.

The installed updater requires the same qualified Linux aarch64, Python 3.13.5,
glibc 2.41 and exact Python distribution versions. It also compares the bytes of
both requirement files with the installed state. Qualify any dependency changes
separately. An application-only release uses the existing environment.

## 1. Prepare and software-test the candidate

1. Inspect the [published releases](https://github.com/blakehelms/CHB-zooo1/releases)
   and choose a new, unused stable version `vX.Y.Z`. Use ordinary numeric version
   components without leading zeroes. The release tag is `zooo1-vX.Y.Z`.
2. Make the change on a branch from `main`. Keep source edits within the paths
   supported by the installed updater when delivering the release through the
   existing desktop buttons.
3. Run the same software checks used by CI. From the repository root, with
   Python 3.13 and Node available:

   ```sh
   export PYTHONDONTWRITEBYTECODE=1
   VERSION=v0.1.3  # Set to the chosen unused version.
   CANDIDATE_DIR="$(mktemp -d)"
   python3 -m unittest discover -s tests -v
   python3 tools/build_release.py "$VERSION" "$CANDIDATE_DIR/zooo1-$VERSION.tar.gz"
   tar -tzf "$CANDIDATE_DIR/zooo1-$VERSION.tar.gz"
   sh -n app/LAUNCH.sh
   sh -n app/INSTALL.sh
   node --check app/zooo1/static/app.js
   ```

4. Review the diff and test results in a pull request. Keep track of the exact
   app source and runtime metadata used to build the candidate. After merge,
   confirm the `main` version still builds the same archive and its checks pass.

These tests use synthetic fixtures and verify source, packaging and updater
behavior. Use Pi 1 and a real Muse to verify acquisition.

## 2. Optional Pi 1 candidate test

Use this procedure to test a candidate before publication if needed. You can
also run the hardware acceptance checks after installing the published release.

End any session, wait for it to finish saving, stop the foreground launcher with
Ctrl+C, and close the viewer and any separate OpenMuse stream. Use the ordinary
lab user. Check the existing desktop command with
`sed -n '/^Exec=/p' "$HOME/Desktop/Update-zooo1.desktop"`. The documented updater
checkout is `~/src/CHB-zooo1`; use the shortcut's actual script path if it differs.

Use a previously qualified and updater-initialized Pi 1 development copy where
available. The same updater accepts a local candidate through its `install`
command. Transfer only the code archive to Pi 1 and compare the digest with the
value from the reviewed build. Use the chosen version, path and reviewed digest:

```sh
UPDATER="$HOME/src/CHB-zooo1/tools/update_zooo1.py"
TEST_ROOT="$HOME/Downloads/zooo1-raspberry-pi"  # Set to the qualified dev root if using one.
VERSION=v0.1.3
CANDIDATE="/path/to/zooo1-$VERSION.tar.gz"
sha256sum "$CANDIDATE"
python3 "$UPDATER" --root "$TEST_ROOT" install "$CANDIDATE" "$VERSION" REVIEWED_SHA256
```

Type `INSTALL vX.Y.Z` when prompted. A candidate installed on Pi 1's regular
deployment can be rolled back with the command below. If it is kept and the
published archive has the same bytes, the button reports it is already current.
Avoid using copied venvs with stale paths. Follow the existing
[provisioning guide](PI-UPDATE-WORKFLOW.md) if a qualified development copy is needed.

Perform the hardware acceptance steps below. Keep the test recordings on Pi 1.
If acquisition or saving fails, save the local diagnostics, roll back the test
installation and resolve the issue before research use.

## 3. Publish from GitHub

Open [Publish approved zooo1 release](https://github.com/blakehelms/CHB-zooo1/actions/workflows/publish-release.yml)
in an authorized GitHub session. Select **Run workflow**, choose branch `main`,
enter the chosen version, and enter `APPROVE vX.Y.Z` as the approval text
after source review. If the GitHub CLI is already authenticated with workflow
permission, the equivalent is:

```sh
VERSION=v0.1.3
gh workflow run publish-release.yml --repo blakehelms/CHB-zooo1 --ref main \
  -f version="$VERSION" -f approval="APPROVE $VERSION"
```

Wait for the workflow to pass, then verify the public release and its asset:

```sh
gh release view "zooo1-$VERSION" --repo blakehelms/CHB-zooo1 \
  --json tagName,isDraft,isPrerelease,body,assets,url
gh api "repos/blakehelms/CHB-zooo1/releases/tags/zooo1-$VERSION" \
  --jq '.assets[] | {name, state, size, digest, browser_download_url}'
```

Check that the release is published and stable, the notes include the exact line
`ZOOO1_APPROVED_RELEASE=1`, and one uploaded asset is named
`zooo1-vX.Y.Z.tar.gz` with GitHub's `sha256:` digest. Match its source commit
and digest to the reviewed candidate. A push, merge, tag alone, draft, prerelease,
or GitHub-generated source archive does not deliver an update. Never replace an
asset under an existing version. Publish a higher stable version for a fix.

## 4. Install and check both Pis

1. On Pi 1, end the session, let saving finish, stop **zooo1**, and close the
   viewer and other Muse processes. Double-click **Update zooo1**.
2. Check the version the updater displays and type `INSTALL vX.Y.Z` exactly.
   If the same archive was already installed for candidate testing, the updater
   reports the version is current. Check the installed version without dumping
   local settings:

   ```sh
   cd "$HOME/Downloads/zooo1-raspberry-pi"
   python3 -c 'import json; print(json.load(open(".local/zooo1-updater/state.json"))["version"])'
   ```

3. Launch **zooo1** and run the hardware checks. Once Pi 1 passes, perform the
   same install and checks on Pi 2. Use separate headsets if both Pis acquire
   simultaneously.
4. To run the same command as the button in a terminal:

   ```sh
   python3 "$HOME/src/CHB-zooo1/tools/update_zooo1.py" \
     --root "$HOME/Downloads/zooo1-raspberry-pi" github
   ```

The button checks startup, service and viewer locks, same-user acquisition
processes, clean managed source and runtime drift before contacting GitHub.
It selects the highest numerically versioned, explicitly approved stable
release. It verifies the expected HTTPS asset URL, length, SHA-256, archive
contents and file hashes. Before writing, it checks again that acquisition
is stopped and verifies compatible dependencies, local device identity, and
at least 128 MiB free. It saves a private code backup, verifies installed code
and the software runtime, and leaves the app stopped. Verification errors
trigger automatic restore. Existing `.local` authentication, settings and
headset preference, `bench-recordings/`, and `.venv` remain in place.

### Real Muse hardware acceptance on each Pi

- Open the normal **zooo1** shortcut and use the existing researcher login.
  Verify the saved headset selection, then connect to the expected physical Muse.
  Confirm fresh real EEG, the expected channel names and a live trace.
- Use fictional bench details and **Begin**, record a short sitting and gentle
  movement check, add a researcher marker, and press **End**. Wait for
  successful finalization. Check that `raw.csv` retains its EEG columns,
  `events.jsonl` contains the marker, and `manifest.json` reports
  `status: complete` and an EEG count equal to the data rows.
- For a multisensor release, record for at least 30 seconds. Confirm motion
  channels respond to movement, compare the timestamp ranges across EEG and
  the auxiliary files, and reconcile their row counts with the manifest.
  Record which optical and battery streams the headset actually emits.
  Software tests alone cannot establish timing accuracy, optical validity,
  or stream availability on either headset.
- Verify previous session folders remain accessible. Stop acquisition before
  changing deployments. Record the Pi, headset, version, and pass/fail summary
  without exporting the files or any participant information.

### Multisensor recording files

The recorder keeps the existing `raw.csv` EEG column layout. The additional
files are `accgyro.csv` (accelerometer and gyroscope), `optics.csv` (raw
decoded PPG/fNIRS optical channels), and `battery.csv` (reported battery
percentage). Each saves the channel values and timestamps at the stream's
native rate. `manifest.json` reports the observed streams, counts, channel
names, rates and any read errors. A stream without samples has no CSV.
Compare the `source_time` values across streams and use `lsl_time` in
`events.jsonl` to place markers on the same LSL clock. Verify alignment on
hardware before using it for time-sensitive analysis.

## Recovery and troubleshooting

| Symptom | Action |
| --- | --- |
| Button says zooo1 or Muse is running | Finish saving, stop the launcher and close the viewer or other streamer. Closing the browser tab alone leaves the service running. |
| No new release is offered | Check the stable tag, approval line, exact asset name, GitHub digest, and Pi internet access. Re-run the same command in a terminal to see its output. |
| Source drift, runtime drift, or missing startup gate | Preserve the live install and inspect the error. Reconcile reviewed source or qualify the device separately before retrying. |
| Incomplete update after a power loss or interruption | Fully stop the app and run `recover` using the command below. The startup gate blocks launches while a transaction is pending. |
| New code installs but the bench check fails | Stop the app, run `rollback`, verify the restored version and repeat the bench check. Leave the second Pi on its last working version until a fix passes. |
| Missing desktop shortcut | Inspect the existing checkout and launcher path first. The updater's `desktop` command creates a shortcut when it is absent. See the [provisioning guide](PI-UPDATE-WORKFLOW.md) for initial setup. |

Run as the ordinary Pi lab user, with zooo1 and Muse stopped:

```sh
UPDATER="$HOME/src/CHB-zooo1/tools/update_zooo1.py"
ROOT="$HOME/Downloads/zooo1-raspberry-pi"
python3 "$UPDATER" --root "$ROOT" recover   # Interrupted install
python3 "$UPDATER" --root "$ROOT" rollback  # Restore previous code after a completed install
```

Use the command matching the release state. Private backups and transaction
state live under `.local/zooo1-updater/`. The updater verifies the backup
before restore. Keep pending state and lock files intact while diagnosing an error.
