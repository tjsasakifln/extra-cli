---
story_id: B2G-2
status: draft
priority: P1
epic: EPIC-MASTER-B2G-READINESS
agent: @data-engineer
depends_on: [B2G-1, TD-2.1, TD-2.4]
---

# Story B2G-2: Metricas Comerciais — Preco Praticado

## Context

O PRD v2.0 define 4 momentos de valor em uma licitacao:

| Termo | Definição | Fonte Atual | Status |
|-------|-----------|-------------|--------|
| **Valor Estimado** | Valor estimado da licitacao, publicado no edital | PNCP (edital), DOM-SC | NOT_READY |
| **Valor Homologado** | Valor da proposta vencedora, homologado no resultado | PNCP (resultado), DOM-SC | NOT_READY |
| **Valor Contratado** | Valor global do contrato assinado | `pncp_supplier_contracts.valor_global` | DISPONIVEL |
| **Valor Pago** | Valor efetivamente empenhado/pago | Portais de transparencia, TCE-SC | NOT_READY |

O `valor_global` atualmente disponivel em `pncp_supplier_contracts` e o campo `valorGlobal` do PNCP — que e o valor do contrato assinado, **nao o preco praticado**. Para calcular preco praticado e desagio, precisamos de:

1. Valor estimado do edital (fonte: edital publicado, item "valor estimado")
2. Valor homologado da proposta vencedora (fonte: resultado da licitacao, item "valor homologado")
3. Capacidade de comparar estimado vs homologado por item/lote

### Decisao arquitetonica (ADR-002)

Conforme ADR-002, a abordagem e multi-source:

- **PNCP**: Fornece `valor_global` do contrato (disponivel). Nao expoe valores homologados item a item via API publica.
- **DOM-SC**: Publica resultado de licitacoes com valores homologados. Fonte principal para desagio.
- **TCE-SC**: Publica dados de empenhos (valor pago). Fonte para valor efetivamente pago.
- **Portais de transparencia**: Publicam dados de execucao financeira (valor pago).

Para esta story, o escopo e:

1. **Valor contratado** — ja disponivel, documentar semantica claramente
2. **Valor homologado** — extrair de DOM-SC (resultados de licitacao) quando disponivel
3. **Desagio** — calcular como (valor_estimado - valor_homologado) / valor_estimado, usando dados disponiveis
4. **CLI** — comando `precos` que mostra desagio medio por modalidade, orgao, periodo

## Acceptance Criteria

1. **AC1: Diagnostico de fontes** — Mapear exatamente quais fontes fornecem cada tipo de valor (estimado, homologado, contratado, pago) e qual a cobertura de cada uma no universo de 200km
2. **AC2: Schema extendido** — Migration cria colunas `valor_estimado`, `valor_homologado`, `valor_pago` em `pncp_raw_bids` ou tabela auxiliar, com semantica documentada
3. **AC3: Parser de valor homologado (DOM-SC)** — Implementar extracao de valor homologado de resultados publicados no DOM-SC, quando disponivel no HTML estruturado
4. **AC4: View de precos** — Criar view analitica `v_preco_praticado` com colunas: `orgao`, `cnpj_8`, `modalidade`, `objeto`, `valor_estimado`, `valor_homologado`, `valor_contratado`, `valor_pago`, `desagio_percentual`, `data_publicacao`, `fonte`
5. **AC5: Desagio calculado** — `desagio = (valor_estimado - valor_homologado) / valor_estimado * 100`. Quando apenas um dos valores estiver disponivel, a metrica e marcada como `parcial` com justificativa
6. **AC6: CLI `precos`** — Comando `local_datalake precos` com filtros: `--orgao`, `--modalidade`, `--periodo`, `--setor`, `--format table|json|csv`
7. **AC7: CLI mostra desagio medio** — `local_datalake precos --desagio-medio --por modalidade` retorna: modalidade, qtd_licitacoes, valor_estimado_medio, valor_homologado_medio, desagio_medio_percentual
8. **AC8: Testes** — Testes unitarios para calculo de desagio (incluindo edge cases: estimado = 0, homologado > estimado, valores nulos)
9. **AC9: Integracao com manifest** — `coverage_manifest.commercial_metrics.desagio.status == "ready"` apos implementacao
10. **AC10: Documentacao** — ADR-002 atualizado com resultados reais, semântica de cada coluna de valor documentada em `docs/semantics/value-semantics.md`

## Technical Design

### Schema

Migration para criar:

