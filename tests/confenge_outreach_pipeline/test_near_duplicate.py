"""Near-duplicate batch gate."""

from __future__ import annotations

from scripts.confenge_outreach_pipeline.near_duplicate import (
    audit_near_duplicates,
    jaccard,
    subject_is_generic_contrato,
)


def test_jaccard_identical() -> None:
    assert jaccard("pavimentação asfáltica no município", "pavimentação asfáltica no município") == 1.0


def test_clone_batch_blocked() -> None:
    body = (
        "Pelo que está público, observamos contratos públicos de engenharia/construção "
        "no histórico recente da empresa. Isso não prova crédito sozinho, mas índice "
        "aplicável não formalizado no prazo esperado. Posso te mandar o recorte público?"
    )
    drafts = [
        {"cnpj": f"{i:014d}", "body": body, "subject": f"Contrato Empresa {i}"}
        for i in range(1, 8)
    ]
    audit = audit_near_duplicates(drafts)
    assert audit.blocked is True
    assert audit.high_similarity_pairs > 0


def test_any_high_pair_blocks_even_low_global_fraction() -> None:
    """Skeptic: max_sim~0.94 with template clones must block (not only frac>=0.35)."""
    template = (
        "Pelo que está público sobre {co}, portfólio público observado com {n} contrato(s) "
        "no input. Isso não prova crédito sozinho, mas se houver evento extraordinário, "
        "o nexo e a memória precisam estar organizados. Ofereço uma leitura técnica."
    )
    # Mix: two near-clones + many distinct → global frac may be low, but any high pair blocks
    drafts = [
        {"cnpj": "1", "body": template.format(co="Empresa Alpha", n=3), "service_id": "PLANILHAS"},
        {"cnpj": "2", "body": template.format(co="Empresa Beta", n=5), "service_id": "PLANILHAS"},
        {
            "cnpj": "3",
            "body": "Aditivo DEINFRA 033/2023 de duplicação de via urbana com memorial quantitativo.",
            "service_id": "ADITIVOS",
        },
        {
            "cnpj": "4",
            "body": "Glosa de medição no trecho de reabilitação de obra de arte especial DNIT.",
            "service_id": "MEDICOES",
        },
        {
            "cnpj": "5",
            "body": "Edital de concorrência para saneamento na região metropolitana publicado ontem.",
            "service_id": "APOIO_LICITACAO",
        },
        {
            "cnpj": "6",
            "body": "Contrato de reforma predial com termino em 90 dias e obrigação de entrega parcial.",
            "service_id": "MONITORAMENTO_CONTRATUAL",
        },
    ]
    audit = audit_near_duplicates(drafts)
    assert audit.max_similarity >= 0.82
    assert audit.blocked is True
    assert "near_duplicate_any_high_pair" in audit.reason_codes or audit.high_similarity_pairs >= 1


def test_distinct_facts_not_blocked() -> None:
    drafts = [
        {
            "cnpj": "1",
            "body": "Contrato DEINFRA 033/2023 de duplicação de via urbana atingiu aniversário.",
        },
        {
            "cnpj": "2",
            "body": "Aditivo recente no contrato municipal de pavimentação CBUQ em Coxilha.",
        },
        {
            "cnpj": "3",
            "body": "Glosa de medição no trecho de reabilitação de obra de arte especial DNIT.",
        },
        {
            "cnpj": "4",
            "body": "Edital de concorrência para saneamento na região metropolitana publicado.",
        },
    ]
    audit = audit_near_duplicates(drafts)
    assert audit.blocked is False


def test_generic_contrato_subject() -> None:
    assert subject_is_generic_contrato("Contrato ROSA IMOVEIS") is True
    assert subject_is_generic_contrato("Aditivo pavimentação Coxilha") is False
