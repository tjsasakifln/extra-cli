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

# Infra (VPS)
ssh ec-prod "systemctl list-timers 'extra-*'"                     # Listar timers
ssh ec-prod "journalctl -u extra-crawl-pncp.service -n 30"        # Logs do crawler

# Cache IBGE
python -c "from scripts.crawl.enricher import _ibge_cache; _ibge_cache.clear()"  # Limpar cache
```
