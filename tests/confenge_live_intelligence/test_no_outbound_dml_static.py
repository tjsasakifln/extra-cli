"""AC11 — zero escrita cruzada com o outbound (teste estatico, glob-based).

Varre ``scripts/confenge_live_intelligence/**.py`` por GLOB (nao por lista fixa
de arquivos), de modo que o teste continue valido quando ``events.py`` for
adicionado na story 2.

AR-2 (gate HIGH-RISK do @architect, ADR-040 §"Gate HIGH-RISK"). A prova original
do AC11 era de **ausencia de literal**: exigia verbo DML e nome de tabela
outbound na MESMA string. O idiom ``f"DELETE FROM public.{table}"`` com ``table``
vindo de uma tupla local evadia a checagem — os dois pedacos ficam em literais
separados. A segunda metade deste modulo fecha essa evasao: todo DML construido
dinamicamente no pacote tem de interpolar nomes de tabela resolviveis a UMA
UNICA constante nomeada, exportada pelo pacote e importada por nome aqui.

Criterio de aceite do proprio teste: uma tupla local nova (por exemplo em
``events.py`` na story 2) tem de **quebrar** este teste, nao passar por ele. Isso
e provado pelos auto-testes negativos ao final, que rodam o checker sobre fontes
sinteticas — sem eles AR-2 apenas reproduziria o defeito do AC11 um nivel acima.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

import scripts.confenge_live_intelligence as engine_pkg
from scripts.confenge_live_intelligence import ALLOWED_WRITE_TARGETS

PACKAGE_DIR = Path(__file__).resolve().parents[2] / "scripts" / "confenge_live_intelligence"
ENGINE_PACKAGE = "scripts.confenge_live_intelligence"
WRITE_GUARD = "assert_write_target"

OUTBOUND_TABLES = (
    "opportunity_intel",
    "confenge_company_target_fit_current",
    "confenge_company_target_fit_history",
    "confenge_target_fit_dirty",
    "confenge_target_fit_events",
    "confenge_target_fit_shadow",
    "pncp_supplier_contracts",
    "canonical_public_snapshots",
    "canonical_snapshot_dossiers",
    "canonical_snapshot_source_watermarks",
    "confenge_company_sector_current",
    "confenge_company_sector_history",
    "v_open_opportunities_canonical",
    "v_contracts_canonical_v2",
    "pncp_raw_bids",
    "sc_public_entities",
)

DML = re.compile(r"\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM|TRUNCATE|MERGE\s+INTO)\b", re.IGNORECASE)


def _python_sources() -> list[Path]:
    files = sorted(PACKAGE_DIR.glob("**/*.py"))
    assert files, "glob nao encontrou nenhum modulo do motor inbound"
    return files


def _code_strings(path: Path) -> list[str]:
    """Literais de string do modulo, EXCLUINDO docstrings.

    Comentario e docstring descrevem a proibicao; so o codigo executavel pode
    viola-la. Varredura textual crua produziria falso positivo sobre a propria
    documentacao da invariante.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                docstrings.add(id(body[0].value))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings
    ]


def _sql_statements(path: Path) -> list[str]:
    return [s for s in _code_strings(path) if DML.search(s)]


@pytest.mark.parametrize("path", _python_sources(), ids=lambda p: p.name)
def test_no_dml_over_outbound_tables(path: Path) -> None:
    for statement in _sql_statements(path):
        for table in OUTBOUND_TABLES:
            assert not re.search(rf"\b{re.escape(table)}\b", statement), (
                f"{path.name}: DML alcanca tabela outbound {table!r} — proibido por AC11.\ntrecho: {statement[:200]!r}"
            )


@pytest.mark.parametrize("path", _python_sources(), ids=lambda p: p.name)
def test_no_reference_to_target_fit_dirty(path: Path) -> None:
    """R3 — ausencia TOTAL de escrita em confenge_target_fit_dirty."""
    for statement in _code_strings(path):
        if "confenge_target_fit_dirty" not in statement:
            continue
        assert not DML.search(statement), f"{path.name}: escrita em confenge_target_fit_dirty"


def test_no_scoring_or_ranking_import() -> None:
    """AC6 — nenhum import de opportunity_intel.scoring / .ranking."""
    for path in _python_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert not module.endswith(("opportunity_intel.scoring", "opportunity_intel.ranking")), (
                    f"{path.name}: import proibido de {module}"
                )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    assert "opportunity_intel.scoring" not in alias.name, path.name
                    assert "opportunity_intel.ranking" not in alias.name, path.name


