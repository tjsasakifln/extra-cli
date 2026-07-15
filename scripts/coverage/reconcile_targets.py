#!/usr/bin/env python3
"""Target universe reconciliation — CM-03.

Reads the target universe manifest, reconciliation CSV, and source coverage
CSV to produce a reconciliation report with recall metrics by entity type,
municipality, source breakdown, and missed-entity root cause classification.

Usage:
    python scripts/coverage/reconcile_targets.py
    python scripts/coverage/reconcile_targets.py --format json
    python scripts/coverage/reconcile_targets.py --format table --output-csv report.csv

CLI integration:
    python scripts/opportunity_intel/cli.py reconcile
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants — file paths
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent.parent
TARGET_MANIFEST = BASE_DIR / "output" / "readiness" / "target-universe-manifest.json"
RECONCILIATION_CSV = BASE_DIR / "output" / "readiness" / "target-reconciliation.csv"
SOURCE_COVERAGE_CSV = BASE_DIR / "output" / "readiness" / "source-entity-coverage.csv"

# ---------------------------------------------------------------------------
# Root cause heuristic (from validate_coverage.py + refinements)
# Maps natureza_juridica to a root cause category for missed entities.
# ---------------------------------------------------------------------------

NATUREZA_ROOT_CAUSE: dict[str, str] = {
    # === Lei das Estatais (13.303/2016) — nao abrangidas pela Lei 14.133 ===
    "Serviço Social Autônomo": "NAO_ABRANGIDO_LEI_14133",
    "Consórcio Público de Direito Privado": "NAO_ABRANGIDO_LEI_14133",
    "Sociedade de Economia Mista": "NAO_ABRANGIDO_LEI_14133",
    "Empresa Pública": "NAO_ABRANGIDO_LEI_14133",
    # === Orgaos do Judiciario — regime juridico distinto (LC 35/79) ===
    "Órgão Público do Poder Judiciário Estadual": "NAO_ABRANGIDO_LEI_14133",
    "Órgão Público do Poder Judiciário Federal": "NAO_ABRANGIDO_LEI_14133",
    # === Fundos publicos — raramente publicam em portais de licitacao ===
    "Fundo Público da Administração Indireta Estadual ou do Distrito Federal": "SEM_DADOS_PUBLICOS",
    "Fundo Público da Administração Direta Estadual ou do Distrito Federal": "SEM_DADOS_PUBLICOS",
    "Fundo Público da Administração Direta Federal": "SEM_DADOS_PUBLICOS",
    # === Fundacoes de direito privado — regime hibrido ===
    "Fundação Pública de Direito Privado Federal": "SEM_DADOS_PUBLICOS",
    "Fundação Pública de Direito Privado Municipal": "SEM_DADOS_PUBLICOS",
    # === Fundacoes de direito publico — cobertura PNCP incompleta ===
    "Fundação Pública de Direito Público Municipal": "SEM_DADOS_PUBLICOS",
    "Fundação Pública de Direito Público Estadual ou do Distrito Federal": "SEM_DADOS_PUBLICOS",
    "Fundação Pública de Direito Público Federal": "SEM_DADOS_PUBLICOS",
    # === Autarquias — cobertura PNCP incompleta ===
    "Autarquia Municipal": "SEM_DADOS_PUBLICOS",
    "Autarquia Federal": "SEM_DADOS_PUBLICOS",
    "Autarquia Estadual ou do Distrito Federal": "SEM_DADOS_PUBLICOS",
    # === Orgaos autonomos ===
    "Órgão Público Autônomo Municipal": "SEM_DADOS_PUBLICOS",
    "Órgão Público Autônomo Estadual ou do Distrito Federal": "SEM_DADOS_PUBLICOS",
    "Órgão Público Autônomo Federal": "SEM_DADOS_PUBLICOS",
    # === Entes estaduais/federais ===
    "Estado ou Distrito Federal": "SEM_DADOS_PUBLICOS",
    "Órgão Público do Poder Executivo Estadual ou do Distrito Federal": "SEM_DADOS_PUBLICOS",
    "Órgão Público do Poder Executivo Federal": "SEM_DADOS_PUBLICOS",
    # === Orgaos legislativos — publicam no DOM-SC ===
    "Órgão Público do Poder Legislativo Municipal": "DOM_SC_PENDENTE",
    "Órgão Público do Poder Legislativo Estadual ou do Distrito Federal": "DOM_SC_PENDENTE",
    "Órgão Público do Poder Legislativo Federal": "DOM_SC_PENDENTE",
    # === Consorcios ===
    "Consórcio Público de Direito Público (Associação Pública)": "SEM_DADOS_PUBLICOS",
}

# ---------------------------------------------------------------------------
# Short label mapping — natureza_juridica -> canonical entity type label
# (mirrors target-universe-manifest.json entity_types labels)
# ---------------------------------------------------------------------------

NATUREZA_SHORT_LABEL: dict[str, str] = {
    "Município": "Prefeitura Municipal",
    "Órgão Público do Poder Executivo Municipal": "Secretaria Municipal",
    "Órgão Público do Poder Legislativo Municipal": "Camara Municipal",
    "Órgão Público do Poder Legislativo Estadual ou do Distrito Federal": "Assembleia Legislativa",
    "Órgão Público do Poder Legislativo Federal": "Camara Federal",
    "Órgão Público do Poder Executivo Estadual ou do Distrito Federal": "Orgao Estadual",
    "Órgão Público do Poder Executivo Federal": "Orgao Federal",
    "Órgão Público do Poder Judiciário Estadual": "Poder Judiciario Estadual",
    "Órgão Público do Poder Judiciário Federal": "Poder Judiciario Federal",
    "Autarquia Municipal": "Autarquia Municipal",
    "Autarquia Estadual ou do Distrito Federal": "Autarquia Estadual",
    "Autarquia Federal": "Autarquia Federal",
    "Fundação Pública de Direito Público Municipal": "Fundacao Municipal",
    "Fundação Pública de Direito Público Estadual ou do Distrito Federal": "Fundacao Estadual",
    "Fundação Pública de Direito Público Federal": "Fundacao Federal",
    "Fundação Pública de Direito Privado Municipal": "Fundacao Privada Municipal",
    "Fundação Pública de Direito Privado Federal": "Fundacao Privada Federal",
    "Fundo Público da Administração Direta Estadual ou do Distrito Federal": "Fundo Estadual",
    "Fundo Público da Administração Direta Federal": "Fundo Federal",
    "Fundo Público da Administração Indireta Estadual ou do Distrito Federal": "Fundo Estadual",
    "Sociedade de Economia Mista": "Sociedade Economia Mista",
    "Empresa Pública": "Empresa Publica",
    "Consórcio Público de Direito Público (Associação Pública)": "Consorcio Publico",
    "Consórcio Público de Direito Privado": "Consorcio Privado",
    "Serviço Social Autônomo": "Servico Social Autonomo",
    "Estado ou Distrito Federal": "Governo Estadual",
    "Órgão Público Autônomo Estadual ou do Distrito Federal": "Orgao Autonomo",
    "Órgão Público Autônomo Municipal": "Orgao Autonomo",
    "Órgão Público Autônomo Federal": "Orgao Autonomo",
}

ROOT_CAUSE_LABELS: dict[str, str] = {
    "MISSED_SOURCE_NOT_COVERED": "SOURCE_NOT_COVERED",
    "MISSED_GEOGRAPHY": "GEOGRAPHY",
    "FOUND_EXACT": "MATCHED",
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class EntityReconciliation:
    """A single entity's reconciliation record."""

    entity_id: int
    razao_social: str
    cnpj_8: str
    municipio: str
    codigo_ibge: str
    natureza_juridica: str
    latitude: str
    longitude: str
    distancia_km: str
    raio_flag: str
    is_target: bool
    match_status: str
    match_detail: str


