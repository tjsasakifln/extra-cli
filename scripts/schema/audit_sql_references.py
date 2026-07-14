#!/usr/bin/env python3
"""Audit SQL references — extracts all SQL queries embedded in Python,
resolves table/column references, and validates against known schema.

Part of Story 1.2 (Unify Schema): 6.1 Automatic SQL Reference Audit.

Usage:
    python scripts/schema/audit_sql_references.py             # Scan + report
    python scripts/schema/audit_sql_references.py --json      # JSON output
    python scripts/schema/audit_sql_references.py --verbose   # Verbose logging
"""

from __future__ import annotations

import argparse
import ast
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

_logger = logging.getLogger(__name__)

# ── Known schema objects (tables, views, functions) ──────────────────────
# Derived from db/migrations/ + supabase/migrations/
# This is the target schema after applying ALL migrations 001-029 + 030-036.

KNOWN_TABLES: set[str] = {
    "pncp_raw_bids",
    "pncp_supplier_contracts",
    "sc_public_entities",
    "enriched_entities",
    "entity_coverage",
    "entity_hierarchy",
    "ingestion_runs",
    "ingestion_checkpoints",
    "coverage_snapshots",
    "sc_dados_abertos_backfill_log",
    "sc_municipalities",
    "pncp_enrichment_cache",
    "engineering_opportunities",
    "coverage_evidence",
    "opportunity_intel",
    "opportunity_checkpoints",
    "opportunity_runs",
    "opportunity_coverage",
    "_migrations",
    "contract_version_history",
    "capability_coverage",
    "retention_policy",
}

KNOWN_VIEWS: set[str] = {
    "v_latest_evidence",
    "v_source_health",
    "v_entities_canonical",
    "v_open_opportunities_canonical",
    "v_contracts_canonical",
    "v_suppliers_canonical",
    "v_value_observations_canonical",
    "v_coverage_gaps_by_municipio",
    "v_unmatched_bids",
    "v_contract_historical",
    "v_supplier_winners",
    "v_expiring_contracts",
    "v_capability_coverage_summary",
    "v_coverage_health",
    "v_schema_integrity",
    "v_migration_status",
    "v_entity_match_summary",
}

KNOWN_FUNCTIONS: set[str] = {
    "upsert_pncp_raw_bids",
    "upsert_pncp_supplier_contracts",
    "search_datalake",
    "purge_old_bids",
    "generate_coverage_snapshot",
    "fn_get_contract_intel_truth",
    "fn_reconciliation_summary",
    "fn_cap_coverage_updated_at",
    "fn_capture_contract_snapshot",
    "fn_purge_old_data",
    "fn_value_statistics",
}

KNOWN_SCHEMA_OBJECTS = KNOWN_TABLES | KNOWN_VIEWS | KNOWN_FUNCTIONS

# False positive words that look like identifiers but are Portuguese/English words
FALSE_POSITIVE_WORDS: set[str] = {
    # Portuguese words
    "a",
    "ao",
    "aos",
    "as",
    "da",
    "das",
    "de",
    "do",
    "dos",
    "em",
    "entre",
    "na",
    "nas",
    "no",
    "nos",
    "o",
    "os",
    "ou",
    "para",
    "por",
    "pra",
    "que",
    "se",
    "sem",
    "sobre",
    "um",
    "uma",
    "com",
    "como",
    "mais",
    "mas",
    "ate",
    "ate",
    "pela",
    "pelas",
    "pelo",
    "pelos",
    "tabela",
    "chamada",
    "edital",
    "editais",
    "fornecedor",
    "disponivel",
    "disponível",
    "licitacao",
    "municipio",
    # English words likely to appear in strings that look like SQL
    "all",
    "also",
    "an",
    "and",
    "any",
    "are",
    "based",
    "between",
    "both",
    "but",
    "by",
    "can",
    "change",
    "changes",
    "cluster",
    "clusters",
    "config",
    "configuration",
    "contract",
    "day",
    "each",
    "efficiency",
    "end",
    "every",
    "evidence",
    "extracted",
    "faster",
    "field",
    "first",
    "following",
    "for",
    "found",
    "from",
    "full",
    "has",
    "have",
    "having",
    "into",
    "its",
    "just",
    "key",
    "last",
    "latitude",
    "longitude",
    "match",
    "matches",
    "matching",
    "mode",
    "modes",
    "more",
    "most",
    "name",
    "names",
    "new",
    "next",
    "not",
    "now",
    "object",
    "of",
    "off",
    "old",
    "only",
    "onto",
    "other",
    "our",
    "out",
    "over",
    "own",
    "part",
    "per",
    "profile",
    "programmatic",
    "range",
    "record",
    "records",
    "respect",
    "row",
    "rows",
    "same",
    "second",
    "set",
    "show",
    "shown",
    "some",
    "space",
    "start",
    "state",
    "status",
    "still",
    "string",
    "such",
    "take",
    "than",
    "that",
    "the",
    "their",
    "them",
    "then",
    "these",
    "they",
    "thing",
    "third",
    "this",
    "those",
    "three",
    "through",
    "time",
    "type",
    "unit",
    "units",
    "until",
    "use",
    "used",
    "uses",
    "using",
    "value",
    "values",
    "various",
    "way",
    "ways",
    "were",
    "what",
    "when",
    "where",
    "which",
    "while",
    "whole",
    "will",
    "with",
    "within",
    "without",
    "work",
    "year",
    "years",
    "yet",
    # Value semantics specific
    "award",
    "awarded",
    "dominant_nature",
    "disbursed",
    "pay",
    "payment",
    "signed",
    "efficiency",
    "change",
    # Other common SQL false positives
    "date",
    "time",
    "timestamp",
    "interval",
    "string",
    "text",
    "boolean",
    "integer",
    "numeric",
    "double",
    "precision",
    "first",
    "last",
    "next",
    "current",
    # Crawler / domain specific
    "match_entities",
    "run_type",
    "objeto_contrato",
    "cluster_contract_activities",
    "cluster",
    "clusters",
    "tender",
    "validity",
    "workload",
    # Views from other stories (not part of Story 1.2 but valid)
    "updated",
}

