"""Test canonical status computation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from scripts.opportunity_intel.status import (
    compute_canonical_status,
    is_active_status,
    is_terminal_status,
    needs_review,
)


class TestComputeCanonicalStatus:
    """Test status computation from various inputs."""

    def test_pncp_recebendo_proposta(self):
        status, motivo = compute_canonical_status(
            status_fonte="recebendo proposta",
            source="pncp",
        )
        assert status == "open"
        assert "PNCP" in motivo

    def test_pncp_encerrada(self):
        status, motivo = compute_canonical_status(
            status_fonte="encerrada",
            source="pncp",
        )
        assert status == "closed"

    def test_pncp_suspensa(self):
        status, motivo = compute_canonical_status(
            status_fonte="suspensa",
            source="pncp",
        )
        assert status == "suspended"

    def test_pncp_revogada(self):
        status, motivo = compute_canonical_status(
            status_fonte="revogada",
            source="pncp",
        )
        assert status == "revoked"

    def test_pncp_anulada(self):
        status, motivo = compute_canonical_status(
            status_fonte="anulada",
            source="pncp",
        )
        assert status == "annulled"

    def test_pncp_deserta(self):
        status, motivo = compute_canonical_status(
            status_fonte="deserta",
            source="pncp",
        )
        assert status == "failed"

    def test_pncp_fracassada(self):
        status, motivo = compute_canonical_status(
            status_fonte="fracassada",
            source="pncp",
        )
        assert status == "failed"

    def test_dom_sc_publicado(self):
        status, motivo = compute_canonical_status(
            status_fonte="Publicado",
            source="dom_sc",
        )
        assert status == "open"

    def test_dom_sc_cancelado(self):
        status, motivo = compute_canonical_status(
            status_fonte="Cancelado",
            source="dom_sc",
        )
        assert status == "revoked"

    def test_generic_aberta(self):
        status, motivo = compute_canonical_status(
            status_fonte="aberta",
            source="unknown",
        )
        assert status == "open"

    def test_generic_suspenso(self):
        status, motivo = compute_canonical_status(
            status_fonte="suspenso",
            source="unknown",
        )
        assert status == "suspended"

    def test_case_insensitive(self):
        status, motivo = compute_canonical_status(
            status_fonte="RECEBENDO PROPOSTA",
            source="pncp",
        )
        assert status == "open"

    def test_temporal_open_future_deadline(self):
        now = datetime.now(UTC)
        yesterday = now - timedelta(days=1)
        next_week = now + timedelta(days=7)
        status, motivo = compute_canonical_status(
            status_fonte=None,
            data_abertura=yesterday,
            data_encerramento=next_week,
        )
        assert status == "open"
        assert "futuro" in motivo.lower()

    def test_temporal_closed_past_deadline(self):
        now = datetime.now(UTC)
        last_month = now - timedelta(days=30)
        last_week = now - timedelta(days=7)
        status, motivo = compute_canonical_status(
            status_fonte=None,
            data_abertura=last_month,
            data_encerramento=last_week,
        )
        assert status == "closed"

    def test_temporal_upcoming_future_abertura(self):
        now = datetime.now(UTC)
        next_week = now + timedelta(days=7)
        status, motivo = compute_canonical_status(
            status_fonte=None,
            data_abertura=next_week,
        )
        assert status == "upcoming"
        assert "futuro" in motivo.lower()

    def test_unknown_no_data(self):
        status, motivo = compute_canonical_status(
            status_fonte=None,
        )
        assert status == "unknown"
        assert "sem status_fonte" in motivo.lower()

    def test_fail_closed_recent_publication(self):
        """Recent publication without explicit status → unknown, NOT open."""
        now = datetime.now(UTC)
        yesterday = now - timedelta(days=1)
        status, motivo = compute_canonical_status(
            status_fonte=None,
            data_publicacao=yesterday,
        )
        assert status == "unknown"  # fail-closed: not open just by recency
        assert "fail-closed" in motivo.lower()

    def test_closed_old_publication(self):
        """Old publication (>90d) without status → closed."""
        now = datetime.now(UTC)
        six_months_ago = now - timedelta(days=180)
        status, motivo = compute_canonical_status(
            status_fonte=None,
            data_publicacao=six_months_ago,
        )
        assert status == "closed"

    def test_source_status_overrides_temporal(self):
        """Source status should take priority over temporal evidence."""
        now = datetime.now(UTC)
        next_week = now + timedelta(days=7)
        # Temporal evidence suggests "open" but source says "revogada"
        status, motivo = compute_canonical_status(
            status_fonte="revogada",
            source="pncp",
            data_abertura=now,
            data_encerramento=next_week,
        )
        assert status == "revoked"  # source wins


class TestStatusHelpers:
    """Test status helper functions."""

    def test_is_active_status(self):
        assert is_active_status("open") is True
        assert is_active_status("upcoming") is True
        assert is_active_status("suspended") is True
        assert is_active_status("closed") is False
        assert is_active_status("revoked") is False

    def test_is_terminal_status(self):
        assert is_terminal_status("closed") is True
        assert is_terminal_status("revoked") is True
        assert is_terminal_status("annulled") is True
        assert is_terminal_status("failed") is True
        assert is_terminal_status("open") is False
        assert is_terminal_status("unknown") is False

    def test_needs_review(self):
        assert needs_review("unknown") is True
        assert needs_review("suspended") is True
        assert needs_review("open") is False
        assert needs_review("closed") is False
