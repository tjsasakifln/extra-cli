"""Sprint 2 Parte 13: enriquecimento de fornecedores com APIs publicas externas.

Fluxo diario (08:00 UTC, apos contracts crawl):
  1. Busca CNPJs unicos em pncp_supplier_contracts nao enriquecidos ha 30+ dias
  2. Para cada CNPJ: chama BrasilAPI /cnpj/v1/{cnpj}
  3. Upsert resultado em enriched_entities (entity_type='fornecedor')

Throttle: semaforo asyncio(10) — no maximo 10 chamadas concorrentes.
Taxa BrasilAPI: sem rate limit documentado; CDN 23 regioes.
Taxa Portal da Transparencia: 90 req/min (6h-23h59). Reservado para fases futuras.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_BRASILAPI_BASE = "https://brasilapi.com.br/api"
_ENRICH_STALENESS_DAYS = 30
_BATCH_SIZE = 500         # CNPJs por lote de busca no Supabase
_MAX_CNPJS_PER_RUN = 5000 # teto de seguranca por execucao
_HTTP_TIMEOUT = 10.0      # segundos por requisicao externa
_CONCURRENCY = 10         # requisicoes paralelas maximas


async def enrich_entities_job() -> dict[str, Any]:
    """Entry point do job ARQ.

    Enriquece fornecedores nao atualizados ha mais de _ENRICH_STALENESS_DAYS dias.
    Retorna: {enriched, skipped, failed, total_fetched, duration_s}
    """
    start = time.monotonic()

    try:
        stale = await _fetch_stale_fornecedores()
    except Exception as e:
        logger.error("[Enricher] Falha ao buscar CNPJs para enriquecer: %s", e, exc_info=True)
        return {"status": "failed", "error": str(e), "duration_s": round(time.monotonic() - start, 1)}

    if not stale:
        logger.info("[Enricher] Nenhum CNPJ desatualizado encontrado — job encerrado.")
        return {"status": "completed", "enriched": 0, "skipped": 0, "failed": 0,
                "total_fetched": 0, "duration_s": round(time.monotonic() - start, 1)}

    logger.info("[Enricher] %d CNPJs para enriquecer", len(stale))

    sem = asyncio.Semaphore(_CONCURRENCY)
    tasks = [_enrich_one_fornecedor(cnpj, sem) for cnpj in stale]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    records: list[dict] = []
    enriched = 0
    failed = 0
    skipped = 0

    for cnpj, res in zip(stale, results):
        if isinstance(res, Exception):
            logger.warning("[Enricher] CNPJ %s falhou: %s", cnpj, res)
            failed += 1
        elif res is None:
            skipped += 1
        else:
            records.append(res)
            enriched += 1

    if records:
        try:
            await _upsert_batch(records)
        except Exception as e:
            logger.error("[Enricher] Falha no upsert batch: %s", e, exc_info=True)
            # Nao propaga — resultado parcial e melhor que zero

    duration_s = round(time.monotonic() - start, 1)
    logger.info(
        "[Enricher] Concluido em %.1fs — enriquecidos=%d, ignorados=%d, falhas=%d",
        duration_s, enriched, skipped, failed,
    )
    return {
        "status": "completed",
        "enriched": enriched,
        "skipped": skipped,
        "failed": failed,
        "total_fetched": len(stale),
        "duration_s": duration_s,
    }


async def _fetch_stale_fornecedores() -> list[str]:
    """Retorna CNPJs unicos de pncp_supplier_contracts que precisam de enriquecimento.

    Criterio de staleness: sem registro em enriched_entities OU enriched_at
    mais antigo que _ENRICH_STALENESS_DAYS dias.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=_ENRICH_STALENESS_DAYS)
    cutoff_iso = cutoff.isoformat()

    from supabase_client import get_supabase, sb_execute
    sb = get_supabase()

    # Passo 1: CNPJs distintos no datalake de contratos (is_active=true)
    cnpj_set: set[str] = set()
    offset = 0
    while len(cnpj_set) < _MAX_CNPJS_PER_RUN:
        resp = await sb_execute(
            sb.table("pncp_supplier_contracts")
            .select("ni_fornecedor")
            .eq("is_active", True)
            .not_.is_("ni_fornecedor", "null")
            .neq("ni_fornecedor", "")
            .range(offset, offset + _BATCH_SIZE - 1)
        )
        rows = resp.data or []
        if not rows:
            break
        for row in rows:
            ni = (row.get("ni_fornecedor") or "").strip()
            if ni and len(ni) == 14 and ni.isdigit():
                cnpj_set.add(ni)
        if len(rows) < _BATCH_SIZE:
            break
        offset += _BATCH_SIZE

    if not cnpj_set:
        return []

    # Passo 2: quais ja foram enriquecidos recentemente?
    fresh_cnpjs: set[str] = set()
    cnpj_list = list(cnpj_set)
    for i in range(0, len(cnpj_list), _BATCH_SIZE):
        chunk = cnpj_list[i:i + _BATCH_SIZE]
        resp = await sb_execute(
            sb.table("enriched_entities")
            .select("entity_id, enriched_at")
            .eq("entity_type", "fornecedor")
            .in_("entity_id", chunk)
            .gte("enriched_at", cutoff_iso)
        )
        for row in (resp.data or []):
            fresh_cnpjs.add(row["entity_id"])

    stale = [cnpj for cnpj in cnpj_list if cnpj not in fresh_cnpjs]
    return stale[:_MAX_CNPJS_PER_RUN]