@dataclass
class SourceCoverageEntry:
    """A single entry from the source-entity-coverage CSV."""

    cnpj_8: str
    razao_social: str
    municipio: str
    natureza_juridica: str
    has_opportunity: bool
    source: str
    opportunity_count: int


@dataclass
class GroupedRecall:
    """Recall metrics for a group (natureza, municipio, etc.)."""

    group: str
    total: int
    matched: int
    pct: float


@dataclass
class ReconciliationReport:
    """Complete reconciliation report."""

    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    manifest_version: str = "1.0"

    # Global
    total_targets: int = 0
    total_matched: int = 0
    recall_pct: float = 0.0

    # By match status
    match_status_breakdown: dict[str, int] = field(default_factory=dict)

    # By entity type (short label)
    recall_by_natureza: list[GroupedRecall] = field(default_factory=list)

    # By municipio
    recall_by_municipio: list[GroupedRecall] = field(default_factory=list)

    # Top missed (sorted by entity, up to 50)
    top_missed: list[dict[str, Any]] = field(default_factory=list)

    # Source coverage breakdown (from source-entity-coverage.csv)
    source_coverage: dict[str, int] = field(default_factory=dict)

    # Miss classification by root cause
    root_cause_breakdown: dict[str, int] = field(default_factory=dict)

    # Manifest metadata
    radius_km: float = 200.0
    origin_city: str = ""
    total_in_spreadsheet: int = 0
    total_with_coords: int = 0
    within_radius: int = 0
    unique_municipalities: int = 0

    # Debug fields
    loader_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "manifest_version": self.manifest_version,
            "origin": {
                "city": self.origin_city,
                "radius_km": self.radius_km,
            },
            "universe": {
                "total_in_spreadsheet": self.total_in_spreadsheet,
                "total_with_coords": self.total_with_coords,
                "within_radius": self.within_radius,
                "unique_municipalities": self.unique_municipalities,
            },
            "global_recall": {
                "total_targets": self.total_targets,
                "total_matched": self.total_matched,
                "recall_pct": round(self.recall_pct, 1),
            },
            "match_status_breakdown": dict(
                sorted(self.match_status_breakdown.items(), key=lambda x: -x[1])
            ),
            "recall_by_entity_type": [
                {"entity_type": r.group, "total": r.total, "matched": r.matched, "recall_pct": round(r.pct, 1)}
                for r in sorted(self.recall_by_natureza, key=lambda x: -x.total)
            ],
            "recall_by_municipio_top_30": [
                {"municipio": r.group, "total": r.total, "matched": r.matched, "recall_pct": round(r.pct, 1)}
                for r in sorted(self.recall_by_municipio, key=lambda x: -x.total)[:30]
            ],
            "top_missed_entities": self.top_missed[:50],
            "source_coverage": dict(
                sorted(self.source_coverage.items(), key=lambda x: -x[1])
            ),
            "root_cause_breakdown": dict(
                sorted(self.root_cause_breakdown.items(), key=lambda x: -x[1])
            ),
            "total_missed": self.total_targets - self.total_matched,
        }

    def to_markdown(self) -> str:
        """Render report as a markdown summary (for --format table)."""
        lines: list[str] = [
            "# Relatorio de Reconciliacao — CM-03",
            "",
            f"Gerado em: {self.generated_at}",
            f"Origem: {self.origin_city} | Raio: {self.radius_km}km",
            "",
            "## 1. Resumo do Universo",
            "",
            "| Metrica | Valor |",
            "|---------|-------|",
            f"| Total na planilha | {self.total_in_spreadsheet} |",
            f"| Com coordenadas | {self.total_with_coords} |",
            f"| Dentro do raio | {self.within_radius} |",
            f"| Municipios unicos | {self.unique_municipalities} |",
            f"| **Alvos (targets)** | **{self.total_targets}** |",
            "",
            "## 2. Recall Global",
            "",
            "| Metrica | Valor |",
            "|---------|-------|",
            f"| Matched (FOUND_EXACT) | {self.total_matched} |",
            f"| Missed | {self.total_targets - self.total_matched} |",
            f"| **Recall** | **{self.recall_pct:.1f}%** |",
            "",
            "### Match Status Breakdown",
            "",
        ]
        for status, count in sorted(self.match_status_breakdown.items(), key=lambda x: -x[1]):
            lines.append(f"- **{status}**: {count}")
        lines.append("")

        # Recall by entity type
        lines.extend([
            "## 3. Recall por Tipo de Entidade",
            "",
            "| Tipo de Entidade | Total | Matched | Recall |",
            "|------------------|-------|---------|--------|",
        ])
        for r in sorted(self.recall_by_natureza, key=lambda x: -x.total):
            bar = _make_bar(r.pct, 20)
            lines.append(f"| {r.group:35s} | {r.total:5d} | {r.matched:5d} | {r.pct:5.1f}% {bar} |")

        # Recall by municipio (top 10)
        lines.extend([
            "",
            "## 4. Recall por Municipio (Top 10 por total de entes)",
            "",
            "| Municipio | Total | Matched | Recall |",
            "|-----------|-------|---------|--------|",
        ])
        for r in sorted(self.recall_by_municipio, key=lambda x: -x.total)[:10]:
            bar = _make_bar(r.pct, 20)
            lines.append(f"| {r.group:25s} | {r.total:5d} | {r.matched:5d} | {r.pct:5.1f}% {bar} |")

        # Root cause breakdown
        lines.extend([
            "",
            "## 5. Classificacao por Causa Raiz (Missed Entities)",
            "",
            "| Causa Raiz | Quantidade | % dos Missed |",
            "|------------|------------|--------------|",
        ])
        total_missed = self.total_targets - self.total_matched
        for cause, count in sorted(self.root_cause_breakdown.items(), key=lambda x: -x[1]):
            pct = count / total_missed * 100 if total_missed else 0
            lines.append(f"| {cause:35s} | {count:8d} | {pct:5.1f}% |")

        # Source coverage
        lines.extend([
            "",
            "## 6. Cobertura por Fonte",
            "",
            "| Fonte | Entes com Dados |",
            "|-------|----------------|",
        ])
        for source, count in sorted(self.source_coverage.items(), key=lambda x: -x[1]):
            lines.append(f"| {source:10s} | {count:5d} |")

        # Top missed entities
        lines.extend([
            "",
            "## 7. Top Entes Nao Encontrados (Primeiros 20)",
            "",
            "| Ente | Municipio | Tipo | Status |",
            "|------|-----------|------|--------|",
        ])
        for m in self.top_missed[:20]:
            lines.append(
                f"| {m.get('razao_social', '')[:45]:45s} "
                f"| {m.get('municipio', ''):20s} "
                f"| {_short_nat(m.get('natureza_juridica', '')):25s} "
                f"| {m.get('match_status', ''):30s} |"
            )

        lines.append("")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bar(pct: float, width: int = 20) -> str:
    """Generate a simple ASCII bar for a percentage."""
    filled = round(pct / 100 * width)
    return "[" + "#" * filled + "." * (width - filled) + "]"


