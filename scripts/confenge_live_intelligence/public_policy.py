"""LI-W2 §A.1/§A.4 — politica de projecao publica do bundle.

Este modulo concentra tudo o que separa o vocabulario INTERNO do motor do
vocabulario PUBLICO do contrato ``CONFENGE_LIVE_INTELLIGENCE/1.0``:

* mapas de enum (``SNAPSHOT_* → DATA_*``, ``DEADLINE_* → ABERTA/ENCERRADA``);
* listas do que NUNCA pode aparecer no bundle serializado (campos de conclusao e
  jargao interno), copiadas do contrato vendorizado;
* o ``disclaimer_pt`` obrigatorio e as demais ``limitations`` em pt-BR;
* a derivacao de ``freshness`` — **funcao pura**, exatamente como a emenda do
  AC3 manda, para que a fronteira de 48h seja testavel sem banco.

Nada aqui toca IO, banco ou relogio de parede.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Final

from scripts.confenge_live_intelligence.schema import (
    DEADLINE_CLOSED,
    DEADLINE_OPEN,
    SNAPSHOT_BLOCKED,
    SNAPSHOT_PARTIAL,
    SNAPSHOT_READY,
    UNKNOWN,
)

# --- envelope --------------------------------------------------------------

CONTRACT_SCHEMA: Final[str] = "CONFENGE_LIVE_INTELLIGENCE/1.0"
# AC11 — o contrato PUBLICO nao muda com o bump de SCHEMA_VERSION/ENGINE_VERSION.
# NAO trocar por "v1.0.0": `accepted_versions` das duas familias contem ambas,
# logo `contract_version_unsupported` nao dispara e a troca seria churn com risco.
CONTRACT_VERSION: Final[str] = "1.0"
OPPORTUNITY_SCHEMA: Final[str] = "live-opportunity/1.0"
COMPANY_SCHEMA: Final[str] = "company-fit-profile/1.0"
CATALOG_MODE_OFFICIAL_LIVE: Final[str] = "official_live"
PRODUCER_STATUS_OFFICIAL_LIVE: Final[str] = "official_live"
# REQ-001 (adjudicacao do @architect, 2026-09-03). O contrato define
# `catalog_mode.official_live` como *"only when producers are live official
# artifacts and **claimed_live is true**"* — ou seja, e uma REIVINDICACAO
# explicita, nunca um default. `catalog_mode.fixture` e o rotulo desenhado para
# o caso contrario (*"labeled fixture; never consumed or labeled as live"*), e o
# consumidor recusa esse bundle por `producer_status_not_official_live`, que e
# exatamente o efeito desejado para um bundle de teste/seed.
CATALOG_MODE_FIXTURE: Final[str] = "fixture"
PRODUCER_STATUS_FIXTURE: Final[str] = "fixture"
# Ordem deliberada: o DEFAULT fail-closed vem primeiro. Omitir a reivindicacao
# NUNCA pode produzir um bundle rotulado live.
CATALOG_MODES: Final[tuple[str, ...]] = (CATALOG_MODE_FIXTURE, CATALOG_MODE_OFFICIAL_LIVE)
DEFAULT_CATALOG_MODE: Final[str] = CATALOG_MODE_FIXTURE
SOURCE_NAME: Final[str] = "PNCP"


def producer_status_for(catalog_mode: str) -> str:
    """``producer_status`` derivado do ``catalog_mode`` — nunca literal.

    Um `producer_status` que nao acompanhe o `catalog_mode` seria a mesma classe
    de defeito do literal que esta adjudicacao remove: um segundo lugar para
    divergir sobre a mesma proposicao (proveniencia).
    """
    return PRODUCER_STATUS_OFFICIAL_LIVE if catalog_mode == CATALOG_MODE_OFFICIAL_LIVE else PRODUCER_STATUS_FIXTURE


# Decisao PUBLICA de publicacao. Distinta de ``data_state`` (completude) e de
# ``catalog_mode`` (proveniencia): so e ``public_safe`` quando as tres condicoes
# coincidem. Nao e INDEX — INDEX e decisao do consumidor.
PUBLIC_SAFE: Final[str] = "public_safe"
NOT_PUBLIC_SAFE: Final[str] = "not_public_safe"
PUBLIC_DECISIONS: Final[tuple[str, ...]] = (PUBLIC_SAFE, NOT_PUBLIC_SAFE)


def public_decision_for(*, catalog_mode: str, data_state: str, freshness_state: str) -> str:
    """Decisao explicita ``public_safe`` / ``not_public_safe``.

    Fail-closed: omitir qualquer eixo (proveniencia, completude, frescor) nao
    produz ``public_safe``. Fixture, DATA_HOLD/DATA_REJECT e STALE sao todos
    ``not_public_safe``. Nao le relogio, IO nem o payload — so os tres rotulos
    ja derivados.
    """
    if catalog_mode == CATALOG_MODE_OFFICIAL_LIVE and data_state == DATA_READY and freshness_state == FRESHNESS_FRESH:
        return PUBLIC_SAFE
    return NOT_PUBLIC_SAFE


# --- §A.1 mapas de enum ----------------------------------------------------

DATA_READY: Final[str] = "DATA_READY"
DATA_HOLD: Final[str] = "DATA_HOLD"
DATA_REJECT: Final[str] = "DATA_REJECT"

# `SNAPSHOT_BUILDING`/`SNAPSHOT_SUPERSEDED` estao DELIBERADAMENTE ausentes: nao
# sao exportaveis, e o export falha fechado ao encontra-los (AC1).
DATA_STATE_BY_SNAPSHOT_STATE: Final[dict[str, str]] = {
    SNAPSHOT_READY: DATA_READY,
    SNAPSHOT_PARTIAL: DATA_HOLD,
    SNAPSHOT_BLOCKED: DATA_REJECT,
}

PRAZO_ABERTA: Final[str] = "ABERTA"
PRAZO_ENCERRADA: Final[str] = "ENCERRADA"
# `SUSPENSA` existe em `prazo_status_enum` do contrato e NUNCA e emitido: nao ha
# fonte para ele no producer. A ausencia e declarada em `limitations`.
PRAZO_SUSPENSA_NEVER_EMITTED: Final[str] = "SUSPENSA"
PRAZO_STATUS_BY_DEADLINE_STATE: Final[dict[str, str]] = {
    DEADLINE_OPEN: PRAZO_ABERTA,
    DEADLINE_CLOSED: PRAZO_ENCERRADA,
    UNKNOWN: UNKNOWN,
}

# --- §A.4 "nunca emitir" ---------------------------------------------------
#
# Copia literal de `forbidden_conclusion_fields` e `forbidden_public_language` do
# contrato vendorizado (`docs/contracts/confenge-live-intelligence-v1.json`). O
# teste de contrato assere que estas duas constantes IGUALAM as listas do
# contrato — nao existe segunda fonte de verdade, so uma copia provada.
FORBIDDEN_FIELDS: Final[tuple[str, ...]] = (
    "habilitado",
    "elegivel",
    "capacidade",
    "recomendacao",
    "vencedor",
    "probabilidade_vitoria",
    "should_bid",
    "INDEX",
)
FORBIDDEN_STRINGS: Final[tuple[str, ...]] = (
    "extra-cli",
    "scripts.public_read",
    "scripts.live_intelligence",
    "SmartLic",
)
# `INDEX` e proibido como VALOR de enum de status/data_state — nao como o campo
# `manifest.index`, que e o indice obrigatorio de arquivos do bundle (AC5).
FORBIDDEN_ENUM_VALUES: Final[tuple[str, ...]] = (
    "INDEX",
    "PUBLISHABLE_INDEX",
    "PUBLISHABLE_NOINDEX",
)

# --- epistemic classes -----------------------------------------------------

FACT: Final[str] = "FACT"
CALCULATION: Final[str] = "CALCULATION"
# `INFERENCE` existe no contrato e NAO e emitido por nos: o motor nao infere.
INFERENCE_NEVER_EMITTED: Final[str] = "INFERENCE"
EPISTEMIC_UNKNOWN: Final[str] = UNKNOWN

# --- textos pt-BR ----------------------------------------------------------

# Copia literal de `adherence_semantics.disclaimer_pt` do contrato vendorizado.
DISCLAIMER_PT: Final[str] = (
    "Aderência histórica não é habilitação, capacidade nem recomendação. "
    "Os dados descrevem o histórico público declarado nas fontes citadas e podem estar incompletos."
)
LIMITATION_SUSPENSA_ABSENT: Final[str] = (
    "O status SUSPENSA previsto no contrato público nunca é emitido: não existe fonte observada para ele no produtor."
)
LIMITATION_SOURCE_SCOPE: Final[str] = (
    "O escopo dos dados é o histórico público declarado na fonte PNCP e pode estar incompleto."
)
LIMITATION_VALUE_SEMANTICS: Final[str] = (
    "O valor é a estimativa pública declarada no documento de origem. Não é preço, proposta, "
    "honorário nem oferta de nenhum fornecedor, e a faixa é um rótulo ordinal, não um cálculo de preço."
)
LIMITATION_UNKNOWN_IS_NOT_ZERO: Final[str] = (
    "UNKNOWN permanece UNKNOWN: ausência de evidência nunca é tratada como zero."
)
LIMITATION_NO_PAYLOAD_EMITTED: Final[str] = (
    "Nenhum payload foi emitido para este snapshot; o bloco de frescor reflete o corte do "
    "próprio snapshot, não a marca d'água de uma fonte observada."
)

# --- reason codes INTERNOS -------------------------------------------------
#
# Todos disjuntos dos 14 codigos de veredito do consumidor — a disjuncao e
# provada por asserção em `test_export_contract.py`, nao por convencao.
REASON_SOURCE_AS_OF_BEYOND_MAX_AGE: Final[str] = "source_as_of_beyond_max_age"
REASON_SOURCE_AS_OF_AFTER_GENERATED_AT: Final[str] = "source_as_of_after_generated_at"
REASON_BUYER_CNPJ_NOT_HASHABLE: Final[str] = "buyer_cnpj_not_hashable"
REASON_ESTABLISHMENT_CNPJ_NOT_OBSERVED: Final[str] = "establishment_cnpj_not_observed"

INTERNAL_EXPORT_REASON_CODES: Final[tuple[str, ...]] = (
    REASON_SOURCE_AS_OF_BEYOND_MAX_AGE,
    REASON_SOURCE_AS_OF_AFTER_GENERATED_AT,
    REASON_BUYER_CNPJ_NOT_HASHABLE,
    REASON_ESTABLISHMENT_CNPJ_NOT_OBSERVED,
)

# --- flag de rollback barato (AC6 / Rollback) ------------------------------
#
# `orgao.cnpj` PERMANECE cru em `opportunities/*.json`: `producer_contracts.
# live_opportunity` nao tem bloco `identity` e CNPJ de orgao publico licitante e
# dado oficial publicado na fonte. Se o consumidor passar a exigir supressao,
# esta flag e o rollback — sem migration nem reexport retroativo.
# NAO cobre `compradores`, que ja nasce sem CNPJ.
SUPPRESS_ORGAO_CNPJ: bool = False

# --- freshness (emenda do AC3) ---------------------------------------------

# `docs/contracts/confenge-live-intelligence-v1.json` → `freshness.max_age_hours`.
FRESHNESS_MAX_AGE_HOURS: Final[int] = 48
FRESHNESS_FRESH: Final[str] = "FRESH"
FRESHNESS_STALE: Final[str] = "STALE"


class FreshnessInvariantError(RuntimeError):
    """Insumo de ``freshness`` ausente ou sem fuso — corrupcao de snapshot.

    Nao e branch de runtime: ``source_as_of`` e ``TIMESTAMPTZ NOT NULL`` na 104 e
    ``datetime`` nao-Optional nas dataclasses. O export ABORTA e nenhum arquivo e
    escrito (nem o manifest).
    """


def build_freshness(generated_at_dt: datetime | None, source_as_of_dt: datetime | None) -> dict[str, Any]:
    """Bloco ``freshness`` conforme a emenda do AC3 — **exatamente**, sem variacao.

    Serializa PRIMEIRO, deriva DEPOIS: o consumidor recomputa ``stale_rule`` sobre
    as strings que recebe. Derivar de ``datetime`` em memoria (com microssegundos)
    e serializar truncando abriria uma janela em que o nosso rotulo e o dele
    discordam sobre o mesmo bundle.

    Comparacao ESTRITA (``>``): 48h exatas → ``FRESH``. O contrato diz *"exceeds
    max_age_hours"*; ``>=`` seria outra regra, divergente por um segundo.
    """
    from datetime import UTC

    if generated_at_dt is None or source_as_of_dt is None:
        raise FreshnessInvariantError("generated_at/source_as_of ausente — snapshot corrompido, export abortado")
    if generated_at_dt.tzinfo is None or source_as_of_dt.tzinfo is None:
        raise FreshnessInvariantError("generated_at/source_as_of sem fuso — snapshot corrompido, export abortado")

    generated_at = generated_at_dt.astimezone(UTC).isoformat(timespec="seconds")
    source_as_of = source_as_of_dt.astimezone(UTC).isoformat(timespec="seconds")

    age = datetime.fromisoformat(generated_at) - datetime.fromisoformat(source_as_of)
    state = FRESHNESS_STALE if age > timedelta(hours=FRESHNESS_MAX_AGE_HOURS) else FRESHNESS_FRESH

    return {
        "max_age_hours": FRESHNESS_MAX_AGE_HOURS,
        "generated_at": generated_at,
        "source_as_of": source_as_of,
        "state": state,
    }


def freshness_reason_codes(freshness: dict[str, Any]) -> tuple[str, ...]:
    """Codigos INTERNOS derivados do bloco ``freshness`` ja montado.

    ``freshness_stale``/``freshness_absent`` sao codigos do CONSUMIDOR e nunca
    sao emitidos por nos — a disjuncao e provada por teste.

    Delta negativo (``source_as_of > generated_at``, anomalia de relogio) mantem
    ``state == FRESH``, porque a formula do contrato nao e satisfeita, **e**
    declara o codigo interno. Rotular ``STALE`` aqui divergiria da recomputacao do
    consumidor — exatamente a falha silenciosa que a emenda do AC3 elimina.
    """
    codes: list[str] = []
    if freshness["state"] == FRESHNESS_STALE:
        codes.append(REASON_SOURCE_AS_OF_BEYOND_MAX_AGE)
    if datetime.fromisoformat(freshness["source_as_of"]) > datetime.fromisoformat(freshness["generated_at"]):
        codes.append(REASON_SOURCE_AS_OF_AFTER_GENERATED_AT)
    return tuple(codes)


def freshness_limitations(freshness: dict[str, Any]) -> tuple[str, ...]:
    """Linhas pt-BR que acompanham cada codigo interno de ``freshness``."""
    lines: list[str] = []
    if freshness["state"] == FRESHNESS_STALE:
        lines.append(
            f"Os dados de origem têm mais de {FRESHNESS_MAX_AGE_HOURS} horas em relação ao corte "
            f"deste conjunto ({freshness['source_as_of']} → {freshness['generated_at']})."
        )
    if datetime.fromisoformat(freshness["source_as_of"]) > datetime.fromisoformat(freshness["generated_at"]):
        lines.append(
            "A marca d'água da fonte é posterior ao corte do conjunto; há anomalia de relógio "
            "entre a fonte e o produtor."
        )
    return tuple(lines)


def data_state_for(snapshot_state: str) -> str:
    """Mapa §A.1. Estado nao exportavel levanta erro — nunca vira DATA_* por default."""
    try:
        return DATA_STATE_BY_SNAPSHOT_STATE[snapshot_state]
    except KeyError as exc:
        raise KeyError(
            f"estado de snapshot nao exportavel: {snapshot_state!r} — "
            f"exportaveis: {sorted(DATA_STATE_BY_SNAPSHOT_STATE)}"
        ) from exc


def prazo_status_for(deadline_state: str) -> str:
    return PRAZO_STATUS_BY_DEADLINE_STATE.get(deadline_state, UNKNOWN)
