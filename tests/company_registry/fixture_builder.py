"""Build tiny RFB-shaped zip fixtures at test time (no binary in git)."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path

from scripts.linkage.keys import is_valid_cnpj14


def make_cnpj(base12: str) -> str:
    weights1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    weights2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]

    def dv(nums: str, weights: list[int]) -> int:
        total = sum(int(n) * w for n, w in zip(nums, weights, strict=True))
        rem = total % 11
        return 0 if rem < 2 else 11 - rem

    d1 = dv(base12, weights1)
    d2 = dv(base12 + str(d1), weights2)
    return base12 + str(d1) + str(d2)


def fixture_cnpjs() -> list[str]:
    out: list[str] = []
    for root, ordem in (("11222333", "0001"), ("34028316", "0001"), ("60746948", "0001")):
        c = make_cnpj(root + ordem)
        assert is_valid_cnpj14(c), c
        out.append(c)
    return out


def _est_row(cnpj: str, fantasia: str, sit: str, cnae: str, uf: str, mun_code: str) -> list[str]:
    fields = [""] * 30
    fields[0], fields[1], fields[2] = cnpj[:8], cnpj[8:12], cnpj[12:14]
    fields[3] = "1"
    fields[4] = fantasia
    fields[5] = sit
    fields[6] = "20200101"
    fields[7] = "00"
    fields[10] = "20100101"
    fields[11] = cnae
    fields[13] = "RUA"
    fields[14] = "TEST"
    fields[15] = "100"
    fields[19] = uf
    fields[20] = mun_code
    fields[21] = "11"
    fields[22] = "99999999"
    fields[27] = "contato@example.com"
    return fields


def write_zip(path: Path, member: str, rows: list[list[str]]) -> None:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\n")
    for r in rows:
        w.writerow(r)
    data = buf.getvalue().encode("latin-1")
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(member, data)


def build_fixture_dir(target: Path) -> Path:
    """Write Empresas/Estabelecimentos zips + meta into target dir."""
    target.mkdir(parents=True, exist_ok=True)
    cnpjs = fixture_cnpjs()
    est_rows = [
        _est_row(cnpjs[0], "ALPHA ENG", "02", "7112000", "SC", "8105"),
        _est_row(cnpjs[1], "BETA OBRAS", "02", "4120400", "SC", "8105"),
        _est_row(cnpjs[2], "GAMA BAIXADA", "08", "7112000", "PR", "7535"),
    ]
    emp_rows = [
        [cnpjs[0][:8], "ALPHA ENGENHARIA LTDA", "2062", "49", "100000,00", "03", ""],
        [cnpjs[1][:8], "BETA CONSTRUCOES SA", "2046", "10", "5000000,00", "05", ""],
        [cnpjs[2][:8], "GAMA ENCERRADA LTDA", "2062", "49", "1000,00", "01", ""],
    ]
    write_zip(target / "Estabelecimentos0.zip", "ESTABELE", est_rows)
    write_zip(target / "Empresas0.zip", "EMPRECSV", emp_rows)
    (target / "fake.html").write_text(
        "<!DOCTYPE html><html><body>not a zip</body></html>", encoding="utf-8"
    )
    (target / "truncated.zip").write_bytes(b"PK\x03\x04incomplete")
    (target / "meta.json").write_text(json.dumps({"cnpjs": cnpjs}, indent=2) + "\n", encoding="utf-8")
    (target / "interest_cnpjs.txt").write_text("\n".join(cnpjs) + "\n", encoding="utf-8")
    return target
