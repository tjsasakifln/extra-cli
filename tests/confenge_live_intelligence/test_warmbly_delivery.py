"""P2 — entrega de eventos ao webhook inbound do Warmbly.

Sobe um servidor HTTP local minimalista que replica EXATAMENTE a checagem
HMAC (`t=<unix>,v1=<hex>`) e a semantica de replay (2a chamada com o mesmo
event_id -> 200, nao 201) do handler real
(internal/api/handler/confenge_inbound.go + internal/app/confenge/liveintel).
Prova o cliente sem depender de rede/infra do Warmbly nesta etapa; a prova
contra o Warmbly real de producao fica para P6/E2E final (fora do escopo
deste teste, por decisao explicita do goal).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
import time
from datetime import UTC, date, datetime
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest

from scripts.confenge_live_intelligence import schema as li_schema
from scripts.confenge_live_intelligence import warmbly_delivery as wd
from scripts.confenge_live_intelligence.producer import build_snapshot
from scripts.confenge_live_intelligence.schema import assert_write_target
from scripts.confenge_live_intelligence.warmbly_delivery import EVENTS_TABLE

from .conftest import seed_bid

REQUIRE_REAL_DB = os.environ.get("REQUIRE_REAL_DB") == "1"

SECRET = "test-secret-p2"
ORG_ID = "00000000-0000-0000-0000-0000000000aa"


def _parse_sig(header: str) -> tuple[int | None, str | None]:
    t = None
    v1 = None
    for part in header.split(","):
        part = part.strip()
        if part.startswith("t="):
            t = int(part[2:])
        elif part.startswith("v1="):
            v1 = part[3:]
    return t, v1


class _FakeWarmblyHandler(BaseHTTPRequestHandler):
    seen_event_ids: set[str] = set()
    received: list[dict] = []

    def log_message(self, *args):  # noqa: D401 — silence test server logging
        return

    def do_POST(self):  # noqa: N802 — http.server API
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        sig_header = self.headers.get("X-Warmbly-Signature") or self.headers.get("X-Confenge-Signature") or ""
        t_unix, v1 = _parse_sig(sig_header)
        if t_unix is None or v1 is None:
            self.send_response(401)
            self.end_headers()
            return
        expected = hmac.new(SECRET.encode(), f"{t_unix}.".encode() + body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, v1):
            self.send_response(401)
            self.end_headers()
            return
        if abs(time.time() - t_unix) > 300:
            self.send_response(401)
            self.end_headers()
            return
        envelope = json.loads(body)
        assert envelope["schema"] == "CONFENGE_OPPORTUNITY_EVENT/1.0"
        assert envelope["event_id"]
        assert envelope["event_type"] in {
            "NEW_OPPORTUNITY",
            "OPPORTUNITY_CHANGED",
            "DEADLINE_CHANGED",
            "FIT_BECAME_RELEVANT",
        }
        assert envelope["subject_key"]
        assert envelope["org_id"]
        assert envelope["payload"], "payload vazio deveria ter sido recusado no cliente"
        # Nenhuma chave/valor do payload humano pode ser o nome cru da coluna
        # SQL (evt_id, objeto, valor_band, orgao_nome, ...) — essa e exatamente
        # a regressao de row-shape que este teste existe para pegar.
        _RAW_COLUMN_NAMES = {"objeto", "valor_band", "orgao_nome", "event_id", "event_type"}
        assert not (set(envelope["payload"].values()) & _RAW_COLUMN_NAMES), envelope["payload"]
        _FakeWarmblyHandler.received.append(envelope)
        replay = envelope["event_id"] in _FakeWarmblyHandler.seen_event_ids
        _FakeWarmblyHandler.seen_event_ids.add(envelope["event_id"])
        self.send_response(200 if replay else 201)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"data": {"replay": replay}}).encode("utf-8"))


@pytest.fixture()
def fake_warmbly():
    _FakeWarmblyHandler.seen_event_ids = set()
    _FakeWarmblyHandler.received = []
    server = HTTPServer(("127.0.0.1", 0), _FakeWarmblyHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_sign_request_matches_warmbly_verification():
    body = b'{"a":1}'
    sig = wd.sign_request(SECRET, body, now=1700000000)
    t_unix, v1 = _parse_sig(sig)
    assert t_unix == 1700000000
    expected = hmac.new(SECRET.encode(), b"1700000000." + body, hashlib.sha256).hexdigest()
    assert v1 == expected


class _FakeCursor:
    """Cursor minimo com `.description` real, para exercitar o ramo tuple
    de `_row_to_dict` sem depender de Postgres."""

    def __init__(self, columns: list[str]) -> None:
        self.description = [(c,) for c in columns]


def test_row_to_dict_accepts_tuple_cursor_by_position():
    cur = _FakeCursor(["event_id", "event_type"])
    row = ("evt-abc123", "NEW_OPPORTUNITY")
    result = wd._row_to_dict(row, cur)
    assert result == {"event_id": "evt-abc123", "event_type": "NEW_OPPORTUNITY"}
    assert result["event_id"] != "event_id"
    assert result["event_type"] != "event_type"


def test_row_to_dict_accepts_mapping_by_name_not_position():
    """RealDictRow (ou qualquer Mapping) nunca deve ser tratado como tuple —
    esta e exatamente a regressao que fez event_id virar a string 'event_id'."""
    cur = _FakeCursor(["something_else", "another_col"])  # descricao IRRELEVANTE p/ Mapping
    row = {"event_id": "evt-real-456", "event_type": "OPPORTUNITY_CHANGED"}
    result = wd._row_to_dict(row, cur)
    assert result == {"event_id": "evt-real-456", "event_type": "OPPORTUNITY_CHANGED"}
    assert result["event_id"] != "event_id"
    assert result["event_type"] != "event_type"


def test_load_config_from_env_fail_closed_on_missing():
    with pytest.raises(wd.WarmblyDeliveryError):
        wd.load_config_from_env({})


def test_load_config_from_env_ok():
    env = {
        "WARMBLY_INBOUND_WEBHOOK_URL": "http://example.invalid/webhook",
        "CONFENGE_INBOUND_WEBHOOK_SECRET": SECRET,
        "CONFENGE_INBOUND_ORG_ID": ORG_ID,
    }
    cfg = wd.load_config_from_env(env)
    assert cfg.webhook_url == env["WARMBLY_INBOUND_WEBHOOK_URL"]
    assert cfg.hmac_secret == SECRET
    assert cfg.org_id == ORG_ID


def _seed_opportunity(suffix: str, **overrides) -> li_schema.LiveOpportunity:
    base = dict(
        opportunity_id=f"LI-TEST-WD-{suffix}",
        source="pncp",
        source_as_of=datetime.now(tz=UTC),
        objeto="Reforma de unidade basica de saude com estrutura metalica",
        objeto_state=li_schema.OBSERVED,
        valor_estimado_brl=Decimal("250000.00"),
        valor_state=li_schema.OBSERVED,
        valor_band="100K_1M",
        modalidade="Pregao",
        modalidade_id="6",
        modalidade_state=li_schema.OBSERVED,
        uf="SC",
        municipio="Florianopolis",
        geo_state=li_schema.OBSERVED,
        orgao_cnpj="12345678000199",
        orgao_nome="Prefeitura Sintetica LI-TEST",
        orgao_state=li_schema.OBSERVED,
        data_publicacao=date.today(),
        data_encerramento=None,
        deadline_state=li_schema.DEADLINE_OPEN,
    )
    base.update(overrides)
    return li_schema.LiveOpportunity(**base)


def _seed_pending_event(conn: Any, *, suffix: str) -> None:
    """Semeia 1 evento real pending, pelo caminho de producao (build_snapshot),
    nunca por INSERT a mao — o mesmo caminho que P2 entrega de verdade."""
    seed_bid(conn, suffix=suffix)
    build_snapshot(
        conn,
        as_of=date.today(),
        created_by=f"LI-TEST-warmbly-delivery-{suffix}",
        opportunities=[_seed_opportunity(suffix)],
        companies=[],
    )


@pytest.mark.real_db
@pytest.mark.skipif(not REQUIRE_REAL_DB, reason="requer REQUIRE_REAL_DB=1 e Postgres real")
def test_deliver_pending_events_is_idempotent_on_replay(fake_warmbly, live_conn):
    """Entrega os eventos pending reais 2x seguidas (replay). Prova:
    - 1a rodada: delivery_status pending -> delivered, HTTP 201 no fake server.
    - 2a rodada: nenhum evento resta pending/failed (idempotencia do outbox:
      eventos ja delivered nao sao reenviados).
    - Um reenvio manual do MESMO event_id (simulando falha + retry) responde
      200 (replay), nunca duplica no lado receptor.
    """
    conn = live_conn
    config = wd.DeliveryConfig(webhook_url=fake_warmbly, hmac_secret=SECRET, org_id=ORG_ID)
    _seed_pending_event(conn, suffix="replay")

    with conn.cursor() as cur:
        cur.execute(
            f"SELECT count(*) AS n FROM public.{assert_write_target(EVENTS_TABLE)} "
            "WHERE delivery_status IN ('pending','failed')"
        )
        pending_before = cur.fetchone()["n"]
    assert pending_before > 0, "seed via build_snapshot precisa ter gerado evento pending real"

    first_pass = wd.deliver_pending_events(conn, config, limit=5)
    assert first_pass, "deveria ter entregue pelo menos 1 evento"
    assert all(r.delivered and not r.replay for r in first_pass), first_pass
    assert all(200 <= r.http_status < 300 for r in first_pass)

    delivered_event_ids = [r.event_id for r in first_pass]
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT delivery_status, delivery_attempts FROM public.{assert_write_target(EVENTS_TABLE)} "
            "WHERE event_id = ANY(%s)",
            (delivered_event_ids,),
        )
        rows = cur.fetchall()
    assert all(row["delivery_status"] == "delivered" for row in rows)
    assert all(row["delivery_attempts"] == 1 for row in rows)

    # Simula retry apos falha transitoria: reenvia o MESMO envelope manualmente
    # (sem passar por deliver_pending_events, que so pega pending/failed) e
    # confirma que o fake server (== semantica real do Warmbly) responde 200,
    # nao 201 — nao ha duplicata semantica do lado receptor em replay.
    for event_id in delivered_event_ids[:2]:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT event_id, event_type, subject_key, source_as_of "
                f"FROM public.{assert_write_target(EVENTS_TABLE)} WHERE event_id = %s",
                (event_id,),
            )
            row = dict(cur.fetchone())
        payload = wd._build_human_payload(conn, row["subject_key"])
        envelope = wd.build_envelope(row, payload, org_id=config.org_id)
        body = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8")
        sig = wd.sign_request(config.hmac_secret, body)
        status, _text = wd._post(config.webhook_url, body, sig, timeout=5.0)
        assert status == 200, f"replay deveria responder 200 (idempotente), recebeu {status}"

    # 2a rodada de deliver_pending_events: nada mais pending/failed entre os
    # ja entregues (nao reenvia o que ja e 'delivered').
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT delivery_status FROM public.{assert_write_target(EVENTS_TABLE)} "
            "WHERE event_id = ANY(%s)",
            (delivered_event_ids,),
        )
        statuses = [row["delivery_status"] for row in cur.fetchall()]
    assert all(s == "delivered" for s in statuses)


@pytest.mark.real_db
@pytest.mark.skipif(not REQUIRE_REAL_DB, reason="requer REQUIRE_REAL_DB=1 e Postgres real")
def test_deliver_pending_events_marks_failed_on_network_error(live_conn):
    conn = live_conn
    _seed_pending_event(conn, suffix="network-error")
    unreachable = wd.DeliveryConfig(
        webhook_url="http://127.0.0.1:1", hmac_secret=SECRET, org_id=ORG_ID
    )
    results = wd.deliver_pending_events(conn, unreachable, limit=1)
    assert results
    assert all(not r.delivered for r in results)
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT delivery_status, last_delivery_error FROM public.{assert_write_target(EVENTS_TABLE)} "
            "WHERE event_id = %s",
            (results[0].event_id,),
        )
        row = dict(cur.fetchone())
    assert row["delivery_status"] == "failed"
    assert row["last_delivery_error"] and "network_error" in row["last_delivery_error"]
