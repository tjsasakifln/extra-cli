"""AC 21 — the recognized ``why_now`` template set is pinned against facts.py.

There is no enum for ``why_now_code``: ``facts.py::why_now`` returns free strings
(lowercase) that ``scripts/confenge_outreach_pipeline/adapt.py`` uppercases. So
``classify.py`` necessarily holds a set of strings — and that set must be fixed
*against* ``facts.py``, never declared privately. A seventh trigger has to break
this test instead of shipping unclassified.

Follows the pattern of ``tests/confenge_universe/test_classifier_version_drift.py``:
the expected value is recomputed from live source, not stored.
"""

from __future__ import annotations

import ast
import inspect
from datetime import date

import pytest

from scripts.confenge_account_intelligence import facts as facts_module
from scripts.confenge_claim_policy import PURPOSE_WHY_NOW, allows_present_tense
from scripts.confenge_claim_safety.classify import AMBIGUOUS_WHY_NOW_CODES, RECOGNIZED_WHY_NOW_CODES

# The two fallbacks ``why_now`` returns directly when no pain check matches.
_FALLBACK_TRIGGERS = {"insufficient_facts", "portfolio_review"}


def _why_now_ast() -> ast.FunctionDef:
    tree = ast.parse(inspect.getsource(facts_module))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "why_now":
            return node
    raise AssertionError("facts.py no longer defines why_now")


def _pain_check_triggers(func: ast.FunctionDef) -> set[str]:
    """Trigger names from the ``pain_checks`` list literal.

    Handles both ``ast.Assign`` and ``ast.AnnAssign``: the list carries a type
    annotation since the CLAIM_POLICY refactor, and only reading ``ast.Assign``
    would silently find nothing and pass vacuously. Only element ``[0]`` of each
    tuple is read — element ``[2]`` may be a string *or* a callable.
    """
    for node in ast.walk(func):
        target_names: list[str] = []
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            target_names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target_names = [node.target.id]
            value = node.value
        if "pain_checks" not in target_names or not isinstance(value, ast.List):
            continue
        triggers: set[str] = set()
        for element in value.elts:
            assert isinstance(element, ast.Tuple), "pain_checks entries must stay tuples"
            head = element.elts[0]
            assert isinstance(head, ast.Constant) and isinstance(head.value, str), (
                "the pain_checks trigger name must stay a string literal"
            )
            triggers.add(head.value)
        return triggers
    raise AssertionError("facts.py::why_now no longer assigns a pain_checks list literal")


def _returned_fallback_triggers(func: ast.FunctionDef) -> set[str]:
    """Trigger literals carried by the ``return {...}`` dicts of ``why_now``."""
    triggers: set[str] = set()
    for node in ast.walk(func):
        if not isinstance(node, ast.Return) or not isinstance(node.value, ast.Dict):
            continue
        for key, value in zip(node.value.keys, node.value.values, strict=True):
            if (
                isinstance(key, ast.Constant)
                and key.value == "trigger"
                and isinstance(value, ast.Constant)
                and isinstance(value.value, str)
            ):
                triggers.add(value.value)
    return triggers


def producible_why_now_codes() -> set[str]:
    func = _why_now_ast()
    triggers = _pain_check_triggers(func) | _returned_fallback_triggers(func)
    return {trigger.upper() for trigger in triggers}


def test_the_ast_extraction_is_not_vacuous() -> None:
    """Guard the guard: an empty extraction would make the drift test pass blindly."""
    func = _why_now_ast()
    pain = _pain_check_triggers(func)
    fallbacks = _returned_fallback_triggers(func)
    assert len(pain) == 4, f"expected 4 pain_checks triggers, extracted {sorted(pain)}"
    assert _FALLBACK_TRIGGERS <= fallbacks, f"fallback triggers missing from {sorted(fallbacks)}"
    assert len(producible_why_now_codes()) == 6


def test_ac21_classify_recognizes_exactly_the_codes_facts_can_produce() -> None:
    produced = producible_why_now_codes()
    assert RECOGNIZED_WHY_NOW_CODES == produced, (
        "why_now template drift: classify.py recognizes "
        f"{sorted(RECOGNIZED_WHY_NOW_CODES)} but facts.py produces {sorted(produced)}. "
        "A new trigger must be classified explicitly, never shipped unclassified."
    )