async def _enrich_one_fornecedor(cnpj: str, sem: asyncio.Semaphore) -> dict | None:
    """Busca dados cadastrais de um CNPJ na BrasilAPI.

    Retorna dict pronto para upsert em enriched_entities, ou None se nao encontrado.
    Levanta excecao em caso de erro de rede (sera capturada pelo gather).
    """
    async with sem:
        url = f"{_BRASILAPI_BASE}/cnpj/v1/{cnpj}"
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.get(url, follow_redirects=True)

        if resp.status_code == 404:
            return None  # CNPJ nao encontrado — ignorar silenciosamente

        if resp.status_code != 200:
            raise RuntimeError(f"BrasilAPI retornou HTTP {resp.status_code} para CNPJ {cnpj}")

        raw = resp.json()

    # Normaliza campos relevantes para as paginas de fornecedores
    data = {
        "razao_social": raw.get("razao_social") or raw.get("nome") or "",
        "nome_fantasia": raw.get("nome_fantasia") or "",
        "cnae_fiscal": raw.get("cnae_fiscal") or "",
        "cnae_fiscal_descricao": raw.get("cnae_fiscal_descricao") or "",
        "natureza_juridica": raw.get("natureza_juridica") or "",
        "porte": raw.get("porte") or "",
        "simples_nacional": bool(raw.get("opcao_pelo_simples")),
        "mei": bool(raw.get("opcao_pelo_mei")),
        "situacao_cadastral": raw.get("descricao_situacao_cadastral") or "",
        "data_situacao_cadastral": raw.get("data_situacao_cadastral") or "",
        "data_abertura": raw.get("data_inicio_atividade") or "",
        "municipio": raw.get("municipio") or "",
        "uf": raw.get("uf") or "",
        "cep": raw.get("cep") or "",
        "logradouro": raw.get("logradouro") or "",
        "numero": raw.get("numero") or "",
        "bairro": raw.get("bairro") or "",
        "email": raw.get("email") or "",
        "telefone": raw.get("telefone") or "",
        "capital_social": _safe_capital(raw.get("capital_social")),
        "qsa_count": len(raw.get("qsa") or []),
        "source": "brasilapi",
        "source_updated_at": datetime.now(timezone.utc).isoformat(),
    }

    return {
        "entity_type": "fornecedor",
        "entity_id": cnpj,
        "data": data,
        "enriched_at": datetime.now(timezone.utc).isoformat(),
    }


async def _upsert_batch(records: list[dict]) -> None:
    """Upsert de registros em enriched_entities via Supabase.

    Usa upsert com on_conflict=(entity_type, entity_id) para idempotencia.
    """
    from supabase_client import get_supabase, sb_execute
    sb = get_supabase()

    # Chunk para evitar payloads muito grandes (Supabase limite ~1MB por request)
    chunk_size = 200
    for i in range(0, len(records), chunk_size):
        chunk = records[i:i + chunk_size]
        await sb_execute(
            sb.table("enriched_entities").upsert(
                chunk,
                on_conflict="entity_type,entity_id",
            ),
            category="write",
        )
        logger.debug("[Enricher] Upsert de %d registros concluido", len(chunk))