# Functions that act as aliases for table access
KNOWN_QUERY_HELPERS: set[str] = {
    "search_datalake",
}

# SQL keywords that introduce relation references
SQL_RELATION_KEYWORDS = re.compile(
    r"\b(?:FROM|JOIN|INTO|UPDATE|TABLE|VIEW|INSERT\s+INTO|DELETE\s+FROM|TRUNCATE|DROP\s+(?:TABLE|VIEW|INDEX)|ALTER\s+(?:TABLE|VIEW))\b",
    re.IGNORECASE,
)

SQLLITERAL_PATTERN = re.compile(
    r"""('''(?:\\.|[^'\\])*?'''|'(?:\\.|[^'\\])*?')""",
    re.DOTALL,
)

# SQL keywords that should not be treated as table references
_SQL_KEYWORDS: set[str] = {
    "select",
    "where",
    "and",
    "or",
    "not",
    "in",
    "as",
    "on",
    "when",
    "then",
    "else",
    "end",
    "case",
    "cast",
    "null",
    "true",
    "false",
    "is",
    "like",
    "between",
    "exists",
    "having",
    "group",
    "order",
    "by",
    "limit",
    "offset",
    "union",
    "all",
    "distinct",
    "count",
    "sum",
    "avg",
    "min",
    "max",
    "coalesce",
    "nullif",
    "abs",
    "round",
    "floor",
    "ceil",
    "power",
    "sqrt",
    "length",
    "substring",
    "trim",
    "upper",
    "lower",
    "replace",
    "concat",
    "split_part",
    "extract",
    "date_trunc",
    "now",
    "current_date",
    "current_timestamp",
    "current_time",
    "array",
    "jsonb",
    "row",
    "least",
    "greatest",
    "to_tsvector",
    "to_tsquery",
    "plainto_tsquery",
    "setweight",
    "ts_rank",
    "ts_headline",
    "returning",
    "except",
    "intersect",
    "fetch",
    "next",
    "rows",
    "only",
    "percent",
    "with",
    "recursive",
    "materialized",
    "tablespace",
    "schema",
    "database",
    "column",
    "columns",
    "constraint",
    "primary",
    "foreign",
    "references",
    "unique",
    "check",
    "default",
    "cascade",
    "restrict",
    "initially",
    "deferred",
    "immediate",
    "enable",
    "disable",
    "validate",
    "cluster",
    "set",
    "reset",
    "tablesample",
    "ordinality",
    "xmlforest",
    "xmlagg",
    "xmlelement",
    "xmlroot",
    "exists",
    "greatest",
    "least",
}