def _short_nat(natureza: str) -> str:
    return NATUREZA_SHORT_LABEL.get(natureza, natureza)


def _infer_root_cause(natureza: str, match_status: str) -> str:
    """Infer root cause for a missed entity."""
    if match_status == "FOUND_EXACT":
        return "MATCHED"
    if match_status == "MISSED_GEOGRAPHY":
        return "GEOGRAPHY"
    # MISSED_SOURCE_NOT_COVERED -> use heuristic by natureza
    return NATUREZA_ROOT_CAUSE.get(natureza, "NAO_INVESTIGADO")


def _normalize_cnpj(cnpj: str) -> str:
    """Strip punctuation from CNPJ for comparison."""
    return cnpj.replace(".", "").replace("/", "").replace("-", "").replace(" ", "")


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def load_manifest(path: str | Path = TARGET_MANIFEST) -> dict[str, Any]:
    """Load target universe manifest."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_reconciliation(path: str | Path = RECONCILIATION_CSV) -> list[EntityReconciliation]:
    """Load target-reconciliation CSV, returning only target entities."""
    entities: list[EntityReconciliation] = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            is_target = row.get("is_target_200km", "").strip() == "True"
            if not is_target:
                continue
            entities.append(
                EntityReconciliation(
                    entity_id=int(row.get("id", 0)),
                    razao_social=row.get("razao_social", ""),
                    cnpj_8=_normalize_cnpj(row.get("cnpj_8", "")),
                    municipio=row.get("municipio", ""),
                    codigo_ibge=row.get("codigo_ibge", ""),
                    natureza_juridica=row.get("natureza_juridica", ""),
                    latitude=row.get("latitude", ""),
                    longitude=row.get("longitude", ""),
                    distancia_km=row.get("distancia_km", ""),
                    raio_flag=row.get("raio_flag", ""),
                    is_target=True,
                    match_status=row.get("match_status", "UNKNOWN"),
                    match_detail=row.get("match_detail", ""),
                )
            )
    return entities


def load_source_coverage(path: str | Path = SOURCE_COVERAGE_CSV) -> list[SourceCoverageEntry]:
    """Load source-entity-coverage CSV."""
    entries: list[SourceCoverageEntry] = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            entries.append(
                SourceCoverageEntry(
                    cnpj_8=_normalize_cnpj(row.get("cnpj_8", "")),
                    razao_social=row.get("razao_social", ""),
                    municipio=row.get("municipio", ""),
                    natureza_juridica=row.get("natureza_juridica", ""),
                    has_opportunity=row.get("has_opportunity", "").strip().lower() == "true",
                    source=row.get("source", ""),
                    opportunity_count=int(row.get("opportunity_count", 0) or 0),
                )
            )
    return entries


# ---------------------------------------------------------------------------
# Reconcilier
# ---------------------------------------------------------------------------


def build_report(
    target_manifest: dict[str, Any] | None = None,
    reconciliations: list[EntityReconciliation] | None = None,
    source_coverage: list[SourceCoverageEntry] | None = None,
) -> ReconciliationReport:
    """Build the full reconciliation report from data sources."""
    report = ReconciliationReport()

    # --- Load data if not provided ---
    if target_manifest is None:
        try:
            target_manifest = load_manifest()
        except Exception as e:
            report.loader_errors.append(f"Failed to load manifest: {e}")
            target_manifest = {}

    if reconciliations is None:
        try:
            reconciliations = load_reconciliation()
        except Exception as e:
            report.loader_errors.append(f"Failed to load reconciliation CSV: {e}")
            reconciliations = []

    if source_coverage is None:
        try:
            source_coverage = load_source_coverage()
        except Exception as e:
            report.loader_errors.append(f"Failed to load source coverage CSV: {e}")
            source_coverage = []

    # --- Universe metadata ---
    report.origin_city = target_manifest.get("origin", {}).get("city", "")
    report.radius_km = target_manifest.get("radius_km", 200.0)
    report.total_in_spreadsheet = target_manifest.get("total_in_spreadsheet", 0)
    report.total_with_coords = target_manifest.get("total_with_coords", 0)
    report.within_radius = target_manifest.get("within_radius", 0)
    report.unique_municipalities = target_manifest.get("unique_municipalities_within_radius", 0)

    # --- Global recall ---
    report.total_targets = len(reconciliations)
    report.total_matched = sum(1 for e in reconciliations if e.match_status == "FOUND_EXACT")
    report.recall_pct = (report.total_matched / report.total_targets * 100) if report.total_targets else 0.0

    # --- Match status breakdown ---
    status_counts: Counter[str] = Counter()
    for e in reconciliations:
        status_counts[e.match_status] += 1
    report.match_status_breakdown = dict(status_counts)

    # --- Recall by natureza_juridica ---
    nat_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "matched": 0})
    for e in reconciliations:
        label = _short_nat(e.natureza_juridica)
        nat_stats[label]["total"] += 1
        if e.match_status == "FOUND_EXACT":
            nat_stats[label]["matched"] += 1
    report.recall_by_natureza = [
        GroupedRecall(
            group=label,
            total=stats["total"],
            matched=stats["matched"],
            pct=(stats["matched"] / stats["total"] * 100) if stats["total"] else 0.0,
        )
        for label, stats in nat_stats.items()
    ]

    # --- Recall by municipio ---
    mun_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "matched": 0})
    for e in reconciliations:
        mun_stats[e.municipio]["total"] += 1
        if e.match_status == "FOUND_EXACT":
            mun_stats[e.municipio]["matched"] += 1
    report.recall_by_municipio = [
        GroupedRecall(
            group=mun,
            total=stats["total"],
            matched=stats["matched"],
            pct=(stats["matched"] / stats["total"] * 100) if stats["total"] else 0.0,
        )
        for mun, stats in mun_stats.items()
    ]

    # --- Top missed entities ---
    missed: list[EntityReconciliation] = [e for e in reconciliations if e.match_status != "FOUND_EXACT"]
    missed.sort(key=lambda e: (e.municipio, e.razao_social))
    report.top_missed = [
        {
            "id": e.entity_id,
            "razao_social": e.razao_social,
            "cnpj_8": e.cnpj_8,
            "municipio": e.municipio,
            "natureza_juridica": e.natureza_juridica,
            "match_status": e.match_status,
            "match_detail": e.match_detail,
            "root_cause": _infer_root_cause(e.natureza_juridica, e.match_status),
        }
        for e in missed
    ]

    # --- Source coverage breakdown ---
    source_counts: Counter[str] = Counter()
    for cov in source_coverage:
        if cov.has_opportunity and cov.source != "none":
            source_counts[cov.source] += 1
    report.source_coverage = dict(source_counts)
    # Also report entities with no coverage at all
    no_coverage = sum(1 for cov in source_coverage if cov.source == "none" or not cov.has_opportunity)
    report.source_coverage["sem_cobertura"] = no_coverage

    # --- Root cause breakdown for missed ---
    root_causes: Counter[str] = Counter()
    for e in missed:
        cause = _infer_root_cause(e.natureza_juridica, e.match_status)
        root_causes[cause] += 1
    report.root_cause_breakdown = dict(root_causes)

    return report


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------


def format_json(report: ReconciliationReport) -> str:
    """Render report as JSON."""
    return json.dumps(report.to_dict(), indent=2, ensure_ascii=False)


def format_table(report: ReconciliationReport) -> str:
    """Render report as Markdown table."""
    return report.to_markdown()


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------


def export_csv(report: ReconciliationReport, output_path: str) -> str:
    """Export missed entities as CSV."""
    fieldnames = [
        "id",
        "razao_social",
        "cnpj_8",
        "municipio",
        "natureza_juridica",
        "match_status",
        "match_detail",
        "root_cause",
    ]
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for m in report.top_missed:
            writer.writerow({k: m.get(k, "") for k in fieldnames})
    return output_path


def run_reconcile(
    manifest_path: str = "",
    reconciliation_path: str = "",
    source_coverage_path: str = "",
    fmt: str = "table",
    output_csv: str = "",
) -> str:
    """Run the full reconciliation pipeline and return formatted output.

    Returns the formatted report string.
    """
    manifest = load_manifest(manifest_path or TARGET_MANIFEST)
    reconciliations = load_reconciliation(reconciliation_path or RECONCILIATION_CSV)
    coverage = load_source_coverage(source_coverage_path or SOURCE_COVERAGE_CSV)

    report = build_report(
        target_manifest=manifest,
        reconciliations=reconciliations,
        source_coverage=coverage,
    )

    if output_csv:
        path = export_csv(report, output_csv)
        print(f"[OK] Missed entities CSV exported: {path}", file=sys.stderr)

    if fmt == "json":
        return format_json(report)
    return format_table(report)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Target universe reconciliation — CM-03",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/coverage/reconcile_targets.py
  python scripts/coverage/reconcile_targets.py --format json
  python scripts/coverage/reconcile_targets.py --output-csv missed.csv
        """,
    )
    parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)",
    )
    parser.add_argument(
        "--output-csv",
        default="",
        help="Export missed entities to CSV at this path",
    )
    parser.add_argument(
        "--manifest",
        default=str(TARGET_MANIFEST),
        help=f"Path to target universe manifest (default: {TARGET_MANIFEST})",
    )
    parser.add_argument(
        "--reconciliation",
        default=str(RECONCILIATION_CSV),
        help=f"Path to reconciliation CSV (default: {RECONCILIATION_CSV})",
    )
    parser.add_argument(
        "--source-coverage",
        default=str(SOURCE_COVERAGE_CSV),
        help=f"Path to source coverage CSV (default: {SOURCE_COVERAGE_CSV})",
    )

    args = parser.parse_args()

    output = run_reconcile(
        manifest_path=args.manifest,
        reconciliation_path=args.reconciliation,
        source_coverage_path=args.source_coverage,
        fmt=args.format,
        output_csv=args.output_csv,
    )
    print(output)


if __name__ == "__main__":
    main()
