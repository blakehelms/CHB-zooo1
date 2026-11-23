# zooo1 mandatory workflow

Scope: only `blakehelms/CHB-zooo1` and explicitly approved project files. This public repository is a bench prototype; do not infer approval for live Pi changes or participant use.

## Before work

1. Read [project state](docs/PROJECT_STATE.md), [release runbook](docs/PI_RELEASE_AND_UPDATE_RUNBOOK.md), [validation](docs/VALIDATION.md), and [changelog](docs/CHANGELOG.md). Inspect current branch, diff, actual source, tests, latest releases and open work. Preserve existing edits.
2. State the requested scope and identify confirmed evidence versus pending work. Source-of-truth order: current explicit owner authorization sets scope; inspected source/workflows at an exact commit define software behavior; published release metadata defines downloadable artifacts; dated per-device bench evidence defines hardware claims; project state summarizes evidence. Old chats and local ZIPs are context, not current source. Resolve conflicts explicitly; never silently promote a report into a measurement.
3. Work on a review branch. Inspect affected contracts before editing: acquisition/LSL, storage schema, controller/UI, updater/runtime as applicable. Use synthetic fixtures for software testing. Do not connect to or change a Pi without explicit authorization.

## Boundaries

- Never merge main without explicit owner approval of the concrete PR. A merge, publication, and each device installation are separate actions. No software release for documentation alone unless needed and explicitly approved.
- Release only through the existing manual workflow on main with exact `APPROVE vX.Y.Z`, after owner approval and source review. Preserve all updater checks; never bypass locks, startup gates, hashes, provenance, runtime, dependency or identity checks. Never replace an existing version's artifact.
- Pi1 is the development/bench device; Pi2 receives approved releases. Code changes do not update either Pi. Use separate headsets for concurrent acquisition; no competing acquisition owners.
- Preserve per-Pi authentication, configuration, headset preference, recordings, journals, backups and `.venv`. Do not reset/clean or overlay archives onto a live deployment. No dependency/OS changes as an application update.
- Never commit passwords, tokens, hashes, private network details or Wi-Fi MACs, recordings, participant data, local settings or environments. The two existing owner-approved Muse choices are the only shared device-address exception. Review every changed/staged path and content; never force-add around default-deny ignores.
- No participant collection until IRB and approved encrypted production storage are resolved. Raw optics are not validated fNIRS/HbO/HbR. Software tests and import checks do not prove hardware, timing or scientific validity.

## Required completion and handoff

For every task, update PROJECT_STATE and CHANGELOG when behavior, evidence, limitations or decisions change. Keep operational commands in the runbook and acceptance procedures in VALIDATION rather than duplicating them.

Before ending, record and report:
- What changed and why; actual docs/PR links; exact branch/commit and base commit. Obtain final commit from Git/PR metadata after creation; do not guess it.
- Release tag/source SHA/digest if a release changed; otherwise explicitly say no release.
- Commands/checks run, results, environment limitations and CI status. Never report unrun checks as passed.
- Hardware evidence by date, Pi, headset, installed version, duration, stream counts, failures and validation scope; or explicitly no hardware run.
- Pending issues, next concrete steps, and whether device/production changes occurred. Default: none without separate authorization.
- Approval still required before merge, release or live installation. Preserve the working baseline.

Use the evidence/handoff template in [VALIDATION](docs/VALIDATION.md#evidence-and-end-of-task-handoff).