def _safe_capital(val: Any) -> float:
    """Converte capital_social da BrasilAPI (pode ser string com virgula) para float."""
    if val is None:
        return 0.0
    try:
        # BrasilAPI retorna strings como "1232000,00"
        return float(str(val).replace(",", ".").replace(" ", ""))
    except (ValueError, TypeError):
        return 0.0


# ---------------------------------------------------------------------------
# Sprint 4 Parte 13: enriquecimento de municipios com dados IBGE
# ---------------------------------------------------------------------------

# Municipios seed (ibge_code → slug) — subconjunto das capitais + polos regionais
_IBGE_SEED: list[tuple[str, str]] = [
    ("3550308", "sao-paulo-sp"),
    ("3304557", "rio-de-janeiro-rj"),
    ("5300108", "brasilia-df"),
    ("2927408", "salvador-ba"),
    ("2304400", "fortaleza-ce"),
    ("3106200", "belo-horizonte-mg"),
    ("1302603", "manaus-am"),
    ("4106902", "curitiba-pr"),
    ("2611606", "recife-pe"),
    ("4314902", "porto-alegre-rs"),
    ("1501402", "belem-pa"),
    ("5208707", "goiania-go"),
    ("2111300", "sao-luis-ma"),
    ("2704302", "maceio-al"),
    ("2408102", "natal-rn"),
    ("2211001", "teresina-pi"),
    ("5002704", "campo-grande-ms"),
    ("2507507", "joao-pessoa-pb"),
    ("2800308", "aracaju-se"),
    ("1100205", "porto-velho-ro"),
    ("1600303", "macapa-ap"),
    ("5103403", "cuiaba-mt"),
    ("4205407", "florianopolis-sc"),
    ("3205309", "vitoria-es"),
    ("1721000", "palmas-to"),
    ("1200401", "rio-branco-ac"),
    ("1400100", "boa-vista-rr"),
    ("3509502", "campinas-sp"),
    ("3518800", "guarulhos-sp"),
    ("3543402", "ribeirao-preto-sp"),
    ("3170206", "uberlandia-mg"),
    ("4209102", "joinville-sc"),
    ("4202404", "blumenau-sc"),
    ("4113700", "londrina-pr"),
    ("4115200", "maringa-pr"),
    ("5107602", "rondonopolis-mt"),
    ("2504009", "campina-grande-pb"),
    ("2307304", "juazeiro-do-norte-ce"),
    ("2312908", "sobral-ce"),
    ("4313409", "novo-hamburgo-rs"),
    ("4316907", "santa-maria-rs"),
    ("4314407", "passo-fundo-rs"),
    ("4304606", "canoas-rs"),
    ("3106705", "betim-mg"),
    ("3143302", "montes-claros-mg"),
    ("3131307", "ipatinga-mg"),
    ("3303302", "niteroi-rj"),
    ("3301702", "duque-de-caxias-rj"),
    ("3303500", "nova-iguacu-rj"),
    ("2910800", "feira-de-santana-ba"),
    ("5201405", "anapolis-go"),
    ("5218805", "rio-verde-go"),
    ("2105302", "imperatriz-ma"),
    ("1506807", "santarem-pa"),
    ("1500800", "ananindeua-pa"),
    ("1504208", "maraba-pa"),
]

_IBGE_API_BASE = "https://servicodados.ibge.gov.br/api"
_MUNICIPIO_STALENESS_DAYS = 30
_MUNICIPIO_HTTP_TIMEOUT = 10.0
_MUNICIPIO_CONCURRENCY = 5


