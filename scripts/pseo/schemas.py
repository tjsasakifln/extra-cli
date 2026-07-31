"""JSON schema pointers and version constants for public pSEO export."""

from __future__ import annotations

from scripts.pseo import SCHEMA_VERSION
from scripts.pseo.provenance import EXPORT_ENTRYPOINT, EXPORT_VERSION

PUBLIC_SCHEMA = {
    "schema_version": SCHEMA_VERSION,
    "export_version": EXPORT_VERSION,
    "export_entrypoint": EXPORT_ENTRYPOINT,
    "description": "CONFENGE public pSEO evidence snapshot (ICP-Derived Evidence)",
    "files": [
        "archetypes.json",
        "markets.json",
        "agencies.json",
        "prices.json",
        "competition.json",
        "opportunities.json",
        "problem_service.json",
        "icp_methodology.json",
        "manifest.json",
    ],
    "classification_labels": [
        "aec_confirmed",
        "aec_probable",
        "non_aec",
        "ambiguous",
        "insufficient_context",
    ],
    "indexable_requires": "aec_confirmed + human_review APPROVED|APPROVED_WITH_NOTES",
    "forbidden_fields_policy": "scripts/pseo/allowlist.py FORBIDDEN_KEYS",
    "dataset_hash_algorithm": "sha256(canonical_json(ordered body keys))",
    "timezone_default": "UTC",
    "dates": [
        "data_coleta",
        "data_publicacao",
        "data_assinatura",
        "data_encerramento_proposta",
        "data_inicio_vigencia",
        "data_fim_vigencia",
        "data_atualizacao_fonte",
        "generated_at",
        "data_as_of",
    ],
}
