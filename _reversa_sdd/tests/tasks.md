# Tests — Tasks

> Gerado pelo Writer em 2026-07-13T21:30:00Z | doc_level: completo

## Tarefas de Implementacao

### Grupo A: Gates de Cobertura (plano-mestre §18 — PRIORIDADE MAXIMA)

| # | Tarefa | Fonte | Criterio de Pronto | Confianca |
|---|--------|-------|-------------------|-----------|
| T-TS01 | Implementar gate de cobertura >=80% para `scripts/lib/universe.py` | `plano-mestre §18` | CI bloqueia se coverage < 80% em universe.py | 🔴 |
| T-TS02 | Implementar gate de cobertura >=80% para `scripts/opportunity_intel/` | `plano-mestre §18` | CI bloqueia se coverage < 80% no modulo | 🔴 |
| T-TS03 | Implementar gate de cobertura >=80% para reconciliation pipeline | `plano-mestre §18` | CI bloqueia se coverage < 80% | 🔴 |
| T-TS04 | Implementar gate de cobertura >=80% para coverage module | `plano-mestre §18` | CI bloqueia se coverage < 80% | 🔴 |
| T-TS05 | Implementar gate de cobertura >=80% para contract pipeline | `plano-mestre §18` | CI bloqueia se coverage < 80% | 🔴 |
| T-TS06 | Implementar gate de cobertura >=80% para supplier metrics | `plano-mestre §18` | CI bloqueia se coverage < 80% | 🔴 |
| T-TS07 | Implementar gate de cobertura >=80% para price pipeline | `plano-mestre §18` | CI bloqueia se coverage < 80% | 🔴 |
| T-TS08 | Implementar gate de cobertura >=80% para report builder | `plano-mestre §18` | CI bloqueia se coverage < 80% | 🔴 |
| T-TS09 | Configurar CI para `REQUIRE_TEST_DB=1` em stage de integracao | `plano-mestre §18`, `conftest_db.py:65` | Testes de integracao falham explicitamente se DB nao disponivel | 🟡 |

### Grupo B: Expansao de Testes (Lacunas de Cobertura)

| # | Tarefa | Fonte | Criterio de Pronto | Confianca |
|---|--------|-------|-------------------|-----------|
| T-TS10 | Criar testes para `scripts/lib/universe.py` — algoritmo de universo canonico | `test_universe.py` (existente, cobertura insuficiente) | Cobertura >=80% em universe.py | 🔴 |
| T-TS11 | Criar testes para reconciliation pipeline (cross-source matching, denominadores, percentis, desagio) | `plano-mestre §18` secao "Testes de dados" | Cobertura >=80%, todos os 12 tipos de teste de dados implementados | 🔴 |
| T-TS12 | Criar testes para supplier metrics (rankings, market share, award share, HHI) | `plano-mestre §18`, `consulting_readiness.py` | Cobertura >=80%, metricas comerciais validadas | 🔴 |
| T-TS13 | Criar testes para price pipeline (precificacao, desagio, consistencia) | `plano-mestre §18` | Cobertura >=80% | 🔴 |
| T-TS14 | Criar testes para report builder (geracao de relatorios, formatos Excel/PDF) | `plano-mestre §18` | Cobertura >=80% | 🔴 |
| T-TS15 | Criar golden tests para relatorios de cobertura e intel | `plano-mestre §18` secao "golden report" | Dados congelados validados contra saida esperada | 🔴 |

### Grupo C: Testes de Dados (plano-mestre §18)

