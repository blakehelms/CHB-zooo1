# zooo1 validation

A passing software test, runtime import check, successful update or `status: complete` does not qualify an experiment. Current evidence and open work live in [PROJECT_STATE](PROJECT_STATE.md). This protocol is bench-only pending IRB and approved encrypted storage.

## Software checks

CI runs on Linux. Local macOS cannot pass the Linux-/proc-specific test; restricted hosts may also block loopback server tests. Report those errors explicitly and use Linux CI for full verification, without weakening checks.

From a clean repository source tree, use the Python 3.13 environment used by CI; set bytecode suppression so packaging inventory stays clean:

```sh
export PYTHONDONTWRITEBYTECODE=1
python3 -m unittest discover -s tests -v
CHECK_DIR="$(mktemp -d)"
python3 tools/build_release.py v0.0.0 "$CHECK_DIR/zooo1-test.tar.gz"
tar -tzf "$CHECK_DIR/zooo1-test.tar.gz"
sh -n app/LAUNCH.sh
sh -n app/INSTALL.sh
node --check app/zooo1/static/app.js
```

`v0.0.0` is a local packaging test only; do not publish it. Inspect the final diff and public archive inventory. CI uses these same categories in `.github/workflows/updater-tests.yml`. Existing tests cover updater transactions/recovery, integrity/archive rejection, data and environment preservation, source/dependency drift, locks, release selection, headset selection/auth/CSRF, multi-stream storage/error handling and a runtime-check regression using the real adapter with simulated dependencies. Simulated LSL tests cannot establish real acquisition or physical accuracy.

On an explicitly authorized Pi only, `.venv/bin/python scripts/check-runtime.py` checks software imports, pinned OpenMuse provenance, CLI and native LSL availability. It does not scan/connect, test Bluetooth or render the GUI. Use the runbook to diagnose failures; do not bypass them.

## Hardware acceptance

Record outcomes separately for **Pi1 × EC25, Pi1 × EC29, Pi2 × EC25, Pi2 × EC29**. Current status: only a short Pi2/EC29 schema-2 capture is evidenced; all combinations still need this full protocol. Do not contend for one headset.

For each authorized bench run:
1. Record date, Pi, exact installed version/source release, headset, runtime check result, stationary/movement condition and test duration. Confirm old recordings/auth/config/environment are preserved after any separately approved install.
2. Open the normal launcher and researcher login. Verify selected physical Muse, real-data labeling, fresh EEG and correct actual labels. Begin must stay disabled without fresh EEG. Verify switching is blocked while recording/saving and old traces clear on selection.
3. Record at least 30 seconds stationary plus a separately labeled gentle-motion segment; add markers, End, and wait for confirmed finalization. Keep fictional bench details. Inspect files locally; never upload recordings.
4. Compare every CSV header, sensor column count and data-row count to manifest metadata. Require complete intended capture, readable finite values, expected identity, final status and matching EEG/auxiliary counts. Check no leftover incomplete marker after success. Every intended stream must have recorded samples and no stream error; missing or errored optional streams fail the **all-stream** criterion even if EEG completes.
5. Compute first/last timestamps, interval distributions, non-increasing counts, gaps and observed rate `(N-1)/(last-first)` for each stream. Require strictly increasing timestamps for an ordering pass. Report actual results against declared 256/52/64/0.2 Hz; unexplained discrepancy remains unresolved, including battery's roughly 1 Hz evidence. Do not divide every stream count by wall duration as proof of its sample rate.
6. Exercise connection loss, stale data, interruption and recovery with disposable bench sessions; confirm partial/incomplete outcomes are truthful and no reconnect silently resumes an ended session. Perform storage/power-interruption tests only in a separately authorized disposable setup.
7. Complete the screen walkthrough listed in PROJECT_STATE. The monitor must display each actually supported stream's freshness/availability/errors and labels, distinguish not observed from zero values, and reflect saved status accurately. Verify readings against local files rather than judging appearance alone.