def test_no_outbound_module_imports_live_intelligence() -> None:
    """Evidencia parcial de AC2: nenhum caminho outbound importa o motor inbound."""
    root = PACKAGE_DIR.parent
    outbound_dirs = (
        "confenge_target_fit",
        "confenge_outreach_pipeline",
        "warmbly_bridge",
        "confenge_contact_resolution",
        "opportunity_intel",
    )
    offenders: list[str] = []
    for name in outbound_dirs:
        directory = root / name
        if not directory.exists():
            continue
        for path in directory.glob("**/*.py"):
            if "confenge_live_intelligence" in path.read_text(encoding="utf-8"):
                offenders.append(str(path))
    assert not offenders, f"modulo outbound referencia o motor inbound: {offenders}"


# ---------------------------------------------------------------------------
# AR-2 — fechamento da evasao de SQL dinamico
# ---------------------------------------------------------------------------


def _sanctioned_allowlist_names() -> frozenset[str]:
    """Identificadores da allowlist, DERIVADOS do que o pacote exporta.

    Deliberadamente nao e uma lista escrita a mao neste arquivo: uma lista local
    seria uma segunda allowlist e o teste passaria a proteger a si mesmo em vez
    de proteger o motor.
    """
    names = set()
    for name in engine_pkg.__all__:
        value = getattr(engine_pkg, name)
        if isinstance(value, (tuple, list, set, frozenset)) and all(isinstance(v, str) for v in value):
            if frozenset(value) == ALLOWED_WRITE_TARGETS:
                names.add(name)
    return frozenset(names)


SANCTIONED_ALLOWLIST_NAMES = _sanctioned_allowlist_names()


def test_package_exports_a_single_resolvable_write_allowlist() -> None:
    assert "ALLOWED_WRITE_TARGETS" in SANCTIONED_ALLOWLIST_NAMES, (
        f"o pacote deve exportar ALLOWED_WRITE_TARGETS; derivados encontrados: {sorted(SANCTIONED_ALLOWLIST_NAMES)}"
    )
    assert ALLOWED_WRITE_TARGETS, "allowlist vazia tornaria a prova vacua"


def test_write_allowlist_is_disjoint_from_outbound_tables() -> None:
    """Sem isto, AR-2 reproduz o defeito do AC11 um nivel acima.

    Bastaria acrescentar ``opportunity_intel`` a ``ALLOWED_WRITE_TARGETS`` para
    que todo o resto continuasse verde.
    """
    intersecao = ALLOWED_WRITE_TARGETS & frozenset(OUTBOUND_TABLES)
    assert not intersecao, f"allowlist de escrita contem tabela outbound: {sorted(intersecao)}"
    fora_do_prefixo = {t for t in ALLOWED_WRITE_TARGETS if not t.startswith("confenge_live_intelligence_")}
    assert not fora_do_prefixo, f"alvo de escrita fora do namespace do motor: {sorted(fora_do_prefixo)}"


def _literal_parts(node: ast.AST) -> str:
    """Concatena as partes constantes de uma construcao dinamica de string."""
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value for v in node.values if isinstance(v, ast.Constant) and isinstance(v.value, str))
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp):
        return _literal_parts(node.left) + " " + _literal_parts(node.right)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        return _literal_parts(node.func.value)
    return ""


def _interpolated_slots(node: ast.AST) -> list[ast.AST]:
    """Expressoes interpoladas em uma construcao dinamica de string."""
    if isinstance(node, ast.JoinedStr):
        return [v.value for v in node.values if isinstance(v, ast.FormattedValue)]
    if isinstance(node, ast.BinOp):
        slots: list[ast.AST] = []
        for side in (node.left, node.right):
            if isinstance(side, ast.Constant):
                continue
            if isinstance(side, (ast.JoinedStr, ast.BinOp)):
                slots.extend(_interpolated_slots(side))
            elif isinstance(side, ast.Tuple):
                slots.extend(side.elts)
            else:
                slots.append(side)
        return slots
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "format":
        return [*node.args, *[kw.value for kw in node.keywords]]
    return []


def _dynamic_string_nodes(tree: ast.AST) -> list[ast.AST]:
    out: list[ast.AST] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            out.append(node)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Mod, ast.Add)):
            if isinstance(node.left, ast.Constant) and isinstance(node.left.value, str):
                out.append(node)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "format":
            target = node.func.value
            if isinstance(target, (ast.Constant, ast.JoinedStr)):
                out.append(node)
    return out


