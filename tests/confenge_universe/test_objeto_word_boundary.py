"""A contract objeto must not be cut mid-clause.

A raw 160-char slice both mangled the copy ("..., com") and starved the pain
keyword detection, which collapsed the moment mix into PORTFOLIO_REVIEW.
"""

from scripts.confenge_universe.aggregate import MAX_OBJECT_SNIPPET, _cut_objeto


def test_short_objeto_is_untouched():
    text = "Obra de pavimentação asfáltica"
    assert _cut_objeto(text) == text


def test_long_objeto_cuts_on_a_word_boundary():
    text = "Complementação da obra na Rodovia LMG-680 " + ("trecho " * 200)
    out = _cut_objeto(text)
    assert len(out) <= MAX_OBJECT_SNIPPET + 1
    assert out.endswith("…")
    # never mid-word
    assert not out[:-1].rstrip().endswith("trech")


def test_budget_is_wide_enough_for_pain_keywords():
    # "termo aditivo" sits well past char 160 in a real PNCP objeto.
    text = (
        "Contratação de empresa especializada para execução de obras de "
        "infraestrutura urbana no município, incluindo drenagem, pavimentação "
        "e sinalização viária, conforme projeto básico anexo, com termo aditivo "
        "de prorrogação previsto."
    )
    assert "termo aditivo" in _cut_objeto(text)
