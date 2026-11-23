# zooo1 changelog

Record user-visible behavior, operational changes, validation evidence and unresolved issues here; release metadata remains on GitHub. Documentation commits are not installed software versions.

## Unreleased — documentation operating system (2026-11-23)

- Added mandatory agent workflow, source/evidence hierarchy, security/release boundaries and end-of-task handoff.
- Added dated project state, architecture/schema reference and separate software/hardware/scientific validation criteria.
- Reconciled stale v0.1.2 runbook baseline with owner-reported v0.1.4 on both Pis and Pi2/EC29 multi-stream bench evidence; Pi1 full-stream validation remains pending.
- Documented v0.1.3 runtime-check failure and v0.1.4 recovery without weakening checks.
- Recorded an additional source-confirmed optional-viewer three-versus-four-value unpack mismatch as pending software work.
- No application code, dependency, workflow, release or Pi change. Documentation commit/PR and verification are recorded in the PR/task delivery.

## v0.1.4 — 2026-11-23

[Release](https://github.com/blakehelms/CHB-zooo1/releases/tag/zooo1-v0.1.4), source [b5be910](https://github.com/blakehelms/CHB-zooo1/commit/b5be91061e6d81358f385f89f829ebf55977451d).

Fixed runtime-check unpacking to consume the adapter's four dependency values, preserving provenance, CLI, BlueZ, LSL and runtime checks; added regression coverage with simulated dependencies. Both installations reported by owner. Pi2/EC29 complete 9.062-second bench: 2332 EEG, 468 motion, 567 optics and 9 battery rows; details/limits in [PROJECT_STATE](PROJECT_STATE.md).

## v0.1.3 — 2026-11-23

[Release](https://github.com/blakehelms/CHB-zooo1/releases/tag/zooo1-v0.1.3), source [6fcca5e](https://github.com/blakehelms/CHB-zooo1/commit/6fcca5ee8195704e9efaf463ff564f97791e8be3).

Added native-rate motion, optics and battery recording alongside unchanged EEG CSV format (schema 2). The adapter added an LSL clock return value but deployment runtime-check unpacking still expected three values; installation verification failed. v0.1.4 corrected this contract. Publishing workflow no longer requires Pi1 recording evidence as an input; hardware acceptance remains separately required before research use.

## v0.1.2 — 2026-11-16

[Release](https://github.com/blakehelms/CHB-zooo1/releases/tag/zooo1-v0.1.2), source [aed09cd](https://github.com/blakehelms/CHB-zooo1/commit/aed09cd17d2d831dc6370f463508521d42a72b73).

Enabled explicit selection of either owner-approved Muse on either Pi, with recording/saving restrictions and per-device preferences.

## v0.1.1 — 2026-11-16

[Release](https://github.com/blakehelms/CHB-zooo1/releases/tag/zooo1-v0.1.1), source [db3574d](https://github.com/blakehelms/CHB-zooo1/commit/db3574d79c7e3d891e642fb91199a3aee6104bd2).

Connected the manual desktop updater to approved stable public GitHub application releases, retaining integrity/runtime checks, backups and local device state.
