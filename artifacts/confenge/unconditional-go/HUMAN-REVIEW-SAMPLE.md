# CONFENGE human review sample (CLEAN cohort)

Generated: `2026-08-10T03:58:53Z`

Status of this package: **HUMAN_REVIEW_PENDING** (machine cannot mint HUMAN_REVIEW_APPROVED).

Reviewer must fill: reviewer, reviewed_at, decision (APPROVED/REJECTED), evidence_inspected.

| # | CNPJ | Empresa | Email | Service | Target | Provenance | Decision |
|---|------|---------|-------|---------|--------|------------|----------|
| 1 | `00061493000170` | ENCOPAV ENGENHARIA LTDA | `encopav@encopav.com.br` | gestao_monitoramento_contratual | TARGET_CONFIRMED | REAL_OFFICIAL_SITE | PENDING |
| 2 | `00638562000165` | AMF ENGENHARIA E SERVICO LTDA | `amf@amf.com.br` | gestao_monitoramento_contratual | TARGET_CONFIRMED | REAL_OFFICIAL_SITE | PENDING |
| 3 | `00820854000114` | QUALIDADE CONSTRUÇÕES E PAVIMENTAÇÕES LT | `contato@qualidademineracao.com.br` | gestao_monitoramento_contratual | TARGET_CONFIRMED | REAL_OFFICIAL_SITE | PENDING |
| 4 | `00472805000138` | Traçado Construções e Serviços Ltda. | `comercial@tracado.com.br` | apoio_licitacoes_propostas | TARGET_CONFIRMED | REAL_OFFICIAL_SITE | PENDING |
| 5 | `03667661000163` | COMPACTA SUL PAVIMENTACAO LTDA | `compactasul@compactasul.com.br` | apoio_licitacoes_propostas | TARGET_CONFIRMED | REAL_OFFICIAL_SITE | PENDING |
| 6 | `05895635000118` | JR CONSTRUÇÕES E TERRAPLENAGEM LTDA EPP | `arantes@terraplenagem.com` | apoio_licitacoes_propostas | TARGET_CONFIRMED | REAL_OFFICIAL_SITE | PENDING |
| 7 | `07792269000105` | CONSTRUTORA LYTORANEA S.A - EM RECUPERAÇ | `lytoranea@lytoranea.com.br` | medicoes_glosas_memoria | TARGET_CONFIRMED | REAL_OFFICIAL_SITE | PENDING |
| 8 | `10412300000131` | TERRA FORTE BRASIL CONSTRUTORA LTDA | `terraforte@terraforte.com.br` | auditoria_orcamento_bdi | TARGET_CONFIRMED | REAL_OFFICIAL_SITE | PENDING |
| 9 | `09663315000193` | CONSTRUSIL ENGENHARIA | `engenharia@construsil.com.br` | reforco_temporario_backoffice | TARGET_CONFIRMED | REAL_OFFICIAL_SITE | PENDING |

## How to approve
```bash
# After review, record decisions (example JSONL)
# artifacts/confenge/unconditional-go/human-review-decisions.jsonl
# {"cnpj":"...","reviewer":"tiago.sasaki","decision":"HUMAN_REVIEW_APPROVED","evidence_inspected":["site","cnpj"],"reviewed_at":"..."}
```

Resume after human decisions:
```bash
python3 -m scripts.warmbly_bridge export ...  # re-export only approved
```