# Known columns per table (key tables only — the ones used in queries)
KNOWN_COLUMNS: dict[str, set[str]] = {
    "pncp_raw_bids": {
        "id",
        "pncp_id",
        "objeto_compra",
        "tsv",
        "valor_total_estimado",
        "modalidade_id",
        "modalidade_nome",
        "esfera_id",
        "uf",
        "municipio",
        "codigo_municipio_ibge",
        "orgao_razao_social",
        "orgao_cnpj",
        "data_publicacao",
        "data_abertura",
        "data_encerramento",
        "link_pncp",
        "content_hash",
        "source",
        "source_id",
        "is_active",
        "ingested_at",
        "updated_at",
        "matched_entity_id",
        "matched_at",
        "crawl_batch_id",
        "numero_controle_pncp",
        "ano_compra",
        "sequencial_compra",
        "informacao_complementar",
        "situacao_compra",
        "unidade_nome",
        "link_sistema_origem",
        "synthetic_id",
        "synthetic_id_reason",
        "match_method",
        "match_score",
        "match_confidence",
    },
    "pncp_supplier_contracts": {
        "contrato_id",
        "orgao_cnpj",
        "orgao_nome",
        "fornecedor_cnpj",
        "fornecedor_nome",
        "objeto_contrato",
        "valor_total",
        "valor_global",
        "data_inicio",
        "data_fim",
        "data_publicacao",
        "uf",
        "municipio",
        "source",
        "source_id",
        "is_active",
        "ingested_at",
        "updated_at",
        "codigo_municipio_ibge",
        "municipio_inferido",
    },
    "sc_public_entities": {
        "id",
        "razao_social",
        "cnpj_8",
        "municipio",
        "codigo_ibge",
        "natureza_juridica",
        "cod_natureza",
        "latitude",
        "longitude",
        "distancia_fk",
        "raio_200km",
        "is_active",
        "created_at",
    },
    "enriched_entities": {
        "cnpj",
        "razao_social",
        "nome_fantasia",
        "cnae_principal",
        "cnae_secundarios",
        "municipio",
        "uf",
        "codigo_ibge",
        "natureza_juridica",
        "logradouro",
        "bairro",
        "cep",
        "telefone",
        "email",
        "situacao",
        "enriched_at",
        "enriched_source",
    },
    "entity_coverage": {
        "id",
        "entity_id",
        "source",
        "is_covered",
        "within_200km",
        "total_bids",
        "matched_bids",
        "last_seen_at",
        "updated_at",
        "match_method",
    },
    "opportunity_intel": {
        "id",
        "source",
        "source_id",
        "source_url",
        "content_hash",
        "numero_controle_pncp",
        "crawl_batch_id",
        "run_id",
        "ingested_at",
        "updated_at",
        "first_seen_at",
        "last_seen_at",
        "orgao_cnpj",
        "orgao_nome",
        "ente_federativo",
        "uf",
        "municipio",
        "codigo_ibge",
        "numero_processo",
        "numero_edital",
        "modalidade",
        "modalidade_id",
        "objeto",
        "categoria",
        "valor_estimado",
        "valor_homologado",
        "valor_semantica",
        "data_publicacao",
        "data_abertura",
        "data_encerramento",
        "data_homologacao",
        "status_fonte",
        "status_canonico",
        "status_motivo",
        "status_data",
        "link_edital",
        "link_anexos",
        "qualidade_score",
        "qualidade_fatores",
        "dados_ausentes",
        "ranking",
        "ranking_score",
        "ranking_fatores",
        "ranking_regras",
        "ranking_confianca",
        "proveniencia",
        "is_active",
        "metadata",
    },
}


@dataclass
class SqlReference:
    """A SQL query found embedded in Python code."""

    file: str
    line: int
    sql_snippet: str
    tables_referenced: set[str] = field(default_factory=set)
    suspicious: bool = False
    notes: str = ""


@dataclass
class AuditReport:
    """Complete audit report for a single file scan."""

    scanned_files: int = 0
    references: list[SqlReference] = field(default_factory=list)
    missing_tables: set[str] = field(default_factory=set)
    errors: list[str] = field(default_factory=list)


def extract_multiline_strings(source: str, filename: str) -> list[tuple[int, str]]:
    """Extract multiline string literals (triple-quoted) from Python source."""
    tree = ast.parse(source, filename=filename)
    strings: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            if isinstance(node.value.value, str) and len(node.value.value) > 30:
                strings.append((node.lineno, node.value.value))
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and isinstance(node.value, ast.Constant):
                    if isinstance(node.value.value, str) and len(node.value.value) > 20:
                        strings.append((node.lineno, node.value.value))
        elif isinstance(node, ast.Call):
            # f"..." or f'''...''' — detected via ast.JoinedStr
            pass

    # Also scan raw file for all triple-quoted strings (safe fallback)
    for match in SQLLITERAL_PATTERN.finditer(source):
        lineno = source[: match.start()].count("\n") + 1
        content = match.group(1)
        # Only triple-quoted strings (potential SQL)
        if content.startswith("'''"):
            strings.append((lineno, content[3:-3]))

    return strings


