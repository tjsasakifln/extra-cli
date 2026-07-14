"""Coverage Manifest by Capability — Story 1.5.

Gera reports de cobertura por capacidade de negocio:

    - open_tenders        — Licitacoes abertas detectaveis
    - historical_contracts — Contratos historicos disponiveis
    - competitors          — Dados de concorrentes (fornecedores)
    - prices               — Dados de precos praticados
    - entity_matching     — Qualidade do entity matching
    - coverage_truth      — Precisao das metricas de cobertura
    - source_health       - Saude operacional das fontes

Cada metrica e independente — data presence nunca altera coverage.
success_zero conta como "covered" (o ente foi verificado e confirmado sem dados).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class CoverageManifestEntry:
    """A single entry in the coverage manifest.

    Reports coverage for one (capability, source) pair.
    """

    capability: str
    source: str
    total_pairs: int = 0
    covered_pairs: int = 0
    pct_covered: float = 0.0

    # Breakdown by state
    with_data: int = 0
    zero_data: int = 0
    partial: int = 0
    not_applicable: int = 0
    pending: int = 0
    in_progress: int = 0
    blocked: int = 0
    stale: int = 0
    errored: int = 0

    # Freshness
    fresh_count: int = 0
    stale_count: int = 0
    unknown_freshness: int = 0

    # Metadata
    last_check_at: datetime | None = None


@dataclass
class CoverageManifest:
    """Complete coverage manifest for all capabilities.

    Atende aos ACs da Secao 3 e Secao 9.
    """

    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    manifest_version: str = "1.0"
    total_capabilities: int = 0
    total_sources: int = 0
    entries: list[CoverageManifestEntry] = field(default_factory=list)

    # Aggregate metrics (Secao 3)
    universe_resolution_pct: float = 100.0
    source_applicability_resolution_pct: float = 0.0
    capability_monitoring_coverage_pct: float = 0.0
    active_snapshot_integrity_pct: float = 0.0

    # Blockers
    blockers: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize manifest to dict for JSON/YAML output."""
        return {
            "generated_at": self.generated_at.isoformat(),
            "manifest_version": self.manifest_version,
            "total_capabilities": self.total_capabilities,
            "total_sources": self.total_sources,
            "metrics": {
                "universe_resolution_pct": self.universe_resolution_pct,
                "source_applicability_resolution_pct": self.source_applicability_resolution_pct,
                "capability_monitoring_coverage_pct": self.capability_monitoring_coverage_pct,
                "active_snapshot_integrity_pct": self.active_snapshot_integrity_pct,
            },
            "entries": [
                {
                    "capability": e.capability,
                    "source": e.source,
                    "total_pairs": e.total_pairs,
                    "covered_pairs": e.covered_pairs,
                    "pct_covered": e.pct_covered,
                    "breakdown": {
                        "with_data": e.with_data,
                        "zero_data": e.zero_data,
                        "partial": e.partial,
                        "not_applicable": e.not_applicable,
                        "pending": e.pending,
                        "in_progress": e.in_progress,
                        "blocked": e.blocked,
                        "stale": e.stale,
                        "errored": e.errored,
                    },
                    "freshness": {
                        "fresh": e.fresh_count,
                        "stale": e.stale_count,
                        "unknown": e.unknown_freshness,
                    },
                    "last_check_at": e.last_check_at.isoformat() if e.last_check_at else None,
                }
                for e in self.entries
            ],
            "blockers": self.blockers,
            "warnings": self._generate_warnings(),
        }

    def to_markdown(self) -> str:
        """Render manifest as markdown report."""
        lines = [
            "# Coverage Manifest",
            "",
            f"**Generated at:** {self.generated_at.isoformat()}",
            f"**Version:** {self.manifest_version}",
            "",
            "## Metrics (Secao 3)",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| universe_resolution | {self.universe_resolution_pct:.1f}% |",
            f"| source_applicability_resolution | {self.source_applicability_resolution_pct:.1f}% |",
            f"| capability_monitoring_coverage | {self.capability_monitoring_coverage_pct:.1f}% |",
            f"| active_snapshot_integrity | {self.active_snapshot_integrity_pct:.1f}% |",
            "",
            "## Coverage by Capability",
            "",
            "| Capability | Source | Total | Covered | % | With Data | Zero | Partial | Blocked | Error |",
            "|------------|--------|-------|---------|---|-----------|------|---------|---------|-------|",
        ]
        for e in self.entries:
            lines.append(
                f"| {e.capability} | {e.source} | {e.total_pairs} | {e.covered_pairs} | "
                f"{e.pct_covered:.1f}% | {e.with_data} | {e.zero_data} | "
                f"{e.partial} | {e.blocked} | {e.errored} |"
            )

        if self.blockers:
            lines.extend(
                [
                    "",
                    "## Blockers",
                    "",
                    "| Source | Entity | Action Required | Recommended Action | Owner |",
                    "|--------|--------|----------------|--------------------|-------|",
                ]
            )
            for b in self.blockers:
                lines.append(
                    f"| {b.get('source', '')} | {b.get('entity', '')} | "
                    f"{b.get('action_required', '')} | "
                    f"{b.get('recommended_action', '')} | "
                    f"{b.get('owner', 'TBD')} |"
                )

        lines.append("")
        return "\n".join(lines)

    def _generate_warnings(self) -> list[str]:
        """Generate warnings from manifest data."""
        warnings: list[str] = []
        for e in self.entries:
            if e.blocked > 0:
                warnings.append(f"[{e.capability}/{e.source}] {e.blocked} blocked pairs — action required to unblock")
            if e.stale > 0 and e.stale > e.total_pairs * 0.2:
                warnings.append(
                    f"[{e.capability}/{e.source}] {e.stale} stale pairs "
                    f"({e.stale / e.total_pairs * 100:.0f}%) — above 20% threshold"
                )
            if e.pct_covered < 50.0:
                warnings.append(f"[{e.capability}/{e.source}] Coverage {e.pct_covered:.1f}% below 50% threshold")
        return warnings


