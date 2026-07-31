# Security

- Bind default `127.0.0.1` only.
- CORS restricted to localhost origins.
- CSRF cookie + `X-CC-CSRF` header on mutations.
- Pydantic validation on bodies.
- Closed capability allowlist; no arbitrary `command`/`argv` from client.
- `subprocess` with argument list; `shell=False` always.
- Timeout + concurrency limits.
- Secret redaction in logs and text artifacts.
- Path resolve under allowed roots; traversal denied.
- Sensitive env shown as presence only.
- DOD accept blocked in UI path (audit only).
- No outreach automation endpoints.
