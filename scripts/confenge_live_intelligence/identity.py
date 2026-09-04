"""LI-W2 §B — identidade de empresa: ``company_digest`` publico e ``company_ref`` interno.

Duas funcoes, dois papeis distintos e nao intercambiaveis:

* :func:`cnpj_digest` — **publica**. Reimplementacao byte-a-byte de ``hashCnpj``
  do consumidor (``tjsasakifln/web-cfg``, ``scripts/conversion/cnpj.cjs``, blob
  ``8b88a894e`` @ ``dea6457a14b17279713fb357cbce6c6e8087ce6c``; proveniencia
  congelada em ``docs/contracts/confenge-live-intelligence-v1.md``). E o unico
  identificador de empresa que atravessa a fronteira publica, e serve tanto para
  ``company_digest`` quanto para ``buyer_digest`` (§A.4.1 / AC6) — **funcao
  unica**, porque um segundo esquema de identidade e um segundo lugar para
  divergir.
* :func:`company_ref_from_root8` — **interna**. Pseudonimo 1:1 com a empresa,
  usado em coluna do motor (migration 105), em ``subject_key`` de evento de
  empresa (§C.2) e em artefato de auditoria. **PROIBIDO** em qualquer payload
  publico (AC8).

Ambas sao puras: sem IO, sem relogio, sem banco.

``cnpj_digest`` devolve ``None`` — **nunca** ``""`` — para entrada que nao reduza
a exatamente 14 digitos. String vazia como identidade e descarte silencioso: o
consumidor faria lookup de ``companies/.json`` e receberia 404 mudo. O chamador e
obrigado a tratar o ``None`` de forma declarada (AC6:
``buyer_cnpj_not_hashable`` + ``coverage.buyers_unhashable``).
"""

from __future__ import annotations

import hashlib
from typing import Final

# Salt do consumidor. NAO renomear, NAO parametrizar: qualquer alteracao aqui
# quebra TODO lookup do web-cfg de forma silenciosa (404 em massa, sem excecao
# em lugar nenhum). Risco aberto #1 da story — mitigado por vetores fixos em
# tests/confenge_live_intelligence/test_identity.py.
CNPJ_DIGEST_SALT: Final[str] = "confenge-conversion"
CNPJ_DIGEST_SEPARATOR: Final[str] = "|"
CNPJ_DIGEST_LENGTH: Final[int] = 16

# Pseudonimo interno. Versao no PREFIXO por decisao de §B.2: mudanca de formula
# = `cref2:`, e o CHECK da migration 105 muda junto, de forma visivel.
COMPANY_REF_PREFIX: Final[str] = "cref1:"
COMPANY_REF_SALT: Final[str] = "confenge-live-intelligence|company_ref|v1|"
COMPANY_REF_LENGTH: Final[int] = 32


def only_digits(value: object) -> str:
    """Reducao a digitos, espelhando ``onlyDigits`` do consumidor.

    O consumidor tem duas revisoes desta funcao (``8b88a894e`` e ``1a5452a2d``);
    elas divergem **apenas** na coercao de entrada nao-string. Para uma string de
    CNPJ, ambas reduzem a ``raw.replace(/\\D/g, "")`` — que e exatamente isto.
    """
    if value is None:
        return ""
    return "".join(ch for ch in str(value) if ch.isdigit())


def cnpj_digest(cnpj: str | None) -> str | None:
    """``sha256("confenge-conversion|" + cnpj14).hexdigest()[:16]`` ou ``None``.

    ``None`` (nunca ``""``) quando a entrada nao reduz a exatamente 14 digitos.
    """
    digits = only_digits(cnpj)
    if len(digits) != 14:
        return None
    material = f"{CNPJ_DIGEST_SALT}{CNPJ_DIGEST_SEPARATOR}{digits}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:CNPJ_DIGEST_LENGTH]


def company_ref_from_root8(company_root8: str) -> str:
    """``"cref1:" + sha256("confenge-live-intelligence|company_ref|v1|" + root8)[:32]``.

    Levanta ``ValueError`` para raiz que nao tenha 8 digitos — o formato e travado
    por CHECK na migration 105 (``^cref1:[0-9a-f]{32}$``) e um valor derivado de
    raiz invalida seria um pseudonimo que nao identifica nada.
    """
    root = str(company_root8 or "")
    if len(root) != 8 or not root.isdigit():
        raise ValueError(f"company_root8 invalido para company_ref: {company_root8!r}")
    material = f"{COMPANY_REF_SALT}{root}"
    return COMPANY_REF_PREFIX + hashlib.sha256(material.encode("utf-8")).hexdigest()[:COMPANY_REF_LENGTH]
