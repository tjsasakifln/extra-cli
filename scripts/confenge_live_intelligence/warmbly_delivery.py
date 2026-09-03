"""LI-W2 P2 — entrega de eventos pendentes ao webhook inbound do Warmbly.

Warmbly ja aceita ``CONFENGE_OPPORTUNITY_EVENT/1.0`` em
``POST /api/v1/webhooks/confenge/inbound`` (internal/api/handler/confenge_inbound.go,
internal/app/confenge/liveintel/events.go) com dedup/replay por ``event_id`` —
este modulo so precisa ler os eventos ``pending``/``failed`` de
``confenge_live_intelligence_events`` (migration 106), montar o envelope no
shape exato que o Go espera, assinar com o mesmo HMAC de
``scripts/warmbly_bridge/hmac_sig.py`` (``sign_outcome_hmac``) e fazer POST.

Outbox e a propria tabela: ``delivery_status`` pending -> delivered|failed,
sem broker externo (decisao do goal). ``event_id`` e determinístico
(``LiveEvent.event_id``), entao reenviar o mesmo evento apos falha e seguro —
o lado Warmbly responde 200 (nao 201) em replay, nunca duplica.

Payload e ``map[string]string`` humano: objeto, faixa de valor, orgao, prazo —
projetado a partir da oportunidade/empresa no snapshot atual, nunca CNPJ cru
(mesma politica de ``export.py``/``public_policy.py``).
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from scripts.confenge_live_intelligence.schema import WRITE_TARGET_ORDER, assert_write_target
from scripts.warmbly_bridge.hmac_sig import sign_outcome_hmac

EVENT_ENVELOPE_SCHEMA = "CONFENGE_OPPORTUNITY_EVENT/1.0"
EVENTS_TABLE = WRITE_TARGET_ORDER[WRITE_TARGET_ORDER.index("confenge_live_intelligence_events")]

# subject_key e "opportunity:<id>" ou "company:<company_ref>" (events.py).
_OPPORTUNITY_PREFIX = "opportunity:"
_COMPANY_PREFIX = "company:"


class WarmblyDeliveryError(RuntimeError):
    """Falha de configuracao (secret/org/url ausente). Fail-closed, sem envio."""


@dataclass(frozen=True)
class DeliveryConfig:
    webhook_url: str
    hmac_secret: str
    org_id: str
    timeout_seconds: float = 15.0
    max_attempts_per_run: int = 1


def load_config_from_env(env: dict[str, str]) -> DeliveryConfig:
    url = (env.get("WARMBLY_INBOUND_WEBHOOK_URL") or "").strip()
    secret = (env.get("CONFENGE_INBOUND_WEBHOOK_SECRET") or "").strip()
    org_id = (env.get("CONFENGE_INBOUND_ORG_ID") or "").strip()
    missing = [
        name
        for name, value in (
            ("WARMBLY_INBOUND_WEBHOOK_URL", url),
            ("CONFENGE_INBOUND_WEBHOOK_SECRET", secret),
            ("CONFENGE_INBOUND_ORG_ID", org_id),
        )
        if not value
    ]
    if missing:
        raise WarmblyDeliveryError(f"config ausente, entrega nao autorizada: {', '.join(missing)}")
    return DeliveryConfig(webhook_url=url, hmac_secret=secret, org_id=org_id)


def _row_to_dict(row: Any, cur: Any) -> dict[str, Any]:
    """Normaliza uma linha de cursor para dict, por NOME de coluna.

    ``conn.cursor()`` pode devolver ``RealDictRow`` (ja um Mapping) ou uma
    tuple posicional, dependendo de como o chamador abriu a conexao — este
    modulo nao controla isso. Mesma convencao defensiva ja usada em
    ``producer.py``/``events.py``/``export.py`` neste pacote: nunca depende
    da ORDEM do SELECT para logica semantica, so do nome da coluna.
    """
    if isinstance(row, Mapping):
        return dict(row)
    columns = [d[0] for d in cur.description]
    return dict(zip(columns, row, strict=True))


def _fetch_pending_events(conn: Any, *, limit: int) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT event_id, event_type, subject_key, source_as_of,
                   delivery_status, delivery_attempts
            FROM public.{assert_write_target(EVENTS_TABLE)}
            WHERE delivery_status IN ('pending', 'failed')
            ORDER BY source_as_of ASC
            LIMIT %s
            """,  # noqa: S608
            (limit,),
        )
        return [_row_to_dict(row, cur) for row in cur.fetchall()]