def extract_sql_tables(sql: str) -> set[str]:
    """Extract table/view/function references from a SQL snippet."""
    references: set[str] = set()

    # Remove string literals and comments
    cleaned = re.sub(r"--[^\n]*", "", sql)
    cleaned = re.sub(r"/\*.*?\*/", "", cleaned, flags=re.DOTALL)

    # Match identifiers after FROM, JOIN, INTO, TABLE, etc.
    patterns = [
        r"\bFROM\s+([a-zA-Z_]\w*)",
        r"\bJOIN\s+([a-zA-Z_]\w*)",
        r"\bINTO\s+([a-zA-Z_]\w*)",
        r"\bTABLE\s+([a-zA-Z_]\w*)",
        r"\bVIEW\s+([a-zA-Z_]\w*)",
        r"\bUPDATE\s+([a-zA-Z_]\w*)",
        r"\bINSERT\s+INTO\s+([a-zA-Z_]\w*)",
        r"\bDELETE\s+FROM\s+([a-zA-Z_]\w*)",
        r"\bDROP\s+(?:TABLE|VIEW|INDEX)\s+(?:IF\s+EXISTS\s+)?([a-zA-Z_]\w*)",
        r"\bALTER\s+(?:TABLE|VIEW)\s+([a-zA-Z_]\w*)",
        r"\bTRUNCATE\s+([a-zA-Z_]\w*)",
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, cleaned, re.IGNORECASE):
            name = match.group(1)
            name = name.split(".")[-1]
            if name and name[0].islower() and name != "from" and name not in FALSE_POSITIVE_WORDS:
                references.add(name)

    # Match fully qualified public.tablename
    for match in re.finditer(r"\bpublic\.([a-zA-Z_]\w*)", cleaned):
        name = match.group(1)
        if name not in FALSE_POSITIVE_WORDS:
            references.add(name)

    # Match function calls (only known functions and table references)
    for match in re.finditer(r"\b([a-zA-Z_]\w*)\s*\(", cleaned):
        name = match.group(1)
        # Skip SQL keywords
        if name.lower() in _SQL_KEYWORDS:
            continue
        # Skip UPPER_CASE names (likely types or constants)
        if name[0].isupper():
            continue
        # Skip false positive words
        if name in FALSE_POSITIVE_WORDS:
            continue
        # Only add if it looks like a known table/view/function
        if len(name) > 3:  # Skip very short names (likely false positives)
            references.add(name)

    return references


def is_likely_sql(text: str) -> bool:
    """Heuristic: does this string look like SQL?"""
    sql_keywords = {
        "SELECT",
        "INSERT",
        "UPDATE",
        "DELETE",
        "CREATE",
        "ALTER",
        "DROP",
        "TRUNCATE",
        "WITH",
        "FROM",
        "JOIN",
        "WHERE",
        "TABLE",
        "VIEW",
        "INDEX",
        "INTO",
    }
    upper = text.strip().upper()
    for kw in sql_keywords:
        if upper.startswith(kw) or f"\n{kw}" in upper or f";{kw}" in upper:
            return True
    return False


def scan_file(filepath: Path, report: AuditReport, project_root: Path | None = None) -> None:
    """Scan a single Python file for embedded SQL references."""
    try:
        source = filepath.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        report.errors.append(f"Cannot read {filepath}: {exc}")
        return

    root = project_root or Path.cwd()

    # Extract triple-quoted strings
    strings = extract_multiline_strings(source, str(filepath))

    for lineno, content in strings:
        if not is_likely_sql(content):
            continue

        ref = SqlReference(
            file=str(filepath.relative_to(root)),
            line=lineno,
            sql_snippet=content[:200],
        )
        ref.tables_referenced = extract_sql_tables(content)

        # Check each reference against known schema
        missing = ref.tables_referenced - KNOWN_SCHEMA_OBJECTS
        # Remove common false positives
        common_false = {
            "timestamp",
            "date",
            "numeric",
            "text",
            "boolean",
            "integer",
            "bigint",
            "serial",
            "bigserial",
            "decimal",
            "double",
            "precision",
            "varchar",
            "char",
            "jsonb",
            "json",
            "uuid",
            "interval",
            "time",
            "primary",
            "key",
            "references",
            "constraint",
            "check",
            "default",
            "not",
            "null",
            "unique",
            "index",
        }
        missing = missing - common_false

        if missing:
            ref.suspicious = True
            ref.notes = f"Unknown objects: {', '.join(sorted(missing))}"
            report.missing_tables.update(missing)

        report.references.append(ref)

    report.scanned_files += 1