## Signal quality, units and clipping

The real EEG manifest deliberately says **upstream EEG stream units; verify on hardware**. Do not relabel values as µV solely because synthetic fixtures use microvolts. Motion scaling, optical values and battery calibration also need upstream decoding/provenance and hardware verification; channel names alone do not validate units.

Keep original decoded values. Check per-channel min/max, repeated extrema/plateaus, flatlines, nonfinite values, discontinuities, contact changes, line noise and motion-correlated artifacts. A trace filling the screen is not evidence of saturation: the current browser independently autoscales each EEG channel. Conversely, autoscaling can conceal amplitude problems. Diagnose clipping from raw data and confirmed decoder/ADC limits, not the canvas. Record fractions/durations at verified rails once known. Do not invent a numeric saturation threshold or scientific pass criterion.

Signal-quality acceptance is **pending** until researchers define and approve a protocol with calibrated units, reference limits, contact procedure, baseline conditions, noise/artifact measures and thresholds suited to the intended analysis. Acquisition continuity alone cannot pass it.

## Timing and synchronization

`source_time` is OpenMuse's local LSL-domain timestamp; `received_monotonic_s` is the host time a chunk was pulled (many rows can share it). `events.jsonl.lsl_time` is the local LSL clock when the controller generated the event; UTC is a wall clock, not a substitute for calibrated alignment.

Compare source ranges across streams and align markers in the same domain for exploratory inspection. Validate offsets, jitter, drift, gaps and marker latency with a known shared physical stimulus and a documented reference, repeated over realistic session lengths. Define acceptable tolerances with the research protocol **before** claiming timing acceptance. Separate Pis have separate clocks: equal-looking LSL timestamps do not establish cross-Pi synchronization. No inter-stream or cross-Pi accuracy is currently bench validated.

## Raw optics versus validated fNIRS

OPTICS/PPG transport and 16 recorded values show decoded raw optical acquisition. They do not establish wavelengths, optical power units, source-detector geometry, calibrated intensity/optical density, hemoglobin concentration changes or physiological validity. Channel abbreviations are labels, not calibration evidence.

Use **raw optics — fNIRS not validated** in new UI work. Before using fNIRS/HbO/HbR terminology as a measurement claim, verify device/upstream channel mapping and wavelengths, dark/ambient handling, geometry, quality controls, conversion model and assumptions, units, reference comparison and researcher-approved analysis. Keep derived data separate from unchanged raw files with provenance. This work remains pending.

## Portable/walking acceptance

After stationary acquisition and quality checks, authorize bench walking/portable trials: secure equipment, document power/battery duration, Bluetooth distance/occlusion, motion artifact, data gaps, temperature/storage capacity, markers, End/save and controlled disconnect behavior. Record failures and recovery per device/headset; set duration and dropout/quality tolerances with researchers before a production pass. Do not infer portable readiness from a 9-second desk capture.

## Evidence and end-of-task handoff

Store only nonsensitive summaries in GitHub. Keep raw recordings and diagnostics containing private paths/settings on the originating device or an approved secure destination.

```text
Date / operator:
Scope and changes:
PR / branch / exact commit / inspected base:
Release tag / source SHA / artifact digest (or no release):
Software checks, results, environment and CI links:
Hardware: Pi / headset / installed version / condition / duration (or not run):
Manifest status / schema / per-stream rows, labels, nominal and measured rates:
Timestamp ordering, gaps, units, clipping/quality and timing evidence:
Screens / interruption / recovery / portability results:
Known failures, unverified claims and next tasks:
PROJECT_STATE and CHANGELOG updated:
Device or production changes and authorization (or none):
Merge / release / installation approvals still required:
```

Do not erase failed evidence when adding later passes. Explicitly distinguish **software pass**, **bench capture pass**, **all-stream acceptance**, **signal-quality validation**, **timing validation** and **production approval**.
