# V1 verification

Validated on the managed Linux environment using Python 3.12.14 and Node 24.22.1.
These results describe this revision in the current environment, not a deployed
mini PC, Windows host, or future cloud restore.

## Automated checks

From `backend`: `../.venv/bin/python -m pytest -q` — **133 passed**.
The suite exercises the shared conversation engine, owner/session boundaries,
CSRF/origins, approved memory CRUD/search/export, provider success and sanitized
failures with mocked SDK transports, bounded context, concurrency, cancellation,
lifecycle/readiness/restart persistence, text adapters and authenticated keyboard
client, feature flags, room/device declarations, future action authorization,
and consistent SQLite backup/restore.

One upstream Starlette/httpx TestClient deprecation warning remains. It does not
skip tests or change their results. Do not blindly replace the pinned HTTP stack;
validate dependency upgrades separately.

From `frontend`: `npm test` — **14 passed** across three test files.
`npm run build` — TypeScript and Vite production build passed.
`python -m pip check` — no broken requirements.

A GitHub Actions workflow runs the backend suite on Linux and Windows and builds
and tests the frontend on Linux. The Windows job is configured but has **not run
in this local environment**; no Windows execution result is claimed.

## Live functional checks

The documented `python -m app` entry point started the headless service on
loopback. A real HTTP terminal session using the replaceable input/output
adapters signed in privately, sent text through the same shared engine used by
the dashboard, received an explicitly labeled mock reply, created/listed a saved
conversation, read history, approved/searched a memory, changed mode, inspected
status, and logged out. No credentials or record contents were printed in test
reports.

The preserved Vite frontend served HTML and proxied liveness/readiness requests.
An authenticated WebSocket received the idle status. These are HTTP/WebSocket
checks, not a visual browser or accessibility audit.

A SIGTERM stopped the service with completed lifecycle cleanup. Restarting the
same entry point recovered conversation history, approved memory and preferences.
The portable utility backed up the live database, validated SQLite integrity,
and restored it to a new path. A separate running service opened the restored
database and recovered the same records. Synthetic records were removed from the
main development database after checking recovery.

## Limits

Live OpenAI inference, audio capture/playback, local wake-word/VAD models, real
Home Assistant devices, computer actions, remote dashboard TLS, PostgreSQL, and
mini-PC hardware are not tested or claimed operational. The provider adapter is
tested with mocked success/error responses only.

The systemd file is an uninstalled deployment template. Target-host unit
validation, real reboot/crash recovery, resource limits and 24/7 reliability need
acceptance testing on Linux hardware. `systemd-analyze verify` was unavailable
in the container's read-only `/run` context. Future adapters must cooperate with
cancellation so graceful shutdown can finish before the manager hard timeout.

The command sandbox restricts internal sockets used by TestClient; the backend
suite and live services ran with network-capable execution permissions. No TLS,
package signature, or checksum verification was disabled.
