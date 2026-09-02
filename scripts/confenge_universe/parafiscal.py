"""Single source of truth for the parafiscal / Sistema S institutional taxonomy.

Sistema S, autonomous social services, religious bodies and foundational
education/research institutions appear as "fornecedor" in PNCP (event booths,
training, sponsorship, own-building refurbishment) but are never construction
/ engineering execution clients of CONFENGE.

This module exists so that the taxonomy has exactly one definition consumed by
BOTH defence surfaces:

  * PRIMARY   — `scripts.confenge_universe.target_fit.classify_target_fit`
                (reconcile → compute → confenge_target_fit_shadow → outreach feed)
  * IN DEPTH  — `scripts.confenge_universe.identity.resolve_identity`
                (aggregate.py / universe builder → eligibility → publish)

It depends only on `scripts.linkage.keys`, so it can be imported from both
without any cycle and without pulling the frozen `confenge_universe.__init__`.

`scripts.confenge_target_fit.compute.classifier_sha()` hashes this module's
source, so adding a marker produces classifier drift and the reconcile sweep
re-enqueues every materialized root.
"""

from __future__ import annotations

from scripts.linkage.keys import normalize_name

#: Exclusion code emitted by `resolve_identity` for these entities.
PARAFISCAL_INSTITUTIONAL = "PARAFISCAL_INSTITUTIONAL"

#: Reason code emitted by `classify_target_fit` for these entities.
PARAFISCAL_HARD_OUT_REASON = "parafiscal_institutional_hard_out"

# Taxonomy moved verbatim from `identity.py` (iteration 1, ratified by @qa and
# @po). Content intentionally UNCHANGED in iteration 2 — the gate makes it
# reachable, it does not widen it.
PARAFISCAL_INSTITUTIONAL_MARKERS = (
    # Sistema S
    "sebrae",
    "senai",
    "sesi",
    "sesc",
    "senac",
    "senar",
    "sest",
    "senat",
    "sescoop",
    "sebrae nacional",
    "servico social autonomo",
    "servico social da industria",
    "servico social do comercio",
    "servico social do transporte",
    "servico nacional de aprendizagem",
    "servico nacional de aprendizagem industrial",
    "servico nacional de aprendizagem comercial",
    "servico nacional de aprendizagem rural",
    "servico nacional de aprendizagem do transporte",
    "servico de apoio as micro e pequenas empresas",
    # Religious bodies
    "mitra diocesana",
    "mitra arquidiocesana",
    "arquidiocese",
    "diocese",
    "paroquia",
    "curia diocesana",
    "curia metropolitana",
    "igreja evangelica",
    "igreja batista",
    "igreja catolica",
    "congregacao religiosa",
    "obras sociais da diocese",
    # Foundational education / research institutions.
    # Deliberately NOT here: "fundacao municipal|estadual|nacional|cultural|
    # hospitalar". Those are public organs, not parafiscal bodies — they keep
    # falling through to `_looks_like_public_foundation` → PUBLIC_ORGAN, exactly
    # as before this change. Reclassifying them would silently shift the
    # identity_exclusion_breakdown counters in aggregate.py.
    "fundacao educacional",
    "fundacao universitaria",
    "fundacao de apoio",
    "fundacao de amparo",
    "fundacao de ensino",
    "fundacao de pesquisa",
)


def match_parafiscal_institutional(
    name: str | None,
    markers: tuple[str, ...] = PARAFISCAL_INSTITUTIONAL_MARKERS,
) -> str | None:
    """Return the matched marker for a Sistema S / religious / foundational name.

    Matched as whole-token sequences on the normalized name so that "SESC" does
    not fire on "SESCOOPERATIVA" and "DIOCESE" does not fire on "DIOCESEX".
    Both sides go through `normalize_name` (which upper-cases and strips
    diacritics), so matching is accent- and case-insensitive.
    """
    if not name:
        return None
    n = f" {normalize_name(name)} "
    for m in markers:
        token = f" {normalize_name(m)} "
        if token in n:
            return m
    return None


def match_parafiscal_in_names(
    names: object,
    markers: tuple[str, ...] = PARAFISCAL_INSTITUTIONAL_MARKERS,
) -> tuple[str, str] | None:
    """First (name, marker) pair that matches over an iterable of candidate names.

    Used by `classify_target_fit`, whose decision surface is `razao_social` +
    `nome_fantasia` + every distinct `fornecedor_nome` present in the contract
    list. Evaluating only `razao_social` would be non-deterministic: the loader
    picks it as the first non-null supplier name of a query without ORDER BY.
    """
    if not isinstance(names, (list, tuple, set, frozenset)):
        return None
    for name in names:
        if not isinstance(name, str):
            continue
        marker = match_parafiscal_institutional(name, markers)
        if marker:
            return name, marker
    return None