def _name_bindings(tree: ast.AST, identifier: str) -> list[ast.AST]:
    """Todas as expressoes das quais ``identifier`` recebe valor no modulo."""
    sources: list[ast.AST] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.For, ast.AsyncFor)):
            if isinstance(node.target, ast.Name) and node.target.id == identifier:
                sources.append(node.iter)
        elif isinstance(node, ast.comprehension):
            if isinstance(node.target, ast.Name) and node.target.id == identifier:
                sources.append(node.iter)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == identifier:
                    sources.append(node.value)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == identifier and node.value is not None:
                sources.append(node.value)
    return sources


def _accumulation_violations(tree: ast.AST, label: str) -> list[str]:
    """Proibicao plana: DML nao pode ser montado por acumulacao sobre um nome.

    A familia ``sql += table`` / ``"".join([verbo, table])`` produz o statement
    final apenas em runtime — nenhum no da AST contem verbo DML e slot ao mesmo
    tempo, logo ``_dynamic_string_nodes`` nao a alcanca. O idiom JA existe neste
    pacote (``sources.py:110``, ``sql += f" LIMIT {int(limit)}"``, sobre um
    SELECT), portanto e o caminho natural para ``events.py`` na story 2.

    Regra: se o DML entra na acumulacao, e violacao — o statement dinamico tem
    de ser UMA expressao unica, onde a regra da allowlist e verificavel. A
    guarda e disparada pelo verbo DML, de modo que a acumulacao SELECT-only de
    ``sources.py`` nao produz falso positivo.
    """
    violations: list[str] = []
    dml_names: set[str] = set()

    for node in ast.walk(tree):
        # `sql = "DELETE FROM ..."` marca `sql` como portador de DML.
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            value = node.value
            if value is None:
                continue
            if DML.search(_literal_parts(value)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Name):
                        dml_names.add(target.id)

    for node in ast.walk(tree):
        if isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
            carrega_dml = node.target.id in dml_names or DML.search(_literal_parts(node.value))
            if carrega_dml:
                violations.append(
                    f"{label}:{node.lineno}: DML montado por acumulacao em {node.target.id!r} "
                    f"(`+=`) — a regra da allowlist nao e verificavel estaticamente sobre "
                    f"acumulacao; monte o statement como UMA expressao unica"
                )
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "join":
            partes = " ".join(_literal_parts(a) for a in node.args) + " " + _literal_parts(node.func.value)
            elementos: list[ast.AST] = []
            for arg in node.args:
                if isinstance(arg, (ast.List, ast.Tuple, ast.Set)):
                    elementos.extend(arg.elts)
            partes += " " + " ".join(_literal_parts(e) for e in elementos)
            if DML.search(partes):
                violations.append(
                    f"{label}:{node.lineno}: DML montado por `join()` — mesma proibicao "
                    f"da acumulacao por `+=`; monte o statement como UMA expressao unica"
                )
    return violations


def _sanctioned_root(node: ast.AST) -> str | None:
    """Identificador sancionado do qual ``node`` deriva, se houver."""
    if isinstance(node, ast.Name):
        return node.id if node.id in SANCTIONED_ALLOWLIST_NAMES else None
    if isinstance(node, ast.Attribute):
        return node.attr if node.attr in SANCTIONED_ALLOWLIST_NAMES else None
    if isinstance(node, ast.Subscript):
        return _sanctioned_root(node.value)
    if isinstance(node, ast.Call):
        # sorted(WRITE_TARGET_ORDER) / tuple(ALLOWED_WRITE_TARGETS) etc.
        for arg in node.args:
            root = _sanctioned_root(arg)
            if root is not None:
                return root
    return None


def _imported_from_engine(tree: ast.AST, identifier: str) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == ENGINE_PACKAGE or module.startswith(f"{ENGINE_PACKAGE}."):
                for alias in node.names:
                    if (alias.asname or alias.name) == identifier:
                        return True
    return False


def _module_level_rebinds(tree: ast.Module, identifier: str) -> bool:
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == identifier for t in stmt.targets):
                return True
        elif isinstance(stmt, ast.AnnAssign):
            if isinstance(stmt.target, ast.Name) and stmt.target.id == identifier:
                return True
    return False


def _unwrap_guard(node: ast.AST) -> tuple[ast.AST, bool]:
    """Remove a chamada de ``assert_write_target(...)`` do slot, se presente."""
    if isinstance(node, ast.Call):
        func = node.func
        name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
        if name == WRITE_GUARD and node.args:
            return node.args[0], True
    return node, False


