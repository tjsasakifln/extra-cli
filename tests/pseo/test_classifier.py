"""Multi-layer AEC classifier — regressions and gold metrics."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.pseo.classifiers import classify_objeto, evaluate_classifier

FIXTURES = Path(__file__).parent / "fixtures"
GOLD = FIXTURES / "gold_classification.json"


def test_gold_precision_gate():
    gold = json.loads(GOLD.read_text(encoding="utf-8"))
    assert len(gold) >= 30
    metrics = evaluate_classifier(gold)
    # Prioritize precision for indexable class
    assert metrics["precision_aec_confirmed"] >= 0.97
    assert metrics["fp"] == 0
    # Persist metrics path for report (side-effect free if not writable)
    out = Path(__file__).resolve().parents[2] / "artifacts" / "pseo"
    try:
        out.mkdir(parents=True, exist_ok=True)
        (out / "classifier-metrics.json").write_text(
            json.dumps({k: v for k, v in metrics.items() if k != "details"}, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError:
        pass


def test_false_positive_regressions():
    cases = [
        "Credenciamento de escolas privadas para oferta de vagas",
        "Aquisição de ônibus rodoviário para transporte intermunicipal",
        "Locação de imóvel para funcionamento de secretaria",
        "Serviços de limpeza e higienização predial",
        "Aquisição de materiais de construção (cimento e areia)",
        "Fornecimento de merenda escolar",
        "escola",  # alone
        "Compra de equipamento de informática para escola",
    ]
    for obj in cases:
        r = classify_objeto(obj)
        assert r.label != "aec_confirmed", f"{obj!r} -> {r.label} {r.reasons}"


def test_true_positive_works():
    cases = [
        "Execução de obra de pavimentação asfáltica em vias urbanas",
        "Construção de escola com alvenaria e concreto armado",
        "Rede de esgoto sanitário e drenagem pluvial",
        "Climatização e ar-condicionado central em prédio público",
        "Manutenção predial de edifícios públicos",
    ]
    for obj in cases:
        r = classify_objeto(obj)
        assert r.label == "aec_confirmed", f"{obj!r} -> {r.label} {r.reasons}"
        assert r.archetypes


def test_rodovi_onibus_not_pavement():
    r = classify_objeto("Aquisição de ônibus rodoviário para frota municipal")
    assert r.label == "non_aec"
    assert "pavimentacao-infraestrutura-viaria" not in r.archetypes


def test_veiculo_passeio_not_calcada():
    r = classify_objeto(
        "Credenciamento de empresas para manutenção de veículos de passeio, "
        "vans, ônibus, caminhões e máquinas rodoviárias da frota municipal"
    )
    assert r.label != "aec_confirmed"
    assert "pavimentacao-infraestrutura-viaria" not in r.archetypes


def test_equipment_purchase_not_aec():
    for obj in (
        "Compra de ar condicionado tipo split 12000 BTUs",
        "Compra de equipamento de ar-condicionado tipo janela",
        "Aquisição de ferramentas e materiais de manutenção predial",
        "Assinatura anual de ferramenta de software para orçamentos e serviços de engenharia",
    ):
        r = classify_objeto(obj)
        assert r.label != "aec_confirmed", (obj, r.label, r.reasons)


def test_locacao_maquinas_not_pavement():
    r = classify_objeto(
        "Locação de máquinas e equipamentos para obras de pavimentação (sem mão de obra)"
    )
    assert r.label != "aec_confirmed"


def test_installation_of_ac_is_aec():
    r = classify_objeto(
        "Contratação de empresa para instalação de ar-condicionado central "
        "com infraestrutura de dutos em prédio público"
    )
    assert r.label == "aec_confirmed"
    assert "climatizacao-instalacoes" in r.archetypes


def test_construcao_de_without_object():
    r = classify_objeto("Construção de soluções inovadoras para a gestão")
    assert r.label in {"ambiguous", "non_aec", "insufficient_context"}
