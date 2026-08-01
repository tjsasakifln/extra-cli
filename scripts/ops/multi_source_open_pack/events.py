"""Classificação de eventos de processo e disputa ativa."""

from __future__ import annotations

from scripts.ops.multi_source_open_pack.textutil import norm

# Eventos que NÃO são oportunidade aberta independente
TERMINAL_EVENTS = frozenset(
    {
        "contrato",
        "extrato_contrato",
        "homologacao",
        "adjudicacao",
        "resultado",
        "rescisao",
        "revogacao",
        "anulacao",
        "cancelamento",
        "deserto",
        "fracassado",
        "credenciamento_firmado",
        "dispensa_concluida",
        "inexigibilidade_concluida",
    }
)

SUSPENSION_EVENTS = frozenset({"suspensao", "interrupcao"})

# Atos DOM que por si só não abrem disputa (salvo reabertura/edital com prazo)
NON_DISPUTE_ACTS = frozenset(
    {
        "contrato",
        "extrato",
        "extrato_contrato",
        "homologacao",
        "adjudicacao",
        "resultado",
        "rescisao",
        "errata",  # sozinha, sem processo aberto
        "retificacao",  # sozinha
        "credenciamento",  # frequentemente já firmado / sem disputa
        "dispensa",  # frequentemente concluída
        "inexigibilidade",
        "intencao_registro_precos",  # intenção, não disputa
    }
)

OPEN_DISPUTE_ACTS = frozenset(
    {
        "edital",
        "aviso_licitacao",
        "edital_aberto",
        "portal_estadual_aberto",
        "reabertura",
        "chamamento_publico",
        "consulta_publica",
    }
)

_TERMINAL_TEXT = (
    "extrato de contrato",
    "extrato do contrato",
    "contrato n",
    "contrato firmado",
    "homologa",
    "adjudica",
    "resultado da licitacao",
    "resultado do pregao",
    "rescis",
    "revoga",
    "anula o edital",
    "licitacao deserta",
    "licitacao fracassada",
    "credenciamento de",
    "credencia a empresa",
    "dispensa de licitacao",
    "inexigibilidade de licitacao",
)

_OPEN_TEXT = (
    "abre licitacao",
    "torna publico o edital",
    "aviso de licitacao",
    "pregao eletronico n",
    "concorrencia n",
    "tomada de precos",
    "reabre",
    "republica o edital",
)


def classify_event(
    *,
    categoria_ato: str,
    objeto: str,
    status_fonte: str,
    fonte: str,
) -> tuple[str, bool, str]:
    """Return (event_type, is_active_dispute, exclusion_reason)."""
    cat = norm(categoria_ato).replace(" ", "_")
    blob = norm(objeto)
    status = norm(status_fonte)

    # Explicit open statuses from portals
    if fonte in {"pncp", "sc_compras"} and status in {
        "open",
        "aberta",
        "aberto",
        "recebendo propostas",
    }:
        # still check object for terminal language
        if any(t in blob for t in _TERMINAL_TEXT) and not any(t in blob for t in _OPEN_TEXT):
            return "publicacao_terminal", False, "texto_indica_ato_terminal"
        return "edital", True, ""

    if cat in TERMINAL_EVENTS or cat in {
        "contrato",
        "extrato",
        "extrato_contrato",
        "homologacao",
        "adjudicacao",
        "resultado",
    }:
        return cat or "terminal", False, f"evento_terminal:{cat or 'unknown'}"

    if cat in SUSPENSION_EVENTS or "suspens" in blob:
        return "suspensao", False, "processo_suspenso"

    if cat in NON_DISPUTE_ACTS:
        # retificação/errata sozinhas sem prazo
        return cat, False, f"ato_sem_disputa_ativa:{cat}"

    if cat in OPEN_DISPUTE_ACTS:
        if any(t in blob for t in _TERMINAL_TEXT) and cat not in {"reabertura", "edital", "aviso_licitacao"}:
            return cat, False, "texto_terminal_em_ato_aberto"
        return cat, True, ""

    # Free-text fallback for DOM titles
    if any(t in blob for t in _TERMINAL_TEXT):
        return "publicacao_terminal", False, "texto_indica_ato_terminal"
    if any(t in blob for t in _OPEN_TEXT) or "edital" in blob or "pregao" in blob:
        return "aviso_licitacao", True, ""

    if fonte == "ciga_ckan":
        return cat or "publicacao_dom", False, "publicacao_dom_sem_evidencia_disputa"

    return cat or "unknown", False, "status_disputa_nao_comprovado"