async def enrich_municipios_job() -> dict[str, Any]:
    """Enriquece municipios da seed list com dados IBGE (populacao + nome oficial).

    Sprint 4 Parte 13: popula enriched_entities para habilitar paginas
    /municipios/{slug} com populacao, PIB per capita e nome oficial IBGE.

    Criterio de staleness: 30 dias sem enriquecimento.
    """
    start = time.monotonic()
    logger.info("[EnricherMunicipio] Iniciando enriquecimento de %d municipios", len(_IBGE_SEED))

    cutoff = datetime.now(timezone.utc) - timedelta(days=_MUNICIPIO_STALENESS_DAYS)
    cutoff_iso = cutoff.isoformat()

    # Quais ja foram enriquecidos recentemente?
    from supabase_client import get_supabase, sb_execute
    sb = get_supabase()

    ibge_codes = [s[0] for s in _IBGE_SEED]
    fresh: set[str] = set()
    try:
        resp = await sb_execute(
            sb.table("enriched_entities")
            .select("entity_id, enriched_at")
            .eq("entity_type", "municipio")
            .in_("entity_id", ibge_codes)
            .gte("enriched_at", cutoff_iso)
        )
        for row in (resp.data or []):
            fresh.add(row["entity_id"])
    except Exception as e:
        logger.warning("[EnricherMunicipio] Falha ao checar freshness: %s", e)

    stale = [(code, slug) for code, slug in _IBGE_SEED if code not in fresh]
    if not stale:
        logger.info("[EnricherMunicipio] Nenhum municipio desatualizado — job encerrado.")
        return {
            "status": "completed", "enriched": 0, "skipped": len(_IBGE_SEED),
            "failed": 0, "duration_s": round(time.monotonic() - start, 1),
        }

    logger.info("[EnricherMunicipio] %d municipios para enriquecer", len(stale))

    sem = asyncio.Semaphore(_MUNICIPIO_CONCURRENCY)
    tasks = [_enrich_one_municipio(code, slug, sem) for code, slug in stale]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    records: list[dict] = []
    enriched = 0
    failed = 0

    for (code, slug), res in zip(stale, results):
        if isinstance(res, Exception):
            logger.warning("[EnricherMunicipio] Municipio %s falhou: %s", code, res)
            failed += 1
        elif res is None:
            failed += 1
        else:
            records.append(res)
            enriched += 1

    if records:
        try:
            await _upsert_batch(records)
        except Exception as e:
            logger.error("[EnricherMunicipio] Falha no upsert batch: %s", e, exc_info=True)

    duration_s = round(time.monotonic() - start, 1)
    logger.info(
        "[EnricherMunicipio] Concluido em %.1fs — enriquecidos=%d, falhas=%d",
        duration_s, enriched, failed,
    )
    return {
        "status": "completed",
        "enriched": enriched,
        "skipped": len(_IBGE_SEED) - len(stale),
        "failed": failed,
        "total_fetched": len(stale),
        "duration_s": duration_s,
    }


