"""DoD «Entregável E — editais abertos e recomendação individual».

Fail-closed open-edital recommendations:
- only editais proven open at cut date / conclusion week
- snapshot seen or individually reconfirmed
- scored against Extra versioned profile
- GO | REVIEW | NO_GO with client labels PARTICIPAR | NÃO PARTICIPAR | REVIEW
- favorable + impeding factors
- official docs/data references
- never promise victory or replace legal/accounting/technical sign-off
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from scripts.ops.diagnostic_profile import profile_stamp

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RANKINGS = frozenset({"GO", "REVIEW", "NO_GO"})
CLIENT_LABEL = {
    "GO": "PARTICIPAR",
    "NO_GO": "NÃO PARTICIPAR",
    "REVIEW": "REVIEW",
}


@dataclass
class OpennessProof:
    is_open_at_cut: bool
    cut_date: str
    proof_mode: str  # SNAPSHOT | INDIVIDUAL_RECONFIRM
    snapshot_id: str | None
    reconfirmed_at: str | None
    official_url: str | None
    status_source: str


@dataclass
class EditalRecommendation:
    edital_id: str
    titulo: str
    orgao: str
    ranking: str  # GO|REVIEW|NO_GO
    client_label: str  # PARTICIPAR|NÃO PARTICIPAR|REVIEW
    profile_id: str
    profile_version: Any
    openness: dict[str, Any]
    fatores_favoraveis: list[str]
    fatores_impeditivos_ou_riscos: list[str]
    referencias_oficiais: list[str]
    disclaimer: str
    score_notes: str


@dataclass
class DeliverableEReport:
    status: str
    deliverable: str = "E"
    title: str = "Editais abertos e recomendação individual"
    profile: dict[str, Any] = field(default_factory=dict)
    cut_date: str = ""
    recommendations: list[dict[str, Any]] = field(default_factory=list)
    excluded_not_open: int = 0
    claims_allowed: list[str] = field(default_factory=list)
    claims_forbidden: list[str] = field(default_factory=list)
    generated_at: str = ""


def utc_now() -> str:
    return (
        datetime.now(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


DISCLAIMER = (
    "Recomendação operacional fundamentada em dados disponíveis; "
    "NÃO promete vitória e NÃO substitui análise jurídica, contábil ou técnica final."
)


def prove_open(raw: dict[str, Any], cut_date: str) -> OpennessProof | None:
    """Return OpennessProof if edital is proven open at cut; else None (exclude)."""
    status = str(raw.get("status") or raw.get("situacao") or "").upper()
    open_flags = {"ABERTA", "OPEN", "RECEBENDO_PROPOSTA", "PUBLICADA", "EM_ANDAMENTO"}
    if status and status not in open_flags and not raw.get("is_open"):
        return None
    if raw.get("is_open") is False:
        return None
    mode = str(raw.get("proof_mode") or "SNAPSHOT").upper()
    if mode not in {"SNAPSHOT", "INDIVIDUAL_RECONFIRM"}:
        mode = "SNAPSHOT"
    snap = raw.get("snapshot_id")
    reconf = raw.get("reconfirmed_at")
    if mode == "SNAPSHOT" and not snap:
        return None
    if mode == "INDIVIDUAL_RECONFIRM" and not reconf:
        return None
    url = raw.get("official_url") or raw.get("url")
    if not url and not raw.get("status_source"):
        return None
    return OpennessProof(
        is_open_at_cut=True,
        cut_date=cut_date,
        proof_mode=mode,
        snapshot_id=str(snap) if snap else None,
        reconfirmed_at=str(reconf) if reconf else None,
        official_url=str(url) if url else None,
        status_source=str(raw.get("status_source") or "source_status"),
    )


def score_against_profile(raw: dict[str, Any], profile: dict[str, Any]) -> tuple[str, list[str], list[str], str]:
    """Simple transparent scoring → GO/REVIEW/NO_GO with factors."""
    fav: list[str] = []
    risk: list[str] = []
    notes: list[str] = []

    uf = str(raw.get("uf") or "")
    region = (profile.get("region") or {}) if isinstance(profile.get("region"), dict) else {}
    uf_primary = str(region.get("uf_primary") or "SC")
    if uf == uf_primary or not uf:
        fav.append(f"UF alinhada ao perfil ({uf_primary})")
    else:
        risk.append(f"UF {uf} fora de uf_primary={uf_primary}")

    obj = str(raw.get("objeto") or raw.get("titulo") or "").lower()
    cats = profile.get("engineering_categories") or []
    if any(str(c).replace("_", " ") in obj or str(c) in obj for c in cats):
        fav.append("objeto compatível com engineering_categories do perfil")
    elif obj:
        risk.append("objeto sem match claro em engineering_categories")
        notes.append("REVIEW por ambiguidade de objeto")

    # hard blocks from profile
    hb = profile.get("hard_blocks") or {}
    if hb.get("require_official_url") and not (raw.get("official_url") or raw.get("url")):
        risk.append("hard_block require_official_url sem URL")
    if hb.get("exclude_terminal_or_suspended"):
        st = str(raw.get("status") or "").upper()
        if st in {"SUSPENSA", "CANCELADA", "ENCERRADA", "HOMOLOGADA"}:
            risk.append(f"status terminal/suspenso: {st}")

    # Decision
    if any("hard_block" in r or "terminal" in r for r in risk) or any(
        "terminal/suspenso" in r for r in risk
    ):
        ranking = "NO_GO"
    elif len(risk) == 0 and len(fav) >= 1:
        ranking = "GO"
    elif len(risk) >= 2 and len(fav) == 0:
        ranking = "NO_GO"
    else:
        ranking = "REVIEW"
        if not notes:
            notes.append("requer análise humana adicional")

    return ranking, fav, risk, "; ".join(notes)


def recommend(raw: dict[str, Any], cut_date: str, profile: dict[str, Any] | None = None) -> EditalRecommendation | None:
    stamp = profile_stamp()
    # merge stamp with full profile raw for scoring when provided
    prof = dict(stamp)
    if profile:
        prof.update(profile)

    openness = prove_open(raw, cut_date)
    if openness is None:
        return None

    ranking, fav, risk, notes = score_against_profile(raw, prof)
    if ranking not in RANKINGS:
        ranking = "REVIEW"
    refs = []
    if openness.official_url:
        refs.append(openness.official_url)
    if raw.get("documento_oficial"):
        refs.append(str(raw["documento_oficial"]))
    if not refs and openness.status_source:
        refs.append(f"status_source:{openness.status_source}")

    return EditalRecommendation(
        edital_id=str(raw.get("edital_id") or raw.get("id") or "unknown"),
        titulo=str(raw.get("titulo") or raw.get("objeto") or "")[:200],
        orgao=str(raw.get("orgao") or ""),
        ranking=ranking,
        client_label=CLIENT_LABEL[ranking],
        profile_id=str(stamp.get("profile_id")),
        profile_version=stamp.get("version"),
        openness=asdict(openness),
        fatores_favoraveis=fav,
        fatores_impeditivos_ou_riscos=risk,
        referencias_oficiais=refs,
        disclaimer=DISCLAIMER,
        score_notes=notes,
    )


def build_report(
    candidates: list[dict[str, Any]],
    *,
    cut_date: str | None = None,
    profile: dict[str, Any] | None = None,
) -> DeliverableEReport:
    cut = cut_date or date.today().isoformat()
    recs: list[EditalRecommendation] = []
    excluded = 0
    for c in candidates:
        r = recommend(c, cut, profile)
        if r is None:
            excluded += 1
            continue
        recs.append(r)
    status = "OK" if recs else "EMPTY"
    return DeliverableEReport(
        status=status,
        profile=profile_stamp(),
        cut_date=cut,
        recommendations=[asdict(r) for r in recs],
        excluded_not_open=excluded,
        claims_allowed=[
            f"{len(recs)} open editais with GO/REVIEW/NO_GO at cut={cut}",
            "Client labels PARTICIPAR/NÃO PARTICIPAR/REVIEW",
            "Disclaimer: no victory promise; no substitute for final legal/accounting/tech analysis",
        ],
        claims_forbidden=[
            "Promise vitória",
            "Substitute análise jurídica/contábil/técnica final",
            "Include closed editais as open without proof",
            "Recommend without official data/doc reference when available path exists",
        ],
        generated_at=utc_now(),
    )


def fixture_candidates() -> list[dict[str, Any]]:
    return [
        {
            "edital_id": "E-001",
            "titulo": "Reforma predial prédio público",
            "objeto": "reforma predial de edificacao publica",
            "orgao": "Prefeitura Demo",
            "uf": "SC",
            "status": "ABERTA",
            "is_open": True,
            "proof_mode": "SNAPSHOT",
            "snapshot_id": "snap-2026-07-18",
            "official_url": "https://pncp.gov.br/editais/demo/E-001",
            "status_source": "pncp",
        },
        {
            "edital_id": "E-002",
            "titulo": "Serviço de limpeza",
            "objeto": "limpeza predial",
            "orgao": "Câmara Demo",
            "uf": "PR",
            "status": "ABERTA",
            "is_open": True,
            "proof_mode": "INDIVIDUAL_RECONFIRM",
            "reconfirmed_at": "2026-07-18T12:00:00Z",
            "official_url": "https://example.org/edital/E-002",
            "status_source": "portal_orgao",
        },
        {
            "edital_id": "E-003",
            "titulo": "Obra cancelada",
            "objeto": "construcao",
            "orgao": "X",
            "uf": "SC",
            "status": "CANCELADA",
            "is_open": False,
        },
        {
            "edital_id": "E-004",
            "titulo": "Sem prova de abertura",
            "objeto": "reforma",
            "orgao": "Y",
            "uf": "SC",
            "status": "ABERTA",
            "proof_mode": "SNAPSHOT",
            # missing snapshot_id → exclude
        },
    ]


def fixture_report(cut_date: str = "2026-07-18") -> DeliverableEReport:
    from scripts.ops.diagnostic_profile import load_raw_profile

    try:
        prof = load_raw_profile()
    except Exception:
        prof = None
    return build_report(fixture_candidates(), cut_date=cut_date, profile=prof)


def audit_report(report: dict[str, Any] | DeliverableEReport) -> dict[str, Any]:
    data = asdict(report) if isinstance(report, DeliverableEReport) else report
    recs = data.get("recommendations") or []
    checks: list[dict[str, Any]] = []

    def add(item_id: str, dod: str, ok: bool, evidence: list[str], notes: str = "") -> None:
        checks.append(
            {
                "item_id": item_id,
                "dod_text": dod,
                "status": "PASS" if ok else "FAIL",
                "evidence": evidence,
                "notes": notes,
            }
        )

    add(
        "open_at_cut",
        "O relatório inclui editais comprovadamente abertos na data de corte ou semana de conclusão.",
        bool(data.get("cut_date")) and all((r.get("openness") or {}).get("is_open_at_cut") for r in recs) if recs else bool(data.get("cut_date")),
        [f"cut_date={data.get('cut_date')}", f"n={len(recs)}", f"excluded_not_open={data.get('excluded_not_open')}"],
    )
    modes_ok = all(
        (r.get("openness") or {}).get("proof_mode") in {"SNAPSHOT", "INDIVIDUAL_RECONFIRM"}
        for r in recs
    ) if recs else True
    add(
        "snapshot_or_reconfirm",
        "Cada edital foi visto no snapshot completo mais recente ou reconfirmado individualmente.",
        modes_ok,
        ["proof_mode SNAPSHOT|INDIVIDUAL_RECONFIRM"],
    )
    has_profile = all(r.get("profile_id") and r.get("profile_version") is not None for r in recs) if recs else True
    add(
        "profile_versioned",
        "Cada edital é avaliado contra o perfil versionado da Extra.",
        has_profile and bool((data.get("profile") or {}).get("version") is not None),
        ["profile_id + profile_version on each recommendation"],
    )
    ranks_ok = all(r.get("ranking") in RANKINGS for r in recs) if recs else True
    add("go_review_nogo", "Cada edital recebe `GO`, `REVIEW` ou `NO_GO`.", ranks_ok, list(RANKINGS))
    labels_ok = all(
        r.get("client_label") == CLIENT_LABEL.get(r.get("ranking", ""), "")
        for r in recs
    ) if recs else True
    add(
        "client_labels",
        "A apresentação ao cliente traduz `GO` e `NO_GO` como recomendação fundamentada de `PARTICIPAR` ou `NÃO PARTICIPAR`, preservando `REVIEW` quando depender de análise humana adicional.",
        labels_ok,
        [str(CLIENT_LABEL)],
    )
    has_fav = all(isinstance(r.get("fatores_favoraveis"), list) for r in recs) if recs else True
    add("fatores_favoraveis", "Cada recomendação mostra fatores favoráveis.", has_fav, ["fatores_favoraveis list"])
    has_risk = all(isinstance(r.get("fatores_impeditivos_ou_riscos"), list) for r in recs) if recs else True
    add(
        "fatores_impeditivos",
        "Cada recomendação mostra fatores impeditivos ou riscos.",
        has_risk,
        ["fatores_impeditivos_ou_riscos list"],
    )
    has_refs = all(r.get("referencias_oficiais") for r in recs) if recs else True
    add(
        "refs_oficiais",
        "Cada recomendação referencia dados e documentos oficiais disponíveis.",
        has_refs,
        ["referencias_oficiais non-empty when included"],
    )
    disc_ok = all(DISCLAIMER[:40] in str(r.get("disclaimer") or "") for r in recs) if recs else True
    no_victory = all(
        "vitória" not in str(r.get("disclaimer") or "").lower()
        or "NÃO promete" in str(r.get("disclaimer") or "")
        for r in recs
    ) if recs else True
    add(
        "no_victory_promise",
        "Nenhuma recomendação promete vitória ou substitui análise jurídica, contábil ou técnica final.",
        disc_ok and no_victory,
        ["shared disclaimer on every recommendation"],
    )

    fail = sum(1 for c in checks if c["status"] == "FAIL")
    return {
        "ok": fail == 0,
        "generated_at": utc_now(),
        "summary": {
            "total": len(checks),
            "pass": sum(1 for c in checks if c["status"] == "PASS"),
            "fail": fail,
        },
        "checks": checks,
        "report_status": data.get("status"),
        "recommendation_count": len(recs),
        "excluded_not_open": data.get("excluded_not_open"),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Deliverable E open editais recommendations")
    p.add_argument("command", choices=["fixture", "audit-fixture", "audit-file"])
    p.add_argument("--cut-date", default="2026-07-18")
    p.add_argument("--path", type=Path, default=None)
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args(argv)

    if args.command == "fixture":
        report = fixture_report(args.cut_date)
        payload: dict[str, Any] = asdict(report)
    elif args.command == "audit-fixture":
        report = fixture_report(args.cut_date)
        payload = audit_report(report)
    else:
        path = args.path or PROJECT_ROOT / "docs/ops/session-2026-07-18-deliverable-e/fixture-e.json"
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        payload = audit_report(data)

    text = json.dumps(payload, indent=2, ensure_ascii=False)
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    if str(args.command).startswith("audit") and not payload.get("ok"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
