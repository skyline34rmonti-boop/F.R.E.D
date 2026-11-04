# Phase 1 API contract

All paths are relative to `/api`. Responses are JSON except successful deletions/logout (204) and the WebSocket transport. Errors use `{ "detail": "Readable explanation" }`. Inputs are validated; unknown fields are rejected. No endpoint exposes provider secrets.

## Authentication

`POST /auth/login` accepts `{ "username": "owner", "password": "..." }` and sets the HttpOnly `fred_session` cookie. Its response and `GET /auth/me` contain `{ "user": { "username": "...", "display_name": "..." }, "csrf_token": "..." }`. Keep the CSRF value in client memory and send it as `X-CSRF-Token` on all POST/PUT/PATCH/DELETE requests after login. `POST /auth/logout` revokes the current session. Browser origins must appear in the server allowlist. Cookie authentication alone is insufficient for writes.

## Resources

| Method / route | Input or purpose |
| --- | --- |
| `GET /health` | Public liveness, configured provider and version |
| `GET /ready` | Public readiness; 503 if storage or service lifecycle is unavailable |
| `GET /conversations` | Owner's conversations, newest first |
| `POST /conversations` | `{}` creates an empty conversation |
| `GET /conversations/{id}/messages` | Chronological persisted turns |
| `DELETE /conversations/{id}` | Delete conversation and its messages |
| `POST /chat` | `{message, conversation_id?, mode?}`; message up to 8,000 characters |
| `GET /memories?q=...` | Search owner's memory content; q up to 200 characters |
| `POST /memories` | `{category, content}`; content up to 4,000 characters |
| `PATCH /memories/{id}` | `{category?, content?}`; at least one non-null update |
| `DELETE /memories/{id}` | Remove active memory record |
| `GET /memories/export` | Owner's JSON export with version and timestamp |
| `GET /settings` | Current mode, model, provider and owner display name |
| `PUT /settings` | `{mode?, model?}`; validated mode/model selection |
| `GET /system` | Database status, provider, model, disconnected integration capabilities |
| `WS /ws` | Authenticated status stream; trusted Origin required |

Chat returns `{conversation_id, message: {id, role, content, created_at}, provider}`. The backend permits one pending conversation request per service process. A 409 response means one is already in progress. A provider failure preserves the submitted user turn but creates no assistant reply. List conversations again to discover a newly created conversation after an error. HTTP request cancellation is not a guaranteed server-side cancellation.

Categories: `personal`, `operational`, `conversation`, `system`. Modes: `standard`, `executive`, `casual`, `focus`, `briefing`. Exact commands such as `Fred, executive mode.` change the persisted style without invoking the provider; modes grant no permissions.

WebSocket events are `{type: "status", status: "thinking" | "idle" | "error", conversation_id?}`. They describe backend state and do not stream generated text. Session expiry/revocation is checked periodically; clients should reauthenticate when HTTP access expires. A disconnect is a connectivity condition, not evidence that a task succeeded.
