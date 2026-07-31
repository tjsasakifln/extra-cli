# Security

- Bind default `127.0.0.1` only.
- CORS restricted to localhost origins.
- CSRF cookie + `X-CC-CSRF` header on mutations.
- Pydantic validation on bodies.
- Closed capability allowlist; no arbitrary `command`/`argv` from client.
- `subprocess` with argument list; `shell=False` always.
- Timeout + concurrency limits.
- Secret redaction in logs and text artifacts.
- Path resolve under allowed roots; traversal denied (artifacts **and** SPA fallback via `safe_join`).
- Sensitive env shown as presence only.
- Human decision sensitivity + confirmation phrase are **server-owned** (client `sensitive` / `confirmation_phrase` ignored).
- DOD accept blocked in UI path (audit only).
- Commercial cycles go through `confenge_commercial_target_router` (`suppliers` | `public-agencies` | `all`) so official registry precheck is not bypassed.
- No outreach automation endpoints.
- Contract tests assert real argv for every capability button.
