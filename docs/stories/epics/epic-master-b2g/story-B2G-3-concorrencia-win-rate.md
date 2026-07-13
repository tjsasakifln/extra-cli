---
story_id: B2G-3
status: draft
priority: P1
epic: EPIC-MASTER-B2G-READINESS
agent: @data-engineer
depends_on: [B2G-2]
---

# Story B2G-3: Concorrencia e Win Rate

## Context

O coverage_manifest atual mostra `win_rate = NOT_READY` porque "Win rate requer tracking de propostas enviadas vs vencidas por CNPJ — dados de outcomes de propostas nao disponiveis no evidence ledger."

Atualmente, `v_supplier_winners` fornece ranking de fornecedores vencedores historicos (CNPJs que aparecem em contratos assinados), mas nao distingue:

- Quem sao os concorrentes da Extra Construtora por orgao/setor
- Qual o win rate da Extra vs concorrentes
- Qual o ticket medio por concorrente
- Qual a concentracao de mercado por orgao (HHI)

### Abordagem

1. **Concorrentes identificaveis**: CNPJs vencedores em licitacoes de engenharia nos orgaos de interesse (raio 200km). Disponivel em `v_supplier_winners` — precisa de refinamento.
2. **Win rate**: Componente inicial sem tracking de propostas enviadas. Abordagem pragmatica: (a) win rate historico baseado em contratos vencidos vs total de licitacoes do orgao como proxy inicial; (b) tracking manual de propostas enviadas como evolucao futura.
3. **Ticket medio**: Valor total contratos / qtd contratos por fornecedor. Parcialmente disponivel em `v_supplier_winners` — precisa de segmentacao por orgao e setor.
4. **CLI**: Comando `competitors` que mostra ranking, win rate estimado, ticket medio, e concentracao HHI.

### Limitacoes conhecidas

- API publica PNCP nao expoe propostas perdedoras — win rate real requer tracking manual
- Aproximacao inicial: win rate historico = contratos vencidos / total licitacoes do orgao
- Ticket medio sem distincao de setor pode ser enganoso (contratos de engenharia vs facilities)

## Acceptance Criteria

1. **AC1: Mapa de concorrentes** — View/v_tabela `v_competitor_map` com: `cnpj_fornecedor`, `nome_fornecedor`, `qtd_contratos`, `valor_total_contratos`, `ticket_medio`, `orgaos_distintos`, `setores_atuacao`, `primeiro_contrato`, `ultimo_contrato`
2. **AC2: Ranking por orgao** — `v_competitors_by_orgao` com: `orgao_cnpj`, `orgao_nome`, `ranking` (1-N por valor total), `cnpj_fornecedor`, `nome_fornecedor`, `valor_total`, `qtd_contratos`, `share_percentual` (% do orgao)
3. **AC3: Win rate estimado** — `v_competitor_win_rate` com: `cnpj_fornecedor`, `orgao`, `modalidade`, `contratos_vencidos`, `total_licitacoes_orgao`, `win_rate_estimado` (contratos_vencidos / total_licitacoes_orgao * 100). View inclui flag `trust_level: baixa | media` baseada no volume de dados
4. **AC4: Ticket medio por concorrente** — Ticket medio geral + por orgao + por setor. Implementado em `v_competitor_ticket_medio`
5. **AC5: CLI `competitors`** — Comando `local_datalake competitors` com filtros: `--orgao`, `--setor`, `--modalidade`, `--top N`, `--format table|json|csv`
6. **AC6: CLI `competitors --rank`** — Mostra ranking completo por orgao: posicao, fornecedor, contratos, valor_total, share_percentual
7. **AC7: CLI `competitors --win-rate`** — Mostra win rate estimado por fornecedor/orgao com indicador de confianca
8. **AC8: CLI `competitors --ticket-medio`** — Mostra ticket medio por fornecedor, segmentado por orgao e setor
9. **AC9: HHI por orgao** — Indice Herfindahl-Hirschman (0-10000) calculado por orgao, disponivel em `v_competitor_hhi`
10. **AC10: Testes e documentacao** — Testes para todas as views, CLI smoke tests, documentacao de limitacoes em `docs/competitors/known-limitations.md`

## Technical Design

### Views analiticas

