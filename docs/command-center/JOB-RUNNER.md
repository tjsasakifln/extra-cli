# Job Runner

States: `QUEUED`, `VALIDATING`, `RUNNING`, `CANCELLING`, `CANCELLED`, `SUCCEEDED`, `SUCCEEDED_WITH_WARNINGS`, `PARTIAL`, `BLOCKED_EXTERNAL`, `BLOCKED_HUMAN`, `FAILED`, `TIMED_OUT`.

Streaming: `GET /api/jobs/{id}/events` (SSE).

Persistence: SQLite `jobs` + `job_logs` + `audit`.

Cancel: terminate/kill when capability allows.
