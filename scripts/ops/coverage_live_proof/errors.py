"""Typed failures for the coverage live-proof orchestrator."""

from __future__ import annotations


class CoverageLiveProofError(Exception):
    """Base error for the live-proof runner."""


class MissingDsnError(CoverageLiveProofError):
    """No explicit DSN was provided."""


class ProductionDsnError(CoverageLiveProofError):
    """DSN points at a known production host or database."""


class NotPostgresError(CoverageLiveProofError):
    """Connection is not a real PostgreSQL server."""


class FakeConnectionError(CoverageLiveProofError):
    """MagicMock, unittest mock, or other fake proxy was supplied."""


class MigrationApplyError(CoverageLiveProofError):
    """Canonical apply_migrations failed."""


class TeardownSafetyError(CoverageLiveProofError):
    """Refusing to drop a database that this campaign did not create."""


class EphemeralProvisionError(CoverageLiveProofError):
    """Could not create an ephemeral proof database."""


class SeedError(CoverageLiveProofError):
    """Deterministic seed could not be applied."""


class ScenarioExpectationError(CoverageLiveProofError):
    """A seeded scenario did not match the shipped identity rules."""
