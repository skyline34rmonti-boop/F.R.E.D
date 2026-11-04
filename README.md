# F.R.E.D — Personal AI Service

F.R.E.D is a modular Python assistant designed for Windows development and future
headless deployment on a Linux mini PC. V1 provides authenticated text conversation,
persistent sessions, explicit owner-managed memory, and a configurable personality.
A terminal client and the preserved optional React dashboard use the same service
and conversation engine. A graphical desktop is not required.

The default provider is a clearly labeled, deterministic **mock**. It needs no API
key and makes no external AI requests. Select OpenAI deliberately for live model
responses. Voice, smart-home devices, scheduled routines, and computer control are
interfaces and future work; none executes actions in this release.

## What is implemented

- Python API service with a shared conversation engine, provider boundary, bounded
  context retrieval, persisted session selection, and graceful lifecycle cleanup.
- Keyboard input and text output through replaceable adapters and an authenticated
  Python terminal client. The optional dashboard supports text chat and live status.
- SQLite conversation history, preferences, and approved memories across restarts.
  Memories can be inspected, searched, corrected, exported through the API/dashboard,
  and deleted. Chat does not automatically approve or save personal facts.
- Environment-based configuration, model selection, provider-independent personality
  guidance, feature flags, and validated future room/device/hardware declarations.
- Expiring owner sessions, CSRF checks, input limits, rate limits, structured audit
  events, health/readiness endpoints, and deterministic permission boundaries.
- Automated tests, portable SQLite backup/restore, and a future Linux systemd template.

## Start on Windows

Install **Python 3.12** with the Windows Python launcher. Use PowerShell from the
root of this V1 checkout. Node.js is optional unless you want the web dashboard.
Virtual-environment activation and PowerShell execution-policy changes are unnecessary.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.lock.txt
.\.venv\Scripts\python.exe scripts\bootstrap.py
notepad .env
```

The bootstrap creates a private, ignored `.env` with a random owner password and
preserves an existing file. Read `FRED_OWNER_PASSWORD` privately; the default
username is `owner`. Keep `FRED_AI_PROVIDER=mock` initially. Do not commit or share
this file. If you change the username, use that username with the terminal client.

Start the service in the first PowerShell window:

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m app
```

In a **second** PowerShell window, from the same checkout root:

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m app.cli --username owner
```

Enter the generated password at the hidden prompt, then type a message. The mock
reply explicitly identifies itself as a local demonstration. Keep the service
window open. Use `/quit` to sign out; stop the development service with Ctrl+C.

## Start on macOS or Linux

Install Python 3.12 with venv support. From the checkout root:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.lock.txt
.venv/bin/python scripts/bootstrap.py
```

Read `.env` privately in a text editor for the generated password. Start the service:

```bash
cd backend
../.venv/bin/python -m app
```

In a second terminal, from the checkout root:

```bash
cd backend
../.venv/bin/python -m app.cli --username owner
```

The service binds to `127.0.0.1:8000`. The CLI does not start a second backend or
read the server's secret file. A different owner username can be supplied with
`--username`. See `python -m app.cli --help` while in `backend` with the venv Python.

## Terminal commands

| Command | Purpose |
| --- | --- |
| `/help`, `/status` | Commands and configured provider/storage status |
| `/new`, `/sessions`, `/use ID` | Create, inspect, and resume persistent sessions |
| `/history` | Read messages in the selected conversation |
| `/delete-session ID` | Delete a conversation after explicit confirmation |
| `/memories [SEARCH]` | Inspect approved memories and their IDs |
| `/remember CATEGORY TEXT` | Explicitly approve and save a memory |
| `/memory-edit ID TEXT`, `/forget ID` | Correct a memory or confirm its deletion |
| `/mode MODE`, `/model MODEL` | Persist communication style or model selection |
| `/quit` | Revoke the session and exit |

Memory categories: `personal`, `operational`, `conversation`, `system`.
Communication modes: `standard`, `executive`, `casual`, `focus`, `briefing`.
After a timeout or interruption, check `/history` before resubmitting: a submitted
turn may already be saved or still finish on the service.

## Configure live AI and personality

Edit only the server's root `.env` and restart the service:

```dotenv
FRED_AI_PROVIDER=openai
OPENAI_API_KEY=your_actual_key
OPENAI_MODEL=gpt-4.1-mini
FRED_OWNER_NAME=Owner
FRED_PERSONALITY_INSTRUCTION="Communicate naturally and professionally. Be concise and honest about uncertainty."
```

