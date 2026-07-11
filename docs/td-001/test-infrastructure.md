# Test Infrastructure

> Documentacao da infraestrutura de testes estabelecida na Story TD-1.3.
> Debitto tecnico: TD-SYS-009 (CRITICAL — Ausencia de testes automatizados).

## Framework

- **Test runner:** pytest 8.4.1
- **Coverage:** pytest-cov 4.1.0
- **Config file:** `pytest.ini` (raiz do projeto)
- **Conftest compartilhado:** `conftest.py` (raiz do projeto)

## Estrutura

```
tests/
  __init__.py                  # Pacote Python
  test_compras_gov_crawler.py  # Testes existentes (crawler compras.gov)
  test_pcp_crawler.py          # Testes existentes (crawler PCP v2)
  test_transformer.py          # NOVO — Testes do modulo transformer.py
pytest.ini                     # Configuracao pytest
conftest.py                    # Fixtures compartilhadas
```

## Comandos

```bash
# Executar todos os testes
pytest

# Executar com coverage (formato terminal + HTML)
pytest --cov=scripts --cov-report=term-missing

# Executar apenas testes do transformer
pytest tests/test_transformer.py -v

# Executar apenas testes unitarios puros (marker)
pytest -m unit -v

# Gerar relatorio HTML de cobertura
pytest --cov=scripts --cov-report=html:docs/td-001/coverage-reports/
```

## Cobertura (Baseline)

| Modulo | Cobertura | Status |
|--------|-----------|--------|
| `scripts/crawl/transformer.py` | 100% | Alvo inicial |
| `scripts/crawl/pcp_crawler.py` | 60% | Cobertura parcial |
| `scripts/crawl/compras_gov_crawler.py` | 61% | Cobertura parcial |
| Todos os demais modulos | 0% | Pendente (proximas stories) |
| **Total do projeto** | **1%** | **Baseline inicial** |

## Proxima Expansao (Stories Planejadas)

| Story | Escopo | Pre-requisito |
|-------|--------|---------------|
| TD-3.1 | Refatorar `monitor.py` para tornar testavel | — |
| TD-3.2 | Consolidar crawlers (schema de output unificado) | — |
| TD-4.1 | Expandir cobertura para > 40% | TD-3.1, TD-3.2 completas |

## Fixtures Compartilhadas

Definidas em `conftest.py`:

- `sample_pncp_item`: Item PNCP minimo valido para testes de transformacao.

Fixture design decisions:
- Escopo `function` (default) — mais seguro para testes que mutam dados.
- Novas fixtures devem ser adicionadas ao `conftest.py` quando compartilhadas por 2+ modulos de teste.

## Convencoes de Teste

1. **Nome de teste:** `test_<o_que_testa>_<condicao>` — descritivo, em ingles.
2. **Organizacao:** Classes `TestXxx` agrupando testes por funcao/modulo.
3. **Dados mock:** Inline no arquivo de teste ou via fixture no `conftest.py`.
4. **Isolamento:** Testes unitarios puros nao devem depender de database, rede ou IO de arquivos.
5. **Assertions:** Preferir `assert` nativo do Python sobre metodos `self.assert*`.

## Referencias

- Story TD-1.3: `docs/stories/epics/epic-td-001-resolution/story-TD-1.3-iniciar-testes.md`
- Epic TD-001: `docs/stories/epics/epic-td-001-resolution/`
- Relatorio HTML de cobertura: `docs/td-001/coverage-reports/index.html`