def build_manifest_from_db(
    conn: Any,
    capabilities: list[str] | None = None,
) -> CoverageManifest:
    """Build coverage manifest from database (v_coverage_manifest view).

    Args:
        conn: Database connection.
        capabilities: Optional list of capabilities to include.
                     If None, includes all.

    Returns:
        CoverageManifest with entries from the DB.
    """
    import psycopg2

    manifest = CoverageManifest()
    cur = conn.cursor()

    try:
        # Check if view exists
        cur.execute("SELECT EXISTS (SELECT 1 FROM information_schema.views WHERE table_name = 'v_coverage_manifest')")
        view_exists = cur.fetchone()[0]

        if not view_exists:
            manifest.entries = []
            manifest.blockers = [
                {
                    "source": "system",
                    "entity": "v_coverage_manifest",
                    "action_required": "Run migration 040 to create coverage manifest view",
                    "recommended_action": "Apply migration 040_coverage_model_expansion.sql",
                    "owner": "Dex (@dev)",
                }
            ]
            return manifest

        # Query manifest view
        query = "SELECT * FROM v_coverage_manifest"
        params: list[str] = []
        if capabilities:
            placeholders = ",".join("%s" for _ in capabilities)
            query += f" WHERE capability IN ({placeholders})"
            params = capabilities

        cur.execute(query, params)
        cols = [d[0] for d in cur.description]
        for row in cur.fetchall():
            data = dict(zip(cols, row))
            entry = CoverageManifestEntry(
                capability=data.get("capability", ""),
                source=data.get("source", ""),
                total_pairs=data.get("total_entity_pairs", 0),
                covered_pairs=data.get("covered_pairs", 0),
                pct_covered=float(data.get("pct_covered", 0.0)),
                with_data=data.get("with_data", 0),
                zero_data=data.get("zero_data", 0),
                partial=data.get("partial", 0),
                in_progress=data.get("in_progress", 0),
                blocked=data.get("blocked", 0),
                stale=data.get("stale", 0),
                errored=data.get("errored", 0),
                last_check_at=data.get("last_check_at"),
            )
            manifest.entries.append(entry)

        manifest.total_capabilities = len(set(e.capability for e in manifest.entries))
        manifest.total_sources = len(set(e.source for e in manifest.entries))

        # Aggregate metrics
        total_covered = sum(e.covered_pairs for e in manifest.entries)
        total_all = sum(e.total_pairs for e in manifest.entries)
        if total_all > 0:
            manifest.capability_monitoring_coverage_pct = round(total_covered / total_all * 100, 1)

    except psycopg2.Error as e:
        manifest.entries = []
        manifest.blockers = [
            {
                "source": "database",
                "entity": "v_coverage_manifest",
                "action_required": f"Database error querying manifest: {e}",
                "recommended_action": "Verify migration 040 applied and database accessible",
                "owner": "Dex (@dev)",
            }
        ]
    finally:
        cur.close()

    return manifest


__all__ = [
    "CoverageManifest",
    "CoverageManifestEntry",
    "build_manifest_from_db",
]
