# RECOVERY — sessão interrompida 2026-07-18

**Executado em:** 2026-07-18T17:41:32Z (UTC approx)  
**Workspace:** `/mnt/d/extra consultoria`  
**Remote:** `https://github.com/tjsasakifln/extra-consultoria.git`

## Resultado da recuperação forense

**Trabalho local recuperável: SIM — substancial.**

Não era uma sessão “vazia”. A branch épica da campanha anterior
(`epic/advance-30d-local-ready-20260718`) estava **12 commits à frente do
remoto** e continha merges de slices AIOX já com QA/PO.

### Baseline remoto verificado (não presumido)

| Item | Valor verificado |
|------|------------------|
| `main` / `origin/main` | `fbc586856332db11ecb21ae4524dfdf29dd90857` |
| HEAD local (pré-resgate) | `67a87b1d6435b355256270163985f951780fa5ec` |
| `origin/epic/advance-30d-local-ready-20260718` | `311e8ea31f7df2ffee4f2a06532320a37a00c5f3` |
| Ahead | **12 commits** não publicados |
| Worktrees | 1 (principal) |
| Stashes | 12 (históricos; **não** descartados) |
| DoD checkboxes (HEAD local) | **349/1354** aceitos |
| Progress snapshot | 48 slices; baseline_checked 92 → checked 345+ |

### Comandos forenses executados

```text
pwd
git remote -v
git status --short --branch
git branch -vv
git branch --all
git worktree list
git log --all --oneline --decorate --graph -50
git reflog -50
git stash list
git diff / git diff --cached
git ls-files --others --exclude-standard
ps aux (python/postgres relevant)
find locks / .aiox/state / squads/extra-dod-roi/state
```

Saídas capturadas em:

- `git-status.txt`
- `branches.txt`
- `worktrees.txt`
- `reflog.txt`
- `changed-files.txt`
- `untracked-sizes.txt`
- `secret-scan.txt`
- `env-meta.txt`
- `rescue-branch.txt`

## Classificação das mudanças

| Path | Classe | Ação |
|------|--------|------|
| 12 commits em `epic/advance-30d-local-ready-20260718` | **produto válido** (QA/PO) | push imediato |
| `squads/extra-dod-roi/state/cycles/current.json` | **estado AIOX** (ciclo STORY_DRAFT) | preservar + commit resgate |
| `.aiox/state/stories/ROI-cand-dyn-slice-b8d41f43fbfc.json` | **story incompleta** Draft | preservar |
| `docs/stories/ROI-cand-dyn-slice-b8d41f43fbfc.md` | **story incompleta** Draft | preservar |
| `squads/extra-dod-roi/state/execution-cards/current.json` | **estado AIOX** | já versionável / preservar |
| `backups/local-proof/*.dump` (7.6K cada) | **evidência** (pg_dump local-proof) | commit se sem segredo |
| `output/applicability-matrix/*` | **evidência** / artifact | commit seletivo |
| `output/pdfs/gp-pack-*` | **evidência** golden path PDF | commit seletivo |
| 12 stashes | **WIP histórico** | **não** drop |
| Branch `extra-roi/cand-full-suite-schema-debt` ahead 1 | **produto residual** | publicar se seguro |
| Postgres/uvicorn containers | processos de infra | não matar |

## Secret scan

- Heurística `api_key|secret|password|token|PRIVATE KEY|AKIA|sk_live|ghp_` em story/state/output: **sem matches de segredo**.
- Dumps: PostgreSQL custom dump v1.16, ~7.6K (prova local, não dump de produção).
- Nenhum `.env` ou credencial em untracked.

## Branch de resgate

```text
rescue/interrupted-session-20260718-20260718T174132Z
```

Aponta para o mesmo SHA do HEAD épico no momento da recuperação.

## Decisão de campanha (não descartar progresso)

**NÃO** fazer `git switch main` + nova branch vazia a partir de `main` e
abandonar os 12 commits / 48 slices.

A FASE 1 de “rebaseline” será executada **sobre o tip da branch épica
existente**, publicando-a e criando/atualizando artefatos em
`docs/ops/campaign-30d-operational-20260718/` com contagens **reais do HEAD**.

Motivo: o baseline remoto “92/1355” e a branch “não publicada” referem-se ao
estado **antes** desta campanha local; o trabalho já avançou para ~349 DoD e
deve ser preservado e publicado.

## Ciclo AIOX interrompido

| Campo | Valor |
|-------|-------|
| cycle_id | `cyc-2026-07-18T172517Z` |
| phase | `STORY_DRAFT` |
| next_phase_required | `STORY_READY` |
| selected | `cand-dyn-slice:b8d41f43fbfc` |
| story | `ROI-cand-dyn-slice-b8d41f43fbfc` |
| status story | Draft / po_validated=false |
| ranking rule | ranking[0] only |

## Regras absolutas respeitadas

1. Sem `git reset --hard`
2. Sem `git clean`
3. Sem apagar worktree/branch/stash/lock
4. Sem sobrescrever alterações locais
5. Sem add cego de dumps massivos / .env
6. Secret scan antes do commit de resgate

## Próximo comando seguro

Ver `next-safe-command.txt`.
