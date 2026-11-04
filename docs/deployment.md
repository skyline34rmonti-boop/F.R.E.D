# Deployment, recovery, and portable data

FRED's Python service runs without a desktop environment. Windows development,
a Linux mini PC, and the optional browser/terminal clients use the same backend
and SQLite schema. Microphones, speakers, wake-word models, smart-home adapters,
and remote computer agents are future adapters, not prerequisites for V1.

## Deployment status

The systemd unit in `deploy/systemd/fred.service` is a **future Linux deployment
template**. It is not an installed or target-host-tested service. Portable SQLite
backup/restore is implemented and covered by automated tests. Reboot recovery,
crash recovery under systemd, target microphone support, and unattended operation
must be tested on the actual mini PC before treating it as a 24/7 installation.

V1 uses one backend worker. SQLite, the in-process rate limiter, and chat event
hub have not been validated as a multi-worker deployment. There are no versioned
schema migrations yet: retain the application revision associated with each
backup and test any schema upgrade on a copy before updating real data.

## Windows development

Follow the root README for Python 3.12 installation, locked dependencies, owner
configuration, terminal client, and optional React dashboard. Use explicit
`.venv\Scripts\python.exe` executables in PowerShell; activation is optional.
Keep `.env` and `data\fred.db` private. The backend binds to `127.0.0.1:8000` by
default. Closing the server terminal stops the development service. Windows
service registration is not implemented.

## Linux mini PC with systemd

These instructions assume a Linux distribution with systemd and Python 3.12,
with reviewed source already checked out at `/opt/fred`. Install Python 3.12 and
its venv package with the distribution's supported package manager. No Node.js,
GUI, audio driver, container runtime, or desktop login is required for the Python
API and terminal interface. Node.js is needed only to build/use the dashboard.

Create the dedicated account once. If the account already exists, inspect and
reuse it instead of replacing its settings:

```bash
sudo useradd --system --user-group --home-dir /var/lib/fred --no-create-home --shell /usr/sbin/nologin fred
cd /opt/fred
python3.12 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.lock.txt
```

The service account must be able to read/traverse `/opt/fred` and execute its
virtual environment. Keep application code owned by an administrative deployment
account, not writable by the service. Grant the `fred` group read/traverse access;
do not make private local `.env`, databases, or backups broadly readable.

Create `/etc/fred/fred.env` with the settings in `.env.example` as a reference.
Use a unique owner password of at least 12 characters, choose a generic owner
identifier or your own private configuration, and keep `FRED_AI_PROVIDER=mock`
until live AI is deliberately configured. No OpenAI key is needed in mock mode.
Use a root-owned mode `0600` file inside a root-owned mode `0700` directory:

```bash
sudo install -d -o root -g root -m 0700 /etc/fred
sudoedit /etc/fred/fred.env
sudo chown root:root /etc/fred/fred.env
sudo chmod 0600 /etc/fred/fred.env
```

The system service manager reads this file before dropping privileges. The unit
fixes `DATABASE_URL=sqlite:////var/lib/fred/fred.db`; systemd creates the persistent
state directory owned by `fred` with mode `0700`. Keep `FRED_COOKIE_SECURE=false`
for loopback HTTP. Application `.env` defaults must not contain conflicting
production secrets; values from the unit's environment override `.env` values.
Do not copy credentials into the unit, shell history, screenshots, or Git.

Install and start the reviewed unit:

```bash
sudo install -o root -g root -m 0644 /opt/fred/deploy/systemd/fred.service /etc/systemd/system/fred.service
sudo systemctl daemon-reload
sudo systemctl enable --now fred.service
sudo systemctl status fred.service
curl --fail --silent --show-error http://127.0.0.1:8000/api/health
curl --fail --silent --show-error http://127.0.0.1:8000/api/ready
sudo journalctl -u fred.service --since '10 minutes ago'
```

Require a successful health response and an authenticated chat request, not just
an active PID. Health should report the selected provider. Use the terminal
client described in the README to sign in and exercise a conversation. Do not
send owner credentials in curl command arguments. No external device integrations
are operational merely because the health endpoint responds.

