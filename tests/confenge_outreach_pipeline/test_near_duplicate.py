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


def test_semantic_template_same_arc_blocked() -> None:
    """Different contract objects into same commercial arc must still block."""
    drafts = [
        {
            "cnpj": "1",
            "razao_social": "Alpha Construtora LTDA",
            "body": (
                "Pelo que está público sobre Alpha Construtora LTDA, objeto: pavimentação "
                "asfáltica de vias urbanas em CBUQ no município de Coxilha/RS. Em 2026-07-15, "
                "fato contratual público utilizável sem dor especializada dominante. "
                "Posso montar um painel mínimo de acompanhamento?"
            ),
        },
        {
            "cnpj": "2",
            "razao_social": "Beta Engenharia SA",
            "body": (
                "Pelo que está público sobre Beta Engenharia SA, objeto: recuperação de "
                "obra de arte especial no DNIT trecho 12. Em 2026-06-01, fato contratual "
                "público utilizável sem dor especializada dominante. "
                "Posso montar um painel mínimo de acompanhamento?"
            ),
        },
        {
            "cnpj": "3",
            "razao_social": "Gama Obras",
            "body": (
                "Pelo que está público sobre Gama Obras, objeto: saneamento e redes de "
                "água em três municípios catarinenses. Em 2026-05-20, fato contratual "
                "público utilizável sem dor especializada dominante. "
                "Posso montar um painel mínimo de acompanhamento?"
            ),
        },
    ]
    audit = audit_near_duplicates(drafts)
    assert audit.blocked is True
    assert audit.semantic_template_similarity_max >= 0.70 or audit.high_semantic_pairs >= 1
    assert any(
        c in audit.reason_codes
        for c in ("semantic_template_near_duplicate", "near_duplicate_any_high_pair", "near_duplicate_extreme_pair")
    )


def test_blind_template_audit_flags_interpolated_objects() -> None:
    from scripts.confenge_outreach_pipeline.near_duplicate import blind_template_audit

    drafts = [
        {
            "cnpj": str(i),
            "razao_social": f"Empresa {i} LTDA",
            "body": (
                f"Pelo que está público sobre Empresa {i} LTDA, objeto: obra distinta {i} "
                f"com extensão municipal. Em 2026-0{i % 9 + 1}-10, fato contratual público "
                "utilizável sem dor especializada dominante. Posso montar um painel mínimo?"
            ),
        }
        for i in range(1, 8)
    ]
    res = blind_template_audit(drafts)
    assert res["blocked"] is True
    assert res["answer"] == "YES_SAME_TEMPLATE"
