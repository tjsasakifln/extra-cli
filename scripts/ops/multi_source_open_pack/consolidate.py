"""Deduplicação e consolidação em processo canônico."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from collections.abc import Iterable

from scripts.ops.multi_source_open_pack.models import CanonicalProcess, ProcessDocument, SourceObservation
from scripts.ops.multi_source_open_pack.textutil import (
    cnpj8,
    days_remaining,
    norm,
    parse_datetime,
    utc_now,
)


def _pncp_control(obs: SourceObservation) -> str | None:
    # 14digits-1-000047/2026
    rid = obs.id_externo or ""
    if re.match(r"^\d{14}-\d+-\d+/\d{4}$", rid):
        return rid
    raw = obs.raw or {}
    for k in ("numero_controle_pncp", "pncp_id"):
        v = str(raw.get(k) or "")
        if re.match(r"^\d{14}-\d+-\d+/\d{4}$", v):
            return v
    # extract from URL
    m = re.search(r"/editais/(\d{14})/(\d{4})/(\d+)", obs.url or "")
    if m:
        return f"{m.group(1)}-1-{int(m.group(3)):06d}/{m.group(2)}"
    return None


def _process_year_num(obs: SourceObservation) -> str | None:
    rid = obs.id_externo or ""
    m = re.search(r"(\d{1,6})\s*/\s*(\d{4})", rid)
    if m:
        return f"{int(m.group(1))}/{m.group(2)}"
    m2 = re.search(r"(\d{4}).{0,5}(\d{1,6})", rid)
    blob = norm(obs.objeto) + " " + norm(obs.modalidade)
    m3 = re.search(r"(?:pregao|concorrencia|edital|processo)\s*(?:n|no|numero)?\s*(\d+)\s*/\s*(\d{4})", blob)
    if m3:
        return f"{int(m3.group(1))}/{m3.group(2)}"
    if m2 and len(rid) > 8:
        return None
    return None


def _fingerprint(obs: SourceObservation) -> str:
    parts = [
        cnpj8(obs.orgao_cnpj) or norm(obs.orgao)[:40],
        norm(obs.municipio),
        norm(obs.objeto)[:120],
        (obs.data_encerramento or "")[:10],
        str(obs.valor_estimado or ""),
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def merge_key_for(obs: SourceObservation) -> tuple[str, str, float]:
    """Return (merge_key, method, confidence) in priority order."""
    pncp = _pncp_control(obs)
    if pncp:
        return f"pncp:{pncp}", "numero_controle_pncp", 1.0

    c8 = cnpj8(obs.orgao_cnpj)
    py = _process_year_num(obs)
    if c8 and py:
        return f"org_proc:{c8}:{py}", "cnpj_processo_ano", 0.95

    if obs.fonte and obs.id_externo:
        # platform id — only same source for merge key base; cross-source via pncp/process
        return f"plat:{obs.fonte}:{obs.id_externo}", "platform_id", 0.85

    if c8 and obs.modalidade and obs.objeto:
        key = f"comp:{c8}:{norm(obs.modalidade)[:20]}:{norm(obs.objeto)[:80]}"
        return key, "orgao_modalidade_objeto", 0.7

    fp = _fingerprint(obs)
    return f"fp:{fp}", "content_fingerprint", 0.55


def _pick_best_url(urls: list[str]) -> str:
    def score(u: str) -> tuple[int, int]:
        ul = u.lower()
        s = 0
        if "pncp.gov.br/app/editais/" in ul:
            s += 100
        elif "pncp.gov.br" in ul:
            s += 40
        if "/pesquisa" in ul or "search" in ul:
            s -= 20
        if ul.startswith("http"):
            s += 5
        return (s, len(u))

    valid = [u for u in urls if u and u.startswith("http")]
    if not valid:
        return urls[0] if urls else ""
    return sorted(valid, key=score, reverse=True)[0]


def _is_specific_official_url(url: str) -> bool:
    from scripts.ops.multi_source_open_pack.documents import is_specific_official_url

    return is_specific_official_url(url)


def _soft_cluster_key(obs: SourceObservation) -> str | None:
    """Secondary deterministic key: org + value + deadline date + object head."""
    c8 = cnpj8(obs.orgao_cnpj)
    if not c8:
        return None
    if obs.valor_estimado is None:
        return None
    enc = (obs.data_encerramento or "")[:10]
    if not enc:
        return None
    obj = norm(obs.objeto)[:80]
    if len(obj) < 20:
        return None
    return f"soft:{c8}:{obs.valor_estimado:.2f}:{enc}:{obj}"


def consolidate_observations(
    observations: Iterable[SourceObservation],
    *,
    now=None,
) -> tuple[list[CanonicalProcess], int]:
    """Merge observations into canonical processes. Returns (processes, merge_count)."""
    now = now or utc_now()
    groups: dict[str, list[tuple[SourceObservation, str, float]]] = defaultdict(list)

    # First pass: assign keys; also secondary index by pncp extracted from URL across sources
    pncp_index: dict[str, str] = {}  # pncp_id -> merge_key
    soft_index: dict[str, str] = {}  # soft key -> merge_key

    prepared: list[tuple[SourceObservation, str, str, float]] = []
    for obs in observations:
        key, method, conf = merge_key_for(obs)
        pncp = _pncp_control(obs)
        if pncp:
            if pncp in pncp_index:
                key = pncp_index[pncp]
                method = "numero_controle_pncp"
                conf = 1.0
            else:
                pncp_index[pncp] = key
        soft = _soft_cluster_key(obs)
        if soft and soft in soft_index:
            key = soft_index[soft]
            method = "orgao_valor_prazo_objeto"
            conf = max(conf, 0.75)
        elif soft:
            soft_index[soft] = key
        prepared.append((obs, key, method, conf))

    # Second pass: unify via pncp / soft keys after full index built
    # rebuild soft/pncp with final keys
    pncp_index.clear()
    soft_index.clear()
    for obs, key, method, conf in prepared:
        pncp = _pncp_control(obs)
        if pncp:
            pncp_index.setdefault(pncp, key)
        soft = _soft_cluster_key(obs)
        if soft:
            soft_index.setdefault(soft, key)

    for obs, key, method, conf in prepared:
        pncp = _pncp_control(obs)
        if pncp and pncp in pncp_index:
            key = pncp_index[pncp]
            method = "numero_controle_pncp"
            conf = 1.0
        else:
            soft = _soft_cluster_key(obs)
            if soft and soft in soft_index:
                key = soft_index[soft]
                if method != "numero_controle_pncp":
                    method = "orgao_valor_prazo_objeto"
                    conf = max(conf, 0.75)
        groups[key].append((obs, method, conf))

    processes: list[CanonicalProcess] = []
    merges = 0

    for key, items in groups.items():
        if len(items) > 1:
            merges += len(items) - 1
        items_sorted = sorted(
            items,
            key=lambda t: (
                0 if t[0].fonte == "pncp" else 1,
                0 if t[0].is_active_dispute else 1,
                t[0].data_encerramento or "",
            ),
        )
        primary = items_sorted[0][0]
        method = max(items_sorted, key=lambda t: t[2])[1]
        conf = max(t[2] for t in items_sorted)

        fontes = sorted({t[0].fonte for t in items_sorted})
        oids = [t[0].observation_id for t in items_sorted]
        urls = []
        for t in items_sorted:
            if t[0].url:
                urls.append(t[0].url)
        url_oficial = _pick_best_url(urls)

        # Recompute status: any terminal kills open; any active dispute keeps open if deadline ok
        event_types = sorted({t[0].event_type for t in items_sorted})
        any_terminal = any(
            not t[0].is_active_dispute and t[0].event_type
            in {
                "contrato",
                "extrato_contrato",
                "homologacao",
                "adjudicacao",
                "resultado",
                "publicacao_terminal",
                "rescisao",
                "revogacao",
                "anulacao",
            }
            for t in items_sorted
        )
        any_active = any(t[0].is_active_dispute for t in items_sorted)
        # If only terminal publications, not open
        is_active = any_active and not (any_terminal and not any_active)

        # Prefer observation with longest object / best cnpj
        best_obj = max(items_sorted, key=lambda t: len(t[0].objeto or ""))[0]
        best_cnpj = next((t[0] for t in items_sorted if t[0].orgao_cnpj), primary)

        # deadline: latest non-empty encerramento among active
        deadline_raw = ""
        for t in items_sorted:
            if t[0].data_encerramento:
                deadline_raw = t[0].data_encerramento
                break
        # prefer max deadline among those with values
        deadlines = [parse_datetime(t[0].data_encerramento) for t in items_sorted if t[0].data_encerramento]
        deadlines = [d for d in deadlines if d is not None]
        deadline_dt = max(deadlines) if deadlines else parse_datetime(deadline_raw)

        cal, biz, still_open = days_remaining(deadline_dt, now)
        # PNCP/SC without deadline: trust is_active_dispute only if fonte says open
        if deadline_dt is None:
            still_open = is_active and primary.fonte in {"pncp", "sc_compras"}
            if not still_open and is_active:
                # open claim without deadline stays unknown, not shortlistable as open
                status = "unknown"
            elif still_open:
                status = "open"
            else:
                status = "terminal" if any_terminal else "unknown"
        else:
            if not still_open:
                status = "expired"
                is_active = False
            elif is_active:
                status = "open"
            else:
                status = "terminal" if any_terminal else "unknown"

        in_uni = any(t[0].in_universe for t in items_sorted)
        match = next((t[0].match_universo for t in items_sorted if t[0].in_universe), primary.match_universo)
        dist = next((t[0].distance_km for t in items_sorted if t[0].distance_km is not None), None)
        dist_method = next(
            (t[0].distance_method for t in items_sorted if t[0].distance_method),
            "",
        )
        entity_key = next((t[0].entity_key for t in items_sorted if t[0].entity_key), "")

        docs: list[ProcessDocument] = []
        if url_oficial:
            docs.append(
                ProcessDocument(
                    doc_type="pagina_oficial",
                    title="Página oficial do processo",
                    url=url_oficial,
                    fonte=primary.fonte,
                    published_at=primary.data_publicacao,
                    download_status="linked_not_downloaded",
                    parse_status="not_parsed",
                )
            )
        for t in items_sorted:
            u = t[0].url
            if u and u != url_oficial:
                docs.append(
                    ProcessDocument(
                        doc_type="observacao_fonte",
                        title=f"Publicação {t[0].fonte}",
                        url=u,
                        fonte=t[0].fonte,
                        published_at=t[0].data_publicacao,
                        download_status="linked_not_downloaded",
                        parse_status="not_parsed",
                    )
                )

        excl = ""
        if not is_active:
            excl = primary.exclusion_reason or "sem_disputa_ativa"
        if status == "expired":
            excl = "prazo_encerrado"

        layer = "decision" if in_uni else "secondary_reference"

        pid = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
        processes.append(
            CanonicalProcess(
                process_id=pid,
                merge_key=key,
                merge_method=method,
                merge_confidence=conf,
                fontes=fontes,
                observation_ids=oids,
                id_externo_principal=primary.id_externo,
                orgao=best_obj.orgao or primary.orgao,
                orgao_cnpj=best_cnpj.orgao_cnpj,
                municipio=best_obj.municipio or primary.municipio,
                uf=primary.uf or "SC",
                objeto=best_obj.objeto,
                modalidade=primary.modalidade,
                valor_estimado=next(
                    (t[0].valor_estimado for t in items_sorted if t[0].valor_estimado is not None),
                    None,
                ),
                data_publicacao=primary.data_publicacao,
                data_encerramento=deadline_raw or (deadline_dt.isoformat() if deadline_dt else ""),
                deadline_dt=deadline_dt,
                url_oficial=url_oficial,
                urls_all=list(dict.fromkeys(urls)),
                status_processo=status,
                event_types=event_types,
                is_active_dispute=bool(is_active and status == "open"),
                in_universe=in_uni,
                match_universo=match,
                distance_km=dist,
                distance_method=dist_method
                or ("universe_seed_geodesic_from_florianopolis" if dist is not None else ""),
                entity_key=entity_key,
                calendar_days_remaining=cal,
                business_days_remaining=biz,
                documents=docs,
                layer=layer,
                observations_count=len(items_sorted),
                exclusion_reason=excl,
                official_page_validated=_is_specific_official_url(url_oficial),
                docs_inventory_status="urls_linked_only",
            )
        )

    return processes, merges
