"""Inteligência de órgãos e concorrentes a partir do pack + API PNCP (quando viva)."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from scripts.ops.multi_source_open_pack.classify_aec import classify_aec
from scripts.ops.multi_source_open_pack.models import CanonicalProcess
from scripts.ops.multi_source_open_pack.textutil import cnpj8, digits_only, optional_float


@dataclass
class OrgHistory:
    orgao: str
    orgao_cnpj: str
    municipio: str
    source: str
    window_months: int
    n_processos_pack: int = 0
    n_aec_pack: int = 0
    n_contratos_api: int = 0
    n_aec_contratos: int = 0
    valor_total_estimado_pack: float = 0.0
    valor_contratado_api: float = 0.0
    ticket_medio: float | None = None
    modalidades: dict[str, int] = field(default_factory=dict)
    top_fornecedores: list[dict[str, Any]] = field(default_factory=list)
    objetos_recorrentes: list[str] = field(default_factory=list)
    api_error: str = ""
    confidence: float = 0.0
    # Explicit multi-window states (zero vs unavailable vs partial)
    windows: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "orgao": self.orgao,
            "orgao_cnpj": self.orgao_cnpj,
            "municipio": self.municipio,
            "source": self.source,
            "window_months": self.window_months,
            "n_processos_pack": self.n_processos_pack,
            "n_aec_pack": self.n_aec_pack,
            "n_contratos_api": self.n_contratos_api,
            "n_aec_contratos": self.n_aec_contratos,
            "valor_total_estimado_pack": self.valor_total_estimado_pack,
            "valor_contratado_api": self.valor_contratado_api,
            "ticket_medio": self.ticket_medio,
            "modalidades": self.modalidades,
            "top_fornecedores": self.top_fornecedores,
            "objetos_recorrentes": self.objetos_recorrentes,
            "api_error": self.api_error,
            "confidence": self.confidence,
            "windows": self.windows,
        }


def build_pack_org_index(processes: list[CanonicalProcess]) -> dict[str, list[CanonicalProcess]]:
    by: dict[str, list[CanonicalProcess]] = defaultdict(list)
    for p in processes:
        key = cnpj8(p.orgao_cnpj) or (p.orgao or "").strip().upper()[:80]
        if key:
            by[key].append(p)
    return by


def analyze_org_from_pack(
    proc: CanonicalProcess,
    pack_index: dict[str, list[CanonicalProcess]],
) -> OrgHistory:
    key = cnpj8(proc.orgao_cnpj) or (proc.orgao or "").strip().upper()[:80]
    peers = pack_index.get(key) or [proc]
    aec_n = 0
    valores: list[float] = []
    mods: Counter[str] = Counter()
    objetos: list[str] = []
    for p in peers:
        mods[p.modalidade or "n/d"] += 1
        if p.valor_estimado is not None:
            valores.append(float(p.valor_estimado))
        objetos.append((p.objeto or "")[:120])
        cl = classify_aec(p.objeto, is_active_dispute=True)
        if cl.is_aec:
            aec_n += 1
    stems = Counter()
    for o in objetos:
        toks = [t for t in o.lower().split() if len(t) > 4][:6]
        if toks:
            stems[" ".join(toks[:4])] += 1
    pack_window = {
        "status": "parcial",
        "semantica": "recorte_do_pack_multifonte_atual_nao_calendario_fechado",
        "n_processos": len(peers),
        "n_aec": aec_n,
        "valor_estimado_agregado": sum(valores),
        "ticket_medio_estimado": (sum(valores) / len(valores)) if valores else None,
        "modalidades": dict(mods.most_common(8)),
    }
    hist = OrgHistory(
        orgao=proc.orgao,
        orgao_cnpj=proc.orgao_cnpj,
        municipio=proc.municipio,
        source="pack_processes",
        window_months=0,
        n_processos_pack=len(peers),
        n_aec_pack=aec_n,
        valor_total_estimado_pack=sum(valores),
        ticket_medio=(sum(valores) / len(valores)) if valores else None,
        modalidades=dict(mods.most_common(8)),
        objetos_recorrentes=[s for s, _ in stems.most_common(5)],
        confidence=0.45 if len(peers) >= 3 else 0.3,
        windows={
            "12m": {
                "status": "fonte_nao_consultada_ou_api_indisponivel",
                "contratos": None,
                "valor_contratado": None,
                "nota": "preenchido se API PNCP contratos responder com match CNPJ-8",
            },
            "24m": {
                "status": "fonte_nao_consultada",
                "contratos": None,
                "valor_contratado": None,
                "nota": "janela 24m exige 2 chamadas API ≤365d cada; não inventada",
            },
            "36m": {
                "status": "fonte_nao_consultada",
                "contratos": None,
                "valor_contratado": None,
                "nota": "janela 36m exige 3 chamadas API ≤365d cada; não inventada",
            },
            "pack_atual": pack_window,
        },
    )
    return hist


def _org_cnpj_from_contract(row: dict[str, Any]) -> str:
    org = row.get("orgaoEntidade") or row.get("orgao") or {}
    if isinstance(org, dict):
        return digits_only(str(org.get("cnpj") or org.get("cnpjOrgao") or ""))
    return digits_only(
        str(
            row.get("cnpjOrgao")
            or row.get("orgao_cnpj")
            or row.get("cnpjEntidade")
            or ""
        )
    )


def fetch_pncp_contracts_for_org(
    orgao_cnpj: str,
    *,
    months: int = 12,
    page_size: int = 50,
    max_pages: int = 5,
    timeout: float = 25.0,
) -> tuple[list[dict[str, Any]], str]:
    """Live PNCP /contratos for org CNPJ. Returns (records, error).

    Post-filters by org CNPJ-8 because the public API parameter ``cnpj`` is
    ambiguous (often supplier) and may return unrelated rows.
    """
    cnpj = digits_only(orgao_cnpj)
    if len(cnpj) < 8:
        return [], "cnpj_invalido"
    cnpj8 = cnpj[:8]
    cnpj14 = cnpj[:14] if len(cnpj) >= 14 else cnpj

    end = date.today()
    start = end - timedelta(days=min(360, months * 30))
    try:
        import requests
    except ImportError:
        return [], "requests_unavailable"

    all_rows: list[dict[str, Any]] = []
    err = ""
    # Prefer orgao-scoped param names when accepted; always post-filter.
    param_variants = (
        {"cnpjOrgao": cnpj14},
        {"cnpj": cnpj14},
    )
    for extra in param_variants:
        for page in range(1, max_pages + 1):
            params = {
                "dataInicial": start.strftime("%Y%m%d"),
                "dataFinal": end.strftime("%Y%m%d"),
                "pagina": str(page),
                "tamanhoPagina": str(page_size),
                **extra,
            }
            try:
                r = requests.get(
                    "https://pncp.gov.br/api/consulta/v1/contratos",
                    params=params,
                    timeout=timeout,
                    headers={
                        "User-Agent": "extra-cli-ms-open-pack/2.0",
                        "Accept": "application/json",
                    },
                )
                if r.status_code != 200:
                    err = f"HTTP {r.status_code}: {(r.text or '')[:160]}"
                    break
                payload = r.json()
                data = (
                    payload.get("data")
                    if isinstance(payload, dict)
                    else payload
                    if isinstance(payload, list)
                    else []
                )
                if not isinstance(data, list) or not data:
                    break
                all_rows.extend([x for x in data if isinstance(x, dict)])
                if len(data) < page_size:
                    break
            except Exception as exc:  # noqa: BLE001
                err = str(exc)[:200]
                break
        if all_rows:
            break

    matched = [
        row
        for row in all_rows
        if _org_cnpj_from_contract(row)[:8] == cnpj8
        or digits_only(str(row.get("cnpjOrgao") or ""))[:8] == cnpj8
    ]
    if all_rows and not matched:
        return [], (
            "api_retornou_contratos_sem_match_orgao_cnpj8 "
            f"(brutos={len(all_rows)}; filtro={cnpj8})"
            + (f"; last_err={err}" if err else "")
        )
    if not matched and err:
        return [], err
    return matched, ""


def enrich_org_with_contracts(hist: OrgHistory, contracts: list[dict[str, Any]]) -> OrgHistory:
    if not contracts:
        return hist
    hist.n_contratos_api = len(contracts)
    hist.source = "pack_processes+pncp_contratos_api"
    fornecedores: Counter[str] = Counter()
    nomes: dict[str, str] = {}
    valores: list[float] = []
    aec = 0
    objetos: list[str] = []
    for c in contracts:
        fc = digits_only(
            str(c.get("niFornecedor") or c.get("ni_fornecedor") or c.get("fornecedor_cnpj") or "")
        )
        fn = str(
            c.get("nomeRazaoSocialFornecedor")
            or c.get("nomeFornecedor")
            or c.get("nomeRazaoSocialReceita")
            or c.get("fornecedor_nome")
            or ""
        )
        if fc:
            fornecedores[fc] += 1
            if fn:
                nomes[fc] = fn
        val = optional_float(
            c.get("valorGlobal") or c.get("valorInicial") or c.get("valor_global") or c.get("valor")
        )
        if val is not None:
            valores.append(val)
            hist.valor_contratado_api += val
        obj = str(c.get("objetoContrato") or c.get("objeto") or "")
        objetos.append(obj[:120])
        if classify_aec(obj, is_active_dispute=False).is_aec:
            aec += 1
    hist.n_aec_contratos = aec
    hist.ticket_medio = (sum(valores) / len(valores)) if valores else hist.ticket_medio
    hist.top_fornecedores = [
        {
            "cnpj": fc,
            "razao_social": nomes.get(fc, ""),
            "vitorias": n,
            "fonte": "pncp_contratos_api",
        }
        for fc, n in fornecedores.most_common(8)
    ]
    if objetos:
        stems = Counter(o.lower()[:60] for o in objetos if o)
        hist.objetos_recorrentes = [s for s, _ in stems.most_common(5)]
    hist.confidence = min(0.9, 0.55 + 0.05 * min(len(contracts), 6))
    hist.window_months = 12
    hist.windows["12m"] = {
        "status": "ok" if contracts else "zero",
        "contratos": len(contracts),
        "contratos_aec": aec,
        "valor_contratado": hist.valor_contratado_api,
        "ticket_medio": hist.ticket_medio,
        "top_fornecedores_n": len(hist.top_fornecedores),
        "fonte": "pncp_contratos_api",
    }
    # 24m/36m still require additional windows — mark explicit not-fetched
    hist.windows["24m"] = {
        "status": "fonte_nao_consultada",
        "contratos": None,
        "nota": "não consultada nesta execução (economiza rate-limit); 12m disponível",
    }
    hist.windows["36m"] = {
        "status": "fonte_nao_consultada",
        "contratos": None,
        "nota": "não consultada nesta execução (economiza rate-limit); 12m disponível",
    }
    return hist


def competitors_from_ciga_contracts_in_pack(
    proc: CanonicalProcess,
    all_processes: list[CanonicalProcess],
) -> list[dict[str, Any]]:
    """Extract contractor names from CIGA/DOM contract publications for same org/município."""
    import re

    key8 = cnpj8(proc.orgao_cnpj)
    mun = (proc.municipio or "").strip().upper()
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    # Patterns common in DOM extratos
    name_pats = [
        re.compile(
            r"(?:contrata(?:da)?|empresa|adjudicat[aá]ria|credenciada)\s*[:\-]?\s*"
            r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9\s\.\&\-]{8,80})",
            re.I,
        ),
        re.compile(
            r"\b([A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇ\s]{5,60}(?:LTDA|EIRELI|S/?A|ME|EPP))\b",
            re.I,
        ),
    ]
    for p in all_processes:
        same_org = key8 and cnpj8(p.orgao_cnpj) == key8
        same_mun = mun and (p.municipio or "").strip().upper() == mun
        if not (same_org or same_mun):
            continue
        is_contractish = (
            p.status_processo in {"terminal", "expired"}
            or any(
                e in (p.event_types or [])
                for e in ("contrato", "homologacao", "adjudicacao", "extrato_contrato", "resultado")
            )
            or any(x in (p.objeto or "").lower() for x in ("contrato", "homolog", "adjudic", "extrato"))
        )
        if not is_contractish:
            continue
        blob = p.objeto or ""
        for pat in name_pats:
            for m in pat.finditer(blob):
                name = re.sub(r"\s+", " ", m.group(1)).strip(" -.,;")
                if len(name) < 8 or name.upper() in seen:
                    continue
                if any(x in name.lower() for x in ("municipio", "prefeitura", "secretaria", "estado")):
                    continue
                seen.add(name.upper())
                out.append(
                    {
                        "cnpj": "",
                        "razao_social": name,
                        "vitorias_relevantes": 1,
                        "justificativa": (
                            f"Nome extraído de publicação DOM/contrato no pack "
                            f"(mesmo {'órgão' if same_org else 'município'}; "
                            f"eventos={','.join(p.event_types or []) or p.status_processo})"
                        ),
                        "confianca": 0.35 if same_mun and not same_org else 0.45,
                        "fonte": "ciga_dom_pack",
                        "tipo": "concorrente_provavel_por_extrato_dom",
                    }
                )
    return out[:8]


def competitors_from_org_history(
    hist: OrgHistory,
    *,
    objeto: str,
) -> list[dict[str, Any]]:
    """Probable competitors from historical winners of the same org (not invented)."""
    out: list[dict[str, Any]] = []
    obj_n = (objeto or "").lower()
    aec_obj = classify_aec(objeto, is_active_dispute=True).is_aec
    for f in hist.top_fornecedores:
        name = (f.get("razao_social") or "").lower()
        # Filter obvious non-AEC suppliers when current object is AEC
        if aec_obj and any(
            bad in name
            for bad in (
                "posto de combust",
                "farmac",
                "medicament",
                "seguro",
                "telecom",
                "limpeza",
                "aliment",
                "merenda",
            )
        ):
            continue
        reason = (
            f"Venceu {f.get('vitorias')} contrato(s) do mesmo órgão (CNPJ-8 filtrado) "
            f"na janela consultada (fonte={f.get('fonte')})"
        )
        overlap = any(
            w in obj_n
            for rec in hist.objetos_recorrentes
            for w in rec.split()
            if len(w) > 5
        )
        out.append(
            {
                "cnpj": f.get("cnpj"),
                "razao_social": f.get("razao_social") or "nome_nao_informado_na_api",
                "vitorias_relevantes": f.get("vitorias"),
                "justificativa": reason
                + (
                    "; objetos recorrentes do órgão se sobrepõem ao edital atual"
                    if overlap
                    else ""
                ),
                "confianca": 0.55 if overlap else 0.4,
                "fonte": f.get("fonte"),
                "tipo": "concorrente_provavel_por_historico_orgao",
            }
        )
    return out


def apply_market_intel(
    shortlist: list[CanonicalProcess],
    all_processes: list[CanonicalProcess],
    *,
    fetch_contracts: bool = True,
) -> dict[str, Any]:
    """Mutates shortlist processes with buyer/competitor fields; returns summary."""
    idx = build_pack_org_index(all_processes)
    summary: dict[str, Any] = {
        "orgs": 0,
        "with_api_contracts": 0,
        "api_errors": 0,
        "competitors_total": 0,
    }
    cache_contracts: dict[str, tuple[list[dict[str, Any]], str]] = {}

    for p in shortlist:
        hist = analyze_org_from_pack(p, idx)
        ckey = digits_only(p.orgao_cnpj)[:14]
        if fetch_contracts and ckey and len(ckey) >= 8:
            if ckey not in cache_contracts:
                cache_contracts[ckey] = fetch_pncp_contracts_for_org(p.orgao_cnpj, months=12)
            rows, err = cache_contracts[ckey]
            if rows:
                hist = enrich_org_with_contracts(hist, rows)
                summary["with_api_contracts"] += 1
            elif err:
                hist.api_error = err
                summary["api_errors"] += 1

        comps = competitors_from_org_history(hist, objeto=p.objeto)
        if not comps:
            comps = competitors_from_ciga_contracts_in_pack(p, all_processes)
        summary["orgs"] += 1
        summary["competitors_total"] += len(comps)

        # Write human-readable fields
        p.buyer_analysis = _format_buyer(hist, p)
        if comps:
            p.competitors_probable = " | ".join(
                f"{c.get('razao_social')} (CNPJ {c.get('cnpj')}: {c.get('justificativa')})"
                for c in comps[:5]
            )[:1500]
        else:
            p.competitors_probable = (
                "concorrentes_provaveis: nenhum vencedor histórico recuperado para o órgão "
                f"(fonte_pack={hist.n_processos_pack} processos no pack; "
                f"api_contratos={hist.n_contratos_api}"
                + (f"; api_erro={hist.api_error}" if hist.api_error else "")
                + "). Não inventar lista genérica."
            )[:1200]

        # stash structured
        p._org_history = hist.to_dict()  # type: ignore[attr-defined]
        p._competitors = comps  # type: ignore[attr-defined]

        if p.decision:
            # Drop stale placeholders once market intel ran
            drop = {
                "analise_orgao_12_24_36m",
                "concorrentes_provaveis_historicos",
                "mapear_concorrentes_com_base_historica",
                "validar_historico_orgao_contratos_pncp",
                "analise_documental_completa",
                "enriquecer_historico_orgao_se_api_disponivel",
            }
            p.decision.pending = sorted(set(p.decision.pending) - drop)
            if hist.n_contratos_api == 0:
                p.decision.pending = sorted(
                    set(
                        p.decision.pending
                        + ["historico_contratos_12m_api_indisponivel_ou_vazio"]
                    )
                )
            if hist.windows.get("24m", {}).get("status") == "fonte_nao_consultada":
                p.decision.pending = sorted(
                    set(p.decision.pending + ["historico_contratos_24m_36m_nao_consultado"])
                )
            p.decision.risks = [
                r
                for r in p.decision.risks
                if "concorrentes_nao_enumerados" not in r
                and "documentos_nao_baixados" not in r
            ]
            if not comps:
                p.decision.risks = sorted(
                    set(p.decision.risks + ["concorrentes_sem_vencedores_historicos_filtrados"])
                )
    return summary


def _format_buyer(hist: OrgHistory, proc: CanonicalProcess) -> str:
    dist = proc.distance_km
    w12 = hist.windows.get("12m") or {}
    w24 = hist.windows.get("24m") or {}
    w36 = hist.windows.get("36m") or {}
    parts = [
        f"{hist.orgao} ({hist.municipio}); dist={dist if dist is not None else 'n/d'} km "
        f"({proc.distance_method or 'n/d'}).",
        f"Pack atual (recorte, não calendário): {hist.n_processos_pack} processo(s), "
        f"{hist.n_aec_pack} AEC, valor estimado agregado R$ {hist.valor_total_estimado_pack:,.0f}.".replace(
            ",", "."
        ),
        f"Janela 12m: status={w12.get('status')}"
        + (
            f", contratos={w12.get('contratos')}, AEC={w12.get('contratos_aec')}, "
            f"valor_contratado=R$ {float(w12.get('valor_contratado') or 0):,.0f}".replace(",", ".")
            if w12.get("status") in {"ok", "zero"}
            else f" ({w12.get('nota') or hist.api_error or 'sem dados'})"
        )
        + ".",
        f"Janela 24m: status={w24.get('status')} ({w24.get('nota') or 'n/d'}).",
        f"Janela 36m: status={w36.get('status')} ({w36.get('nota') or 'n/d'}).",
    ]
    if hist.modalidades:
        top_m = ", ".join(f"{k}:{v}" for k, v in list(hist.modalidades.items())[:4])
        parts.append(f"Modalidades no pack: {top_m}.")
    if hist.top_fornecedores:
        tops = ", ".join(
            f"{f.get('razao_social') or f.get('cnpj')}×{f.get('vitorias')}"
            for f in hist.top_fornecedores[:4]
        )
        parts.append(f"Principais contratadas (12m filtrado): {tops}.")
    parts.append(f"Confiança: {hist.confidence:.2f} (fonte={hist.source}).")
    return " ".join(parts)[:1800]