def _dynamic_dml_violations(source: str, *, label: str = "<memoria>") -> list[str]:
    """Violacoes de AR-2 em ``source``. Funcao pura — auto-testavel.

    Regra: para todo DML construido dinamicamente, cada slot interpolado tem de
    (a) passar por ``assert_write_target()`` e (b) resolver a uma constante da
    allowlist sancionada, importada por nome do pacote do motor e nao
    re-vinculada no modulo. Qualquer outra coisa — tupla literal local, tupla
    importada de outro lugar, parametro de funcao, literal cru — e violacao.
    """
    tree = ast.parse(source)
    violations: list[str] = _accumulation_violations(tree, label)
    module_tree = tree if isinstance(tree, ast.Module) else None
    for node in _dynamic_string_nodes(tree):
        body = _literal_parts(node)
        if not DML.search(body):
            continue
        slots = _interpolated_slots(node)
        if not slots:
            violations.append(f"{label}:{getattr(node, 'lineno', '?')}: DML dinamico sem slot identificavel")
            continue
        for slot in slots:
            line = getattr(slot, "lineno", getattr(node, "lineno", "?"))
            inner, guarded = _unwrap_guard(slot)
            if not guarded:
                violations.append(
                    f"{label}:{line}: slot de DML dinamico nao passa por {WRITE_GUARD}() — "
                    f"a allowlist nao e consultada antes da execucao"
                )
                continue
            if not isinstance(inner, ast.Name):
                violations.append(
                    f"{label}:{line}: slot de DML dinamico nao resolvivel a um identificador "
                    f"(tipo {type(inner).__name__})"
                )
                continue
            bindings = _name_bindings(tree, inner.id)
            if not bindings:
                violations.append(f"{label}:{line}: {inner.id!r} interpolado em DML sem vinculo rastreavel no modulo")
                continue
            for binding in bindings:
                root = _sanctioned_root(binding)
                if root is None:
                    violations.append(
                        f"{label}:{line}: {inner.id!r} recebe valor de fonte nao sancionada "
                        f"({ast.dump(binding)[:120]}) — use uma das constantes {sorted(SANCTIONED_ALLOWLIST_NAMES)}"
                    )
                    continue
                if not _imported_from_engine(tree, root):
                    violations.append(f"{label}:{line}: {root!r} nao e importado por nome de {ENGINE_PACKAGE}")
                if module_tree is not None and _module_level_rebinds(module_tree, root):
                    violations.append(f"{label}:{line}: {root!r} e re-vinculado no modulo — allowlist sombreada")
    return violations


@pytest.mark.parametrize("path", _python_sources(), ids=lambda p: p.name)
def test_dynamic_dml_resolves_only_to_the_write_allowlist(path: Path) -> None:
    """AR-2 — controle positivo: o codigo entregue satisfaz a regra."""
    violations = _dynamic_dml_violations(path.read_text(encoding="utf-8"), label=path.name)
    assert not violations, "AR-2 violado:\n" + "\n".join(violations)


def test_producer_persist_uses_the_allowlist_loop() -> None:
    """Guarda de regressao: a tupla local do producer nao pode voltar."""
    source = (PACKAGE_DIR / "producer.py").read_text(encoding="utf-8")
    assert "for table in WRITE_TARGET_ORDER:" in source
    assert f"{WRITE_GUARD}(table)" in source
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            literais = {e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)}
            assert not (literais & ALLOWED_WRITE_TARGETS), (
                f"producer.py:{node.lineno}: colecao literal de nomes de tabela — "
                f"a unica enumeracao permitida vive em schema.WRITE_TARGET_ORDER"
            )


# --- auto-testes negativos: o checker tem de ter dentes --------------------

_LOCAL_TUPLE_EVASION = """
from scripts.confenge_live_intelligence.schema import assert_write_target

def purge(cur, snapshot_id):
    for table in ("confenge_live_intelligence_events", "opportunity_intel"):
        cur.execute(f"DELETE FROM public.{assert_write_target(table)} WHERE snapshot_id = %s", (snapshot_id,))
"""

_UNGUARDED_SLOT = """
from scripts.confenge_live_intelligence.schema import WRITE_TARGET_ORDER

def purge(cur, snapshot_id):
    for table in WRITE_TARGET_ORDER:
        cur.execute(f"DELETE FROM public.{table} WHERE snapshot_id = %s", (snapshot_id,))
"""

_PARAMETER_SLOT = """
from scripts.confenge_live_intelligence.schema import assert_write_target

def purge(cur, table, snapshot_id):
    cur.execute(f"UPDATE public.{assert_write_target(table)} SET x = 1 WHERE snapshot_id = %s", (snapshot_id,))
"""