async def _enrich_one_municipio(ibge_code: str, slug: str, sem: asyncio.Semaphore) -> dict | None:
    """Busca dados de um municipio no IBGE e monta registro para enriched_entities."""
    async with sem:
        async with httpx.AsyncClient(timeout=_MUNICIPIO_HTTP_TIMEOUT) as client:
            # Nome, UF e regiao
            r_local = await client.get(
                f"{_IBGE_API_BASE}/v1/localidades/municipios/{ibge_code}",
            )
            if r_local.status_code != 200:
                logger.debug(
                    "[EnricherMunicipio] IBGE municipio %s retornou %d",
                    ibge_code, r_local.status_code,
                )
                return None

            local_data = r_local.json()
            nome = local_data.get("nome") or ""
            uf = (local_data.get("microrregiao", {})
                  .get("mesorregiao", {})
                  .get("UF", {})
                  .get("sigla") or "")
            regiao = (local_data.get("microrregiao", {})
                      .get("mesorregiao", {})
                      .get("UF", {})
                      .get("regiao", {})
                      .get("nome") or "")

            # Populacao estimada (SIDRA agregado 1705, variavel 93)
            populacao: Optional[int] = None
            try:
                r_pop = await client.get(
                    f"{_IBGE_API_BASE}/v3/agregados/1705/periodos/2023/variaveis/93"
                    f"?localidades=N6[{ibge_code}]",
                )
                if r_pop.status_code == 200:
                    pop_data = r_pop.json()
                    if pop_data and isinstance(pop_data, list):
                        series = pop_data[0].get("resultados", [])
                        if series:
                            vals = series[0].get("series", [])
                            if vals:
                                serie_vals = vals[0].get("serie", {})
                                # Pega o valor mais recente disponivel
                                for _year in ["2023", "2022", "2021", "2020"]:
                                    v = serie_vals.get(_year)
                                    if v and v != "...":
                                        try:
                                            populacao = int(str(v).replace(".", "").replace(",", ""))
                                        except ValueError:
                                            pass
                                        break
            except Exception as e:
                logger.debug("[EnricherMunicipio] Populacao falhou para %s: %s", ibge_code, e)

    data = {
        "nome": nome,
        "slug": slug,
        "uf": uf,
        "regiao": regiao,
        "ibge_code": ibge_code,
        "populacao": populacao,
        "pib_per_capita": None,  # reservado para expansao futura (SIDRA 5938)
        "source": "ibge",
        "source_updated_at": datetime.now(timezone.utc).isoformat(),
    }

    return {
        "entity_type": "municipio",
        "entity_id": ibge_code,
        "data": data,
        "enriched_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# IBGE code enricher for pncp_raw_bids.codigo_municipio_ibge
# ---------------------------------------------------------------------------
# The PNCP API does NOT return codigoMunicipioIbge in its response payload,
# so pncp_raw_bids.codigo_municipio_ibge is empty for 100% of rows.
# This enricher resolves (municipio_name, uf) → IBGE code via the IBGE
# localidades API and backfills the column so municipio-profile queries
# (.eq("codigo_municipio_ibge", ...)) can work without the name fallback.

_IBGE_MUNICIPIOS_CACHE: dict[tuple[str, str], str] = {}
_IBGE_MUNICIPIOS_CACHE_TS: float = 0.0
_IBGE_MUNICIPIOS_CACHE_TTL = 7 * 24 * 3600  # 7 days — municipios change rarely


async def _fetch_ibge_municipio_lookup() -> dict[tuple[str, str], str]:
    """Fetch full IBGE municipios list and build (nome_lower, uf) → codigo mapping.

    Uses a module-level cache with 7-day TTL because the 5,570+ municipio list
    changes only when new municipios are created (extremely rare).
    """
    global _IBGE_MUNICIPIOS_CACHE, _IBGE_MUNICIPIOS_CACHE_TS
    now = time.monotonic()
    if _IBGE_MUNICIPIOS_CACHE and (now - _IBGE_MUNICIPIOS_CACHE_TS) < _IBGE_MUNICIPIOS_CACHE_TTL:
        return _IBGE_MUNICIPIOS_CACHE

    logger.info("[EnricherIBGE] Fetching full municipios list from IBGE API...")
    lookup: dict[tuple[str, str], str] = {}

    # Simple retry with exponential backoff: 1s → 2s → 4s
    max_retries = 3
    last_error: str | None = None
    for attempt in range(max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"{_IBGE_API_BASE}/v1/localidades/municipios",
                    follow_redirects=True,
                )
                if resp.status_code != 200:
                    last_error = f"HTTP {resp.status_code}"
                    if attempt < max_retries:
                        delay = 2 ** attempt
                        logger.warning(
                            "[EnricherIBGE] IBGE API returned %d (attempt %d/%d) — retrying in %ds",
                            resp.status_code, attempt + 1, max_retries + 1, delay,
                        )
                        await asyncio.sleep(delay)
                        continue
                    logger.error(
                        "[EnricherIBGE] IBGE municipios API returned %d after %d attempts — using cached lookup",
                        resp.status_code, max_retries + 1,
                    )
                    return _IBGE_MUNICIPIOS_CACHE  # fallback to stale cache

                municipios = resp.json()
                break  # success — exit retry loop
        except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError) as e:
            last_error = str(e)
            if attempt < max_retries:
                delay = 2 ** attempt
                logger.warning(
                    "[EnricherIBGE] IBGE API request failed: %s (attempt %d/%d) — retrying in %ds",
                    e, attempt + 1, max_retries + 1, delay,
                )
                await asyncio.sleep(delay)
                continue
            logger.error(
                "[EnricherIBGE] IBGE API request failed after %d attempts: %s — using cached lookup",
                max_retries + 1, e,
            )
            return _IBGE_MUNICIPIOS_CACHE  # fallback to stale cache

        for m in municipios:
            nome = (m.get("nome") or "").strip().lower()
            uf = (
                (m.get("microrregiao") or {})
                .get("mesorregiao", {})
                .get("UF", {})
                .get("sigla") or ""
            ).strip().upper()
            codigo = str(m.get("id") or "")
            if nome and uf and codigo:
                lookup[(nome, uf)] = codigo

    _IBGE_MUNICIPIOS_CACHE = lookup
    _IBGE_MUNICIPIOS_CACHE_TS = now
    logger.info(
        "[EnricherIBGE] Municipios lookup built: %d entries (%.1f KB)",
        len(lookup), len(str(lookup)) / 1024,
    )
    return lookup