```sql
-- Mapa de concorrentes
CREATE OR REPLACE VIEW v_competitor_map AS
SELECT
    ni_fornecedor AS cnpj_fornecedor,
    nome_fornecedor,
    COUNT(*) AS qtd_contratos,
    SUM(valor_global) AS valor_total_contratos,
    ROUND(SUM(valor_global) / COUNT(*), 2) AS ticket_medio,
    COUNT(DISTINCT orgao_cnpj) AS orgaos_distintos,
    MIN(data_assinatura) AS primeiro_contrato,
    MAX(data_assinatura) AS ultimo_contrato
FROM pncp_supplier_contracts
WHERE ni_fornecedor IS NOT NULL
    AND ni_fornecedor != ''
    AND valor_global IS NOT NULL
    AND data_assinatura >= CURRENT_DATE - INTERVAL '3 years'
GROUP BY ni_fornecedor, nome_fornecedor;

-- Ranking por orgao
CREATE OR REPLACE VIEW v_competitors_by_orgao AS
WITH ranked AS (
    SELECT
        orgao_cnpj,
        orgao_nome,
        ni_fornecedor AS cnpj_fornecedor,
        nome_fornecedor,
        SUM(valor_global) AS valor_total,
        COUNT(*) AS qtd_contratos,
        ROW_NUMBER() OVER (PARTITION BY orgao_cnpj ORDER BY SUM(valor_global) DESC) AS rank
    FROM pncp_supplier_contracts
    WHERE data_assinatura >= CURRENT_DATE - INTERVAL '3 years'
    GROUP BY orgao_cnpj, orgao_nome, ni_fornecedor, nome_fornecedor
)
SELECT * FROM ranked;

-- HHI por orgao
CREATE OR REPLACE VIEW v_competitor_hhi AS
WITH shares AS (
    SELECT
        orgao_cnpj,
        ni_fornecedor,
        SUM(valor_global) AS fornecedor_valor,
        SUM(SUM(valor_global)) OVER (PARTITION BY orgao_cnpj) AS orgao_total
    FROM pncp_supplier_contracts
    WHERE data_assinatura >= CURRENT_DATE - INTERVAL '3 years'
    GROUP BY orgao_cnpj, ni_fornecedor
)
SELECT
    orgao_cnpj,
    COUNT(DISTINCT ni_fornecedor) AS num_fornecedores,
    ROUND(SUM((fornecedor_valor / NULLIF(orgao_total, 0) * 100) ^ 2), 2) AS hhi
FROM shares
GROUP BY orgao_cnpj;
```

### CLI

```python
# scripts/local_datalake.py novo comando
@app.command("competitors")
def competitors(
    orgao: str = None,
    setor: str = None,
    modalidade: str = None,
    top: int = 10,
    rank: bool = False,
    win_rate: bool = False,
    ticket_medio: bool = False,
    format: str = "table",
):
    ...
```

### Win rate tracking manual (futuro)

Para win rate real (nao estimado), criar estrutura para tracking manual:

```sql
CREATE TABLE IF NOT EXISTS proposal_tracking (
    id SERIAL PRIMARY KEY,
    cnpj_extra VARCHAR(8) DEFAULT 'ExtraConstrutora',
    orgao_cnpj VARCHAR(14),
    licitacao_identificador VARCHAR(100),
    data_envio DATE,
    valor_proposta NUMERIC(18,2),
    resultado VARCHAR(20), -- 'vencida', 'perdida', 'cancelada', 'em_andamento'
    observacao TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

## Files to Create/Modify

- **CREATE** `db/migrations/028_competitors_views.sql` — Migration com todas as views
- **CREATE** `db/migrations/029_proposal_tracking.sql` — Tabela de tracking manual (opcional)
- **CREATE** `scripts/competitors/cli.py` — Logica do comando competitors
- **CREATE** `tests/test_competitors.py` — Testes
- **CREATE** `docs/competitors/known-limitations.md` — Documentacao de limitacoes
- **MODIFY** `scripts/local_datalake.py` — Adicionar comando `competitors`

## Rollback

- Migration 028 revertida, migration 029 revertida
- Comando `competitors` removido de `local_datalake.py`

## Observability

- Metrica: qtd_fornecedores_unicos, hhi_medio, orgaos_com_competicao
- Coverage manifest: `win_rate -> ready`
- Log de execucao do comando `competitors`

## Security Considerations

- Dados de concorrentes sao publicos (contratos assinados) — sem dados sensiveis
- Tracking manual de propostas (future) contem dados de negocio da Extra — garantir que `proposal_tracking` nao seja exposta

## Tests

- `test_v_competitor_map` — Verifica colunas e agregacao
- `test_v_competitors_by_orgao` — Verifica ranking por orgao
- `test_v_competitor_hhi` — Verifica calculo HHI (caso conhecido: 1 fornecedor = 10000)
- `test_win_rate_estimado` — Verifica formula de win rate
- `test_ticket_medio` — Verifica calculo com dados conhecidos
- `test_cli_competitors` — Smoke test do CLI

## Definition of Done

- [ ] AC1 a AC10 implementados e verificados
- [ ] Migrations 028 e 029 aplicadas limpas em PostgreSQL
- [ ] `local_datalake competitors` executa com dados reais e retorna resultados
- [ ] `local_datalake competitors --rank --orgao X` mostra ranking correto
- [ ] `local_datalake competitors --win-rate` mostra win rate estimado
- [ ] `coverage_manifest.commercial_metrics.win_rate.status == "ready"`
- [ ] `ruff check scripts/competitors/` retorna 0 erros
- [ ] `pytest tests/test_competitors.py -v` retorna all passed
