"""today works offline with fixture session data — never crashes silently."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.workspace.cli import build_parser, cmd_today  # noqa: E402
from scripts.workspace.queue import build_today  # noqa: E402


@pytest.fixture
def no_pg(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force PG unavailable and clear DSN."""
    monkeypatch.delenv("LOCAL_DATALAKE_DSN", raising=False)
    monkeypatch.setenv("LOCAL_DATALAKE_DSN", "postgresql://invalid:invalid@127.0.0.1:1/none")

    def _fail_conn(*_a, **_k):  # type: ignore[no-untyped-def]
        raise ConnectionError("forced offline for test")

    # Patch at common.try_pg_conn level
    monkeypatch.setattr(
        "scripts.workspace.queue.try_pg_conn",
        lambda dsn=None, timeout=3: (None, "PostgreSQL unavailable: forced offline"),
    )
    monkeypatch.setattr(
        "scripts.workspace.common.try_pg_conn",
        lambda dsn=None, timeout=3: (None, "PostgreSQL unavailable: forced offline"),
    )


class TestTodayOffline:
    def test_build_today_never_raises(self, no_pg: None) -> None:
        payload = build_today(dsn="postgresql://invalid:invalid@127.0.0.1:1/none")
        assert payload["command"] == "today"
        assert "sections" in payload
        assert len(payload["sections"]) >= 6
        assert payload["pg_available"] is False

    def test_sections_have_status(self, no_pg: None) -> None:
        payload = build_today()
        for sec in payload["sections"]:
            assert sec["status"] in {"OK", "EMPTY", "UNAVAILABLE"}
            assert sec["name"]
            # UNAVAILABLE must explain why
            if sec["status"] == "UNAVAILABLE":
                assert sec.get("reason"), f"UNAVAILABLE without reason: {sec['name']}"

    def test_pending_profile_section_present(self, no_pg: None) -> None:
        payload = build_today()
        names = [s["name"] for s in payload["sections"]]
        assert any("perfil" in n.lower() or "pendente" in n.lower() for n in names)
        profile_sec = next(
            s for s in payload["sections"] if "perfil" in s["name"].lower() or "pendente" in s["name"].lower()
        )
        # With PENDING markers in extra.yaml we expect OK + items
        assert profile_sec["status"] in {"OK", "EMPTY", "UNAVAILABLE"}
        if profile_sec["status"] == "OK":
            fields = {i.get("field") for i in profile_sec.get("items") or []}
            assert "capital_giro" in fields or "margem_minima" in fields

    def test_session_fallback_or_unavailable_honest(self, no_pg: None) -> None:
        """With session artifacts present, at least one opp section should be OK/EMPTY not crash."""
        payload = build_today()
        new_sec = payload["sections"][0]
        assert new_sec["status"] in {"OK", "EMPTY", "UNAVAILABLE"}
        # If session files exist, prefer OK
        session_sample = _ROOT / "output" / "session-2026-07-17" / "radar_opportunities_sample.jsonl"
        commercial = _ROOT / "docs" / "ops" / "session-2026-07-17" / "commercial-sample-sc.json"
        if session_sample.exists() or commercial.exists():
            # May still be EMPTY if filters exclude all — but not silent exception
            assert isinstance(new_sec.get("items"), list)

    def test_cmd_today_json_stdout(self, no_pg: None, capsys: pytest.CaptureFixture[str]) -> None:
        parser = build_parser()
        args = parser.parse_args(["today", "--json"])
        code = cmd_today(args)
        assert code == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["command"] == "today"
        assert len(data["sections"]) >= 6

    def test_cmd_today_text_stdout(self, no_pg: None, capsys: pytest.CaptureFixture[str]) -> None:
        parser = build_parser()
        args = parser.parse_args(["today"])
        code = cmd_today(args)
        assert code == 0
        out = capsys.readouterr().out
        assert "WORKSPACE TODAY" in out
        assert "UNAVAILABLE" in out or "OK" in out or "EMPTY" in out
