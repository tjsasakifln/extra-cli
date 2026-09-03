"""Verifier (nucleo) — re-derivacao fail-closed de hashes e whitelist de PII.

Duas garantias:

1. **AC9 — fail-closed.** Todo hash persistido (``universe``, ``policy``,
   ``schema``, ``data``, ``fit``, ``content``, alem dos hashes por linha) e
   RE-DERIVADO a partir do conteudo gravado. Qualquer divergencia levanta
   ``LiveIntelligenceVerificationError``. Nao existe retorno de sucesso parcial
   nem degradacao silenciosa.
2. **AC10 — zero PII por WHITELIST.** O key-set de cada payload emitido precisa
   ser SUBCONJUNTO do schema declarado em ``schema.py``. Whitelist, nao
   blacklist: uma chave nova como ``responsavel_nome`` e rejeitada por nao estar
   declarada, mesmo sem bater em nenhum termo de regex proibido.

O verifier NUNCA escreve. Ele apenas le ``confenge_live_intelligence_*``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Final

from scripts.confenge_live_intelligence.contract_date_resolver import DATE_RESOLVER_VERSION
from scripts.confenge_live_intelligence.fit import derive_fit_state
from scripts.confenge_live_intelligence.producer import (
    content_hash_of,
    data_hash_of,
    fit_hash_of,
    normalize_source_as_of,
    universe_hash_of,
)
from scripts.confenge_live_intelligence.schema import (
    COMPANY_PAYLOAD_KEYS,
    FIT_PAYLOAD_KEYS,
    FORBIDDEN_PII_KEY_TERMS,
    OPPORTUNITY_PAYLOAD_KEYS,
    SNAPSHOT_BLOCKED,
    SNAPSHOT_PARTIAL,
    SNAPSHOT_READY,
    LiveCompany,
    LiveCompanyOpportunityFit,
    LiveIntelligenceSchemaError,
    LiveOpportunity,
    assert_payload_within_schema,
    policy_hash,
    schema_hash,
)


class LiveIntelligenceVerificationError(RuntimeError):
    """Divergencia de verificacao. Sempre fatal — nunca sucesso parcial."""


@dataclass(frozen=True)
class VerificationReport:
    snapshot_id: str
    state: str
    checks: tuple[str, ...]
    verified_opportunities: int
    verified_companies: int
    verified_fits: int

    @property
    def ok(self) -> bool:
        return True  # a instancia so existe quando tudo passou (fail-closed)


def _rows(cur: Any) -> list[dict[str, Any]]:
    if cur.description is None:
        return []
    cols = [d[0] for d in cur.description]
    return [dict(r) if isinstance(r, dict) else dict(zip(cols, r, strict=True)) for r in (cur.fetchall() or [])]


def _fail(message: str) -> None:
    raise LiveIntelligenceVerificationError(message)


def assert_no_undeclared_keys(payload: Mapping[str, Any], *, kind: str) -> None:
    """AC10 — whitelist de key-set por tipo de objeto emitido."""
    allowed = {
        "opportunity": OPPORTUNITY_PAYLOAD_KEYS,
        "company": COMPANY_PAYLOAD_KEYS,
        "fit": FIT_PAYLOAD_KEYS,
    }.get(kind)
    if allowed is None:
        _fail(f"tipo de payload desconhecido: {kind!r}")
        return
    try:
        assert_payload_within_schema(dict(payload), allowed, label=f"payload {kind}")
    except LiveIntelligenceSchemaError as exc:
        raise LiveIntelligenceVerificationError(str(exc)) from exc
    # Trava redundante de revisao: nenhum termo de contato pode existir como
    # chave, ainda que alguem o declarasse no schema por engano.
    offending = sorted(key for key in payload if any(term in str(key).lower() for term in FORBIDDEN_PII_KEY_TERMS))
    if offending:
        _fail(f"payload {kind} contem chave de contato/PII: {offending}")


def _as_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    return tuple(str(v) for v in value)


def _rebuild_opportunity(row: Mapping[str, Any]) -> LiveOpportunity:
    """Reconstroi a OPPORTUNITY persistida para re-derivar o hash de linha.

    ``source_as_of`` passa por ``normalize_source_as_of`` (→ UTC) porque a coluna
    e ``TIMESTAMPTZ`` e o driver devolve o INSTANTE no fuso da SESSAO corrente.
    ``live_hash`` serializa ``datetime`` por ``isoformat()``, logo o mesmo
    instante lido sob ``CUTOFF_TIMEZONE`` e sob UTC dava hashes diferentes e o
    verifier falhava fechado sobre um snapshot intacto — bastava verificar na
    MESMA conexao que acabou de fazer o build (que pina o fuso). Mesma classe de
    REL-001, latente no caminho de verify; a normalizacao dos dois lados torna o
    hash funcao do instante, nao do fuso da sessao.
    """
    valor = row.get("valor_estimado_brl")
    return LiveOpportunity(
        opportunity_id=str(row["opportunity_id"]),
        source=str(row["source"]),
        source_as_of=normalize_source_as_of(row["source_as_of"]),
        objeto=row.get("objeto"),
        objeto_state=str(row["objeto_state"]),
        valor_estimado_brl=Decimal(str(valor)) if valor is not None else None,
        valor_state=str(row["valor_state"]),
        valor_band=row.get("valor_band"),
        modalidade_id=row.get("modalidade_id"),
        modalidade=row.get("modalidade"),
        modalidade_state=str(row["modalidade_state"]),
        uf=row.get("uf"),
        municipio=row.get("municipio"),
        codigo_ibge=row.get("codigo_ibge"),
        geo_state=str(row["geo_state"]),
        orgao_cnpj=row.get("orgao_cnpj"),
        orgao_nome=row.get("orgao_nome"),
        orgao_state=str(row["orgao_state"]),
        data_publicacao=row.get("data_publicacao"),
        data_encerramento=row.get("data_encerramento"),
        deadline_state=str(row["deadline_state"]),
        link_edital=row.get("link_edital"),
        source_id=row.get("source_id"),
        row_completeness_state=str(row["row_completeness_state"]),
        exclusion_reason_codes=_as_tuple(row.get("exclusion_reason_codes")),
        reason_codes=_as_tuple(row.get("reason_codes")),
    )


def _rebuild_company(row: Mapping[str, Any]) -> LiveCompany:
    return LiveCompany(
        company_root8=str(row["company_root8"]),
        # Mesma normalizacao de `_rebuild_opportunity` — ver docstring de la.
        source_as_of=normalize_source_as_of(row["source_as_of"]),
        date_resolver_version=str(row["date_resolver_version"]),
        razao_social=row.get("razao_social"),
        portfolio_contract_ids=_as_tuple(row.get("portfolio_contract_ids")),
        observed_objects=_as_tuple(row.get("observed_objects")),
        observed_value_bands=_as_tuple(row.get("observed_value_bands")),
        observed_ufs=_as_tuple(row.get("observed_ufs")),
        observed_buyer_cnpjs=_as_tuple(row.get("observed_buyer_cnpjs")),
        # §B.3 — coluna da 105. Omitir aqui faria o rebuild produzir `()` contra
        # o array real persistido, `portfolio_hash()` divergiria e o verifier
        # falharia fechado sobre um snapshot INTACTO. Mesma classe do defeito de
        # fuso documentado em `_rebuild_opportunity`.
        observed_establishment_cnpjs=_as_tuple(row.get("observed_establishment_cnpjs")),
        most_recent_contracting_date=row.get("most_recent_contracting_date"),
        contracting_date_state=str(row["contracting_date_state"]),
        row_completeness_state=str(row["row_completeness_state"]),
        exclusion_reason_codes=_as_tuple(row.get("exclusion_reason_codes")),
        reason_codes=_as_tuple(row.get("reason_codes")),
    )


def _rebuild_fit(row: Mapping[str, Any]) -> LiveCompanyOpportunityFit:
    return LiveCompanyOpportunityFit(
        company_root8=str(row["company_root8"]),
        opportunity_id=str(row["opportunity_id"]),
        dim_object=str(row["dim_object"]),
        dim_value_band=str(row["dim_value_band"]),
        dim_geography=str(row["dim_geography"]),
        dim_comparable_buyer=str(row["dim_comparable_buyer"]),
        dim_recency=str(row["dim_recency"]),
        fit_state=str(row["fit_state"]),
        matched_dimensions=_as_tuple(row.get("matched_dimensions")),
        unknown_dimensions=_as_tuple(row.get("unknown_dimensions")),
        reason_codes=_as_tuple(row.get("reason_codes")),
        evidence_refs=dict(row.get("evidence_refs") or {}),
    )


def verify_snapshot(conn: Any, snapshot_id: str) -> VerificationReport:
    """Re-deriva todos os hashes do snapshot persistido. Falha fechado."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM public.confenge_live_intelligence_snapshots WHERE snapshot_id = %s",
            (snapshot_id,),
        )
        headers = _rows(cur)
        if not headers:
            _fail(f"snapshot inexistente: {snapshot_id!r}")
        header = headers[0]

        cur.execute(
            "SELECT * FROM public.confenge_live_intelligence_opportunities "
            "WHERE snapshot_id = %s ORDER BY opportunity_id",
            (snapshot_id,),
        )
        opportunity_rows = _rows(cur)
        cur.execute(
            "SELECT * FROM public.confenge_live_intelligence_companies WHERE snapshot_id = %s ORDER BY company_root8",
            (snapshot_id,),
        )
        company_rows = _rows(cur)
        cur.execute(
            "SELECT * FROM public.confenge_live_intelligence_fit "
            "WHERE snapshot_id = %s ORDER BY company_root8, opportunity_id",
            (snapshot_id,),
        )
        fit_rows = _rows(cur)

    state = str(header["state"])
    checks: list[str] = []

    if state == SNAPSHOT_BLOCKED:
        if not header.get("blockers"):
            _fail("snapshot BLOCKED sem blockers declarados")
        return VerificationReport(snapshot_id, state, ("blocked_has_blockers",), 0, 0, 0)

    if state not in (SNAPSHOT_READY, SNAPSHOT_PARTIAL):
        _fail(f"estado nao verificavel: {state!r} (esperado READY_CANONICAL ou PARTIAL)")

    if header.get("closed_at") is None or header.get("content_hash") is None:
        _fail(f"estado terminal {state} sem closed_at/content_hash: snapshot nao selado")
    if header.get("blockers"):
        _fail(f"{state} com blockers e contradicao estrutural: {header.get('blockers')!r}")
    checks.append("terminal_state_sealed")

    opportunities = [_rebuild_opportunity(r) for r in opportunity_rows]
    companies = [_rebuild_company(r) for r in company_rows]
    fits = [_rebuild_fit(r) for r in fit_rows]

    for obj, row, kind, column in (
        *[(o, r, "opportunity", "opportunity_hash") for o, r in zip(opportunities, opportunity_rows, strict=True)],
        *[(c, r, "company", "portfolio_hash") for c, r in zip(companies, company_rows, strict=True)],
        *[(f, r, "fit", "fit_hash") for f, r in zip(fits, fit_rows, strict=True)],
    ):
        payload = obj.as_payload()
        assert_no_undeclared_keys(payload, kind=kind)
        recomputed = {
            "opportunity": lambda: obj.content_hash(),
            "company": lambda: obj.portfolio_hash(),
            "fit": lambda: obj.fit_hash(),
        }[kind]()
        if recomputed != str(row[column]):
            _fail(f"hash de linha divergente ({kind}, {column}): persistido={row[column]} rederivado={recomputed}")
    checks.append("row_hashes_rederived")
    checks.append("payload_keyset_whitelisted")

    for fit in fits:
        derived = derive_fit_state(
            {
                "dim_object": fit.dim_object,
                "dim_value_band": fit.dim_value_band,
                "dim_geography": fit.dim_geography,
                "dim_comparable_buyer": fit.dim_comparable_buyer,
                "dim_recency": fit.dim_recency,
            }
        )
        if derived != fit.fit_state:
            _fail(
                f"fit_state persistido ({fit.fit_state}) diverge da derivacao ({derived}) "
                f"para {fit.company_root8}/{fit.opportunity_id}"
            )
    checks.append("fit_state_derivation")

    as_of = header["as_of_date"]
    if isinstance(as_of, datetime):
        as_of = as_of.date()
    if not isinstance(as_of, date):
        _fail("as_of_date ausente ou nao e data civil")

    expected = {
        "universe_hash": universe_hash_of(opportunities, companies, as_of=as_of),
        "policy_hash": policy_hash(
            date_resolver_version=str(header.get("date_resolver_version") or DATE_RESOLVER_VERSION)
        ),
        "schema_hash": schema_hash(),
        "data_hash": data_hash_of(opportunities, companies),
        "fit_hash": fit_hash_of(fits),
    }
    for column, value in expected.items():
        if str(header[column]) != value:
            _fail(f"{column} divergente: persistido={header[column]} rederivado={value}")
    checks.append("aggregate_hashes_rederived")

    content = content_hash_of(
        universe=expected["universe_hash"],
        policy=expected["policy_hash"],
        schema=expected["schema_hash"],
        data=expected["data_hash"],
        fits=expected["fit_hash"],
    )
    if content != str(header["content_hash"]):
        _fail(f"content_hash divergente: persistido={header['content_hash']} rederivado={content}")
    checks.append("content_hash_rederived")

    excluded_opportunities = sum(1 for o in opportunities if o.row_completeness_state != "COMPLETE")
    excluded_companies = sum(1 for c in companies if c.row_completeness_state != "COMPLETE")
    if excluded_opportunities != int(header["excluded_opportunity_count"]):
        _fail("excluded_opportunity_count nao bate com as linhas excluidas persistidas")
    if excluded_companies != int(header["excluded_company_count"]):
        _fail("excluded_company_count nao bate com as linhas excluidas persistidas")
    if state == SNAPSHOT_READY and (excluded_opportunities or excluded_companies):
        _fail("READY_CANONICAL com linha excluida e contradicao estrutural")
    if state == SNAPSHOT_PARTIAL and not (excluded_opportunities or excluded_companies):
        _fail("PARTIAL sem nenhuma linha excluida e contradicao estrutural")
    checks.append("exclusion_counts_reconciled")

    return VerificationReport(
        snapshot_id=snapshot_id,
        state=state,
        checks=tuple(checks),
        verified_opportunities=len(opportunities),
        verified_companies=len(companies),
        verified_fits=len(fits),
    )


