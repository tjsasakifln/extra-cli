"""LI-1 — fundacao de schema do motor inbound (Decisoes 2, 3, 4).

Contratos desta camada:

* ``live_hash()`` — canonical-JSON (``sort_keys``, ``separators`` compactos,
  ``ensure_ascii=False``) + SHA256. Mesma disciplina de
  ``scripts/inference_runtime/jobs.py:39`` (``sha256_payload``). A funcao e
  reimplementada aqui em vez de importada para nao acoplar o motor inbound ao
  runtime de inferencia; a equivalencia byte-a-byte com ``sha256_payload`` e
  provada por teste (``tests/confenge_live_intelligence/test_schema.py``).
* Dataclasses ``frozen`` para OPPORTUNITY / COMPANY / COMPANY_OPPORTUNITY_FIT.
* Tri-estado explicito por dimensao. ZERO campo numerico de score (Decisao 4 /
  R6): nao existe ``fit_score``, ``matched_count`` nem percentual.
* Whitelist de chaves (AC10): ``*_PAYLOAD_KEYS`` e a unica fonte de verdade do
  key-set emitido. O verifier rejeita qualquer chave nao declarada — inclusive
  campos vazados por join lateral que nenhuma blacklist regex pegaria.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, fields
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Final

ENGINE_ID: Final[str] = "CONFENGE_LIVE_INTELLIGENCE"
ENGINE_VERSION: Final[str] = "1.0"
SCHEMA_VERSION: Final[str] = "confenge-live-intelligence-schema/1.0"
POLICY_VERSION: Final[str] = "confenge-live-intelligence-policy/1.0"
CUTOFF_TIMEZONE: Final[str] = "America/Sao_Paulo"

# --- AR-2: allowlist unica de alvos de escrita -----------------------------
#
# AC11 provava apenas ausencia de literal (verbo DML + nome de tabela na MESMA
# string). O idiom `f"DELETE FROM public.{table}"` com `table` vindo de uma tupla
# local evadia essa prova. AR-2 do gate HIGH-RISK do @architect (ADR-040) exige
# que todo nome de tabela usado em SQL dinamico do pacote resolva a UMA UNICA
# constante nomeada, exportada pelo pacote e importada por nome pelo teste.
#
# `WRITE_TARGET_ORDER` e a UNICA enumeracao literal. Tudo o mais e derivado —
# duas listas independentes seriam duas allowlists, reproduzindo o defeito um
# nivel acima. A ordem e a de DELETE seguro para as FKs (filhos antes do pai).
WRITE_TARGET_ORDER: Final[tuple[str, ...]] = (
    "confenge_live_intelligence_events",
    "confenge_live_intelligence_fit",
    "confenge_live_intelligence_companies",
    "confenge_live_intelligence_opportunities",
    "confenge_live_intelligence_source_watermarks",
    "confenge_live_intelligence_snapshots",
)
ALLOWED_WRITE_TARGETS: Final[frozenset[str]] = frozenset(WRITE_TARGET_ORDER)


class OutboundWriteAttemptError(RuntimeError):
    """DML dinamico apontou para tabela fora de ``ALLOWED_WRITE_TARGETS``.

    Falha fechada: o motor inbound prefere abortar a escrever em objeto que nao
    seja ``confenge_live_intelligence_*``.
    """


def assert_write_target(table: str) -> str:
    """Valida ``table`` contra a allowlist ANTES de qualquer execucao de DML.

    Retorna o proprio nome para permitir uso inline no ponto de execucao, de
    modo que nao exista caminho em que a validacao seja pulada por descuido.
    """
    if table not in ALLOWED_WRITE_TARGETS:
        raise OutboundWriteAttemptError(
            f"alvo de escrita proibido: {table!r} nao esta em ALLOWED_WRITE_TARGETS "
            f"({sorted(ALLOWED_WRITE_TARGETS)}) — AC11/AR-2"
        )
    return table


# --- estados tipados -------------------------------------------------------

OBSERVED: Final[str] = "OBSERVED"
UNKNOWN: Final[str] = "UNKNOWN"
OBSERVATION_STATES: Final[tuple[str, ...]] = (OBSERVED, UNKNOWN)

DEADLINE_OPEN: Final[str] = "OPEN"
DEADLINE_CLOSED: Final[str] = "CLOSED"
DEADLINE_STATES: Final[tuple[str, ...]] = (DEADLINE_OPEN, DEADLINE_CLOSED, UNKNOWN)

MATCH: Final[str] = "MATCH"
NO_MATCH: Final[str] = "NO_MATCH"
DIMENSION_STATES: Final[tuple[str, ...]] = (MATCH, NO_MATCH, UNKNOWN)

FIT_OBSERVED: Final[str] = "OBSERVED_FIT"
FIT_NONE: Final[str] = "NO_OBSERVED_FIT"
FIT_INSUFFICIENT: Final[str] = "INSUFFICIENT_EVIDENCE"
FIT_STATES: Final[tuple[str, ...]] = (FIT_OBSERVED, FIT_NONE, FIT_INSUFFICIENT)

SNAPSHOT_BUILDING: Final[str] = "BUILDING"
SNAPSHOT_BLOCKED: Final[str] = "BLOCKED"
SNAPSHOT_PARTIAL: Final[str] = "PARTIAL"
SNAPSHOT_READY: Final[str] = "READY_CANONICAL"
SNAPSHOT_SUPERSEDED: Final[str] = "SUPERSEDED"
SNAPSHOT_STATES: Final[tuple[str, ...]] = (
    SNAPSHOT_BUILDING,
    SNAPSHOT_BLOCKED,
    SNAPSHOT_PARTIAL,
    SNAPSHOT_READY,
    SNAPSHOT_SUPERSEDED,
)

ROW_COMPLETE: Final[str] = "COMPLETE"
ROW_EXCLUDED_INCOMPLETE: Final[str] = "EXCLUDED_INCOMPLETE"
ROW_EXCLUDED_UNRESOLVED_DATE: Final[str] = "EXCLUDED_UNRESOLVED_DATE"

# Faixa ordinal versionada (Decisao 4). NAO participa de aritmetica: e rotulo.
VALUE_BANDS: Final[tuple[str, ...]] = ("ATE_100K", "100K_1M", "1M_10M", "ACIMA_10M")
_VALUE_BAND_CEILINGS: Final[tuple[tuple[Decimal, str], ...]] = (
    (Decimal("100000"), "ATE_100K"),
    (Decimal("1000000"), "100K_1M"),
    (Decimal("10000000"), "1M_10M"),
)

# --- reason codes (TEXT[] — decisao AC12-a) --------------------------------

REASON_OBJECT_HOLLOW: Final[str] = "object_text_hollow"
REASON_OBJECT_MISSING: Final[str] = "object_text_missing"
REASON_VALUE_MISSING: Final[str] = "estimated_value_missing"
REASON_MODALIDADE_MISSING: Final[str] = "modalidade_missing"
REASON_GEO_MISSING: Final[str] = "geography_missing"
REASON_ORGAO_MISSING: Final[str] = "buyer_identity_missing"
REASON_DEADLINE_MISSING: Final[str] = "deadline_missing"
REASON_CONTRACTING_DATE_UNRESOLVED: Final[str] = "contracting_date_unresolved"
REASON_PORTFOLIO_EMPTY: Final[str] = "observed_portfolio_empty"
REASON_ROW_EXCLUDED_REQUIRED_UNKNOWN: Final[str] = "required_dimension_unknown"

# Blockers (lista fechada, §7.2 do impact-analysis).
BLOCKER_HASH_DIVERGENCE: Final[str] = "hash_divergence"
BLOCKER_CONTRADICTORY_IDENTITY: Final[str] = "contradictory_identity"
BLOCKER_EMPTY_CONTRACT_ID: Final[str] = "public_contract_id_empty"
BLOCKER_WATERMARK_MISSING: Final[str] = "watermark_missing_or_failed"
BLOCKER_AS_OF_MISSING: Final[str] = "as_of_date_missing"
BLOCKER_OUTBOUND_WRITE_ATTEMPT: Final[str] = "outbound_write_attempt_detected"
CLOSED_BLOCKERS: Final[tuple[str, ...]] = (
    BLOCKER_HASH_DIVERGENCE,
    BLOCKER_CONTRADICTORY_IDENTITY,
    BLOCKER_EMPTY_CONTRACT_ID,
    BLOCKER_WATERMARK_MISSING,
    BLOCKER_AS_OF_MISSING,
    BLOCKER_OUTBOUND_WRITE_ATTEMPT,
)


class LiveIntelligenceSchemaError(RuntimeError):
    """Violacao de contrato de schema. Sempre fail-closed."""


# --- hashing ---------------------------------------------------------------


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        # Forma canonica estavel: string decimal normalizada, nunca float.
        return format(value.normalize(), "f")
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (set, frozenset)):
        return sorted(str(item) for item in value)
    if isinstance(value, tuple):
        return list(value)
    raise LiveIntelligenceSchemaError(f"tipo nao serializavel de forma canonica: {type(value)!r}")


def canonical_json(payload: Any) -> str:
    """JSON canonico: chaves ordenadas, separadores compactos, UTF-8 literal."""
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )


def live_hash(payload: Any) -> str:
    """SHA256 do JSON canonico. Independente da ordem de insercao das chaves."""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def value_band(value: Decimal | int | float | str | None) -> str | None:
    """Rotulo ordinal da faixa de valor. ``None`` quando o valor e desconhecido."""
    if value is None or value == "":
        return None
    try:
        amount = Decimal(str(value))
    except Exception:  # noqa: BLE001 - entrada externa nao confiavel
        return None
    if amount < 0:
        return None
    for ceiling, label in _VALUE_BAND_CEILINGS:
        if amount <= ceiling:
            return label
    return "ACIMA_10M"


# --- dataclasses -----------------------------------------------------------


def _check_choice(name: str, value: str, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        raise LiveIntelligenceSchemaError(f"{name}={value!r} fora do dominio {allowed}")


@dataclass(frozen=True)
class LiveOpportunity:
    """OPPORTUNITY (Decisao 3, §3.1). Sem PII: nenhum campo de pessoa/contato."""

    opportunity_id: str
    source: str
    source_as_of: datetime
    objeto: str | None = None
    objeto_state: str = UNKNOWN
    valor_estimado_brl: Decimal | None = None
    valor_state: str = UNKNOWN
    valor_band: str | None = None
    modalidade_id: str | None = None
    modalidade: str | None = None
    modalidade_state: str = UNKNOWN
    uf: str | None = None
    municipio: str | None = None
    codigo_ibge: str | None = None
    geo_state: str = UNKNOWN
    orgao_cnpj: str | None = None
    orgao_nome: str | None = None
    orgao_state: str = UNKNOWN
    data_publicacao: date | None = None
    data_encerramento: date | None = None
    deadline_state: str = UNKNOWN
    link_edital: str | None = None
    source_id: str | None = None
    row_completeness_state: str = ROW_COMPLETE
    exclusion_reason_codes: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not str(self.opportunity_id or "").strip():
            raise LiveIntelligenceSchemaError("opportunity_id vazio")
        for name in ("objeto_state", "valor_state", "modalidade_state", "geo_state", "orgao_state"):
            _check_choice(name, getattr(self, name), OBSERVATION_STATES)
        _check_choice("deadline_state", self.deadline_state, DEADLINE_STATES)
        _check_choice(
            "row_completeness_state",
            self.row_completeness_state,
            (ROW_COMPLETE, ROW_EXCLUDED_INCOMPLETE),
        )
        if self.valor_band is not None and self.valor_band not in VALUE_BANDS:
            raise LiveIntelligenceSchemaError(f"valor_band invalida: {self.valor_band!r}")
        excluded = self.row_completeness_state == ROW_EXCLUDED_INCOMPLETE
        if excluded != bool(self.exclusion_reason_codes):
            raise LiveIntelligenceSchemaError(
                "exclusao sem reason_code (ou reason_code sem exclusao) e descarte silencioso"
            )

    def as_payload(self) -> dict[str, Any]:
        return _as_payload(self, OPPORTUNITY_PAYLOAD_KEYS)

    def content_hash(self) -> str:
        return live_hash({"schema_version": SCHEMA_VERSION, "opportunity": self.as_payload()})


@dataclass(frozen=True)
class LiveCompany:
    """COMPANY (Decisao 3, §3.2) — projecao INDEPENDENTE do portfolio observado.

    Proibido copiar ``target_fit_class``/``target_fit_confidence``/``sector_class``
    de qualquer tabela outbound: essas tabelas sao lidas apenas por SELECT de
    diagnostico e nunca materializadas aqui.
    """

    company_root8: str
    source_as_of: datetime
    date_resolver_version: str
    razao_social: str | None = None
    portfolio_contract_ids: tuple[str, ...] = ()
    observed_objects: tuple[str, ...] = ()
    observed_value_bands: tuple[str, ...] = ()
    observed_ufs: tuple[str, ...] = ()
    observed_buyer_cnpjs: tuple[str, ...] = ()
    most_recent_contracting_date: date | None = None
    contracting_date_state: str = UNKNOWN
    row_completeness_state: str = ROW_COMPLETE
    exclusion_reason_codes: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not (len(self.company_root8) == 8 and self.company_root8.isdigit()):
            raise LiveIntelligenceSchemaError(f"company_root8 invalido: {self.company_root8!r}")
        _check_choice("contracting_date_state", self.contracting_date_state, OBSERVATION_STATES)
        _check_choice(
            "row_completeness_state",
            self.row_completeness_state,
            (ROW_COMPLETE, ROW_EXCLUDED_UNRESOLVED_DATE),
        )
        observed_date = self.contracting_date_state == OBSERVED
        if observed_date != (self.most_recent_contracting_date is not None):
            raise LiveIntelligenceSchemaError("contracting_date_state incoerente com a data resolvida")
        if not observed_date and self.row_completeness_state != ROW_EXCLUDED_UNRESOLVED_DATE:
            raise LiveIntelligenceSchemaError("data nao resolvida exige exclusao declarada da linha")
        excluded = self.row_completeness_state == ROW_EXCLUDED_UNRESOLVED_DATE
        if excluded != bool(self.exclusion_reason_codes):
            raise LiveIntelligenceSchemaError("exclusao sem reason_code e descarte silencioso")

    def as_payload(self) -> dict[str, Any]:
        return _as_payload(self, COMPANY_PAYLOAD_KEYS)

    def portfolio_hash(self) -> str:
        return live_hash({"schema_version": SCHEMA_VERSION, "company": self.as_payload()})


@dataclass(frozen=True)
class LiveCompanyOpportunityFit:
    """COMPANY_OPPORTUNITY_FIT (Decisao 4). ZERO campo numerico, por construcao."""

    company_root8: str
    opportunity_id: str
    dim_object: str
    dim_value_band: str
    dim_geography: str
    dim_comparable_buyer: str
    dim_recency: str
    fit_state: str
    matched_dimensions: tuple[str, ...] = ()
    unknown_dimensions: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()
    evidence_refs: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in DIMENSION_NAMES:
            _check_choice(name, getattr(self, name), DIMENSION_STATES)
        _check_choice("fit_state", self.fit_state, FIT_STATES)

    def as_payload(self) -> dict[str, Any]:
        return _as_payload(self, FIT_PAYLOAD_KEYS)

    def fit_hash(self) -> str:
        return live_hash({"schema_version": SCHEMA_VERSION, "fit": self.as_payload()})


DIMENSION_NAMES: Final[tuple[str, ...]] = (
    "dim_object",
    "dim_value_band",
    "dim_geography",
    "dim_comparable_buyer",
    "dim_recency",
)

# Whitelist declarada (AC10). Derivada dos campos das dataclasses frozen: a
# unica forma de acrescentar uma chave ao payload emitido e declara-la aqui.
OPPORTUNITY_PAYLOAD_KEYS: Final[frozenset[str]] = frozenset(f.name for f in fields(LiveOpportunity))
COMPANY_PAYLOAD_KEYS: Final[frozenset[str]] = frozenset(f.name for f in fields(LiveCompany))
FIT_PAYLOAD_KEYS: Final[frozenset[str]] = frozenset(f.name for f in fields(LiveCompanyOpportunityFit))

# Termos que jamais podem aparecer como chave de payload. Guarda redundante ao
# whitelist (o whitelist e a regra; isto e uma trava de revisao de codigo).
FORBIDDEN_PII_KEY_TERMS: Final[tuple[str, ...]] = (
    "email",
    "e_mail",
    "telefone",
    "phone",
    "celular",
    "whatsapp",
    "responsavel",
    "contato",
    "cargo",
    "linkedin",
    "cpf",
)


def _as_payload(obj: Any, allowed: frozenset[str]) -> dict[str, Any]:
    payload = asdict(obj)
    extra = set(payload) - allowed
    if extra:
        raise LiveIntelligenceSchemaError(f"chaves nao declaradas no schema: {sorted(extra)}")
    return payload


def assert_payload_within_schema(payload: dict[str, Any], allowed: frozenset[str], *, label: str) -> None:
    """AC10 — whitelist. Falha fechado em QUALQUER chave nao declarada."""
    extra = sorted(set(payload) - allowed)
    if extra:
        raise LiveIntelligenceSchemaError(
            f"{label}: key-set do payload nao e subconjunto do schema declarado; chaves extras={extra}"
        )


def schema_hash() -> str:
    """Hash do contrato de schema. Drift silencioso vira divergencia (R9)."""
    return live_hash(
        {
            "engine_id": ENGINE_ID,
            "engine_version": ENGINE_VERSION,
            "schema_version": SCHEMA_VERSION,
            "opportunity_keys": sorted(OPPORTUNITY_PAYLOAD_KEYS),
            "company_keys": sorted(COMPANY_PAYLOAD_KEYS),
            "fit_keys": sorted(FIT_PAYLOAD_KEYS),
            "dimension_names": list(DIMENSION_NAMES),
            "dimension_states": list(DIMENSION_STATES),
            "fit_states": list(FIT_STATES),
            "value_bands": list(VALUE_BANDS),
        }
    )


def policy_hash(*, date_resolver_version: str) -> str:
    return live_hash(
        {
            "policy_version": POLICY_VERSION,
            "cutoff_timezone": CUTOFF_TIMEZONE,
            "date_resolver_version": date_resolver_version,
            "closed_blockers": list(CLOSED_BLOCKERS),
        }
    )