def scan_directory(root: str) -> AuditReport:
    """Scan all Python files in directory tree for SQL references."""
    report = AuditReport()
    root_path = Path(root)

    for filepath in sorted(root_path.rglob("*.py")):
        # Skip __pycache__
        if "__pycache__" in str(filepath):
            continue
        # Skip venv if inside scripts
        if "venv" in str(filepath):
            continue
        try:
            scan_file(filepath, report, project_root=root_path)
        except SyntaxError as exc:
            _logger.warning("Syntax error in %s: %s", filepath, exc)
        except Exception as exc:
            _logger.error("Error scanning %s: %s", filepath, exc)

    return report


def generate_report(report: AuditReport, output_dir: Path) -> str:
    """Generate a markdown gap report."""
    lines = [
        "# Schema-Gap Report",
        "",
        "**Generated:** Auto",
        f"**Scanned files:** {report.scanned_files}",
        f"**SQL references found:** {len(report.references)}",
        f"**Suspicious references:** {sum(1 for r in report.references if r.suspicious)}",
        f"**Missing objects:** {len(report.missing_tables)}",
        "",
        "---",
        "## Summary",
        "",
    ]

    if not report.missing_tables:
        lines.append("✅ **No missing schema objects found.** All SQL references are valid.")
        lines.append("")
    else:
        lines.append("### Missing Tables/Views/Functions")
        lines.append("")
        lines.append("| Object | Type | Referenced In |")
        lines.append("|--------|------|---------------|")
        for obj in sorted(report.missing_tables):
            files = set()
            for ref in report.references:
                if obj in ref.tables_referenced:
                    files.add(ref.file)
            if obj[0].islower():
                obj_type = "unknown (lowercase)"
            else:
                obj_type = "unknown"
            lines.append(f"| `{obj}` | {obj_type} | {', '.join(sorted(files)[:5])} |")
        lines.append("")

    if report.errors:
        lines.append("### Scan Errors")
        lines.append("")
        for err in report.errors:
            lines.append(f"- {err}")
        lines.append("")

    # Detailed references
    lines.append("## Detailed SQL References")
    lines.append("")
    for ref in report.references:
        marker = "⚠️ " if ref.suspicious else "✓ "
        lines.append(f"{marker}**{ref.file}:{ref.line}**")
        if ref.notes:
            lines.append(f"   *{ref.notes}*")
        if ref.tables_referenced:
            lines.append(f"   Tables: `{'`, `'.join(sorted(ref.tables_referenced))}`")
        lines.append("   ```sql")
        lines.append(f"   {ref.sql_snippet}")
        lines.append("   ```")
        lines.append("")

    return "\n".join(lines)


def export_json(report: AuditReport) -> str:
    """Export report as JSON."""
    data = {
        "scanned_files": report.scanned_files,
        "total_references": len(report.references),
        "suspicious": sum(1 for r in report.references if r.suspicious),
        "missing_objects": sorted(report.missing_tables),
        "references": [
            {
                "file": r.file,
                "line": r.line,
                "suspicious": r.suspicious,
                "notes": r.notes,
                "tables": sorted(r.tables_referenced),
                "sql": r.sql_snippet[:300],
            }
            for r in report.references
        ],
    }
    return json.dumps(data, indent=2, ensure_ascii=False, default=str)


def main():
    parser = argparse.ArgumentParser(description="Audit SQL references in Python codebase")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose logging",
    )
    parser.add_argument(
        "--output-dir",
        default="output/schema",
        help="Output directory for reports (default: output/schema)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    root_dir = Path("scripts")
    if not root_dir.exists():
        _logger.error("Directory 'scripts/' not found. Run from project root.")
        sys.exit(1)

    _logger.info("Scanning %s for embedded SQL...", root_dir)
    report = scan_directory("scripts")
    _logger.info(
        "Found %d SQL references in %d files (%d suspicious)",
        len(report.references),
        report.scanned_files,
        sum(1 for r in report.references if r.suspicious),
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.json:
        json_report = export_json(report)
        json_path = output_dir / "schema-gap-report.json"
        json_path.write_text(json_report, encoding="utf-8")
        print(json_report)
    else:
        md_report = generate_report(report, output_dir)
        md_path = output_dir / "schema-gap-report.md"
        md_path.write_text(md_report, encoding="utf-8")
        print(md_report[:5000])
        print(f"\n---\nFull report written to {md_path}")

    return 0 if len(report.missing_tables) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