The unit restarts an unexpectedly exited process after five seconds, limits
repeated startup failures to five attempts in a minute, sends SIGTERM on stop,
and allows 30 seconds for shutdown (Uvicorn's request-drain limit is 20 seconds).
Its sandbox makes the filesystem read-only except for `/var/lib/fred` and its
private temporary directory. It does not grant microphone, speaker, USB, GPU,
or shell control. Add only specifically reviewed device access when an adapter
is implemented. Journald provides log retention according to host policy; confirm
retention and disk limits on the mini PC. Audit events and database data contain
private operational metadata even when message contents are excluded from logs.

Before relying on unattended operation, test a real reboot, one controlled
process crash, persistence after restart, network outage, full disk, and restore
from a backup on the target host. `Restart=on-failure` handles process exits; it
does not detect a hung process. External health alerting and health-triggered
recovery are future operational work. A failed startup requires reading the
journal and correcting the underlying problem; do not loop restarts blindly.
After correcting a start-limit failure, use `sudo systemctl reset-failed fred`
and `sudo systemctl start fred`.

## Network and future dashboard access

The service binds only to loopback. Devices on the LAN cannot connect by default.
The development dashboard server is not a public deployment server. To provide
future authenticated device access, serve built `frontend/dist` assets and proxy
`/api` plus `/api/ws` through the same trusted HTTPS origin. Configure the exact
origin in `FRED_ALLOWED_ORIGINS` and set `FRED_COOKIE_SECURE=true`. Preserve session
and CSRF authentication, require LAN/VPN/firewall controls, and test session
expiry and WebSocket authentication. No reverse proxy, certificate automation,
mobile client, or computer-control agent is deployed by this template. Never
forward a raw development port from the public Internet. A remote control adapter
must expose explicit authenticated actions, never unrestricted shell commands.

## Backup and restore

Run the stdlib utility from the project root. It uses SQLite's online backup API,
so committed transactions in the WAL are included in a consistent snapshot even
when the application is running. It validates the copied database with SQLite's
full integrity check, creates the output exclusively, and refuses to overwrite
any existing destination. Parent directories must exist. A failed copy removes
its own incomplete output. This is a local database backup, not encryption or
an automatic retention/off-site backup system.

For a development database on POSIX:

```bash
mkdir -m 700 backups
python3.12 scripts/backup.py backup data/fred.db backups/fred-before-upgrade.db
```

PowerShell uses the same utility and file format:

```powershell
New-Item -ItemType Directory -Path backups
.\.venv\Scripts\python.exe scripts\backup.py backup data\fred.db backups\fred-before-upgrade.db
```

The Linux service directory is private. Have an administrator create a private
backup directory owned by `fred`, then run the utility with that identity:

```bash
sudo install -d -o fred -g fred -m 0700 /var/backups/fred
sudo -u fred /opt/fred/.venv/bin/python /opt/fred/scripts/backup.py backup /var/lib/fred/fred.db /var/backups/fred/fred-before-upgrade.db
```

Every backup filename must be new; use your backup schedule's unique names. New
files are mode `0600` on POSIX. On Windows configure a private folder ACL; POSIX
mode bits do not establish Windows access control. Backups include private
conversations, approved memories, hashed passwords, and session records. Encrypt
and restrict off-device copies. `.env`/API credentials are **not copied**: store
and restore them separately using secure secret management. Protect source code
revision information as part of the recovery record.

Restore only with FRED stopped. The `--service-stopped` flag records the operator's
confirmation; the portable tool cannot verify an external service manager. It
restores into a **new** database path and never replaces the current one:

```bash
sudo systemctl stop fred.service
sudo -u fred /opt/fred/.venv/bin/python /opt/fred/scripts/backup.py restore /var/backups/fred/fred-before-upgrade.db /var/lib/fred/fred-restored.db --service-stopped
```

For development, stop the server terminal first and use a new path such as
`data/fred-restored.db`. On the mini PC, an administrator can use
`sudo systemctl edit fred.service` to select the new database without deleting
the original:

```ini
[Service]
Environment=DATABASE_URL=sqlite:////var/lib/fred/fred-restored.db
```

Then start the service, confirm health, sign in, and inspect conversation history
and approved memory. Preserve the original database until recovery is verified.
A full database restore also restores its session records: rotate the owner
password in secure configuration before starting a restored service to revoke
old sessions. See the application authentication implementation for this startup
revocation behavior. To return to the original path, remove only your database
path override, reload systemd, and restart with the service stopped between
changes. Do not delete an unrelated override file.

Moving from Windows to Linux requires copying a verified backup and separately
providing credentials/configuration. Do not move a Windows virtual environment;
install the pinned requirements in a new Linux venv. Hardware selection and
integration configuration change at deployment time; the conversation engine
and persisted application data remain independent of the operating system.

Future model, voice, and event adapters must cooperate with task cancellation. A stalled adapter can delay cleanup until the service manager hard timeout; target shutdown/drain testing is required before enabling an adapter.
