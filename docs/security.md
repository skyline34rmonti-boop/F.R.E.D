# Security and privacy

This is a single-owner local MVP with production-oriented boundaries. It is not certified or ready to expose to the Internet without deployment hardening.

## Identity and sessions

The configured owner account is initialized from server environment configuration. Passwords are hashed using salted PBKDF2-SHA256. Session tokens are random and only their hashes are retained in the database. Cookies are HttpOnly, SameSite=Strict, expiring and revocable at logout. State-changing requests require the session's CSRF token and browser origins are checked against an explicit allowlist. Configure secure cookies and TLS in deployment.

All conversation, memory and settings operations use the authenticated owner scope. A role field and deterministic tool gate establish extension boundaries. Multi-user account creation, device enrollment, and remote computer agents are not implemented.

## Server-side secrets

`.env`, data files and dependencies are ignored by Git. The bootstrap script creates `.env` with mode 0600 and never prints its password. The OpenAI key stays server-side and is not returned by API settings. Do not dump environment variables or provider error bodies to application logs. Rotate exposed credentials and restrict OS access to the service directory.

The database contains plaintext conversation and memory content. **Application-level encryption at rest is not implemented.** Use encrypted local disks and encrypted backups; do not put passwords, payment data or other sensitive records into memories. Memory deletion removes the active record, not earlier conversation mentions, existing backups, provider-retained data or forensic remnants in SQLite pages. Delete conversations separately when appropriate. Configure provider data retention and obtain authorization before sending confidential material to OpenAI.

## AI and external content

Conversation context is bounded, and relevant memories are retrieved rather than forwarding the entire memory database. Reference material is separated from the personality/system rules and identified as untrusted. Prompt instructions are defense in depth, not an authorization boundary. This release exposes no model action tools. Future integrations must perform deterministic authorization, input validation, registered-resource resolution and execution verification outside the model.

The future action policy requires authenticated, exact identity/target/action allowlists. Sensitive actions additionally require a signed, expiring, single-use confirmation receipt bound to the exact request and parameters. Destructive computer shutdown remains denied. These are independently tested policy primitives, not an installed executor or confirmation UI/API: no device/computer action can run in V1. A model-supplied boolean cannot grant permission.

## Operational controls

General API, chat and login rate limits apply in-process. Audit events are stored separately from message text and include action/outcome metadata. Audit data is not tamper-evident and no retention/export administration UI is included yet. Persistent history is intentional; set an explicit retention policy before expanding usage.

The documented launch command disables Uvicorn access logs so memory-search query strings are not retained in request logs. Apply the same query-string redaction or logging policy to a deployment reverse proxy.

Before shared deployment: TLS, secure cookies, restricted proxy trust, identity/account lifecycle, shared rate limiting, versioned migrations, encrypted storage/backups, least-privilege credentials, monitoring, security updates and tested recovery are required. Limit API docs and health metadata according to deployment policy. See the [roadmap](roadmap.md) for the phased implementation plan.