```sql
-- Tabela auxiliar para valores desambiguados
CREATE TABLE IF NOT EXISTS contract_values_disambiguated (
    id SERIAL PRIMARY KEY,
    source_contract_id INTEGER REFERENCES pncp_supplier_contracts(id),
    source_bid_id INTEGER REFERENCES pncp_raw_bids(id),
    orgao_cnpj VARCHAR(14),
    orgao_nome VARCHAR(500),
    cnpj_8 VARCHAR(8),
    modalidade VARCHAR(100),
    objeto TEXT,
    valor_estimado NUMERIC(18,2),
    valor_homologado NUMERIC(18,2),
    valor_contratado NUMERIC(18,2),
    valor_pago NUMERIC(18,2),
    fonte_estimado VARCHAR(50),
    fonte_homologado VARCHAR(50),
    fonte_contratado VARCHAR(50),
    fonte_pago VARCHAR(50),
    data_publicacao DATE,
    data_assinatura DATE,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### View analitica

```sql
CREATE OR REPLACE VIEW v_preco_praticado AS
SELECT
    cnpj_8,
    orgao_nome,
    modalidade,
    objeto,
    valor_estimado,
    valor_homologado,
    valor_contratado,
    valor_pago,
    CASE
        WHEN valor_estimado IS NOT NULL AND valor_homologado IS NOT NULL AND valor_estimado > 0
        THEN ROUND(((valor_estimado - valor_homologado) / valor_estimado) * 100, 2)
        ELSE NULL
    END AS desagio_percentual,
    CASE
        WHEN valor_estimado IS NOT NULL AND valor_homologado IS NOT NULL THEN 'completo'
        WHEN valor_contratado IS NOT NULL THEN 'parcial_contrato'
        ELSE 'indisponivel'
    END AS status_metrica,
    data_publicacao,
    fonte_estimado,
    fonte_homologado,
    fonte_contratado,
    fonte_pago
FROM contract_values_disambiguated;
```

### CLI

```python
# scripts/local_datalake.py novo comando
@app.command("precos")
def precos(
    orgao: str = None,
    modalidade: str = None,
    periodo: str = None,
    setor: str = None,
    desagio_medio: bool = False,
    por: str = "modalidade",  # modalidade, orgao, periodo
    format: str = "table",
    limit: int = 20,
):
    ...
```

## Files to Create/Modify

- **CREATE** `db/migrations/027_value_disambiguation.sql` — Migration com tabela + view
- **CREATE** `scripts/precos/__init__.py`
- **CREATE** `scripts/precos/pipeline.py` — Pipeline de extracao e calculo
- **CREATE** `scripts/precos/desagio.py` — Logica de calculo de desagio
- **CREATE** `tests/test_precos.py` — Testes unitarios
- **MODIFY** `scripts/local_datalake.py` — Adicionar comando `precos`
- **MODIFY** `docs/decisions/adr-002-preco-praticado.md` — Atualizar com resultados
- **CREATE** `docs/semantics/value-semantics.md` — Documentacao de semantica de valores

## Rollback

- Migration 027 revertida: `db/migrations/027_value_disambiguation.sql` com `DROP VIEW IF EXISTS v_preco_praticado; DROP TABLE IF EXISTS contract_values_disambiguated;`
- Comando `precos` removido de `local_datalake.py`

## Observability

- Logging em `scripts/precos/pipeline.py` — quantas linhas processadas, quantas com valores desambiguados
- Metrica: desagio_medio_calculado, qtd_licitacoes_com_desagio
- Coverage manifest reflete novo status de `desagio`

## Security Considerations

- Dados de precos sao publicos (licitacoes) — sem dados sensiveis
- Nenhuma autenticacao adicional necessaria

## Tests

- `test_desagio_calculo_basico` — valida formula com valores conhecidos
- `test_desagio_estimado_zero` — edge case: divisao por zero
- `test_desagio_homologado_maior` — edge case: desagio negativo (superavit)
- `test_desagio_valores_nulos` — NULL handling
- `test_view_preco_praticado` — integracao com PostgreSQL
- `test_cli_precos` — smoke test do comando

## Definition of Done

- [ ] AC1 a AC10 implementados e verificados
- [ ] Migration 027 aplicada limpa em PostgreSQL
- [ ] `local_datalake precos` executa com dados reais e retorna resultados
- [ ] Desagio medio calculado para ao menos 1 modalidade, 1 orgao, 1 periodo
- [ ] `coverage_manifest.commercial_metrics.desagio.status == "ready"`
- [ ] `ruff check scripts/precos/` retorna 0 erros
- [ ] `pytest tests/test_precos.py -v` retorna all passed