def verify_payload_keysets(payloads: Sequence[tuple[str, Mapping[str, Any]]]) -> None:
    """Helper de gate: valida uma sequencia de ``(kind, payload)``."""
    for kind, payload in payloads:
        assert_no_undeclared_keys(payload, kind=kind)


# =========================================================================
# LI-W2 §A.4 / Task 8 — verificacao do BUNDLE PUBLICO SERIALIZADO
# =========================================================================
#
# A prova roda sobre o JSON **de disco**, nao sobre o dict Python: uma chave que
# so aparece na serializacao (ou um valor que so vira string ao serializar)
# escaparia de qualquer verificacao feita em memoria. E o que AC5 exige
# literalmente.

# Chaves cujo VALOR e um token hexadecimal opaco. Elas sao mascaradas antes da
# varredura de CNPJ porque um digest de 16 hex ou um hash de 64 hex pode conter,
# por acaso, 14 digitos consecutivos — um falso positivo probabilistico que
# transformaria a prova de AC6 num teste instavel. A mascara e segura porque o
# formato de cada uma e validado ANTES, e nenhum CNPJ (14 digitos) satisfaz
# `^[0-9a-f]{16}$` nem `^[0-9a-f]{64}$` (comprimento errado).
_HEX16_KEYS: Final[tuple[str, ...]] = ("company_digest", "buyer_digest")
_HEX64_KEYS: Final[tuple[str, ...]] = ("content_hash", "manifest_hash")
_HEX16_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{16}$")
_HEX64_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")

