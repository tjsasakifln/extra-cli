# ADR-020 — Operational Data Not in Git

| Campo | Valor |
|-------|-------|
| **Status** | Accepted |
| **Data** | 2026-07-17 |
| **Decisores** | PM (Morgan), Architect, DevOps |
| **Epic** | E3 Resilient scheduled collection (transversal) |

---

## Contexto

O repositório acumula:

- `output/**` JSONL/JSON de crawls e relatórios;
- checkpoints em `data/*_checkpoints/`;
- dumps raw e artefatos de sessão misturados a código.

Efeitos: working tree sujo, PRs gigantes, risco de commitar PII/volume, confusão entre **evidência auditável** e **dado operacional mutável**, e CI frágil.

## Decisão

### Classificação de artefatos

| Classe | Exemplos | Git? | Onde vive |
|--------|----------|------|-----------|
| **A. Código & schema** | scripts/, db/migrations/, config templates | **Sim** | repo |
| **B. Specs & decisões** | docs/prd, docs/architecture, stories, ADRs | **Sim** | repo |
| **C. Evidência de gate carimbada** | `docs/ops/session-*/` summary, coverage_canonical **agregado**, hashes | **Sim (mínimo)** | repo — só resumo + hashes + paths |
| **D. Operacional / raw** | JSONL crawls, raw payloads, checkpoints quentes, DB dumps | **Não** | `output/`, `data/`, object storage, VPS paths |
| **E. Segredos** | .env, keys | **Nunca** | secret store / env |

### Políticas

1. **Raw dumps nunca entram no git** (JSONL de publicações, payloads API, PDFs).
2. Checkpoints operacionais: gitignore; opcionalmente **schema** de checkpoint versionado, não o estado quente.
3. Relatórios de release: commitar **apenas** manifesto resumido (`as_of`, counts, sha256 dos artefatos externos, git_sha).
4. CI não depende de JSONL grandes no repo; fixtures mínimas em `tests/fixtures/`.
5. Documentar layout:

```
output/                  # gitignored operational
  {source}/{run_id}/
data/                    # gitignored checkpoints & caches
docs/ops/session-*/      # stamped evidence (small)
```

6. Scripts de crawl escrevem **somente** em output/data; se gerarem docs, é passo explícito de “seal/stamp”.

## Alternativas rejeitadas

| Alternativa | Motivo |
|-------------|--------|
| Commitar tudo “para reprodutibilidade” | Repo inviável; não é reprodutibilidade de código |
| Nada no git (zero evidência) | Quebra auditoria AIOX / DoD |
| Git-LFS para raw | Complexidade; ainda polui histórico |

## Consequências

- Atualizar `.gitignore` (story E3) sem apagar histórico já commitado em follow-up.
- DoD de crawls exige path em `output/` + stamp opcional em docs/ops.
- DevOps valida PRs: bloquear JSONL grandes e dumps.

## Critérios de aceite

- [ ] Política documentada e referenciada no epic E3
- [ ] Novos crawls default para paths gitignored
- [ ] Checklist pre-push / review menciona ban de raw dumps

## Referências

- Session seals: `docs/ops/session-2026-07-17/`
- Epic E3 · story collection paths