| # | Tarefa | Fonte | Criterio de Pronto | Confianca |
|---|--------|-------|-------------------|-----------|
| T-TS16 | Implementar teste de identidade CNPJ (formato, digito verificador, consistencia) | `plano-mestre §18` | Teste falha se CNPJ invalido ou inconsistente | 🟡 |
| T-TS17 | Implementar teste de duplicidade cross-source | `plano-mestre §18` | Nenhuma duplicata entre fontes diferentes para mesmo contrato | 🟡 |
| T-TS18 | Implementar teste de datas (formato, consistencia, ordem cronologica) | `plano-mestre §18` | Datas validas e consistentes em todas as fontes | 🟡 |
| T-TS19 | Implementar teste de valores (numericos, positivos, consistencia estimated vs homologated) | `plano-mestre §18` | Valores validos e consistentes | 🟡 |
| T-TS20 | Implementar teste de paginacao (todas as paginas, sem perda) | `plano-mestre §18` | Crawlers retornam todos os registros independente de paginacao | 🟡 |
| T-TS21 | Implementar teste de zero real (fonte retorna 0 registros validos) | `plano-mestre §18` | Crawler nao falha quando fonte tem 0 registros no periodo | 🟡 |
| T-TS22 | Implementar teste de freshness (dados atualizados dentro do SLA) | `plano-mestre §18` | SLA de frescor por fonte validado | 🟡 |
| T-TS23 | Implementar teste de stale (dados desatualizados sao detectados) | `plano-mestre §18` | Alerta de stale dispara quando SLA excedido | 🟡 |
| T-TS24 | Implementar teste de reconciliação (cross-source, contagem, valores) | `plano-mestre §18` | Dados reconciliados entre fontes diferentes | 🟡 |
| T-TS25 | Implementar teste de consistencia Excel/PDF | `plano-mestre §18` | Relatorios em Excel e PDF tem mesmos dados | 🟡 |

### Grupo D: Infraestrutura de Qualidade

| # | Tarefa | Fonte | Criterio de Pronto | Confianca |
|---|--------|-------|-------------------|-----------|
| T-TS26 | Configurar stage de CI para `pytest -m unit` (gate rapido) | `pytest.ini:addopts` | CI executa testes unitarios em < 30s | 🟢 |
| T-TS27 | Configurar stage de CI para `pytest -m integration` com `REQUIRE_TEST_DB=1` | `pytest.ini` | CI executa testes de integracao com PostgreSQL real | 🟢 |
| T-TS28 | Configurar stage de CI para `ruff check` + `ruff format --check` | `pyproject.toml` | CI bloqueia se lint falha | 🟢 |
| T-TS29 | Configurar stage de CI para `bandit -r scripts/` | `pyproject.toml` | CI bloqueia se bandit encontra vulnerabilidades criticas | 🟢 |
| T-TS30 | Configurar stage de CI para `python -m compileall scripts/` | `plano-mestre §18` | CI bloqueia se compileall falha | 🟢 |
| T-TS31 | Configurar stage de CI para `pip-audit` | `plano-mestre §18` | CI bloqueia se dependencia com vulnerabilidade conhecida | 🟢 |
| T-TS32 | Habilitar mypy gradualmente em `tests/` — remover `ignore_errors = true` | `pyproject.toml:mypy.overrides` | mypy passa em tests/ com `disallow_untyped_defs` (opcional) | 🟡 |

### Grupo E: Testes de Contrato de Fonte (plano-mestre §18)

| # | Tarefa | Fonte | Criterio de Pronto | Confianca |
|---|--------|-------|-------------------|-----------|
| T-TS33 | Implementar contract test para fonte PNCP | `plano-mestre §18` secao "contract tests de cada fonte" | Teste valida schema de resposta, campos obrigatorios, paginacao | 🟡 |
| T-TS34 | Implementar contract test para fonte DOM-SC | `plano-mestre §18` | Teste valida schema, auth, categorias | 🟡 |
| T-TS35 | Implementar contract test para fonte DOE-SC | `plano-mestre §18` | Teste valida schema, auth Bearer, paginacao | 🟡 |
| T-TS36 | Implementar contract test para fonte ComprasGov | `plano-mestre §18` | Teste valida 2 endpoints (legado + Lei 14.133) | 🟡 |
| T-TS37 | Implementar contract test para fonte TCE-SC | `plano-mestre §18` | Teste valida schema SCMWeb | 🟡 |
| T-TS38 | Implementar contract test para fonte SC Compras | `plano-mestre §18` | Teste valida extracao HTML | 🟡 |
| T-TS39 | Implementar contract test para fonte PCP v2 | `plano-mestre §18` | Teste valida schema e modalidade mapping | 🟡 |
| T-TS40 | Implementar contract test para portais de transparencia (4 templates) | `plano-mestre §18` | Teste valida deteccao de plataforma e extracao minima | 🟡 |