Never put credentials in browser `VITE_` variables, command arguments, or source.
The model must support Chat Completions and be available to your OpenAI project.
The saved model preference takes precedence over the initial `OPENAI_MODEL` default;
use `/model MODEL` or Settings to change an existing owner's selection. Provider
failures are reported and never silently fall back to mock responses. Live mode
sends the submitted text, bounded recent history, and relevant approved memory to
the provider. Personality guidance changes style, never authorization.

## Optional web dashboard

Requires Node.js **20.19+ or 22.12+**, with npm; Node 24 was used during setup. With
the Python service running, use a third terminal from the checkout root:

```bash
cd frontend
npm ci
npm run dev -- --port 5173 --strictPort
```

In PowerShell, use `npm.cmd` if execution policy blocks `npm.ps1`. On the machine
running the frontend, enter `http://127.0.0.1:5173` in your browser and sign in using
the same owner credentials. Use the same hostname consistently for cookies. The
frontend proxies `/api` and WebSockets to the Python service. A cloud workspace's
loopback address is separate from your own computer's loopback address.

The Projects page contains explicitly fictional demonstration records. No real
business, property, calendar, email, or smart-home systems are connected. Vite's
development server is not a production deployment.

## Validation and operation

Run the backend suite from the checkout root:

```powershell
# Windows PowerShell
Set-Location backend
..\.venv\Scripts\python.exe -m pytest -q
```

```bash
# macOS/Linux
cd backend
../.venv/bin/python -m pytest -q
```

For the optional frontend, from `frontend`, run `npm test` and `npm run build`.
Backend/provider tests use temporary databases and mocked network transports; no
live OpenAI key, microphone, or connected device is needed. See
[verification](docs/verification.md) for recorded results and their limits.

`GET /api/health` reports liveness and the configured provider. `GET /api/ready`
checks database readiness. A successful health response does not prove live AI,
external device connectivity, or target hardware support. Confirm a real
authenticated conversation when diagnosing application readiness.

SQLite defaults to `data/fred.db` relative to the checkout root, regardless of the
launch directory. Keep this directory private. The backup utility creates a new,
verified database copy without overwriting an existing destination:

```bash
python scripts/backup.py --help
```

Use the venv Python on your platform. [Deployment and recovery](docs/deployment.md)
documents exact backup/restore commands, Windows-to-Linux data migration, and the
future systemd service. Backups contain private data and must be protected.

## Architecture and limits

```text
backend/app/
  core/            Shared conversation engine, configuration, security, logging
  ai/              Model-provider protocol and independent personality guidance
  io/              Replaceable keyboard input and text output
  cli.py           Authenticated terminal adapter
  api/             HTTP/WebSocket validation, authentication and routing
  database/        SQLAlchemy storage setup
  models/          Owner-scoped sessions, messages, memory and audit records
  memory/          Bounded approved-memory retrieval
  services/        Lifecycle/status support
  integrations/    Validated device/room declarations and future adapter contracts
  permissions/     Deterministic authorization boundaries
  voice/           Future local wake-word, VAD, STT, TTS and audio contracts
  automations/     Future routine contracts
frontend/          Optional React dashboard
scripts/           Private setup and portable database backup/restore
backend/tests/     Automated backend/core/client tests
deploy/systemd/   Future Linux service template
```

V1 supports one owner and one backend worker. It has no multi-user account
provisioning, distributed rate limiter, versioned schema migrations, remote
execution agent, audio controller, or deployed HTTPS gateway. PostgreSQL is an
optional configuration path and has not been validated against a running server.
The systemd unit is a future deployment template; actual mini-PC reboot/crash
recovery, device drivers, and continuous operation still require target-host tests.

`FRED_MEMORY_ENABLED=false` disables approved-memory retrieval during chat. Stored
memories remain inspectable, editable, deletable, and exportable. Future voice, smart-home, remote-control, and automation flags default to
false; enabling an unimplemented capability fails startup explicitly. Declaring a
device in configuration does not connect it or authorize an action. No model has
unrestricted shell or device-execution access.

Read [architecture](docs/architecture.md), [configuration](docs/installation.md),
[security](docs/security.md), [API](docs/api.md), and the [roadmap](docs/roadmap.md).
The next milestones are tested Linux deployment/recovery, explicit push-to-talk
voice adapters, local wake-word/VAD on selected hardware, and then narrowly scoped
Home Assistant and authenticated computer-agent integrations.
