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

[Setup, click-to-update, Pi 2 installation, publishing from Pi 1 and rollback](docs/PI-UPDATE-WORKFLOW.md).

Tests run in GitHub Actions using synthetic fixtures. Passing software tests does not
qualify Bluetooth, EEG signal quality or experiments. Each Pi needs acceptance checks.