### Grupo F: Testes de Pipeline de Oportunidade (QW-01)

| # | Tarefa | Fonte | Criterio de Pronto | Confianca |
|---|--------|-------|-------------------|-----------|
| T-TS41 | Testar QW-01 radar: pipeline completo de oportunidade | `test_qw01_radar.py` | Testes de integracao com dados reais, gates executados no artefato | 🟡 |
| T-TS42 | Testar QW-01 Postgres: persistencia e queries do radar | `test_qw01_postgres.py` | Dados persistidos corretamente, queries retornam resultados esperados | 🟡 |

### Grupo G: Documentacao e Relatorios

| # | Tarefa | Fonte | Criterio de Pronto | Confianca |
|---|--------|-------|-------------------|-----------|
| T-TS43 | Documentar setup de ambiente de teste (docker-compose, env vars, fixture) | `conftest_db.py`, `README.md` | Novo desenvolvedor consegue rodar todos os testes em < 10 min | 🟡 |
| T-TS44 | Gerar relatorio de cobertura consolidado por modulo | `pytest.ini:--cov-report=html` | Relatorio HTML publicado no CI | 🟢 |
| T-TS45 | Mapear cobertura atual dos 8 modulos criticos do plano-mestre §18 | `plano-mestre §18` | Tabela de cobertura por modulo disponivel | 🔴 |

## Dependencias entre Tarefas

```
T-TS09 (REQUIRE_TEST_DB=1) → T-TS26..T-TS27 (CI stages)
T-TS01..T-TS08 (gates cobertura) → T-TS10..T-TS15 (expansao testes)
T-TS16..T-TS25 (testes de dados) → T-TS43 (documentacao)
T-TS33..T-TS40 (contract tests) → T-TS09 (DB real disponivel)
T-TS28..T-TS31 (gates qualidade) → paralelo com todos os grupos
T-TS44..T-TS45 (relatorios) → apos T-TS01..T-TS08 implantados

Sequencia recomendada:
1. T-TS28..T-TS31 (gates CI quality — ja configurados via pyproject.toml)
2. T-TS09 (REQUIRE_TEST_DB=1 no CI)
3. T-TS01..T-TS08 (gates de cobertura — plano-mestre §18)
4. T-TS10..T-TS15 (expansao de testes para modulos criticos)
5. T-TS16..T-SS25 (testes de dados)
6. T-TS33..T-TS40 (contract tests por fonte)
7. T-TS41..T-TS42 (QW-01 QA gates)
8. T-TS44..T-TS45 (relatorios)
```

## Estimativa de Esforco

| Categoria | Tarefas | Esforco estimado |
|-----------|---------|-----------------|
| Gates de cobertura (CI) | T-TS01..T-TS09 | 2-3 dias |
| Expansao de testes (cobertura) | T-TS10..T-TS15 | 5-8 dias |
| Testes de dados | T-TS16..T-TS25 | 3-5 dias |
| Infraestrutura de qualidade | T-TS26..T-TS32 | 1-2 dias |
| Contract tests | T-TS33..T-TS40 | 3-5 dias |
| Testes QW-01 | T-TS41..T-TS42 | 1 dia |
| Documentacao e relatorios | T-TS43..T-TS45 | 1 dia |
| **Total** | 45 tarefas | **16-25 dias** |