# 14 digitos consecutivos (CNPJ cru) e CNPJ mascarado (99.999.999/9999-99).
_CNPJ_RAW_RE: Final[re.Pattern[str]] = re.compile(r"(?<!\d)\d{14}(?!\d)")
_CNPJ_MASKED_RE: Final[re.Pattern[str]] = re.compile(r"(?<!\d)\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}(?!\d)")

_DIGEST_MASK: Final[str] = "<hex>"


@dataclass(frozen=True)
class BundleVerificationReport:
    files_verified: int
    checks: tuple[str, ...]


def _mask_hex_tokens(node: Any) -> Any:
    """Substitui valores de chave hexadecimal declarada por ``<hex>``.

    Valida o formato antes de mascarar: um valor que nao satisfaz o regex nao e
    um digest/hash e continua visivel para a varredura de CNPJ.
    """
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for key, value in node.items():
            if key in _HEX16_KEYS and isinstance(value, str) and _HEX16_RE.match(value):
                out[key] = _DIGEST_MASK
            elif key in _HEX64_KEYS and isinstance(value, str) and _HEX64_RE.match(value):
                out[key] = _DIGEST_MASK
            else:
                out[key] = _mask_hex_tokens(value)
        return out
    if isinstance(node, list):
        return [_mask_hex_tokens(item) for item in node]
    return node


