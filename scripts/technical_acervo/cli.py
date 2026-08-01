#!/usr/bin/env python3
"""CLI — Acervo técnico-operacional EXTRA EMPREITEIRA LTDA.

Usage:
  python -m scripts.technical_acervo list
  python -m scripts.technical_acervo list --type CAT
  python -m scripts.technical_acervo show --cat 252025173593
  python -m scripts.technical_acervo show --art 10023860-0
  python -m scripts.technical_acervo show --cao 7-250004663-6
  python -m scripts.technical_acervo show --file arquivo5.pdf
  python -m scripts.technical_acervo search "estrutura metalica" --min-qty 500 --unit m2
  python -m scripts.technical_acervo search "edificacao tombada"
  python -m scripts.technical_acervo search "prevenção contra incêndio"
  python -m scripts.technical_acervo experiences --contractor Cobasi
  python -m scripts.technical_acervo match --service "estrutura metalica" --qty 500 --unit m2
  python -m scripts.technical_acervo ask "A Extra possui acervo de estrutura metálica acima de 500 m²?"
  python -m scripts.technical_acervo ask "A CAO está válida?"
  python -m scripts.technical_acervo ask "arquivo5 e arquivo8 são documentos diferentes?"
  python -m scripts.technical_acervo matrix
  python -m scripts.technical_acervo inventory --json
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from scripts.technical_acervo.format import (
    DISCLAIMER,
    dumps_json,
    format_item_hit,
    render_text_document,
    render_text_hits,
    render_text_inventory,
    render_text_match,
)
from scripts.technical_acervo.guards import cao_guard_notes, scan_store_for_pii
from scripts.technical_acervo.match import match_natural, match_requirement
from scripts.technical_acervo.search import (
    build_search_chunks,
    max_quantity_for_service,
    search_experiences,
    search_items,
)
from scripts.technical_acervo.store import DEFAULT_ACERVO_PATH, AcervoStore, load_store


def _load(args: argparse.Namespace) -> AcervoStore:
    path = getattr(args, "data", None) or DEFAULT_ACERVO_PATH
    return load_store(path)


def _out(payload: Any, *, as_json: bool, text: str) -> int:
    if as_json:
        print(dumps_json(payload))
    else:
        print(text)
    return 0


def cmd_inventory(args: argparse.Namespace) -> int:
    store = _load(args)
    inv = store.inventory()
    inv["dedup"] = store.assert_dedup_integrity()
    inv["pii_scan"] = scan_store_for_pii(store)
    return _out(inv, as_json=args.json, text=render_text_inventory(inv) + f"\n\nDedup OK: {inv['dedup']['ok']}")


def cmd_list(args: argparse.Namespace) -> int:
    store = _load(args)
    docs = store.documents
    if args.type:
        docs = [d for d in docs if (d.get("document_type") or "").upper() == args.type.upper()]
    rows = []
    lines = [f"=== DOCUMENTOS ({len(docs)}) ===", ""]
    for d in docs:
        rows.append(
            {
                "id": d["id"],
                "type": d.get("document_type"),
                "number": d.get("certificate_number"),
                "art": d.get("art_number"),
                "status": d.get("current_status"),
                "sources": d.get("source_files"),
                "aliases": d.get("duplicate_aliases"),
            }
        )
        lines.append(
            f"  [{d.get('document_type')}] {d.get('certificate_number')} "
            f"ART {d.get('art_number')} | {d.get('current_status')} | "
            f"{', '.join(d.get('source_files') or [])}"
        )
    if not args.type or args.type.upper() != "CAT":
        lines.append("")
        lines.append(f"=== EXPERIÊNCIAS ({len(store.experiences)}) ===")
        for e in store.experiences:
            rows.append(
                {
                    "experience_id": e["id"],
                    "title": e.get("title"),
                    "evidence_level": e.get("evidence_level"),
                    "individual_cat_not_provided": e.get("individual_cat_not_provided"),
                    "city": e.get("city"),
                }
            )
            flag = " [SOMENTE CAO]" if e.get("individual_cat_not_provided") else ""
            lines.append(f"  • {e.get('title')}{flag} — {e.get('city')}/{e.get('state')}")
    lines.append("")
    lines.append(DISCLAIMER)
    return _out({"documents": rows, "disclaimer": DISCLAIMER}, as_json=args.json, text="\n".join(lines))


def cmd_show(args: argparse.Namespace) -> int:
    store = _load(args)
    docs = store.find_document(
        certificate=args.cat or args.cao or args.certificate,
        art=args.art,
        source_file=args.file,
        document_type="CAO" if args.cao else ("CAT" if args.cat else None),
        query=args.query,
    )
    if not docs:
        msg = "Documento não encontrado."
        if args.json:
            print(dumps_json({"ok": False, "error": msg}))
        else:
            print(msg)
        return 1
    # Prefer exact cert match order
    doc = docs[0]
    exps = store.experiences_for_document(doc["id"])
    # For CAO, also attach experiences that are only on CAO
    if (doc.get("document_type") or "").upper() == "CAO":
        for eid in doc.get("linked_experience_ids") or []:
            e = store.get_experience(eid)
            if e and e not in exps:
                exps.append(e)
    payload = {
        "document": doc,
        "experiences": exps,
        "cao_notes": cao_guard_notes(doc),
        "disclaimer": DISCLAIMER,
    }
    return _out(payload, as_json=args.json, text=render_text_document(doc, exps))


def cmd_search(args: argparse.Namespace) -> int:
    store = _load(args)
    hits = search_items(
        store,
        args.query,
        min_quantity=args.min_qty,
        unit=args.unit,
        activity=args.activity,
        evidence=args.evidence,
        document_type=args.type,
        limit=args.limit,
    )
    # If no item hits, try experience-level (tombada etc.)
    exp_hits: list[dict[str, Any]] = []
    if not hits or args.experiences_too:
        exp_hits = search_experiences(store, args.query, limit=args.limit)
    formatted = [format_item_hit(h) for h in hits]
    payload = {
        "query": args.query,
        "items": formatted,
        "experiences": exp_hits,
        "disclaimer": DISCLAIMER,
    }
    text_parts = [render_text_hits(hits, title=f"BUSCA: {args.query}")]
    if exp_hits and (not hits or args.experiences_too):
        text_parts.append("")
        text_parts.append(f"=== EXPERIÊNCIAS ({len(exp_hits)}) ===")
        for e in exp_hits:
            text_parts.append(
                f"  • {e.get('title')} | {e.get('city')}/{e.get('state')} | "
                f"{e.get('document_type')} {e.get('certificate_number')} | "
                f"evidência={e.get('evidence_level')}"
            )
            if e.get("individual_cat_not_provided"):
                text_parts.append("    ⚠ Somente CAO — CAT individual não fornecida.")
            for r in (e.get("restrictions") or [])[:2]:
                text_parts.append(f"    Ressalva: {r}")
        text_parts.append("")
        text_parts.append(DISCLAIMER)
    return _out(payload, as_json=args.json, text="\n".join(text_parts))


def cmd_experiences(args: argparse.Namespace) -> int:
    store = _load(args)
    if args.contractor:
        exps = store.experiences_for_contractor(args.contractor)
    elif args.query:
        exps = [
            e
            for h in search_experiences(store, args.query)
            if (e := store.get_experience(h["experience_id"])) is not None
        ]
    else:
        exps = list(store.experiences)
    if args.cao_only:
        exps = [e for e in exps if e.get("individual_cat_not_provided") or e.get("evidence_level") == "operational_certificate_only"]
    payload = {"experiences": exps, "count": len(exps), "disclaimer": DISCLAIMER}
    lines = [f"=== EXPERIÊNCIAS ({len(exps)}) ===", ""]
    for e in exps:
        doc = store.get_document(e.get("primary_document_id") or "")
        lines.append(f"• {e.get('title')}")
        lines.append(f"  Contratante: {e.get('contractor')} | {e.get('city')}/{e.get('state')}")
        lines.append(
            f"  Documento: {(doc or {}).get('document_type')} {(doc or {}).get('certificate_number')} "
            f"ART {(doc or {}).get('art_number')} | evidência={e.get('evidence_level')}"
        )
        lines.append(f"  Fontes: {', '.join((doc or {}).get('source_files') or [])}")
        if e.get("individual_cat_not_provided"):
            lines.append("  ⚠ Somente CAO — CAT individual não fornecida.")
        for item in (e.get("technical_items") or [])[:5]:
            lines.append(
                f"    - {item.get('service')}: {item.get('quantity')} {item.get('unit')} "
                f"(p.{item.get('source_page')})"
            )
        lines.append("")
    lines.append(DISCLAIMER)
    return _out(payload, as_json=args.json, text="\n".join(lines))


def cmd_match(args: argparse.Namespace) -> int:
    store = _load(args)
    result = match_requirement(
        store,
        service=args.service,
        quantity=args.qty,
        unit=args.unit,
        activity=args.activity,
        allow_sum=bool(args.allow_sum),
        require_cat_attestation=bool(args.require_cat),
    )
    return _out(result, as_json=args.json, text=render_text_match(result))


def cmd_ask(args: argparse.Namespace) -> int:
    """Natural language questions over the acervo."""
    store = _load(args)
    q = args.question.strip()
    nq = q.lower()

    # Special-case structured questions
    if re.search(r"arquivo\s*5|arquivo5", nq) and re.search(r"arquivo\s*8|arquivo8", nq):
        dedup = store.assert_dedup_integrity()
        payload = {
            "question": q,
            "answer": (
                "Não. arquivo5.pdf e arquivo8.pdf são a mesma CAT nº 252025174528 "
                "(aliases de origem; um único documento canônico)."
                if dedup.get("arquivo5_arquivo8_same_document")
                else "Mapeamento inesperado — revisar store."
            ),
            "same_document": dedup.get("arquivo5_arquivo8_same_document"),
            "document_id": dedup.get("shared_document_id"),
            "certificate_number": dedup.get("certificate"),
            "disclaimer": DISCLAIMER,
        }
        text = (
            f"Pergunta: {q}\nResposta: {payload['answer']}\n"
            f"Documento: CAT {payload.get('certificate_number')} id={payload.get('document_id')}\n\n"
            f"{DISCLAIMER}"
        )
        return _out(payload, as_json=args.json, text=text)

    if re.search(r"\bcao\b", nq) and re.search(r"v[aá]lid|vencid|expir", nq):
        caos = store.caos()
        doc = caos[0] if caos else None
        notes = cao_guard_notes(doc) if doc else ["CAO não encontrada."]
        payload = {
            "question": q,
            "document": doc,
            "current_status": (doc or {}).get("current_status"),
            "valid_until": (doc or {}).get("valid_until"),
            "issued_at": (doc or {}).get("issued_at"),
            "notes": notes,
            "disclaimer": DISCLAIMER,
        }
        text = (
            f"Pergunta: {q}\n"
            f"CAO nº {(doc or {}).get('certificate_number')}: status={(doc or {}).get('current_status')} "
            f"(válida até {(doc or {}).get('valid_until')}; emissão interna {(doc or {}).get('issued_at')}).\n"
            + "\n".join(f"  • {n}" for n in notes)
            + f"\n\n{DISCLAIMER}"
        )
        return _out(payload, as_json=args.json, text=text)

    if re.search(r"somente\s+por\s+cao|apenas\s+pela\s+cao|s[oó]\s+por\s+cao|sem\s+cat\s+individual", nq):
        exps = [
            e
            for e in store.experiences
            if e.get("individual_cat_not_provided") or e.get("evidence_level") == "operational_certificate_only"
        ]
        payload = {"question": q, "experiences": exps, "disclaimer": DISCLAIMER}
        lines = [f"Pergunta: {q}", f"Experiências somente CAO ({len(exps)}):", ""]
        for e in exps:
            lines.append(f"  • {e.get('title')} — {e.get('city')}/{e.get('state')}")
            lines.append(f"    ART: {', '.join(e.get('linked_arts') or [])}")
            lines.append(f"    evidence_level={e.get('evidence_level')}")
        lines.append("")
        lines.append(DISCLAIMER)
        return _out(payload, as_json=args.json, text="\n".join(lines))

    if re.search(r"maior.*(hidr[aá]ul|rede hidrossan)", nq):
        mx = max_quantity_for_service(store, "instalacoes hidraulicas", unit="m2")
        # also try rede hidrossanitaria
        mx2 = max_quantity_for_service(store, "rede hidrossanitaria", unit="m2")
        candidates = (mx.get("candidates") or []) + (mx2.get("candidates") or [])
        candidates = sorted(candidates, key=lambda c: -(c.get("quantity") or 0))
        best = candidates[0] if candidates else None
        payload = {"question": q, "best": best, "candidates": candidates[:10], "disclaimer": DISCLAIMER}
        text = render_text_hits([best] if best else [], title="MAIOR HIDRÁULICA INDIVIDUAL")
        return _out(payload, as_json=args.json, text=text)

    # Quantity / acervo match style questions
    if re.search(r"\d+[.,]?\d*\s*m", nq) or re.search(r"acima\s+de|maior\s+que|minimo", nq):
        result = match_natural(store, q)
        result["question"] = q
        return _out(result, as_json=args.json, text=f"Pergunta: {q}\n\n" + render_text_match(result))

    # Default: search experiences + items
    items = search_items(store, q, limit=args.limit)
    exps = search_experiences(store, q, limit=args.limit)
    payload = {
        "question": q,
        "items": [format_item_hit(h) for h in items],
        "experiences": exps,
        "disclaimer": DISCLAIMER,
    }
    text = f"Pergunta: {q}\n\n" + render_text_hits(items, title="ITENS")
    if exps:
        text += "\n\n=== EXPERIÊNCIAS ===\n"
        for e in exps:
            text += (
                f"  • {e.get('title')} | {e.get('city')} | "
                f"{e.get('document_type')} {e.get('certificate_number')} | "
                f"{e.get('evidence_level')}\n"
            )
            if e.get("individual_cat_not_provided"):
                text += "    ⚠ Somente CAO\n"
        text += f"\n{DISCLAIMER}"
    return _out(payload, as_json=args.json, text=text)


def cmd_matrix(args: argparse.Namespace) -> int:
    """Matriz de aderência técnico-documental (serviço × max qty × evidência)."""
    store = _load(args)
    # Aggregate by normalized service
    from scripts.technical_acervo.normalize import normalize_text

    matrix: dict[str, dict[str, Any]] = {}
    for row in store.experience_items_flat():
        item = row["item"]
        exp = row["experience"]
        doc = row["document"]
        key = normalize_text(item.get("service"))
        qty = item.get("quantity") or 0
        cur = matrix.get(key)
        if cur is None or qty > cur["max_quantity"]:
            matrix[key] = {
                "service": item.get("service"),
                "max_quantity": qty,
                "unit": item.get("unit"),
                "activity": item.get("activity"),
                "experience_id": exp.get("id"),
                "title": exp.get("title"),
                "document_type": (doc or {}).get("document_type"),
                "certificate_number": (doc or {}).get("certificate_number"),
                "art_number": (doc or {}).get("art_number"),
                "source_file": item.get("source_file"),
                "source_page": item.get("source_page"),
                "evidence_level": exp.get("evidence_level"),
                "document_status": (doc or {}).get("current_status"),
            }
    rows = sorted(matrix.values(), key=lambda r: (-(r["max_quantity"] or 0), r["service"] or ""))
    payload = {"matrix": rows, "count": len(rows), "disclaimer": DISCLAIMER}
    lines = ["=== MATRIZ DE ADERÊNCIA TÉCNICO-DOCUMENTAL ===", ""]
    for r in rows:
        lines.append(
            f"  {r['service']}: max {r['max_quantity']} {r['unit']} | "
            f"{r['document_type']} {r['certificate_number']} ART {r['art_number']} | "
            f"{r['source_file']} p.{r['source_page']} | {r['evidence_level']}"
        )
    lines.append("")
    lines.append(DISCLAIMER)
    return _out(payload, as_json=args.json, text="\n".join(lines))


def cmd_chunks(args: argparse.Namespace) -> int:
    store = _load(args)
    chunks = build_search_chunks(store)
    payload = {"chunks": chunks, "count": len(chunks), "disclaimer": DISCLAIMER}
    if args.json:
        print(dumps_json(payload))
    else:
        print(f"Chunks: {len(chunks)}")
        for ch in chunks[: args.limit]:
            print(f"  [{ch.get('chunk_type')}] {(ch.get('text') or '')[:120]}")
        print(DISCLAIMER)
    return 0


def _add_common_flags(sp: argparse.ArgumentParser) -> None:
    """Flags available after subcommand (argparse does not inherit parent optionals into subs)."""
    sp.add_argument(
        "--data",
        type=Path,
        default=None,
        help=f"Path do store canônico (default: {DEFAULT_ACERVO_PATH})",
    )
    sp.add_argument("--json", action="store_true", help="Saída JSON")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Acervo técnico-operacional EXTRA EMPREITEIRA LTDA.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    # Also allow global flags before subcommand.
    p.add_argument(
        "--data",
        type=Path,
        default=None,
        help=f"Path do store canônico (default: {DEFAULT_ACERVO_PATH})",
    )
    p.add_argument("--json", action="store_true", help="Saída JSON")
    sub = p.add_subparsers(dest="command", required=True)

    inv = sub.add_parser("inventory", help="Contagens e integridade")
    _add_common_flags(inv)
    inv.set_defaults(func=cmd_inventory)

    lst = sub.add_parser("list", help="Listar documentos e experiências")
    _add_common_flags(lst)
    lst.add_argument("--type", choices=["CAT", "CAO", "ATESTADO"], default=None)
    lst.set_defaults(func=cmd_list)

    show = sub.add_parser("show", help="Consultar documento por CAT/ART/CAO/arquivo")
    _add_common_flags(show)
    show.add_argument("--cat", default=None)
    show.add_argument("--cao", default=None)
    show.add_argument("--certificate", default=None)
    show.add_argument("--art", default=None)
    show.add_argument("--file", default=None)
    show.add_argument("--query", default=None)
    show.set_defaults(func=cmd_show)

    search = sub.add_parser("search", help="Buscar serviços / tags")
    _add_common_flags(search)
    search.add_argument("query")
    search.add_argument("--min-qty", type=float, default=None)
    search.add_argument("--unit", default=None)
    search.add_argument("--activity", default=None)
    search.add_argument("--evidence", default=None)
    search.add_argument("--type", choices=["CAT", "CAO"], default=None)
    search.add_argument("--limit", type=int, default=20)
    search.add_argument("--experiences-too", action="store_true")
    search.set_defaults(func=cmd_search)

    exp = sub.add_parser("experiences", help="Listar/filtrar experiências")
    _add_common_flags(exp)
    exp.add_argument("--contractor", default=None)
    exp.add_argument("--query", default=None)
    exp.add_argument("--cao-only", action="store_true")
    exp.set_defaults(func=cmd_experiences)

    match = sub.add_parser("match", help="Comparar exigência de edital ao acervo")
    _add_common_flags(match)
    match.add_argument("--service", required=True)
    match.add_argument("--qty", type=float, default=None)
    match.add_argument("--unit", default="m2")
    match.add_argument("--activity", default=None)
    match.add_argument("--allow-sum", action="store_true")
    match.add_argument("--require-cat", action="store_true")
    match.set_defaults(func=cmd_match)

    ask = sub.add_parser("ask", help="Pergunta em linguagem natural")
    _add_common_flags(ask)
    ask.add_argument("question")
    ask.add_argument("--limit", type=int, default=15)
    ask.set_defaults(func=cmd_ask)

    matrix = sub.add_parser("matrix", help="Matriz de aderência técnico-documental")
    _add_common_flags(matrix)
    matrix.set_defaults(func=cmd_matrix)

    chunks = sub.add_parser("chunks", help="Listar chunks semânticos de busca")
    _add_common_flags(chunks)
    chunks.add_argument("--limit", type=int, default=30)
    chunks.set_defaults(func=cmd_chunks)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