_SHADOWED_ALLOWLIST = """
from scripts.confenge_live_intelligence.schema import WRITE_TARGET_ORDER, assert_write_target

WRITE_TARGET_ORDER = ("opportunity_intel",)

def purge(cur, snapshot_id):
    for table in WRITE_TARGET_ORDER:
        cur.execute(f"DELETE FROM public.{assert_write_target(table)} WHERE snapshot_id = %s", (snapshot_id,))
"""

_FOREIGN_CONSTANT = """
from scripts.confenge_live_intelligence.schema import assert_write_target
from scripts.opportunity_intel.tables import ALLOWED_WRITE_TARGETS

def purge(cur, snapshot_id):
    for table in ALLOWED_WRITE_TARGETS:
        cur.execute(f"DELETE FROM public.{assert_write_target(table)} WHERE snapshot_id = %s", (snapshot_id,))
"""

_FORMAT_EVASION = """
def purge(cur, snapshot_id):
    for table in ("opportunity_intel",):
        cur.execute("DELETE FROM public.{} WHERE snapshot_id = %s".format(table), (snapshot_id,))
"""

_PERCENT_EVASION = """
def purge(cur, snapshot_id):
    for table in ("opportunity_intel",):
        cur.execute("DELETE FROM public.%s WHERE snapshot_id = 1" % table)
"""

_CONCAT_EVASION = """
def purge(cur, snapshot_id):
    for table in ("opportunity_intel",):
        cur.execute("DELETE FROM public." + table + " WHERE snapshot_id = 1")
"""

# A familia de ACUMULACAO. Nenhum no da AST carrega verbo DML e slot ao mesmo
# tempo — e o idiom que `sources.py:110` ja usa (sobre um SELECT), portanto o
# caminho natural para `events.py` na story 2. Sem estes dois casos o checker
# tem buraco e o criterio de aceite do @architect nao esta atendido.
_AUGASSIGN_EVASION = """
def purge(cur, snapshot_id):
    for table in ("opportunity_intel",):
        sql = "DELETE FROM public."
        sql += table
        sql += " WHERE snapshot_id = 1"
        cur.execute(sql)
"""

_JOIN_EVASION = """
def purge(cur, snapshot_id):
    for table in ("opportunity_intel",):
        cur.execute("".join(["DELETE FROM public.", table, " WHERE snapshot_id = 1"]))
"""


@pytest.mark.parametrize(
    ("label", "source"),
    [
        ("tupla_local", _LOCAL_TUPLE_EVASION),
        ("slot_sem_guarda", _UNGUARDED_SLOT),
        ("parametro_de_funcao", _PARAMETER_SLOT),
        ("allowlist_sombreada", _SHADOWED_ALLOWLIST),
        ("constante_estrangeira", _FOREIGN_CONSTANT),
        ("format", _FORMAT_EVASION),
        ("percent", _PERCENT_EVASION),
        ("concatenacao", _CONCAT_EVASION),
        ("acumulacao_augassign", _AUGASSIGN_EVASION),
        ("acumulacao_join", _JOIN_EVASION),
    ],
)
def test_checker_rejects_every_known_evasion(label: str, source: str) -> None:
    """Se qualquer um destes passar, AR-2 nao esta fechado — e o AC11 mente.

    ``tupla_local`` e literalmente o cenario nomeado pelo @architect: uma tupla
    local nova em ``events.py`` (story 2) TEM de quebrar o teste.
    """
    violations = _dynamic_dml_violations(source, label=label)
    assert violations, f"o checker aceitou a evasao {label!r} — AR-2 sem dentes"


def test_checker_accepts_the_sanctioned_idiom() -> None:
    """Controle negativo do controle: o checker nao e um `assert False`."""
    sanctioned = """
from scripts.confenge_live_intelligence.schema import WRITE_TARGET_ORDER, assert_write_target

def purge(cur, snapshot_id):
    for table in WRITE_TARGET_ORDER:
        cur.execute(f"DELETE FROM public.{assert_write_target(table)} WHERE snapshot_id = %s", (snapshot_id,))
"""
    assert not _dynamic_dml_violations(sanctioned, label="sancionado")


def test_write_guard_rejects_outbound_target_at_runtime() -> None:
    """AR-2, metade de runtime: a guarda falha fechada, sem precisar de banco."""
    from scripts.confenge_live_intelligence.schema import (
        OutboundWriteAttemptError,
        assert_write_target,
    )

    for table in ("opportunity_intel", "confenge_target_fit_dirty", "pncp_raw_bids", ""):
        with pytest.raises(OutboundWriteAttemptError):
            assert_write_target(table)
    for table in ALLOWED_WRITE_TARGETS:
        assert assert_write_target(table) == table