def _walk_strings(node: Any) -> list[str]:
    """Todas as chaves e valores-string do documento, para a varredura de AC5."""
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            found.append(str(key))
            found.extend(_walk_strings(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_walk_strings(item))
    elif isinstance(node, str):
        found.append(node)
    return found


def _walk_keys(node: Any) -> list[str]:
    """Somente as CHAVES do documento (nomes de campo)."""
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            found.append(str(key))
            found.extend(_walk_keys(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_walk_keys(item))
    return found


def assert_no_forbidden_content(serialized: str, parsed: Any, *, label: str) -> None:
    """AC5 — campos de conclusao, valores de enum editorial e jargao interno."""
    from scripts.confenge_live_intelligence import public_policy as policy

    keys = _walk_keys(parsed)
    tokens = _walk_strings(parsed)
    for field_name in policy.FORBIDDEN_FIELDS:
        if field_name == "INDEX":
            # `INDEX` e proibido como VALOR de enum, nao como o campo
            # `manifest.index` (indice obrigatorio de arquivos do bundle).
            continue
        if any(field_name == key.lower() for key in keys):
            _fail(f"{label}: campo de conclusao proibido presente como CHAVE: {field_name!r}")
        # Comparacao por IGUALDADE, nao por substring. O proprio contrato exige
        # `disclaimer_pt` = "Aderência histórica não é habilitação, capacidade
        # nem recomendação...", que CONTEM a palavra `capacidade` em prosa. O que
        # `forbidden_conclusion_fields` proibe e o campo/valor de conclusao — um
        # valor que seja a conclusao — nao a palavra dentro da frase que existe
        # justamente para NEGAR a conclusao. Substring aqui tornaria o AC5
        # autocontraditorio com o disclaimer obrigatorio do AC6/§A.4.
        if any(field_name == token.strip().lower() for token in tokens):
            _fail(f"{label}: campo/valor de conclusao proibido presente como VALOR: {field_name!r}")
    for enum_value in policy.FORBIDDEN_ENUM_VALUES:
        if any(token == enum_value for token in tokens):
            _fail(f"{label}: valor de enum editorial proibido presente: {enum_value!r}")
    for forbidden in policy.FORBIDDEN_STRINGS:
        if forbidden.lower() in serialized.lower():
            _fail(f"{label}: linguagem publica proibida presente: {forbidden!r}")


def assert_no_raw_cnpj(parsed: Any, *, label: str) -> None:
    """AC6 — nenhum CNPJ cru ou mascarado, de nenhuma entidade."""
    masked = json.dumps(_mask_hex_tokens(parsed), ensure_ascii=False, sort_keys=True)
    raw_hits = _CNPJ_RAW_RE.findall(masked)
    if raw_hits:
        _fail(f"{label}: CNPJ cru (14 digitos) presente no JSON serializado: {sorted(set(raw_hits))}")
    mask_hits = _CNPJ_MASKED_RE.findall(masked)
    if mask_hits:
        _fail(f"{label}: CNPJ mascarado presente no JSON serializado: {sorted(set(mask_hits))}")


def verify_bundle(out_dir: str | Path) -> BundleVerificationReport:
    """Prova o bundle EM DISCO. Falha fechado na primeira violacao.

    Cobre AC1 (indice == conjunto de arquivos), AC5 (campos/linguagem proibidos),
    AC6 (nenhum CNPJ cru/mascarado em ``companies/*.json``) e a recomputabilidade
    de ``content_hash``/``manifest_hash``.
    """
    from scripts.confenge_live_intelligence import public_policy as policy
    from scripts.confenge_live_intelligence.export import (
        COMPANIES_DIR,
        MANIFEST_FILE,
        OPPORTUNITIES_DIR,
        load_bundle,
    )
    from scripts.confenge_live_intelligence.schema import live_hash

    root = Path(out_dir)
    if not (root / MANIFEST_FILE).is_file():
        _fail(f"bundle sem {MANIFEST_FILE}: {root}")
    bundle = load_bundle(root)
    manifest = bundle["manifest"]
    files = bundle["files"]
    checks: list[str] = []

    # --- envelope -----------------------------------------------------------
    if manifest.get("schema") != policy.CONTRACT_SCHEMA:
        _fail(f"manifest.schema ausente ou divergente: {manifest.get('schema')!r}")
    if "contract" in manifest:
        _fail("manifest emite a chave 'contract' — proibido (AC1): a chave de envelope e 'schema', sem alias")
    if manifest.get("data_state") not in policy.DATA_STATE_BY_SNAPSHOT_STATE.values():
        _fail(f"manifest.data_state fora do enum do contrato: {manifest.get('data_state')!r}")
    checks.append("manifest_envelope")

    # --- indice == conjunto exato de arquivos emitidos ----------------------
    indexed = {entry["file"] for entry in manifest["index"]["opportunities"]} | {
        entry["file"] for entry in manifest["index"]["companies"]
    }
    if indexed != set(files):
        _fail(
            "manifest.index nao e o conjunto exato de arquivos emitidos: "
            f"so_no_indice={sorted(indexed - set(files))} so_no_disco={sorted(set(files) - indexed)}"
        )
    for entry in manifest["index"]["opportunities"]:
        if entry.get("schema") != policy.OPPORTUNITY_SCHEMA:
            _fail(f"entrada de index sem schema de familia: {entry!r}")
    for entry in manifest["index"]["companies"]:
        if entry.get("schema") != policy.COMPANY_SCHEMA:
            _fail(f"entrada de index sem schema de familia: {entry!r}")
    checks.append("index_matches_emitted_files")

    # --- hashes recomputaveis ----------------------------------------------
    recomputed_manifest = live_hash({k: v for k, v in manifest.items() if k != "manifest_hash"})
    if recomputed_manifest != manifest.get("manifest_hash"):
        _fail("manifest_hash nao e recomputavel a partir do manifest serializado")
    for rel, payload in files.items():
        recomputed = live_hash({k: v for k, v in payload.items() if k != "content_hash"})
        if recomputed != payload.get("content_hash"):
            _fail(f"{rel}: content_hash nao e recomputavel ({payload.get('content_hash')!r} != {recomputed!r})")
    for entry in (*manifest["index"]["opportunities"], *manifest["index"]["companies"]):
        if files[entry["file"]]["content_hash"] != entry["content_hash"]:
            _fail(f"content_hash do index diverge do arquivo: {entry['file']}")
    checks.append("hashes_recomputable")

    # --- AC5 / AC6 sobre o SERIALIZADO --------------------------------------
    manifest_text = (root / MANIFEST_FILE).read_text(encoding="utf-8")
    assert_no_forbidden_content(manifest_text, manifest, label=MANIFEST_FILE)
    for rel, payload in files.items():
        text = (root / rel).read_text(encoding="utf-8")
        assert_no_forbidden_content(text, payload, label=rel)
        if rel.startswith(f"{COMPANIES_DIR}/"):
            # AC6 — nem da empresa, nem de estabelecimento, nem de terceiros.
            assert_no_raw_cnpj(payload, label=rel)
            if "company_root8" in payload or "company_ref" in payload:
                _fail(f"{rel}: identificador interno vazado no payload publico (AC6/AC8)")
        elif rel.startswith(f"{OPPORTUNITIES_DIR}/"):
            # `orgao.cnpj` e ESPERADO aqui e nao e violacao (AC6): a assimetria e
            # do contrato (`live_opportunity` nao tem bloco `identity`).
            if "company_ref" in json.dumps(payload):
                _fail(f"{rel}: company_ref vazou para payload publico (AC8)")
    checks.append("forbidden_content_absent")
    checks.append("no_raw_cnpj_in_companies")

    # --- freshness identico em todo payload (AC3) ---------------------------
    for rel, payload in files.items():
        if payload.get("freshness") != manifest.get("freshness"):
            _fail(f"{rel}: bloco freshness diverge do manifest — o bloco e computado UMA vez (AC3)")
    checks.append("freshness_block_uniform")

    return BundleVerificationReport(files_verified=len(files), checks=tuple(checks))
