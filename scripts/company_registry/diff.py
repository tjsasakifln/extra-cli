"""Diff between two official registry releases."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from scripts.company_registry.paths import db_path_for_release
from scripts.company_registry.store import connect_db


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def diff_releases(
    old_release_id: str,
    new_release_id: str,
    *,
    sample_limit: int = 50,
) -> dict[str, Any]:
    old_db = db_path_for_release(old_release_id)
    new_db = db_path_for_release(new_release_id)
    if not old_db.is_file() or not new_db.is_file():
        return {
            "ok": False,
            "errors": [
                e
                for e, p in (
                    ("old_missing", old_db.is_file()),
                    ("new_missing", new_db.is_file()),
                )
                if not p
            ],
            "old_release_id": old_release_id,
            "new_release_id": new_release_id,
        }

    old = connect_db(old_db, readonly=True)
    new = connect_db(new_db, readonly=True)
    try:
        old_ids = {r["cnpj14"] for r in old.execute("SELECT cnpj14 FROM establishments")}
        new_ids = {r["cnpj14"] for r in new.execute("SELECT cnpj14 FROM establishments")}
        added = sorted(new_ids - old_ids)
        removed = sorted(old_ids - new_ids)
        common = old_ids & new_ids

        changes = {
            "situacao": [],
            "razao_social": [],
            "nome_fantasia": [],
            "cnae": [],
            "porte": [],
            "municipio_uf": [],
            "capital": [],
        }
        for cnpj in list(common)[:5000]:  # bound scan
            o = old.execute(
                """
                SELECT e.situacao_cadastral, e.nome_fantasia, e.cnae_principal, e.uf, e.municipio,
                       c.razao_social, c.porte, c.capital_social
                FROM establishments e
                LEFT JOIN companies c ON c.cnpj_basico = e.cnpj_basico
                WHERE e.cnpj14 = ?
                """,
                (cnpj,),
            ).fetchone()
            n = new.execute(
                """
                SELECT e.situacao_cadastral, e.nome_fantasia, e.cnae_principal, e.uf, e.municipio,
                       c.razao_social, c.porte, c.capital_social
                FROM establishments e
                LEFT JOIN companies c ON c.cnpj_basico = e.cnpj_basico
                WHERE e.cnpj14 = ?
                """,
                (cnpj,),
            ).fetchone()
            if not o or not n:
                continue
            if o["situacao_cadastral"] != n["situacao_cadastral"]:
                changes["situacao"].append(
                    {"cnpj": cnpj, "old": o["situacao_cadastral"], "new": n["situacao_cadastral"]}
                )
            if o["razao_social"] != n["razao_social"]:
                changes["razao_social"].append(
                    {"cnpj": cnpj, "old": o["razao_social"], "new": n["razao_social"]}
                )
            if o["nome_fantasia"] != n["nome_fantasia"]:
                changes["nome_fantasia"].append(
                    {"cnpj": cnpj, "old": o["nome_fantasia"], "new": n["nome_fantasia"]}
                )
            if o["cnae_principal"] != n["cnae_principal"]:
                changes["cnae"].append(
                    {"cnpj": cnpj, "old": o["cnae_principal"], "new": n["cnae_principal"]}
                )
            if o["porte"] != n["porte"]:
                changes["porte"].append({"cnpj": cnpj, "old": o["porte"], "new": n["porte"]})
            if (o["municipio"], o["uf"]) != (n["municipio"], n["uf"]):
                changes["municipio_uf"].append(
                    {
                        "cnpj": cnpj,
                        "old": f"{o['municipio']}/{o['uf']}",
                        "new": f"{n['municipio']}/{n['uf']}",
                    }
                )
            if o["capital_social"] != n["capital_social"]:
                changes["capital"].append(
                    {"cnpj": cnpj, "old": o["capital_social"], "new": n["capital_social"]}
                )

        summary = {k: len(v) for k, v in changes.items()}
        sampled = {k: v[:sample_limit] for k, v in changes.items()}
        return {
            "ok": True,
            "generated_at": utc_now(),
            "old_release_id": old_release_id,
            "new_release_id": new_release_id,
            "cnpjs_added_n": len(added),
            "cnpjs_removed_n": len(removed),
            "cnpjs_added_sample": added[:sample_limit],
            "cnpjs_removed_sample": removed[:sample_limit],
            "change_counts": summary,
            "changes_sample": sampled,
            "note": "Historical provenance of commercial runs is not deleted by cadastral diffs.",
        }
    finally:
        old.close()
        new.close()
