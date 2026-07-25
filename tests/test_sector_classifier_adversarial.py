"""Testes adversariais do classificador setorial Extra Construtora."""
from __future__ import annotations

from scripts.ops.sector_classifier import (
    E_ALLOWED_LABELS,
    RULE_VERSION,
    classify_object,
    is_engineering_for_e,
)


AUDIT_KEYS = {
    "label",
    "positive_terms",
    "negative_terms",
    "category",
    "subcategory",
    "reason",
    "confidence",
    "textual_evidence",
    "rule_version",
}


def _assert_audit(clf) -> None:
    d = clf.to_dict()
    assert AUDIT_KEYS.issubset(d.keys())
    assert d["rule_version"] == RULE_VERSION
    assert d["label"] in {
        "ENGINEERING_HIGH_CONFIDENCE",
        "ENGINEERING_REVIEW",
        "NON_ENGINEERING",
        "AMBIGUOUS",
        "EXCLUDED_CATEGORY",
    }
    assert 0.0 <= float(d["confidence"]) <= 1.0
    assert isinstance(d["reason"], str) and d["reason"]


def test_pavimentacao_asfaltica_engineering():
    clf = classify_object(
        "Contratação de empresa para execução de pavimentação asfáltica em vias urbanas"
    )
    _assert_audit(clf)
    assert clf.label == "ENGINEERING_HIGH_CONFIDENCE"
    assert is_engineering_for_e(clf)


def test_ampliacao_escola_engineering():
    clf = classify_object("Ampliação de escola municipal com 6 salas de aula")
    _assert_audit(clf)
    assert clf.label == "ENGINEERING_HIGH_CONFIDENCE"


def test_drenagem_urbana_engineering():
    clf = classify_object("Execução de drenagem urbana e galerias pluviais")
    _assert_audit(clf)
    assert clf.label == "ENGINEERING_HIGH_CONFIDENCE"


def test_manutencao_predial_engineering_or_review():
    clf = classify_object(
        "Execução de serviços de engenharia para Manutenção Predial e Civil das edificações"
    )
    _assert_audit(clf)
    assert clf.label in {"ENGINEERING_HIGH_CONFIDENCE", "ENGINEERING_REVIEW"}


def test_projetos_arquitetonicos_review():
    clf = classify_object(
        "Elaboração de projetos arquitetônicos e complementares de engenharia"
    )
    _assert_audit(clf)
    assert clf.label in {"ENGINEERING_HIGH_CONFIDENCE", "ENGINEERING_REVIEW"}


def test_manutencao_frota_non_engineering():
    clf = classify_object(
        "Credenciamento de empresa para prestação de serviços de manutenção da frota municipal"
    )
    _assert_audit(clf)
    assert clf.label in {"NON_ENGINEERING", "EXCLUDED_CATEGORY"}
    assert not is_engineering_for_e(clf)


def test_computador_non_engineering():
    clf = classify_object(
        "Aquisição de 01 (um) computador do tipo All in One, processador Intel"
    )
    _assert_audit(clf)
    assert clf.label == "NON_ENGINEERING"


def test_lencois_mantas_non_engineering():
    clf = classify_object(
        "AQUISIÇÃO DE LENÇÓIS E MANTAS DESTINADOS AOS LEITOS DA UNIDADE BÁSICA DE SAÚDE"
    )
    _assert_audit(clf)
    assert clf.label in {"NON_ENGINEERING", "EXCLUDED_CATEGORY"}


def test_exames_laboratoriais_non_engineering():
    clf = classify_object(
        "CREDENCIAMENTO PARA EXECUÇÃO DE EXAMES LABORATORIAIS COMPLEMENTARES AO SUS"
    )
    _assert_audit(clf)
    assert clf.label in {"NON_ENGINEERING", "EXCLUDED_CATEGORY"}


def test_oficina_karate_non_engineering():
    clf = classify_object("Contratação de oficina de karatê para alunos da rede municipal")
    _assert_audit(clf)
    assert clf.label == "NON_ENGINEERING"


def test_construcao_conhecimento_non_engineering():
    clf = classify_object("Oficina de construção de conhecimento para professores")
    _assert_audit(clf)
    assert clf.label == "NON_ENGINEERING"


def test_manutencao_software_non_engineering():
    clf = classify_object("Contratação de manutenção de software de gestão escolar")
    _assert_audit(clf)
    assert clf.label == "NON_ENGINEERING"


def test_material_construcao_isolado_review_or_exclude():
    clf = classify_object(
        "Registro de preços para futura e eventual aquisição de materiais para uso nas pavimentações"
    )
    _assert_audit(clf)
    assert clf.label in {"ENGINEERING_REVIEW", "EXCLUDED_CATEGORY", "NON_ENGINEERING", "AMBIGUOUS"}


def test_residuos_cc_not_auto_obra():
    clf = classify_object(
        "Contratação de coleta e destinação de resíduos da construção civil e entulho"
    )
    _assert_audit(clf)
    assert clf.label in {"NON_ENGINEERING", "AMBIGUOUS", "EXCLUDED_CATEGORY"}


def test_generic_servico_alone_not_high_confidence():
    clf = classify_object("serviço")
    _assert_audit(clf)
    assert clf.label != "ENGINEERING_HIGH_CONFIDENCE"
    assert clf.label in {"NON_ENGINEERING", "AMBIGUOUS"}


def test_generic_manutencao_alone_not_high_confidence():
    clf = classify_object("manutenção")
    assert clf.label != "ENGINEERING_HIGH_CONFIDENCE"


def test_generic_construcao_alone_not_high_confidence():
    clf = classify_object("construção")
    assert clf.label != "ENGINEERING_HIGH_CONFIDENCE"


def test_generic_projeto_alone_not_high_confidence():
    clf = classify_object("projeto")
    assert clf.label != "ENGINEERING_HIGH_CONFIDENCE"


def test_e_allowed_labels_set():
    assert "ENGINEERING_HIGH_CONFIDENCE" in E_ALLOWED_LABELS
    assert "ENGINEERING_REVIEW" in E_ALLOWED_LABELS
    assert "NON_ENGINEERING" not in E_ALLOWED_LABELS
    assert "EXCLUDED_CATEGORY" not in E_ALLOWED_LABELS


def test_real_v1_e_evidence_objects_excluded():
    """Objects that polluted RC v1 Deliverable E must not pass E filter."""
    bad = [
        "AQUISIÇÃO DE LENÇÓIS E MANTAS DESTINADOS AOS LEITOS DA UNIDADE BÁSICA DE SAÚDE",
        "Aquisição de 01 (um) computador do tipo All in One",
        "CREDENCIAMENTO DE EMPRESA ESPECIALIZADA PARA EXECUÇÃO DE SERVIÇOS DE FORMA COMPLEMENTAR AO SUS, DE EXAMES",
        "Credenciamento de empresa para prestação de serviços de manutenção da frota municipal",
    ]
    for obj in bad:
        clf = classify_object(obj)
        assert not is_engineering_for_e(clf), obj
