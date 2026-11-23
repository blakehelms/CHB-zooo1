# CHB-zooo1

Reviewed zooo1 application source and a manual GitHub release updater for Raspberry Pi.

**Update zooo1** checks this public GitHub repository for the newest explicitly approved
stable application release, downloads it without a GitHub account/token, verifies its
checksum and compatibility, and asks before installation. It refuses while zooo1 or
Muse is running and retains code backups for rollback. No automatic or boot updates.

Pi 1 develops and bench-tests releases. Pi 2 installs approved releases only.
Source commits and pull requests do not update either device. Only a release published
through **Publish approved zooo1 release** with explicit version approval is eligible.

Device authentication, headset address, local configuration, recordings, session
journals and .venv stay on each Pi. No passwords, credential hashes, research data or
environments are published. The headset address is captured from each existing
installation into a private file before the first shared-code update.

[Pi release and update runbook](docs/PI_RELEASE_AND_UPDATE_RUNBOOK.md).

[Setup, click-to-update, Pi 2 installation, publishing from Pi 1 and rollback](docs/PI-UPDATE-WORKFLOW.md).

Tests run in GitHub Actions using synthetic fixtures. Passing software tests does not
qualify Bluetooth, EEG signal quality or experiments. Each Pi needs acceptance checks.

## Start every research or coding session here

- [Mandatory agent workflow and handoff](AGENTS.md)
- [Current project state, architecture, schemas and next session](docs/PROJECT_STATE.md)
- [Release/install/rollback runbook](docs/PI_RELEASE_AND_UPDATE_RUNBOOK.md)
- [Software, hardware and scientific validation](docs/VALIDATION.md)
- [Project changelog](docs/CHANGELOG.md)

As of November 23, the owner reports v0.1.4 on both Pis. Pi2/EC29 has a short
complete four-stream bench capture; Pi1 full-stream acceptance is pending.
The researcher monitor currently shows EEG; auxiliary live display is next.
Recorded optics are **raw optics, not validated fNIRS**. IRB and approved encrypted
production storage remain pending. See project state for dated evidence and limits.

PRs require explicit owner approval before merging main. Publication and live Pi
installation require separate approval. Documentation changes do not release software.
