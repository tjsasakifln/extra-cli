"""Near-duplicate draft/batch gate for CONFENGE outreach.

Blocks a batch when bodies are near-clones across different companies despite
distinct facts. Compares both raw lexical similarity AND a semantic skeleton
after stripping company/object/date/value variables — so interpolating different
PNCP objects into the same template is NOT a copy-quality pass.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any

# Jaccard token similarity above this across different accounts → flag / block
DEFAULT_SIMILARITY_THRESHOLD = 0.82
# Semantic skeleton similarity (after variable normalization)
DEFAULT_SEMANTIC_THRESHOLD = 0.78
# Legacy global fraction (still recorded); block is driven by any high pair.
DEFAULT_PAIR_FRACTION_LIMIT = 0.35
# Extreme clone pair (identical templates)
DEFAULT_EXTREME_SIMILARITY = 0.95
# Blind-template / skeleton cluster dominance
DEFAULT_SKELETON_CLUSTER_LIMIT = 0.30
DEFAULT_OPENING_REUSE_LIMIT = 0.30
DEFAULT_TRANSITION_REUSE_LIMIT = 0.40
DEFAULT_CTA_REUSE_LIMIT = 0.50

_TOKEN_RE = re.compile(r"[a-z0-9à-ü]+", re.I)

# Variable fact patterns → tokens (order matters: longer first)
_NORMALIZERS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b"), " CNPJ "),
    (re.compile(r"\b\d{14}\b"), " CNPJ "),
    (re.compile(r"R\$\s*[\d.,]+", re.I), " VALOR "),
    (re.compile(r"\b\d{1,3}(?:\.\d{3})+(?:,\d+)?\b"), " VALOR "),
    (re.compile(r"\b20\d{2}-\d{2}-\d{2}\b"), " DATA "),
    (re.compile(r"\b\d{1,2}/\d{1,2}/20\d{2}\b"), " DATA "),
    (re.compile(r"\b(?:jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)[a-z]*\s*/?\s*20\d{2}\b", re.I), " DATA "),
    (re.compile(r"\b20\d{2}\b"), " ANO "),
    (re.compile(r"\b(?:contrato|aditivo|edital|ata)\s*(?:n[ºo°.]?\s*)?[\w./-]{3,}", re.I), " CONTRATO "),
    (re.compile(r"\bobjeto:\s*[^.;\n]{20,180}", re.I), " OBJETO "),
    (re.compile(r"\bórg[aã]o:\s*[^.;\n]{5,120}", re.I), " ORGAO "),
    (re.compile(r"\bUF\s+[A-Z]{2}\b"), " UF "),
    (re.compile(r"\b(?:AC|AL|AP|AM|BA|CE|DF|ES|GO|MA|MT|MS|MG|PA|PB|PR|PE|PI|RJ|RN|RS|RO|RR|SC|SP|SE|TO)\b"), " UF "),
]

_STOP = {
    "de", "da", "do", "das", "dos", "a", "o", "e", "que", "em", "para", "com",
    "por", "um", "uma", "os", "as", "no", "na", "nos", "nas", "ao", "à", "pelo",
    "pela", "olá", "ola", "vocês", "voces", "sua", "seu", "sobre",
}


def _tokens(text: str) -> set[str]:
    return {
        t.lower()
        for t in _TOKEN_RE.findall(text or "")
        if len(t) > 2 and t.lower() not in _STOP
    }


def jaccard(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


def normalize_semantic_skeleton(text: str, *, company: str | None = None) -> str:
    """Strip variable facts so template structure is comparable."""
    t = text or ""
    if company:
        # longest-first word chunks of company name
        for part in sorted({company, company.split()[0] if company.split() else company}, key=len, reverse=True):
            if len(part) >= 3:
                t = re.sub(re.escape(part), " EMPRESA ", t, flags=re.I)
    for pat, repl in _NORMALIZERS:
        t = pat.sub(repl, t)
    # Long quoted/object-like spans after "Pelo que está público sobre"
    t = re.sub(
        r"(?i)pelo que est[aá] p[uú]blico sobre\s+\S+",
        "Pelo que está público sobre EMPRESA",
        t,
    )
    # Collapse whitespace
    t = re.sub(r"\s+", " ", t).strip().lower()
    return t


def sentence_skeleton(text: str) -> str:
    """Keep only non-variable content words, order-preserving (structure)."""
    norm = normalize_semantic_skeleton(text)
    # Drop pure placeholder tokens from skeleton comparison set string
    keep = []
    for tok in _TOKEN_RE.findall(norm):
        low = tok.lower()
        if low in _STOP or low in {
            "empresa", "cnpj", "valor", "data", "ano", "contrato", "objeto",
            "orgao", "órgão", "uf", "municipio", "município",
        }:
            continue
        keep.append(low)
    return " ".join(keep)


def _opening_phrase(text: str) -> str:
    first = re.split(r"[.!?\n]", text or "", maxsplit=1)[0]
    sk = sentence_skeleton(first)
    return " ".join(sk.split()[:12])


def _cta_phrase(text: str) -> str:
    # Last non-empty sentence often is CTA
    parts = [p.strip() for p in re.split(r"[.!?\n]+", text or "") if p.strip()]
    if not parts:
        return ""
    return sentence_skeleton(parts[-1])


def _transition_phrase(text: str) -> str:
    parts = [p.strip() for p in re.split(r"[.!?\n]+", text or "") if p.strip()]
    if len(parts) < 2:
        return ""
    mid = parts[len(parts) // 2]
    return sentence_skeleton(mid)


@dataclass
class NearDuplicateAudit:
    total_drafts: int
    compared_pairs: int
    high_similarity_pairs: int
    max_similarity: float
    pair_fraction_high: float
    threshold: float
    blocked: bool
    reason_codes: list[str] = field(default_factory=list)
    sample_pairs: list[dict[str, Any]] = field(default_factory=list)
    # Semantic / blind-template metrics (always recorded)
    lexical_similarity_raw_max: float = 0.0
    semantic_template_similarity_max: float = 0.0
    normalized_skeleton_similarity_max: float = 0.0
    high_semantic_pairs: int = 0
    cta_reuse_rate: float = 0.0
    opening_reuse_rate: float = 0.0
    sentence_pattern_reuse_rate: float = 0.0
    dominant_skeleton_share: float = 0.0
    metrics: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def audit_near_duplicates(
    drafts: list[dict[str, Any]],
    *,
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    semantic_threshold: float = DEFAULT_SEMANTIC_THRESHOLD,
    pair_fraction_limit: float = DEFAULT_PAIR_FRACTION_LIMIT,
    extreme_similarity: float = DEFAULT_EXTREME_SIMILARITY,
    block_any_high_pair: bool = True,
    skeleton_cluster_limit: float = DEFAULT_SKELETON_CLUSTER_LIMIT,
    opening_reuse_limit: float = DEFAULT_OPENING_REUSE_LIMIT,
    transition_reuse_limit: float = DEFAULT_TRANSITION_REUSE_LIMIT,
    cta_reuse_limit: float = DEFAULT_CTA_REUSE_LIMIT,
) -> NearDuplicateAudit:
    """Audit a batch of draft dicts with keys: account_id/cnpj, body, subject optional.

    Block rules (structural, not diversity quota):
    - any multi-account pair with raw sim >= similarity_threshold
    - any multi-account pair with semantic-skeleton sim >= semantic_threshold
    - OR any pair with sim >= extreme_similarity
    - OR global high-pair fraction >= pair_fraction_limit
    - OR per-service_id family high-pair fraction >= pair_fraction_limit
    - OR dominant skeleton / opening / transition / CTA reuse above limits
    """
    bodies: list[tuple[str, str, str, str]] = []  # key, body, service_id, company
    for d in drafts:
        if not isinstance(d, dict):
            continue
        key = str(d.get("cnpj") or d.get("account_id") or d.get("id") or len(bodies))
        body = str(d.get("body") or d.get("body_text") or d.get("BodyText") or "")
        svc = str(
            d.get("service_id")
            or d.get("service_code")
            or d.get("canonical_service_code")
            or ((d.get("offer") or {}) if isinstance(d.get("offer"), dict) else {}).get("service_code")
            or ""
        )
        company = str(
            d.get("razao_social")
            or d.get("company")
            or d.get("nome_fantasia")
            or ""
        )
        if body.strip():
            bodies.append((key, body, svc, company))

    n = len(bodies)
    high = 0
    high_sem = 0
    pairs = 0
    max_sim = 0.0
    max_sem = 0.0
    max_skel = 0.0
    samples: list[dict[str, Any]] = []
    reasons: list[str] = []
    family_stats: dict[str, list[int]] = {}

    skeletons = [sentence_skeleton(b[1]) for b in bodies]
    openings = [_opening_phrase(b[1]) for b in bodies]
    transitions = [_transition_phrase(b[1]) for b in bodies]
    ctas = [_cta_phrase(b[1]) for b in bodies]

    for i in range(n):
        for j in range(i + 1, n):
            if bodies[i][0] == bodies[j][0]:
                continue
            pairs += 1
            raw_i, raw_j = bodies[i][1], bodies[j][1]
            sim = jaccard(raw_i, raw_j)
            sk_i = normalize_semantic_skeleton(raw_i, company=bodies[i][3] or None)
            sk_j = normalize_semantic_skeleton(raw_j, company=bodies[j][3] or None)
            sem = jaccard(sk_i, sk_j)
            skel = jaccard(skeletons[i], skeletons[j])
            max_sim = max(max_sim, sim)
            max_sem = max(max_sem, sem)
            max_skel = max(max_skel, skel)
            svc_i, svc_j = bodies[i][2], bodies[j][2]
            fam = svc_i if svc_i and svc_i == svc_j else ""
            if fam:
                family_stats.setdefault(fam, [0, 0])
                family_stats[fam][0] += 1
            is_high = sim >= similarity_threshold or sem >= semantic_threshold or skel >= semantic_threshold
            if is_high:
                high += 1
                if sem >= semantic_threshold or skel >= semantic_threshold:
                    high_sem += 1
                if fam:
                    family_stats[fam][1] += 1
                if len(samples) < 12:
                    samples.append(
                        {
                            "a": bodies[i][0],
                            "b": bodies[j][0],
                            "lexical_similarity_raw": round(sim, 4),
                            "semantic_template_similarity": round(sem, 4),
                            "normalized_skeleton_similarity": round(skel, 4),
                            "similarity": round(max(sim, sem, skel), 4),
                            "service_id": fam or None,
                        }
                    )

    frac = (high / pairs) if pairs else 0.0

    def _reuse_rate(items: list[str]) -> float:
        clean = [x for x in items if x and len(x.split()) >= 3]
        if len(clean) < 2:
            return 0.0
        c = Counter(clean)
        top = c.most_common(1)[0][1]
        return top / len(clean)

    opening_reuse = _reuse_rate(openings)
    transition_reuse = _reuse_rate(transitions)
    cta_reuse = _reuse_rate(ctas)
    skel_reuse = _reuse_rate(skeletons)

    blocked = False
    if block_any_high_pair and n >= 2 and high >= 1:
        blocked = True
        reasons.append("near_duplicate_any_high_pair")
    if n >= 2 and high_sem >= 1:
        blocked = True
        if "semantic_template_near_duplicate" not in reasons:
            reasons.append("semantic_template_near_duplicate")
    if n >= 2 and max_sim >= extreme_similarity and high >= 1:
        blocked = True
        if "near_duplicate_extreme_pair" not in reasons:
            reasons.append("near_duplicate_extreme_pair")
    if n >= 3 and pairs > 0 and frac >= pair_fraction_limit:
        blocked = True
        if "near_duplicate_batch_fraction" not in reasons:
            reasons.append("near_duplicate_batch_fraction")
    for fam, (fpairs, fhigh) in family_stats.items():
        if fpairs >= 1 and (fhigh / fpairs) >= pair_fraction_limit:
            blocked = True
            code = f"near_duplicate_family_fraction:{fam}"
            if code not in reasons:
                reasons.append(code)
    if n >= 5 and skel_reuse > skeleton_cluster_limit:
        blocked = True
        reasons.append("dominant_skeleton_cluster")
    if n >= 5 and opening_reuse > opening_reuse_limit:
        blocked = True
        reasons.append("opening_template_reuse")
    if n >= 5 and transition_reuse > transition_reuse_limit:
        blocked = True
        reasons.append("identical_transition_reuse")
    if n >= 5 and cta_reuse > cta_reuse_limit:
        blocked = True
        reasons.append("identical_cta_mass_reuse")
    if not blocked:
        reasons.append("near_duplicate_ok")

    metrics = {
        "lexical_similarity_raw": round(max_sim, 4),
        "semantic_template_similarity": round(max_sem, 4),
        "normalized_skeleton_similarity": round(max_skel, 4),
        "CTA_reuse_rate": round(cta_reuse, 4),
        "opening_reuse_rate": round(opening_reuse, 4),
        "sentence_pattern_reuse_rate": round(skel_reuse, 4),
        "transition_reuse_rate": round(transition_reuse, 4),
        "dominant_skeleton_share": round(skel_reuse, 4),
        "high_semantic_pairs": high_sem,
    }

    return NearDuplicateAudit(
        total_drafts=n,
        compared_pairs=pairs,
        high_similarity_pairs=high,
        max_similarity=round(max(max_sim, max_sem, max_skel), 4),
        pair_fraction_high=round(frac, 4),
        threshold=similarity_threshold,
        blocked=blocked,
        reason_codes=reasons,
        sample_pairs=samples,
        lexical_similarity_raw_max=round(max_sim, 4),
        semantic_template_similarity_max=round(max_sem, 4),
        normalized_skeleton_similarity_max=round(max_skel, 4),
        high_semantic_pairs=high_sem,
        cta_reuse_rate=round(cta_reuse, 4),
        opening_reuse_rate=round(opening_reuse, 4),
        sentence_pattern_reuse_rate=round(skel_reuse, 4),
        dominant_skeleton_share=round(skel_reuse, 4),
        metrics=metrics,
    )


def subject_is_generic_contrato(subject: str, company: str | None = None) -> bool:
    s = (subject or "").strip().lower()
    if s.startswith("contrato ") or s == "contrato":
        return True
    if company and s == f"contrato {company.strip().lower()}":
        return True
    return False


def blind_template_audit(drafts: list[dict[str, Any]]) -> dict[str, Any]:
    """Adversarial: strip variable facts and ask if messages share one template."""
    audit = audit_near_duplicates(drafts)
    return {
        "pass": not audit.blocked,
        "blocked": audit.blocked,
        "reason_codes": audit.reason_codes,
        "metrics": audit.metrics,
        "sample_pairs": audit.sample_pairs[:5],
        "question": (
            "Se eu remover os fatos variáveis, estas mensagens ainda parecem o mesmo template?"
        ),
        "answer": "YES_SAME_TEMPLATE" if audit.blocked else "NO_SUFFICIENT_VARIATION",
    }