async def enrich_pncp_ibge_codes_job() -> dict[str, Any]:
    """ARQ job: backfill pncp_raw_bids.codigo_municipio_ibge from IBGE API.

    Resolves (municipio, uf) → codigo_municipio_ibge for rows where the
    column is empty. Runs as a scheduled ARQ cron after each crawl wave so
    newly ingested rows get backfilled promptly.

    Returns: {resolved, skipped, unmatched, duration_s}
    """
    start = time.monotonic()
    logger.info("[EnricherIBGE] Starting IBGE code backfill job")

    try:
        lookup = await _fetch_ibge_municipio_lookup()
    except Exception as e:
        logger.error("[EnricherIBGE] Failed to build lookup: %s", e, exc_info=True)
        return {"status": "failed", "error": str(e), "duration_s": round(time.monotonic() - start, 1)}

    if not lookup:
        logger.warning("[EnricherIBGE] Lookup empty — aborting backfill")
        return {"status": "failed", "error": "empty lookup", "duration_s": round(time.monotonic() - start, 1)}

    # Fetch distinct (municipio, uf) pairs with empty IBGE code
    from supabase_client import get_supabase, sb_execute
    sb = get_supabase()

    pairs: set[tuple[str, str]] = set()
    offset = 0
    batch_size = 1000
    while True:
        resp = await sb_execute(
            sb.table("pncp_raw_bids")
            .select("municipio, uf")
            .or_("codigo_municipio_ibge.is.null,codigo_municipio_ibge.eq.''")
            .eq("is_active", True)
            .range(offset, offset + batch_size - 1)
        )
        rows = resp.data or []
        if not rows:
            break
        for row in rows:
            nome = (row.get("municipio") or "").strip().lower()
            uf = (row.get("uf") or "").strip().upper()
            if nome and uf:
                pairs.add((nome, uf))
        if len(rows) < batch_size:
            break
        offset += batch_size

    if not pairs:
        logger.info("[EnricherIBGE] No rows with empty IBGE code — job done")
        return {
            "status": "completed", "resolved": 0, "skipped": 0,
            "unmatched": 0, "duration_s": round(time.monotonic() - start, 1),
        }

    # Resolve codes
    resolved = 0
    skipped = 0
    unmatched = 0
    updates: list[dict] = []

    for nome, uf in pairs:
        codigo = lookup.get((nome, uf))
        if codigo:
            updates.append({"municipio": nome, "uf": uf, "codigo": codigo})
            resolved += 1
        else:
            unmatched += 1
            if unmatched <= 20:
                logger.debug("[EnricherIBGE] No match for municipio=%r uf=%r", nome, uf)

    # Apply updates in batches via a single RPC call or batch UPDATE
    # Use a raw UPDATE for efficiency — 4000+ individual upserts would be too slow
    if updates:
        # Build a mapping table via JSONB and update in one pass
        try:
            mapping = [
                {"nome": u["municipio"], "uf": u["uf"], "codigo": u["codigo"]}
                for u in updates
            ]
            result = await sb_execute(
                sb.rpc(
                    "backfill_ibge_codes",
                    {"p_mapping": mapping},
                ),
                category="rpc",
            )
            actual_updated = result.data if result.data else 0
            if isinstance(actual_updated, list):
                actual_updated = actual_updated[0].get("rows_updated", resolved) if actual_updated else resolved
            logger.info(
                "[EnricherIBGE] Backfill RPC returned: %s (expected ~%d rows)",
                actual_updated, resolved,
            )
            resolved = actual_updated if isinstance(actual_updated, int) else resolved
        except Exception as e:
            logger.error("[EnricherIBGE] Backfill RPC failed: %s", e, exc_info=True)
            skipped = resolved
            resolved = 0

    duration_s = round(time.monotonic() - start, 1)
    logger.info(
        "[EnricherIBGE] Job done in %.1fs — resolved=%d, skipped=%d, unmatched=%d/%d",
        duration_s, resolved, skipped, unmatched, len(pairs),
    )
    return {
        "status": "completed",
        "resolved": resolved,
        "skipped": skipped,
        "unmatched": unmatched,
        "total_pairs": len(pairs),
        "duration_s": duration_s,
    }
