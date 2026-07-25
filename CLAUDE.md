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

## Guia canônico e onboarding

- **Dev/ops:** [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md)
- **Onboarding / estado honesto:** [`README.md`](README.md)
- **Hub de docs:** [`docs/INDEX.md`](docs/INDEX.md)
- **DoD:** [`DOD.md`](DOD.md) — não inventar selos sem evidência

## Comandos Frequentes (Extra Consultoria)

```bash
# Setup / validação / golden path / weekly (canônicos)
export LOCAL_DATALAKE_DSN="${LOCAL_DATALAKE_DSN:-postgresql://test:test@127.0.0.1:5433/extra_test}"
python3 -m scripts.ops.apply_migrations --dsn "$LOCAL_DATALAKE_DSN"
python3 -m pytest tests/ -q --tb=no -x
python3 -m scripts.golden_path --dsn "$LOCAL_DATALAKE_DSN"
make extra-weekly   # python3 -m scripts.ops.weekly_cycle --strict

# Workspace (dia a dia)
python3 -m scripts.workspace today
python3 -m scripts.workspace coverage
python3 -m scripts.workspace opportunities --status open --limit 20

# Crawl
python3 -m scripts.crawl.monitor --source pncp --mode full
python3 -m scripts.crawl.monitor --source all --mode incremental
python3 -m scripts.crawl.monitor --report-coverage

# Testes / lint
pytest tests/ -v
ruff check scripts/
ruff format scripts/
mypy scripts/

# Opportunity Intelligence
python3 -m scripts.opportunity_intel.cli list --status open --limit 20
python3 -m scripts.opportunity_intel.cli source-health
python3 -m scripts.opportunity_intel.cli update --source pncp

# DOD / campanha
python3 tools/dod_controller.py next
python3 squads/extra-dod-roi/scripts/cli.py force-next

# Infra (VPS — host de record Netcup; ≠ VPS_OPERATIONAL)
ssh ec-prod "systemctl list-timers 'extra-*' 'pncp-*'"
ssh ec-prod "journalctl -u pncp-contracts.service -n 30"
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


## Canonical development guide

**Guia canônico:** [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md)
