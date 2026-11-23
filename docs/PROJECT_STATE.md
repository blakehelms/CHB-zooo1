# zooo1 project state

Last reconciled: **2026-11-23 (America/Chicago)**. This is the durable session entry point. Update dated evidence here after each material task; retain unresolved limitations.

## Evidence and current baseline

Inspected repository main/source commit: [b5be91061e6d81358f385f89f829ebf55977451d](https://github.com/blakehelms/CHB-zooo1/commit/b5be91061e6d81358f385f89f829ebf55977451d).
[Approved v0.1.4](https://github.com/blakehelms/CHB-zooo1/releases/tag/zooo1-v0.1.4) names that source commit and asset `zooo1-v0.1.4.tar.gz`; GitHub SHA-256:
`3d841da8f63a115bf562cf5e8aca65c35a4cb1293364dbb102b42c486592bd19`.
Release availability does not prove installation or acceptance on a device.

| Item | Confirmed / reported status | Still pending |
| --- | --- | --- |
| Pi1 | User reports v0.1.4 installed Nov23; development and bench device; previous real EEG acquisition reported | Full v0.1.4 multi-stream acceptance and independent installed-state evidence |
| Pi2 | User reports v0.1.4 installed Nov23; real EC29 multi-stream bench manifest supplied | Longer and repeated tests, timing, quality and portable acceptance |
| Both installations | Owner-reported `~/Downloads/zooo1-raspberry-pi`; desktop **zooo1** and **Update zooo1** | Check actual shortcut/updater paths before any authorized maintenance |
| Muse choices | Source offers Muse EC25 (`00:55:DA:B9:EC:25`) and EC29 (`00:55:DA:B9:EC:29`); either Pi can select either | Test each Pi/headset combination; never acquire one headset from two Pis |
| Network | Owner reports university IT request submitted; visitor network fallback | University access approval and actual connection status |
| Research readiness | Bench only, fictional details, local test storage | IRB and approved encrypted production storage |

No Pi was accessed or changed while preparing this documentation. The prior chat's images were not used as independent evidence.

## Confirmed bench evidence: Pi2, Nov23

Source: user-pasted manifest in [Raspberry Pi Interface Planning](chatgpt-conversation://6af7988e-0334-83e9-954e-7e6bb0d2c7aa), plus current owner confirmation of v0.1.4. This is a transcribed bench result, not re-analysis of raw files. Session `23e50b18bc72453392603d08db47c504`, EC29, `synthetic: false`, `status: complete`, schema 2, purpose **NO PARTICIPANTS: BENCH ONLY**. UTC start/end 1795473427.3630736 / 1795473436.425076: **9.062 s wall duration**.

| File | Data rows | Sensor columns (excluding 3 metadata columns) | Declared nominal Hz | Timestamp evidence |
| --- | ---: | ---: | ---: | --- |
| raw.csv | 2332 | 8 | 256 adapter expectation | EEG timestamp span not supplied |
| accgyro.csv | 468 | 6 | 52 | 604420.5878908614–604429.5551496975; 0 non-increasing |
| optics.csv | 567 | 16 | 64 | 604420.6968982744–604429.5308946294; 0 non-increasing |
| battery.csv | 9 | 1 | 0.2 | 604421.2858975824–604429.265922837; 0 non-increasing |

All three optional streams reported `recorded`, `issue: null`. Endpoint estimates `(N-1)/(last-first)` are about 52.08, 64.07 and 1.003 Hz respectively. Battery's declared 0.2 Hz versus roughly 1 Hz observed needs investigation. These estimates do not establish jitter, packet loss, duration coverage or synchronization. Finalization is not scientific validation; inter-stream timing has not been bench measured. Pi1 has no equivalent full-stream evidence in this reconciliation.

## Architecture and ownership

- `app/LAUNCH.sh` runs foreground through `zooo1.__main__` and the updater startup gate. It binds the browser service to loopback port 8765, enables bench recording by default, and does not install a boot service. Close the foreground owner only after saving completes; closing a browser tab does not stop acquisition.
- `web.py` handles researcher authentication, same-origin/CSRF checks and controller routes. Browser `/` covers login, connection, bench form and session screens; `/monitor` is the researcher monitor.
- `controller.py` owns connection/selection, acquisition worker, recording lifecycle, queued storage writer, markers and journal. Selection is locked during recording/saving. Fresh EEG gates Begin.
- `muse.py` owns one OpenMuse subprocess: `stream --address <selected Muse> --sensors EEG ACCGYRO OPTICS BATTERY --clock windowed`. OpenMuse 0.1.8 is pinned to revision `a9be252188321e269537eabf609bc207be293f8c` in requirements. No hardware starts merely by importing the module.
- mne-lsl resolves selected-address source IDs ending `_eeg`, `_accgyro`, `_optics`, `_battery`. Separate inlets preserve native stream rates/labels. EEG requires 4 or 8 labeled channels at declared 256 Hz; auxiliary discovery is lazy and optional failures are recorded without treating EEG as proof of every stream.
- `storage.py` saves local test files. `viewer.py` provides optional OpenMuse viewing; it is not a validation instrument.
- `tools/build_release.py`, `tools/update_zooo1.py`, release runtime metadata and the manual workflow define deployment. See the [runbook](PI_RELEASE_AND_UPDATE_RUNBOOK.md) for commands and [provisioning guide](PI-UPDATE-WORKFLOW.md) for one-time setup.

## Recorded data contract

See `app/zooo1/acquisition.py`, `muse.py`, `storage.py` and `controller.py` at the inspected commit.

Every CSV starts with `synthetic,source_time,received_monotonic_s`, followed by actual stream labels. Row counts exclude the header. “8 columns” for EEG means 8 sensor values, hence 11 total CSV columns. The bench captured:
- EEG: EEG_TP9, EEG_AF7, EEG_AF8, EEG_TP10, AUX_1–AUX_4. Do not interpret AUX channels as additional validated scalp electrodes.
- Motion: ACC_X, ACC_Y, ACC_Z, GYRO_X, GYRO_Y, GYRO_Z.
- Optics: OPTICS_LO_NIR, OPTICS_RO_NIR, OPTICS_LO_IR, OPTICS_RO_IR, OPTICS_LI_NIR, OPTICS_RI_NIR, OPTICS_LI_IR, OPTICS_RI_IR, OPTICS_LO_RED, OPTICS_RO_RED, OPTICS_LO_AMB, OPTICS_RO_AMB, OPTICS_LI_RED, OPTICS_RI_RED, OPTICS_LI_AMB, OPTICS_RI_AMB.
- Battery: BATTERY_PERCENT.

The adapter accepts optics type `PPG` with 4, 8 or 16 channels, motion `ACCGYRO` with 6, battery `Battery` with 1. Labels are read from LSL, not guessed. Counts/rates above describe one bench capture, not guaranteed output from every headset.

Schema 1 retains EEG metadata and raw.csv; Muse sensor capture enables schema 2 with `sensor_streams` and `timing`. Optional entries contain file, samples, channels, nominal_rate_hz, first/last_source_time, non_increasing_timestamps, issue and status (`not_observed`, `recorded`, `stream_error`). No optional CSV is created until samples arrive. A complete EEG session can still have absent/failed optional streams.

`manifest.incomplete.json` exists during recording; successful finalization writes `manifest.json` with final status, reason, samples and ended_utc, then removes the incomplete manifest. Storage failures must not be reported as successful saves. `events.jsonl` has kind, utc, received_monotonic and, for Muse, lsl_time. Source timestamps and event LSL clocks share a claimed local LSL domain; receive time is chunk arrival, not per-sample acquisition time. See [validation](VALIDATION.md) for limits and acceptance.

## Known limitations and next session

1. **Researcher monitor:** current snapshot exposes EEG points/channels and `battery=None`; it does not expose auxiliary live series. Recording support is not all-stream display support. Add and verify actual motion, raw optics and battery state/plots/counts/freshness/errors. Label **raw optics — fNIRS not validated**; clarify the intended optical measurement with researchers before HbO/HbR claims.
2. **Optional viewer source issue:** `viewer.py:run_viewer` still unpacks three `_dependencies()` values although the current adapter returns four. This is a source-confirmed contract mismatch, not a new hardware observation; correct and regression-test in a separately reviewed software change. Do not assume v0.1.4's runtime-script fix also fixed the viewer.
3. Walk through every screen and transition: login/setup, selection/connect/cancel/stale/reconnect, connected/form, Begin/record/marker/End/saving/complete/reset, interrupted/storage failure, monitor offline/recovery and optional viewer. Verify both form and monitor enforce recording/saving restrictions.
4. Run the [hardware matrix](VALIDATION.md#hardware-acceptance) on both Pis and both headsets, using different headsets concurrently. Include a longer multi-stream bench capture and integrity checks; Pi1 full-stream acceptance remains pending.
5. Measure actual rates/units, timestamp gaps/jitter, event alignment and cross-stream/cross-Pi synchronization. Investigate battery metadata discrepancy.
6. Evaluate clipping/saturation, contact, stationary versus movement artifacts and a documented signal-quality protocol; then walking/portable tests, power/range/dropout and safe stop/recovery.
7. Resolve university network, approved encrypted storage and IRB before production use.

## Documentation handoff — 2026-11-23

Prepared a documentation-only operating system against the exact baseline above: AGENTS, state, validation, changelog and reconciled release guidance. No application, dependency, release or device change. Final documentation commit/PR and checks are recorded in the PR and task delivery (the document does not invent its own future commit SHA). Hardware evidence remains the transcribed Pi2 result above. Follow the [mandatory handoff](../AGENTS.md#required-completion-and-handoff) on every future task.

Documentation verification: Python 3.13 local suite ran 46 tests: 41 passed,
four route tests could not bind a local socket under host restrictions, and one
Linux-/proc-specific test could not run on macOS. The default Python 3.9 run had
the same five environment errors. Package build/inventory, shell syntax and
browser JavaScript syntax passed. No hardware tests ran. See PR checks for Linux CI.
