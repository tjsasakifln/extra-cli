# Reversa

> Framework de Engenharia Reversa instalado neste projeto.

## Como usar

Use o fluxo adequado no chat:

- `/reversa` — descobrir e documentar um sistema existente
- `/reversa-new` — criar PRD e specs para um projeto novo
- `/reversa-forward` — implementar ou evoluir código a partir das specs
- `/reversa-migrate` — planejar a migração de um sistema legado
- `/reversa-docs` — gerar o mini-site visual da documentação
- `/reversa-agents-help` — consultar o catálogo completo de agentes

## Comportamento ao ativar

Quando o usuário digitar `/reversa` ou a palavra `reversa` sozinha em uma mensagem:

1. Ative o skill `reversa` disponível em `.claude/skills/reversa/SKILL.md`
2. Se não encontrar em `.claude/skills/`, tente `.agents/skills/reversa/SKILL.md`
3. Leia o SKILL.md na íntegra e siga exatamente as instruções do Reversa

## Regra não-negociável

Nunca apague, modifique ou sobrescreva arquivos pré-existentes do projeto legado.
O Reversa escreve apenas em `.reversa/`, `_reversa_sdd/`, `_reversa_docs/` e `_reversa_forward/`.

## Comandos Frequentes (Extra Consultoria)

```bash
# Crawl
python scripts/crawl/monitor.py --source pncp --mode full        # Crawl completo PNCP
python scripts/crawl/monitor.py --source all --mode incremental   # Crawl incremental todas fontes
python scripts/crawl/monitor.py --report-coverage                 # Relatorio de cobertura

# Testes
pytest tests/test_cache_ibge.py -v                                # Testes do cache IBGE
pytest tests/test_transformer.py -v                               # Testes do transformer
pytest -m unit                                                     # Apenas testes unitarios
pytest --cov=scripts --cov-report=term-missing                    # Com cobertura

# Lint e Type Check
ruff check scripts/                                               # Lint
ruff format scripts/                                              # Formatacao
mypy scripts/                                                     # Type checking

# Pipeline de Inteligencia
python scripts/intel_pipeline.py --cnpj <CNPJ> --ufs SC           # Pipeline para 1 CNPJ
python scripts/reports/panorama.py --output-excel                 # Relatorio panoramico

# DataLake CLI
python scripts/local_datalake.py search --uf SC --dias 30         # Buscar licitacoes
python scripts/local_datalake.py supplier --cnpj <CNPJ>           # Dados de fornecedor
python scripts/local_datalake.py stats                            # Estatisticas

# Opportunity Intelligence (licitacoes abertas, raio 200km Fpolis)
python scripts/opportunity_intel/cli.py list --status open --limit 20
python scripts/opportunity_intel/cli.py show 1
python scripts/opportunity_intel/cli.py explain 1
python scripts/opportunity_intel/cli.py coverage
python scripts/opportunity_intel/cli.py source-health
python scripts/opportunity_intel/cli.py update --source pncp
python scripts/opportunity_intel/cli.py export --format csv -o opportunities.csv
python scripts/opportunity_intel/manifest.py                     # Manifestos de cobertura

# Infra (VPS)
ssh ec-prod "systemctl list-timers 'extra-*'"                     # Listar timers
ssh ec-prod "journalctl -u extra-crawl-pncp.service -n 30"        # Logs do crawler

# Cache IBGE
python -c "from scripts.crawl.enricher import _ibge_cache; _ibge_cache.clear()"  # Limpar cache
```

## Quality Assurance Toolkit (incorporado do ECC)

Acervo de agentes, comandos e skills de qualidade de código Python.
Origem: [affaan-m/ecc](https://github.com/affaan-m/ecc) — adaptado para stack Python/crawling/dados.

### Uso Proativo (OBRIGATÓRIO)

Sempre que pertinente, ative **proativamente** estes recursos sem que o usuário precise pedir:

| Gatilho | Ação Proativa |
|---------|---------------|
| Editando arquivo `.py` | Rode `/quality-gate` no arquivo após editar |
| Antes de commit (`git commit`) | Rode `/code-review` em modo local |
| Criando/alterando crawler | Ative skill `error-handling` para padrões de retry/logging |
| Escrevendo função pública nova | Ative skill `coding-standards` para nomenclatura e docstrings |
| Refatorando script existente | Ative skill `python-patterns` para padrões Pythonicos |
| Debugging de falha em produção | Invoque agente `silent-failure-hunter` para caçar exceções engolidas |
| Adicionando chamada HTTP/API | Ative skill `error-handling` para retry/circuit breaker |
| Revisão de PR/ código alheio | Invoque agente `python-reviewer` para revisão completa |
| Alterando autenticação/secrets | Invoque agente `security-reviewer` para scan de segurança |
| Suspeita de vulnerabilidade | Invoque agente `security-reviewer` + `bandit -r scripts/` |

### Agentes Disponíveis

| Agente | Arquivo | Quando Usar |
|--------|---------|-------------|
| **python-reviewer** | `.claude/agents/python-reviewer.md` | Review de código Python (PEP 8, type hints, segurança, padrões) |
| **silent-failure-hunter** | `.claude/agents/silent-failure-hunter.md` | Caçar exceções engolidas, fallbacks perigosos e logging inadequado |
| **security-reviewer** | `.claude/agents/security-reviewer.md` | Scan de vulnerabilidades OWASP, secrets, injeção, crypto |

Para invocar: mencione o nome do agente no chat (ex: "revise este arquivo com python-reviewer").

### Comandos Disponíveis

| Comando | Arquivo | Quando Usar |
|---------|---------|-------------|
| `/code-review` | `.claude/commands/code-review.md` | Revisão completa local ou PR (segurança + padrões + testes) |
| `/quality-gate` | `.claude/commands/quality-gate.md` | Gate rápido: formatação + lint + type check (pré-commit) |

### Skills Disponíveis

| Skill | Arquivo | Quando Usar |
|-------|---------|-------------|
| **error-handling** | `.claude/skills/error-handling/SKILL.md` | Padrões de erro Python: exceções tipadas, retry, circuit breaker, logging |
| **coding-standards** | `.claude/skills/coding-standards/SKILL.md` | Convenções de código: nomenclatura, KISS, DRY, imutabilidade, code smells |
| **python-patterns** | `.claude/skills/python-patterns/SKILL.md` | Padrões Pythonicos: type hints, dataclasses, geradores, decorators, concorrência |

Para ativar: use `Skill` tool com o nome da skill (ex: `error-handling`).

### Fluxo de Qualidade Padrão

```
Editar código → /quality-gate (automático) → Corrigir → /code-review (manual) → Commit → Push
```

- `/quality-gate`: ~2s, roda `ruff format --check` + `ruff check` no arquivo
- `/code-review`: ~30s, revisão completa com `mypy` + `pytest` + `bandit` + revisão humana
- Ambos bloqueiam commit se CRÍTICO ou ALTO encontrado