def test_ac21_mature_no_reajuste_is_covered_and_declared_ambiguous() -> None:
    """The sixth trigger the story's original enumeration missed (@po Decisão nº 1)."""
    assert "MATURE_NO_REAJUSTE" in producible_why_now_codes()
    assert "MATURE_NO_REAJUSTE" in RECOGNIZED_WHY_NOW_CODES
    assert AMBIGUOUS_WHY_NOW_CODES <= RECOGNIZED_WHY_NOW_CODES


def test_ac9_addendum_template_no_longer_asserts_present_activity() -> None:
    """AC 9 — the ADDENDUM template must not claim the contract is current.

    Written as an invariant rather than a string equality: ``facts.py`` is owned
    concurrently by ``story-outreach-claim-policy-01``, which replaced the fixed
    text with a lifecycle-driven callable. Either shape satisfies AC 9 as long as
    no *unconditional* present assertion survives.
    """
    from scripts.confenge_claim_safety.claim_surface import CLAIM_PRESENT, detect_temporal_claim

    source = inspect.getsource(facts_module)
    assert '"Aditivos/alterações observados em contrato público recente ou ativo."' not in source

    func = _why_now_ast()
    for node in ast.walk(func):
        if not isinstance(node, ast.List):
            continue
        for element in node.elts:
            if not isinstance(element, ast.Tuple) or len(element.elts) < 3:
                continue
            head, _pred, text = element.elts[0], element.elts[1], element.elts[2]
            if not (isinstance(head, ast.Constant) and head.value == "addendum"):
                continue
            if isinstance(text, ast.Constant) and isinstance(text.value, str):
                # Fixed string: it must carry no present claim at all.
                assert detect_temporal_claim(text.value) != CLAIM_PRESENT, text.value
            else:
                # Callable: the present branch must be gated by the claim policy.
                assert isinstance(text, ast.Name), "addendum text must be a literal or a named callable"
                resolver = getattr(facts_module, text.id)
                gated = inspect.getsource(resolver)
                assert "allows_present_tense" in gated, (
                    "a callable ADDENDUM template must gate its present tense on the claim policy"
                )


def test_ac9_callable_addendum_template_emits_no_present_claim_when_ungated() -> None:
    """Behavioural half of AC 9: the gate must actually govern the tense.

    Asserting that ``allows_present_tense`` merely *appears* in the source proves
    a gate exists, not that it decides. This calls the resolver with a policy that
    forbids the present tense and checks the emitted copy.

    Couples to ``scripts.confenge_claim_policy``, owned by the concurrent story
    ``story-outreach-claim-policy-01``: if that constructor changes, this test
    breaks. That break is the intended drift signal, not a regression here.
    """
    resolver = getattr(facts_module, "_addendum_temporal_fact", None)
    if resolver is None:
        pytest.skip("facts.py carries a fixed ADDENDUM string; covered by the invariant test above")

    from scripts.confenge_claim_policy import PAST_ONLY, ClaimCandidate, evaluate_claim_policy
    from scripts.confenge_claim_safety.claim_surface import CLAIM_PRESENT, detect_temporal_claim

    candidate = ClaimCandidate(
        contract_id="c-1",
        lifecycle_state="",
        evidence_ids=(),
        has_hollow_fact=False,
        has_contemporary_event=False,
        event_date=date(2024, 1, 1),
    )
    policy = evaluate_claim_policy(candidate, evaluated_as_of=date(2026, 9, 1), purpose=PURPOSE_WHY_NOW)
    assert not allows_present_tense(policy), "fixture must reach a state that forbids the present tense"

    emitted = resolver({"id": "c-1", "object": "Obra qualquer."}, policy)
    assert detect_temporal_claim(emitted) != CLAIM_PRESENT, emitted

    # And the past-only branch must not smuggle a present assertion either.
    past_policy = evaluate_claim_policy(
        ClaimCandidate(
            contract_id="c-2",
            lifecycle_state="ENCERRADO",
            evidence_ids=("ev-contract-c-2",),
            has_hollow_fact=False,
            has_contemporary_event=False,
            event_date=date(2024, 1, 1),
        ),
        evaluated_as_of=date(2026, 9, 1),
        purpose=PURPOSE_WHY_NOW,
    )
    if past_policy.allowed_tense == PAST_ONLY:
        assert detect_temporal_claim(resolver({"id": "c-2"}, past_policy)) != CLAIM_PRESENT
