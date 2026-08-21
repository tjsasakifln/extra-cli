"""Fresh consumer of the shipped outreach projection.

Writes a classified-route sample. Never sends mail. auto_send stays false.
"""

from __future__ import annotations

import json
import sys

from scripts.decision_unit_intelligence.models import (
    AccountInvestigation,
    ActionMode,
    ChannelType,
    ConfidenceLevel,
    DecisionRoleClass,
    DecisionUnitCandidate,
    EpistemicClass,
    FreshnessState,
    OwnershipStatus,
    ReachabilityClass,
    ReachabilityRoute,
    RouteRelation,
    SuppressionState,
)
from scripts.decision_unit_intelligence.projection import project_warmbly_outreach

ACCOUNT_ID = "12345678000190"


def _sample_account() -> AccountInvestigation:
    person = DecisionUnitCandidate(
        candidate_id="cand-ana",
        company_entity_id=ACCOUNT_ID,
        person_id="person-ana",
        person_name="ANA SOUZA",
        observed_roles=["Gerente de Contratos"],
        decision_role_class=DecisionRoleClass.GERENTE_CONTRATOS,
        identity_confidence=ConfidenceLevel.HIGH,
        role_confidence=ConfidenceLevel.HIGH,
    )
    routes = [
        ReachabilityRoute(
            route_id="r-ana",
            company_entity_id=ACCOUNT_ID,
            channel_type=ChannelType.DIRECT_EMAIL,
            reachability_class=ReachabilityClass.R1_DIRECT,
            action_mode=ActionMode.HUMAN_REVIEW_EMAIL,
            decision_unit_candidate_id=person.candidate_id,
            channel_value="ana.souza@empresaexemplo.com.br",
            route_relation=RouteRelation.PERSON_OWNS_CHANNEL,
            epistemic_class=EpistemicClass.OBSERVED,
            source_type="company_website",
            source_url="https://empresaexemplo.com.br/equipe",
            freshness=FreshnessState.FRESH,
            ownership=OwnershipStatus.COMPANY_OWNED,
            suppression=SuppressionState.NONE,
            extra={"identity_explicitly_associated": True, "email_discovery_class": "EMAIL_VALIDATED"},
        ),
        ReachabilityRoute(
            route_id="r-comercial",
            company_entity_id=ACCOUNT_ID,
            channel_type=ChannelType.ROLE_MAILBOX,
            reachability_class=ReachabilityClass.R4_ROLE_ROUTE,
            action_mode=ActionMode.ROLE_EMAIL,
            channel_value="comercial@empresaexemplo.com.br",
            route_relation=RouteRelation.ROUTES_TO_ROLE,
            epistemic_class=EpistemicClass.OBSERVED,
            source_type="company_website",
            source_url="https://empresaexemplo.com.br/contato",
            freshness=FreshnessState.FRESH,
            ownership=OwnershipStatus.COMPANY_OWNED,
            suppression=SuppressionState.NONE,
            extra={"email_discovery_class": "ROLE_MAILBOX"},
        ),
        ReachabilityRoute(
            route_id="r-contato",
            company_entity_id=ACCOUNT_ID,
            channel_type=ChannelType.GENERIC_CORPORATE_EMAIL,
            reachability_class=ReachabilityClass.R5_CORPORATE_ONLY,
            action_mode=ActionMode.GENERIC_EMAIL_LAST_RESORT,
            channel_value="contato@empresaexemplo.com.br",
            route_relation=RouteRelation.ACCOUNT_LEVEL_ONLY,
            epistemic_class=EpistemicClass.OBSERVED,
            source_type="company_website",
            source_url="https://empresaexemplo.com.br/contato",
            freshness=FreshnessState.FRESH,
            ownership=OwnershipStatus.COMPANY_OWNED,
            suppression=SuppressionState.NONE,
            extra={"email_discovery_class": "GENERIC_MAILBOX"},
        ),
        ReachabilityRoute(
            route_id="r-gmail",
            company_entity_id=ACCOUNT_ID,
            channel_type=ChannelType.GENERIC_CORPORATE_EMAIL,
            reachability_class=ReachabilityClass.R5_CORPORATE_ONLY,
            action_mode=ActionMode.GENERIC_EMAIL_LAST_RESORT,
            channel_value="empresa@gmail.com",
            route_relation=RouteRelation.ACCOUNT_LEVEL_ONLY,
            epistemic_class=EpistemicClass.OBSERVED,
            source_type="company_website",
            source_url="https://empresaexemplo.com.br/contato",
            freshness=FreshnessState.FRESH,
            ownership=OwnershipStatus.COMPANY_OWNED,
            suppression=SuppressionState.NONE,
            extra={"company_associated": True, "mailbox_company_evidence": "OBSERVED"},
        ),
        ReachabilityRoute(
            route_id="r-inferred",
            company_entity_id=ACCOUNT_ID,
            channel_type=ChannelType.INFERRED_DIRECT_EMAIL,
            reachability_class=ReachabilityClass.INFERRED_UNVERIFIED,
            action_mode=ActionMode.HUMAN_REVIEW_EMAIL,
            channel_value="joao.silva@empresaexemplo.com.br",
            route_relation=RouteRelation.INFERRED_ASSOCIATION,
            epistemic_class=EpistemicClass.INFERRED,
            source_type="pattern",
            freshness=FreshnessState.UNKNOWN,
            ownership=OwnershipStatus.COMPANY_OWNED,
            suppression=SuppressionState.NONE,
            reason_codes=["INFERRED"],
            extra={"email_discovery_class": "INFERRED_PATTERN_EMAIL"},
        ),
    ]
    return AccountInvestigation(
        company_entity_id=ACCOUNT_ID,
        cnpj=ACCOUNT_ID,
        legal_name="EMPRESA EXEMPLO ENGENHARIA LTDA",
        service_context="reajuste_14133",
        why_now="contrato ativo",
        candidates=[person],
        routes=routes,
    )


def main() -> int:
    payload = project_warmbly_outreach(_sample_account())
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
