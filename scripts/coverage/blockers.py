"""Blocker management for coverage — Story 1.5.

Todo blocker tem:
    - acao recomendada (o que fazer para desbloquear)
    - responsavel (quem pode desbloquear)
    - prazo estimado (estimativa de esforco)
    - impacto (qual metrica de coverage afetada)

Formato padrao de blocker usado pelo coverage manifest e sistemas de alerta.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class CoverageBlocker:
    """A coverage blocker with recommended action and owner.

    Attributes:
        source: Data source affected.
        entity: Entity or scope affected (can be an entity_id, canonical_key,
                or "ALL" for all entities).
        capability: Business capability affected.
        action_required: What needs to happen to unblock.
        recommended_action: Specific recommendation for resolution.
        owner: Who is responsible for resolving.
        impact: Coverage metric affected and severity.
        created_at: When this blocker was first identified.
        estimated_effort_hours: Estimated effort to resolve.
        blocker_type: Type of blocker.
    """

    source: str
    entity: str = "ALL"
    capability: str = "open_tenders"
    action_required: str = ""
    recommended_action: str = ""
    owner: str = "TBD"
    impact: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    estimated_effort_hours: float = 0.0
    blocker_type: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "entity": self.entity,
            "capability": self.capability,
            "action_required": self.action_required,
            "recommended_action": self.recommended_action,
            "owner": self.owner,
            "impact": self.impact,
            "created_at": self.created_at.isoformat(),
            "estimated_effort_hours": self.estimated_effort_hours,
            "blocker_type": self.blocker_type,
        }


# ---------------------------------------------------------------------------
# Known blocker patterns
# ---------------------------------------------------------------------------

KNOWN_BLOCKERS: dict[str, list[dict[str, Any]]] = {
    "dom_sc": [
        {
            "action_required": "Obter credenciais de API do CIGA para DOM-SC",
            "recommended_action": (
                "Solicitar API key ao CIGA (Consorcio de Informatica na Gestao "
                "Publica Municipal). Contrato anual necessario."
            ),
            "owner": "Equipe de Operacoes",
            "impact": "Cobertura de editais municipais de SC via DOM-SC",
            "estimated_effort_hours": 8.0,
            "blocker_type": "credential",
        },
    ],
    "doe_sc": [
        {
            "action_required": "Obter credenciais de acesso ao DOE-SC",
            "recommended_action": ("Solicitar login/senha de acesso ao Diario Oficial Estadual de SC"),
            "owner": "Equipe de Operacoes",
            "impact": "Cobertura de editais estaduais de SC via DOE-SC",
            "estimated_effort_hours": 4.0,
            "blocker_type": "credential",
        },
    ],
    "tce_sc": [
        {
            "action_required": "Decisao sobre certificado ICP-Brasil para e-Sfinge",
            "recommended_action": (
                "Avaliar custo-beneficio do certificado ICP-Brasil (R$300-800/ano). "
                "Alternativa: usar apenas SCMWeb (dados abertos, sem certificado)."
            ),
            "owner": "Coordenacao",
            "impact": "Cobertura de contratos detalhados do TCE-SC via e-Sfinge",
            "estimated_effort_hours": 4.0,
            "blocker_type": "cost_decision",
        },
    ],
    "mides_bigquery": [
        {
            "action_required": "Provisionar conta de servico Google Cloud",
            "recommended_action": (
                "Criar service account e conceder acesso ao dataset "
                "MIDES BigQuery. Necessario ponto focal no governo estadual."
            ),
            "owner": "Coordenacao / Infra",
            "impact": "Cobertura de compras estaduais via MIDES BigQuery",
            "estimated_effort_hours": 16.0,
            "blocker_type": "infrastructure",
        },
    ],
    "pncp": [
        {
            "action_required": "Monitorar migracao PNCP v3",
            "recommended_action": (
                "Acompanhar cronograma de migracao da API PNCP para v3. Testes de compatibilidade antes da ativacao."
            ),
            "owner": "Dex (@dev)",
            "impact": "Fonte primaria de licitacoes pode sofrer breaking change",
            "estimated_effort_hours": 8.0,
            "blocker_type": "api_migration",
        },
    ],
}


def get_blockers_for_source(source: str) -> list[CoverageBlocker]:
    """Get known blockers for a specific source.

    Args:
        source: Source name.

    Returns:
        List of CoverageBlocker instances.
    """
    raw_blockers = KNOWN_BLOCKERS.get(source, [])
    return [
        CoverageBlocker(
            source=source,
            **b,
        )
        for b in raw_blockers
    ]


def get_all_known_blockers() -> list[CoverageBlocker]:
    """Get all known blockers across all sources.

    Returns:
        List of all known CoverageBlocker instances.
    """
    blockers: list[CoverageBlocker] = []
    for source, raw_list in KNOWN_BLOCKERS.items():
        for b in raw_list:
            blockers.append(
                CoverageBlocker(
                    source=source,
                    **b,
                )
            )
    return blockers


def check_missing_credentials_blocker(
    source: str,
    missing_creds: list[str],
    entity: str = "ALL",
) -> CoverageBlocker | None:
    """Create a blocker for missing credentials.

    Args:
        source: Data source.
        missing_creds: List of missing credential names.
        entity: Entity affected.

    Returns:
        CoverageBlocker or None if no credentials missing.
    """
    if not missing_creds:
        return None

    return CoverageBlocker(
        source=source,
        entity=entity,
        action_required=f"Configurar credenciais faltantes: {', '.join(missing_creds)}",
        recommended_action=(
            f"Definir as seguintes variaveis de ambiente: {', '.join(missing_creds)}. "
            f"Verificar documentacao da fonte {source} para valores corretos."
        ),
        owner="Equipe de Operacoes",
        impact=f"Fonte {source} bloqueada — nenhum dado coletado sem credenciais",
        estimated_effort_hours=2.0,
        blocker_type="credential",
    )


__all__ = [
    "CoverageBlocker",
    "KNOWN_BLOCKERS",
    "check_missing_credentials_blocker",
    "get_all_known_blockers",
    "get_blockers_for_source",
]
