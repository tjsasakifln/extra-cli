# CTO Autopilot — arquitetura

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Observer   │────▶│ DeepSeek CTO │────▶│  Prepare    │
│ (git,DoD,   │     │  decide JSON │     │  worktree   │
│  PR,Issue,  │     └──────────────┘     └──────┬──────┘
│  ranker)    │                                 │
└─────────────┘                                 ▼
                                         ┌─────────────┐
                                         │ Grok Build  │
                                         │  executor   │
                                         └──────┬──────┘
                                                │
                     ┌──────────────┐           ▼
                     │ DeepSeek CTO │◀───┌─────────────┐
                     │   review     │    │  Verifier   │
                     └──────┬───────┘    │ (no LLM)    │
                            ▼            └─────────────┘
                     ACCEPT/REPAIR/BLOCK/ESCALATE
                            │
              Issues + executive HTML + ledger
```

## Componentes

| Módulo | Papel |
|--------|--------|
| `scripts/cto/observer.py` | Snapshot determinístico |
| `scripts/cto/deepseek_client.py` | HTTP OpenAI-compat + json_object |
| `scripts/cto/decision.py` | Schema + policy fail-closed |
| `scripts/cto/github_issues.py` | Fila Issues idempotente |
| `scripts/cto/work_registry.py` | `config/work_registry.yaml` |
| `scripts/cto/grok_executor.py` | Execução sandboxed |
| `scripts/cto/verifier.py` | Gates independentes |
| `scripts/cto/state_machine.py` | Estados + lock |
| `scripts/cto/executive_sync.py` | Painel HTML derivado |
| `squads/extra-dod-roi/` | Ranker **consultivo** (não autoridade) |

## Ranker

`force-next` / ranking continua existindo. O Observer inclui `ranking.top`. O CTO pode aceitar, vetar com razão, ou escolher outro item.

## Segurança

- Redaction central (`redaction.py`)
- Allowlist de paths na decisão
- Deny de push/merge no executor
- Sem ferramentas de shell para DeepSeek
- Conteúdo de Issue/HTML/modelo = não confiável