def _opportunity_payload(conn: Any, opportunity_id: str) -> dict[str, str]:
    """Projecao humana a partir do snapshot mais recente que ainda contem o id.

    Nunca inclui CNPJ. Campos ausentes (UNKNOWN) sao omitidos, nao inventados.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT objeto, valor_band, orgao_nome, data_encerramento, uf, municipio
            FROM public.confenge_live_intelligence_opportunities
            WHERE opportunity_id = %s
            ORDER BY snapshot_id DESC
            LIMIT 1
            """,
            (opportunity_id,),
        )
        raw_row = cur.fetchone()
        if raw_row is None:
            return {"opportunity_id": opportunity_id}
        row = _row_to_dict(raw_row, cur)
    payload = {"opportunity_id": opportunity_id}
    if row.get("objeto"):
        payload["objeto"] = str(row["objeto"])
    if row.get("valor_band"):
        payload["valor_faixa"] = str(row["valor_band"])
    if row.get("orgao_nome"):
        payload["orgao"] = str(row["orgao_nome"])
    if row.get("data_encerramento"):
        payload["prazo"] = str(row["data_encerramento"])
    if row.get("uf"):
        payload["uf"] = str(row["uf"])
    if row.get("municipio"):
        payload["municipio"] = str(row["municipio"])
    return payload


def _company_payload(company_ref: str) -> dict[str, str]:
    """company_ref e opaco por politica (P1) — nenhum outro campo e derivavel
    sem reidentificar a empresa, entao o payload de eventos de empresa carrega
    so o que o subject_key ja expõe."""
    return {"company_ref": company_ref}


def _build_human_payload(conn: Any, subject_key: str) -> dict[str, str]:
    if subject_key.startswith(_OPPORTUNITY_PREFIX):
        return _opportunity_payload(conn, subject_key[len(_OPPORTUNITY_PREFIX) :])
    if subject_key.startswith(_COMPANY_PREFIX):
        return _company_payload(subject_key[len(_COMPANY_PREFIX) :])
    # subject_key desconhecido: nao inventa forma, preserva o dado bruto.
    return {"subject_key": subject_key}


def build_envelope(event_row: dict[str, Any], payload: dict[str, str], *, org_id: str) -> dict[str, Any]:
    occurred_at = event_row["source_as_of"]
    if isinstance(occurred_at, datetime):
        occurred_iso = occurred_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
    else:
        occurred_iso = str(occurred_at)
    return {
        "schema": EVENT_ENVELOPE_SCHEMA,
        "event_id": event_row["event_id"],
        "event_type": event_row["event_type"],
        "subject_key": event_row["subject_key"],
        "org_id": org_id,
        "occurred_at": occurred_iso,
        "payload": payload,
    }


def sign_request(secret: str, body: bytes, *, now: float | None = None) -> str:
    ts = int(now if now is not None else time.time())
    return sign_outcome_hmac(secret, ts, body)


def _post(url: str, body: bytes, signature: str, *, timeout: float) -> tuple[int, str]:
    req = urllib.request.Request(  # noqa: S310 — operator-configured internal webhook
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Warmbly-Signature": signature,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


def _mark_delivered(conn: Any, event_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE public.{assert_write_target(EVENTS_TABLE)}
            SET delivery_status = 'delivered',
                delivered_at = NOW(),
                delivery_attempts = delivery_attempts + 1,
                last_delivery_error = NULL
            WHERE event_id = %s
            """,  # noqa: S608
            (event_id,),
        )
    conn.commit()


def _mark_failed(conn: Any, event_id: str, error: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE public.{assert_write_target(EVENTS_TABLE)}
            SET delivery_status = 'failed',
                delivery_attempts = delivery_attempts + 1,
                last_delivery_error = %s
            WHERE event_id = %s
            """,  # noqa: S608
            (error[:2000], event_id),
        )
    conn.commit()


@dataclass(frozen=True)
class DeliveryResult:
    event_id: str
    event_type: str
    http_status: int
    delivered: bool
    replay: bool


def deliver_pending_events(conn: Any, config: DeliveryConfig, *, limit: int = 200) -> list[DeliveryResult]:
    """Le eventos pending/failed, entrega um a um, atualiza o outbox.

    Cada evento e independente: uma falha nao interrompe os demais (fail
    forward, nao fail fast) — a proxima chamada re-tenta so os que ainda
    estao pending/failed, por construcao (WHERE delivery_status IN (...)).
    """
    results: list[DeliveryResult] = []
    for event_row in _fetch_pending_events(conn, limit=limit):
        payload = _build_human_payload(conn, event_row["subject_key"])
        if not payload:
            _mark_failed(conn, event_row["event_id"], "empty_payload_not_sent")
            results.append(
                DeliveryResult(event_row["event_id"], event_row["event_type"], 0, False, False)
            )
            continue
        envelope = build_envelope(event_row, payload, org_id=config.org_id)
        body = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8")
        signature = sign_request(config.hmac_secret, body)
        try:
            status, resp_text = _post(config.webhook_url, body, signature, timeout=config.timeout_seconds)
        except (urllib.error.URLError, OSError) as e:
            _mark_failed(conn, event_row["event_id"], f"network_error: {e}")
            results.append(
                DeliveryResult(event_row["event_id"], event_row["event_type"], 0, False, False)
            )
            continue
        if 200 <= status < 300:
            _mark_delivered(conn, event_row["event_id"])
            replay = status == 200
            results.append(
                DeliveryResult(event_row["event_id"], event_row["event_type"], status, True, replay)
            )
        else:
            _mark_failed(conn, event_row["event_id"], f"http_{status}: {resp_text[:500]}")
            results.append(
                DeliveryResult(event_row["event_id"], event_row["event_type"], status, False, False)
            )
    return results
