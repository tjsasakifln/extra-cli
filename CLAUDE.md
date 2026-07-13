# Extra Consultoria

<!-- PROJECT-CUSTOMIZED: AIOX-OPERATING-PROTOCOL -->
## Protocolo AIOX — Obrigatório

**Toda solicitação de desenvolvimento segue o AIOX automaticamente.**
Regra: `.claude/rules/aiox-project-operating-protocol.md`
Skills: `.claude/skills/aiox-*/SKILL.md`

### Regras fundamentais

1. **AIOX é modo padrão.** Agentes, workflows e gates inferidos automaticamente. Não digite `@agente`.
2. **Story obrigatória antes de código.** @sm cria → @po valida → @dev implementa. Exceção: FAST.
3. **Ciclo completo:** @sm → @po → @dev → @qa → @po fecha → @devops publica.
4. **Autoridade exclusiva:** @devops push/PR, @architect arquitetura, @qa veredito, @po fechamento.
5. **Níveis de risco:** FAST (trivial), STANDARD (normal, default), HIGH-RISK (segurança/dados/arch).
6. **QA independente:** Nunca o implementador como única fonte de validação.

### Workflows automáticos

| Solicitação | Nível | Workflow |
|------------|-------|----------|
| "corrija um typo no README" | FAST | Registro + diff |
| "corrija um bug" | STANDARD | SDC completo |
| "implemente uma feature" | STANDARD | Spec Pipeline → SDC |
| "refatore este módulo" | STANDARD | Impacto → SDC |
| "faça uma migration" | HIGH-RISK | @data-engineer → @architect → SDC |
| "publique as alterações" | — | @qa gate → @devops push |
| "auditoria do sistema" | — | Brownfield Discovery |

### Correção de desvio

Código sem story, agente fora de autoridade, QA autoaplicado, push sem gates → interromper e corrigir.

> Protocolo completo: `.claude/rules/aiox-project-operating-protocol.md` (10 seções)
<!-- END: AIOX-OPERATING-PROTOCOL -->

---

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
python scripts/crawl/monitor.py --source pncp --mode full
python scripts/crawl/monitor.py --source all --mode incremental
python scripts/crawl/monitor.py --report-coverage

# Testes
pytest tests/ -v
pytest -m unit
pytest --cov=scripts --cov-report=term-missing

# Lint e Type Check
ruff check scripts/
ruff format scripts/
mypy scripts/

# Pipeline de Inteligencia
python scripts/intel_pipeline.py --cnpj <CNPJ> --ufs SC
python scripts/reports/panorama.py --output-excel

# DataLake CLI
python scripts/local_datalake.py search --uf SC --dias 30
python scripts/local_datalake.py supplier --cnpj <CNPJ>
python scripts/local_datalake.py stats

# Opportunity Intelligence
python scripts/opportunity_intel/cli.py list --status open --limit 20
python scripts/opportunity_intel/cli.py show 1
python scripts/opportunity_intel/cli.py explain 1
python scripts/opportunity_intel/cli.py coverage
python scripts/opportunity_intel/cli.py source-health
python scripts/opportunity_intel/cli.py update --source pncp
python scripts/opportunity_intel/cli.py export --format csv -o opportunities.csv
python scripts/opportunity_intel/manifest.py

# Infra (VPS)
ssh ec-prod "systemctl list-timers 'extra-*'"
ssh ec-prod "journalctl -u extra-crawl-pncp.service -n 30"

# Cache IBGE
python -c "from scripts.crawl.enricher import _ibge_cache; _ibge_cache.clear()"
```

## Quality Assurance Toolkit (incorporado do ECC)

Acervo de agentes, comandos e skills de qualidade de código Python.
Origem: [affaan-m/ecc](https://github.com/affaan-m/ecc) — adaptado para stack Python/crawling/dados.

### Uso Proativo (OBRIGATÓRIO)

| Gatilho | Ação Proativa |
|---------|---------------|
| Editando arquivo `.py` | Rode `/quality-gate` no arquivo após editar |
| Antes de commit (`git commit`) | Rode `/code-review` em modo local |
| Criando/alterando crawler | Ative skill `error-handling` |
| Escrevendo função pública nova | Ative skill `coding-standards` |
| Refatorando script existente | Ative skill `python-patterns` |
| Debugging de falha em produção | Invoque agente `silent-failure-hunter` |
| Adicionando chamada HTTP/API | Ative skill `error-handling` |
| Revisão de PR/ código alheio | Invoque agente `python-reviewer` |
| Alterando autenticação/secrets | Invoque agente `security-reviewer` |
| Suspeita de vulnerabilidade | Invoque agente `security-reviewer` + `bandit -r scripts/` |

### Comandos Disponíveis

| Comando | Quando Usar |
|---------|-------------|
| `/code-review` | Revisão completa local ou PR |
| `/quality-gate` | Gate rápido: formatação + lint + type check |

### Fluxo de Qualidade Padrão

```
Editar código → /quality-gate → Corrigir → /code-review → Commit → Push
```
