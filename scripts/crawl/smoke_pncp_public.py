"""PNCP public API smoke probe — Extra Consultoria.

Performs a single anonymous GET against PNCP /contratos (tiny page),
prints status + count, and writes docs/ops/discovery/pncp-smoke.json.

Usage::

    python scripts/crawl/smoke_pncp_public.py
    python -m scripts.crawl.smoke_pncp_public

No secrets. Rate-limited. Timeout 20s.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.crawl.security import USER_AGENT, validate_url_scheme  # noqa: E402

# Defaults match contracts_crawler; overridable via env in that module.
PNCP_CONSULTA_BASE = "https://pncp.gov.br/api/consulta/v1"
DEFAULT_TIMEOUT_S = 20
# PNCP rejects tamanhoPagina=1 on /contratos ("Tamanho de página inválido").
# /contratacoes/publicacao requires >= 10. Use 10 for a minimal valid probe.
DEFAULT_PAGE_SIZE = 10
DEFAULT_WINDOW_DAYS = 7
REQUEST_SLEEP_S = 1.0
OUTPUT_PATH = _PROJECT_ROOT / "docs" / "ops" / "discovery" / "pncp-smoke.json"


def _fmt_ymd(d: date) -> str:
    return d.strftime("%Y%m%d")


def build_contratos_url(
    *,
    base: str = PNCP_CONSULTA_BASE,
    data_inicial: str,
    data_final: str,
    pagina: int = 1,
    tamanho_pagina: int = DEFAULT_PAGE_SIZE,
) -> str:
    """Build PNCP /contratos query URL (public, anonymous)."""
    q = (
        f"dataInicial={data_inicial}"
        f"&dataFinal={data_final}"
        f"&pagina={pagina}"
        f"&tamanhoPagina={tamanho_pagina}"
    )
    return f"{base.rstrip('/')}/contratos?{q}"


def uf_from_unidade(item: dict[str, Any]) -> str | None:
    """Extract UF from PNCP contract item unidadeOrgao (never default)."""
    unidade = item.get("unidadeOrgao") or {}
    if not isinstance(unidade, dict):
        return None
    uf = (unidade.get("ufSigla") or "").strip().upper()
    return uf[:2] if uf else None


def filter_items_by_uf(items: list[dict[str, Any]], uf: str) -> list[dict[str, Any]]:
    """Client-side UF filter (server-side UF filter on /contratos is unreliable)."""
    target = uf.upper().strip()
    out: list[dict[str, Any]] = []
    for it in items:
        item_uf = uf_from_unidade(it)
        if item_uf and item_uf == target:
            out.append(it)
    return out


def fetch_contratos_page(
    *,
    data_inicial: str,
    data_final: str,
    pagina: int = 1,
    tamanho_pagina: int = DEFAULT_PAGE_SIZE,
    base: str = PNCP_CONSULTA_BASE,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    opener: Any | None = None,
) -> dict[str, Any]:
    """GET one page of /contratos. Returns structured smoke result dict.

    ``opener`` is injectable for unit tests (callable url -> http response-like
    object with .status, .read(), .headers, or a custom fetch function).
    """
    url = build_contratos_url(
        base=base,
        data_inicial=data_inicial,
        data_final=data_final,
        pagina=pagina,
        tamanho_pagina=tamanho_pagina,
    )
    started = time.time()
    result: dict[str, Any] = {
        "ok": False,
        "url": url,
        "http_status": None,
        "error": None,
        "count": 0,
        "total_registros": None,
        "total_paginas": None,
        "sample_uf": None,
        "sc_in_page": 0,
        "elapsed_s": None,
        "probed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "window": {"data_inicial": data_inicial, "data_final": data_final},
        "page_size": tamanho_pagina,
        "page": pagina,
    }

    try:
        validate_url_scheme(url)
        if opener is not None:
            # Test double: callable returning (status, body_bytes) or response-like
            raw = opener(url)
            if isinstance(raw, tuple):
                status, body = raw[0], raw[1]
            else:
                status = getattr(raw, "status", 200)
                body = raw.read() if hasattr(raw, "read") else raw
                if isinstance(body, str):
                    body = body.encode("utf-8")
        else:
            req = urllib.request.Request(url)  # noqa: S310 — scheme validated
            req.add_header("User-Agent", USER_AGENT)
            req.add_header("Accept", "application/json")
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:  # noqa: S310
                status = resp.status
                body = resp.read()

        result["http_status"] = int(status)
        text = body.decode("utf-8", errors="replace") if isinstance(body, (bytes, bytearray)) else str(body)
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            result["error"] = f"JSON parse error: {exc}"
            result["elapsed_s"] = round(time.time() - started, 3)
            return result

        if not isinstance(data, dict):
            result["error"] = f"Unexpected payload type: {type(data).__name__}"
            result["elapsed_s"] = round(time.time() - started, 3)
            return result

        if result["http_status"] >= 400:
            result["error"] = data.get("message") or data.get("error") or text[:200]
            result["elapsed_s"] = round(time.time() - started, 3)
            return result

        items = data.get("data") or []
        if not isinstance(items, list):
            items = []

        result["ok"] = True
        result["count"] = len(items)
        result["total_registros"] = data.get("totalRegistros")
        result["total_paginas"] = data.get("totalPaginas")
        if items:
            result["sample_uf"] = uf_from_unidade(items[0])
            result["sc_in_page"] = len(filter_items_by_uf(items, "SC"))
            # Keep a tiny redacted sample (ids only)
            result["sample_ids"] = [
                (it.get("numeroControlePNCP") or "")[:40] for it in items[:3]
            ]
        result["elapsed_s"] = round(time.time() - started, 3)
        return result

    except urllib.error.HTTPError as exc:
        result["http_status"] = exc.code
        try:
            err_body = exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            err_body = str(exc)
        result["error"] = err_body
        result["elapsed_s"] = round(time.time() - started, 3)
        return result
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["elapsed_s"] = round(time.time() - started, 3)
        return result


def run_smoke(
    *,
    write_output: bool = True,
    output_path: Path | None = None,
    opener: Any | None = None,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> dict[str, Any]:
    """Execute one-page public smoke and optionally persist JSON artifact."""
    end = date.today()
    start = end - timedelta(days=window_days)
    result = fetch_contratos_page(
        data_inicial=_fmt_ymd(start),
        data_final=_fmt_ymd(end),
        opener=opener,
    )
    result["source"] = "pncp_consulta_contratos"
    result["base"] = PNCP_CONSULTA_BASE

    if write_output:
        path = output_path or OUTPUT_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result["output_path"] = str(path)

    return result


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    _ = argv  # reserved for future flags
    print("PNCP public smoke — GET /contratos (1 page, anonymous)")
    result = run_smoke(write_output=True)
    print(f"  ok={result.get('ok')} http={result.get('http_status')} count={result.get('count')}")
    print(
        f"  totalRegistros={result.get('total_registros')} "
        f"sample_uf={result.get('sample_uf')} sc_in_page={result.get('sc_in_page')}"
    )
    if result.get("error"):
        print(f"  error={result['error'][:200]}")
    if result.get("output_path"):
        print(f"  wrote {result['output_path']}")
    # Be polite even for single-shot smoke
    time.sleep(REQUEST_SLEEP_S)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
