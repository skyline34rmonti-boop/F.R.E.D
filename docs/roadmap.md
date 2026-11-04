# Roadmap and acceptance gates

V1 prioritizes a working headless service and reviewable state over broad device
coverage. Interfaces describe future boundaries; they do not make a capability
operational. Each milestone requires demonstrated behavior and failure tests.

## V1 foundation

Implemented: authenticated Python service, shared conversation engine, replaceable
model/input/output boundaries, keyboard terminal client, optional React dashboard,
persistent conversations/preferences, explicit owner-managed memory, typed
configuration/feature flags, structured audit events, health/readiness, tests,
and portable SQLite backup/restore. The repository includes a future systemd
deployment template. Mock mode remains the credential-free default.

Known limits include one owner/worker, initial schema creation without versioned
migrations, in-process rate limits, no deployed reverse proxy, and no proven
24/7 mini-PC installation. Live OpenAI behavior requires actual credentials and
account/model access. See [verification](verification.md) for what was executed.

## 1. Prove mini-PC operations

Choose a supported Linux host and validate the documented systemd installation.
Test boot startup, controlled crash recovery, graceful shutdown during a turn,
persistence, disk/network failures, and backup restoration. Establish private
storage/secret handling, log retention, update rollback, and health alerting.
Add versioned database migrations before evolving meaningful persistent data.
This milestone changes deployment/configuration, not the conversation engine.

## 2. Add explicit voice interaction

Implement push-to-talk first behind the existing audio/transcription/synthesis
contracts. Show recording, mute, transcribing, thinking, and playback states.
Pass transcripts through the same authenticated text pipeline; apply existing
session/memory/policy behavior. Test cancellation and interruption without lost
or duplicated turns, separate STT/model/TTS failures, microphone/speaker selection,
listening/conversation timeouts, and echo cancellation on supported hardware.
Do not install unrelated audio dependencies into the core service.

## 3. Add local “Hey Fred” activation

Select and benchmark a local wake-word model and VAD on the actual mini PC.
Ambient audio stays local; only an activated utterance may reach an explicitly
configured transcription provider. Prove mute behavior, false-positive handling,
resource usage, offline failure states, interruption, and speaker echo behavior.
Do not claim always-on readiness from protocol tests alone.

## 4. Connect one Home Assistant capability

Implement an authenticated adapter and real status checks for one allowlisted
light or plug. Drive rooms/devices through validated configuration. Test denied
identity, unknown devices/actions, unavailable peers, replayed confirmations,
timeouts, and truthful execution results. Then expand sensors, thermostats,
room groups, and routines with risk-specific approval rules. Devices remain
unavailable in V1 even if declarations appear in configuration.

## 5. Add an authenticated computer agent

Build a separate least-privilege agent for the gaming PC, with authenticated
transport, status reporting, and explicit named actions. Bind sensitive-action
confirmation to the exact target/parameters and reject replay/expiry. Never pass
model text to a general shell. Test command allowlist denials and transport
failures before allowing any real action. Keep OS-specific control in the agent.

## 6. Add controlled multi-device access

Prepare a trusted same-origin HTTPS gateway, secure cookies, revocable device/
account identities, network controls, and mobile-friendly sessions. Preserve
CSRF and WebSocket authentication. Add shared rate limiting and job coordination
only when a multi-worker/multi-user requirement is justified and tested.
Remote dashboard access is a separate milestone from remote command execution.
