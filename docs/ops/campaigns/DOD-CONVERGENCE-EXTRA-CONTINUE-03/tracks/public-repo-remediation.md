# Public Repo Remediation Track — DOD-CONVERGENCE-EXTRA-CONTINUE-03

| Campo | Valor |
|-------|--------|
| **Auditor** | Subagent C (public-repo security revalidation) |
| **Campaign** | `DOD-CONVERGENCE-EXTRA-CONTINUE-03` |
| **Data** | 2026-07-21 |
| **Public repo** | `tjsasakifln/extra-cli` |
| **Visibility** | **public** (`private: false`) |
| **Branch** | `origin/main` |
| **HEAD SHA** | `432da028f1fed7d70d9d489e689cf3afa350571d` |
| **Prior audit** | `docs/ops/campaigns/DOD-CONVERGENCE-EXTRA-CONTINUE-02/public-exposure-audit.md` |
| **Modo** | READ-ONLY revalidation (sem remediação automática; sem impressão de valores secretos/PII/preços) |
| **Executive risk** | **HIGH** (sem API/cloud key viva confirmada; exposição comercial/PII + defaults fracos confirmados) |

---

## 0. Método e escopo

1. Confirmar visibilidade pública e SHA de `origin/main` via GitHub API.
2. Confirmar presença no **tree público** (Contents API + worktree alinhado ao SHA).
3. Revalidar achados do audit CONTINUE-02 (não inventar novos sem evidência).
4. Buscar padrões de segredo cloud/API e defaults de senha em deploy/seed/docs.
5. Mapear gaps de `.gitignore` vs arquivos ainda tracked.

**Não feito:** rewrite de histórico, remoção de arquivos, rotação automática, eco de valores sensíveis.

**Convenção de tracks de remediação:**

| Track | Escopo |
|-------|--------|
| **S1** | Commercial materials (proposta, intel pack, briefings client-labeled) |
| **S2** | Spreadsheet Extra branding (+ backup) |
| **S3** | Credential defaults / fail-closed deploy-seed |
| **S4** | QA / hygiene gates (gitignore, pre-commit path guards, evidence policy) |

---

## 1. Veredito executivo (delta vs CONTINUE-02)

| Dimensão | CONTINUE-02 | CONTINUE-03 (HEAD) | Delta |
|----------|-------------|---------------------|-------|
| Repo público | SIM | SIM | sem mudança |
| Proposta comercial PDF | presente | **ainda presente** | **não remediated** |
| Planilhas Extra R-0 + backup | presentes | **ainda presentes** | **não remediated** |
| `data/intel/*` | presente | **ainda presente** (3 arquivos) | **não remediated** |
| Perfil cliente real | presente | **ainda presente** | **não remediated** |
| Briefing client-labeled | presente | **ainda presente** | **não remediated** |
| SQLite versionado | presente | **ainda presente** | **não remediated** |
| Defaults `PG_PASSWORD` / DSN fraco | residual | **ainda residual** em deploy/seed | **não remediated** |
| Cloud/API secrets vivos no HEAD | nenhum | **nenhum confirmado** | estável |
| Novos materiais comerciais pós-audit | n/a | **nenhum pacote comercial novo** além do conjunto já auditado | estável (dívida antiga) |

**Conclusão:** exposição pública material **permanece aberta**. Nenhuma remediação P0 do audit anterior entrou no tree de `main`. Multi-campanha de **código/ops** pode continuar com higiene; **não** empacotar novos artefatos de cliente no remoto público até S1–S3.

**Contagens HIGH/CRITICAL (achados abertos no HEAD):**

| Severidade | Count |
|------------|------:|
| **CRITICAL** | **1** |
| **HIGH** | **6** |
| MEDIUM | 8 |
| LOW | 4 |

---

## 2. Findings revalidados

Para cada finding: path, risk, category, tracked, track, notes (sem valores).

### F-01 — Proposta comercial PDF

| Campo | Valor |
|-------|--------|
| **path** | `proposta-24515063000149-consultoria.pdf` |
| **risk** | **CRITICAL** |
| **category** | commercial (+ PII de contato comercial) |
| **tracked_in_git** | **yes** (Contents API `main`) |
| **recommended remediation track** | **S1** |
| **notes** | Confirmado no root do tree público. Contém identidade do cliente, nome de decisor, contatos do consultor e **tabela comercial/preços** (não reimpressos aqui). Introduzido no histórico (~`1195495` per prior audit). Assumir vazamento comercial se clones/crawlers já ocorreram. Ação: untrack + storage privado; não reintroduzir. |

### F-02 — Planilha Extra alvos (canônica)

| Campo | Valor |
|-------|--------|
| **path** | `Extra - alvos de licitação. R-0.xlsx` |
| **risk** | **HIGH** |
| **category** | commercial |
| **tracked_in_git** | **yes** |
| **recommended remediation track** | **S2** |
| **notes** | Branding “Extra” + “alvos” amarra universo de entes (dados majoritariamente públicos) a engajamento comercial. Preferir seed sanitizado (`config/target_entities_200km.csv` ou regenerado) sem branding de cliente. |

### F-03 — Planilha Extra alvos (backup)

| Campo | Valor |
|-------|--------|
| **path** | `Extra - alvos de licitação. R-0.backup.xlsx` |
| **risk** | **HIGH** |
| **category** | commercial |
| **tracked_in_git** | **yes** (mesmo blob SHA da canônica no HEAD — redundante) |
| **recommended remediation track** | **S2** |
| **notes** | Backup desnecessário no remoto público. Remover do tracking; nunca versionar `*.backup.xlsx` de cliente. |

### F-04 — Pacote de inteligência de concorrente

| Campo | Valor |
|-------|--------|
| **path** | `data/intel/intel-01721078000168-lcm-contrucoes-ltda-2026-07-11.{json,pdf,xlsx}` |
| **risk** | **HIGH** |
| **category** | intel (+ PII agregada) |
| **tracked_in_git** | **yes** (3 arquivos no dir público) |
| **recommended remediation track** | **S1** (higiene: **S4**) |
| **notes** | Pacote processado de produto comercial. JSON expõe campos de contato corporativo e QSA (tipos confirmados; valores **não** listados neste doc). Mesmo com origem em fontes abertas, o **pacote empacotado** não deve residir em OSS público. gitignore `data/intel/**` + fixtures sintéticos para testes. |

### F-05 — Default fraco de senha em install

| Campo | Valor |
|-------|--------|
| **path** | `deploy/install.sh` |
| **risk** | **HIGH** |
| **category** | credential-default |
| **tracked_in_git** | **yes** |
| **recommended remediation track** | **S3** |
| **notes** | Fallback `${PG_PASSWORD:-…}` com senha local fraca conhecida + DSN default com mesma classe na chamada a `db/setup_db.sh`. Em VPS sem override → senha previsível. Fail-closed: `${PG_PASSWORD:?}`. |

### F-06 — Fallback fraco residual em provision VPS

| Campo | Valor |
|-------|--------|
| **path** | `deploy/provision-vps.sh` |
| **risk** | **HIGH** |
| **category** | credential-default |
| **tracked_in_git** | **yes** |
| **recommended remediation track** | **S3** |
| **notes** | Gera senha aleatória se `PG_PASSWORD` ausente (melhor que install), mas **ainda** usa fallback da senha fraca conhecida no DSN de `setup_db.sh` quando env incompleto. Unificar fail-closed; nunca ecoar senha em stdout de forma permanente. |

### F-07 — Defaults de DSN em seed scripts

| Campo | Valor |
|-------|--------|
| **path** | `db/seed/seed_sc_entities.py`, `db/seed/001_sc_entities.py` |
| **risk** | **MEDIUM** (elevável a HIGH se seed rodar em host compartilhado) |
| **category** | credential-default |
| **tracked_in_git** | **yes** |
| **recommended remediation track** | **S3** |
| **notes** | `LOCAL_DATALAKE_DSN` default embute senha local fraca conhecida. Preferir default vazio / obrigatório via env. |

### F-08 — Senha literal em README de seed

| Campo | Valor |
|-------|--------|
| **path** | `db/seed/README.md` |
| **risk** | **LOW** |
| **category** | credential-default |
| **tracked_in_git** | **yes** |
| **recommended remediation track** | **S3** |
| **notes** | Tabela de env documenta DSN com senha literal. Substituir por placeholder. |

### F-09 — Perfil operacional real do cliente

| Campo | Valor |
|-------|--------|
| **path** | `config/client_profiles/extra.yaml` |
| **risk** | **MEDIUM** |
| **category** | commercial |
| **tracked_in_git** | **yes** (único arquivo no dir) |
| **recommended remediation track** | **S1** |
| **notes** | Perfil real com `display_name` do cliente, CNPJ, preferências de objeto, thresholds, elicitation comercial pendente. Público: manter só `*.example.yaml` anônimo; perfil real fora do git. |

### F-10 — Briefing diário client-labeled

| Campo | Valor |
|-------|--------|
| **path** | `output/briefing-extra-2026-07-14.txt` |
| **risk** | **MEDIUM** |
| **category** | commercial / client output |
| **tracked_in_git** | **yes** |
| **recommended remediation track** | **S1** (+ **S4** gitignore) |
| **notes** | Output de produto com marca do cliente e lista de oportunidades. Runtime; não versionar. `.gitignore` ignora subdirs de `output/` mas **não** briefings na raiz de `output/`. |

### F-11 — SQLite contract intel versionado

| Campo | Valor |
|-------|--------|
| **path** | `data/contract_intel.db` |
| **risk** | **MEDIUM** |
| **category** | intel / other |
| **tracked_in_git** | **yes** (~237 KB) |
| **recommended remediation track** | **S4** (com S1 se contiver agregados de cliente) |
| **notes** | Blob binário de runtime/DB. Preferir schema + seed reproduzível; untrack `*.db` sob `data/` (exceto fixtures sintéticos em `tests/`). |

### F-12 — Plano executivo HTML de campanha

| Campo | Valor |
|-------|--------|
| **path** | `extra-consultoria-plano-executivo.html` |
| **risk** | **MEDIUM** |
| **category** | commercial / other |
| **tracked_in_git** | **yes** (~496 KB) |
| **recommended remediation track** | **S1** |
| **notes** | Artefato de status/plano operacional com branding Extra Consultoria. Revisar se há métricas internas sensíveis; preferir `docs/ops` privado ou storage autenticado. |

### F-13 — Relatório XLSX de coverage em output

| Campo | Valor |
|-------|--------|
| **path** | `output/reports/coverage/gaps-2026-07-10.xlsx` |
| **risk** | **LOW**–**MEDIUM** |
| **category** | other (ops output) |
| **tracked_in_git** | **yes** |
| **recommended remediation track** | **S4** |
| **notes** | Report operacional versionado. `output/reports/` está no gitignore, mas arquivo **já tracked** permanece no remoto. Untrack; reforçar política “ignore ≠ untrack”. |

### F-14 — Checkpoint PNCP intel volumoso

| Campo | Valor |
|-------|--------|
| **path** | `data/intel_pncp_checkpoint.json` |
| **risk** | **MEDIUM** |
| **category** | intel / other |
| **tracked_in_git** | **yes** (~674 KB) |
| **recommended remediation track** | **S4** |
| **notes** | Runtime checkpoint; não precisa versionar. |

### F-15 — Registry de entidades volumoso

| Campo | Valor |
|-------|--------|
| **path** | `data/entity_source_registry.jsonl` |
| **risk** | **LOW**–**MEDIUM** |
| **category** | other |
| **tracked_in_git** | **yes** (~4.3 MB) |
| **recommended remediation track** | **S4** |
| **notes** | Cobertura/fontes; volume alto no clone público. Avaliar release artifact autenticado vs tree. |

### F-16 — Screenshots selenium debug

| Campo | Valor |
|-------|--------|
| **path** | `data/selenium_debug/**` |
| **risk** | **LOW**–**MEDIUM** |
| **category** | other |
| **tracked_in_git** | **yes** (dezenas de PNGs) |
| **recommended remediation track** | **S4** |
| **notes** | Podem capturar UI de portais. gitignore + untrack. |

### F-17 — Histórico git com DSN/senha local

| Campo | Valor |
|-------|--------|
| **path** | git history (ex.: commits citados em `docs/td-001/secrets-removal.md`) |
| **risk** | **MEDIUM** |
| **category** | credential-default |
| **tracked_in_git** | **yes** (history) |
| **recommended remediation track** | **S3** |
| **notes** | Senha local fraca já documentada como residual histórico. Rotacionar se reutilizada fora de Docker local. History purge (BFG) **só** se counsel exigir — não bloqueia remediação de HEAD. |

### F-18 — Docs com DSN/senha de lab (não deploy)

| Campo | Valor |
|-------|--------|
| **path** | glob: `docs/**/*`, `_reversa_sdd/**/*` com string de senha local conhecida |
| **risk** | **LOW** |
| **category** | credential-default |
| **tracked_in_git** | **yes** |
| **recommended remediation track** | **S3** / **S4** |
| **notes** | Exemplos e ADRs/stories documentam o default fraco. Reduzir a placeholders; manter narrativa de remoção sem reimprimir DSN completo. |

### F-19 — Gaps de `.gitignore` (cobertura incompleta)

| Campo | Valor |
|-------|--------|
| **path** | `.gitignore` |
| **risk** | **MEDIUM** (habilitador de reintrodução) |
| **category** | other |
| **tracked_in_git** | **yes** |
| **recommended remediation track** | **S4** |
| **notes** | **Ausente** de ignore explícito: `data/intel/`, `proposta-*.pdf`, planilhas Extra na raiz, `*.backup.xlsx`, `output/briefing-*`, `data/*.db`, `data/selenium_debug/`, `data/intel_pncp_checkpoint.json`. Ignore parcial de `output/**` **não remove** arquivos já tracked. SA JSON e `.env` estão cobertos (controle positivo). |

### F-20 — Controles positivos (não-finding)

| Campo | Valor |
|-------|--------|
| **path** | `.env.example`, `.pre-commit-config.yaml`, `config/*-sa.json` ignore patterns |
| **risk** | n/a (OK) |
| **category** | other |
| **tracked_in_git** | templates only |
| **recommended remediation track** | manter |
| **notes** | `.env.example` usa placeholders `<password>`. Sem PEM/`ghp_`/`sk_live`/`AKIA` confirmados no HEAD de código. Pre-commit secrets hooks presentes. **Não** impedem material comercial. |

---

## 3. Checklist de missões (status)

| # | Item de missão | Status no HEAD `432da028` |
|---|----------------|---------------------------|
| 1 | Commercial proposal materials | **EXPOSTO** — F-01, F-12 |
| 2 | Spreadsheets Extra branding R-0 + backup | **EXPOSTO** — F-02, F-03 |
| 3 | `data/intel/**` | **EXPOSTO** — F-04 |
| 4 | Real client profile | **EXPOSTO** — F-09 |
| 5 | Client briefings | **EXPOSTO** — F-10 |
| 6 | Versioned SQLite DB | **EXPOSTO** — F-11 |
| 7 | Client outputs | **EXPOSTO** — F-10, F-13; outros `output/*` parciais |
| 8 | Weak password defaults deploy/seed/docs | **EXPOSTO** residual — F-05–F-08, F-17–F-18 |
| 9 | New commercial materials after prior audit | **Nenhum pacote novo** — dívida antiga **intacta** |
| 10 | `.gitignore` coverage gaps | **Confirmado** — F-19 |

---

## 4. Tabela consolidada (prioridade)

| ID | path / glob | risk | category | tracked | track |
|----|-------------|------|----------|---------|-------|
| F-01 | `proposta-24515063000149-consultoria.pdf` | CRITICAL | commercial | yes | S1 |
| F-02 | `Extra - alvos de licitação. R-0.xlsx` | HIGH | commercial | yes | S2 |
| F-03 | `Extra - alvos de licitação. R-0.backup.xlsx` | HIGH | commercial | yes | S2 |
| F-04 | `data/intel/*` | HIGH | intel | yes | S1 |
| F-05 | `deploy/install.sh` | HIGH | credential-default | yes | S3 |
| F-06 | `deploy/provision-vps.sh` | HIGH | credential-default | yes | S3 |
| F-07 | `db/seed/*.py` (DSN default) | MEDIUM | credential-default | yes | S3 |
| F-08 | `db/seed/README.md` | LOW | credential-default | yes | S3 |
| F-09 | `config/client_profiles/extra.yaml` | MEDIUM | commercial | yes | S1 |
| F-10 | `output/briefing-extra-2026-07-14.txt` | MEDIUM | commercial | yes | S1 |
| F-11 | `data/contract_intel.db` | MEDIUM | intel/other | yes | S4 |
| F-12 | `extra-consultoria-plano-executivo.html` | MEDIUM | commercial | yes | S1 |
| F-13 | `output/reports/coverage/gaps-2026-07-10.xlsx` | LOW–MED | other | yes | S4 |
| F-14 | `data/intel_pncp_checkpoint.json` | MEDIUM | other | yes | S4 |
| F-15 | `data/entity_source_registry.jsonl` | LOW–MED | other | yes | S4 |
| F-16 | `data/selenium_debug/**` | LOW–MED | other | yes | S4 |
| F-17 | git history (senha local) | MEDIUM | credential-default | history | S3 |
| F-18 | docs com DSN lab | LOW | credential-default | yes | S3/S4 |
| F-19 | `.gitignore` gaps | MEDIUM | other | yes | S4 |

---

## 5. Plano priorizado de remediação — Phase 2 (sem code changes nesta wave)

### P0 — Humano / @devops (bloquear novos empacotamentos comerciais)

1. **Decisão de produto:** repo **private** vs **OSS sanitizado**.  
   - Private resolve branding de forma ampla (não apaga clones já feitos).  
   - OSS exige remoção explícita S1+S2 do tree.
2. **S1 untrack + private storage:**  
   - `proposta-*.pdf`  
   - `data/intel/**`  
   - `output/briefing-*`  
   - `extra-consultoria-plano-executivo.html` (se classificado comercial)  
   - perfil real → `config/client_profiles/extra.example.yaml` no público
3. **S2 untrack planilhas Extra + backup** da raiz; manter/regenerar seed CSV sem branding.
4. **Assumir vazamento** de F-01/F-04: comunicar stakeholder comercial; **não** depender de history rewrite para “desfazer” clones.
5. **Barreira operacional:** agents **não** fazem push de novos PDF/XLSX/intel de cliente no remoto público até P0 ack.

### P1 — Stories HIGH-RISK (S3 + S4)

6. **S3 fail-closed:**  
   - `deploy/install.sh`: `${PG_PASSWORD:?}` e DSN sem default de senha.  
   - `deploy/provision-vps.sh`: remover fallback fraco no DSN; secret store.  
   - `db/seed/*`: DSN obrigatório via env; sem senha no default.  
   - README/docs: placeholders only.  
   - Prova: `git grep` da string de senha local fraca **zero** em paths de deploy/seed (docs históricos documentados à parte).
7. **S4 gitignore + untrack:**  
   ```
   data/intel/
   data/*.db
   data/selenium_debug/
   data/intel_pncp_checkpoint.json
   proposta-*.pdf
   Extra - alvos*.xlsx
   *.backup.xlsx
   output/briefing-*
   ```  
   + pre-commit path denylist para esses globs.
8. **Rotação:** se senha default de install/provision **já** foi usada em host com porta exposta/VPS → rotacionar role Postgres e secret store (sem commitar o novo valor).

### P2 — Higiene de volume / ops

9. Untrack checkpoints, registry pesado, screenshots se não forem evidência canônica de eng.
10. Política escrita PO: “single-client commercial materials never on public remote”.
11. QA gate de PR: checklist comercial (S4) antes de merge em `main`.

### P3 — Opcional legal

12. History purge (filter-repo/BFG) **somente** com orientação legal; não é pré-requisito para fechar exposição de HEAD.

---

## 6. Ordem de execução sugerida (phase 2 work packages)

| WP | Track | Entregável | Owner | Dependência |
|----|-------|------------|-------|-------------|
| WP0 | — | Decisão private vs OSS | PO/humano | — |
| WP1 | S1 | PR untrack comercial/intel/briefing/profile real | @devops + humano | WP0 |
| WP2 | S2 | PR untrack xlsx Extra + backup | @devops | WP0 |
| WP3 | S4 | `.gitignore` + pre-commit path guards | @devops | WP1/WP2 |
| WP4 | S3 | fail-closed deploy/seed + greps limpos | @dev HIGH-RISK | story validada |
| WP5 | S3 | rotação se senha usada em host real | humano | WP4 |
| WP6 | S4 | QA gate comercial em CI/checklist | @qa | WP3 |

**Critério de “remediation done” (HEAD):**  
- Zero proposta PDF / intel pack / planilha Extra branding / briefing client-labeled no tree de `main`.  
- Deploy/seed fail-closed sem default de senha fraca.  
- gitignore impede reintrodução.  
- Evidência: Contents API + `git grep` + audit note.

---

## 7. O que o coordenador pode / não pode fazer agora

| Trilha | Permitido? |
|--------|------------|
| Código, testes, migrations, DoD ops **sem** novos artefatos de cliente | **SIM** com higiene |
| Campaign evidence numérica (JSON redigido) | **SIM** se sem PDF/XLSX comercial |
| Novos dossiês, propostas, briefings, planilhas de cliente no remoto público | **NÃO** até S1–S2 |
| Push reintroduzindo defaults fracos | **NÃO** |
| Declarar secrets cloud “limpos” e parar aí | **NÃO** — risco dominante é comercial/PII |

---

## 8. Referências

- Prior full audit: `docs/ops/campaigns/DOD-CONVERGENCE-EXTRA-CONTINUE-02/public-exposure-audit.md`
- Secrets residual doc: `docs/td-001/secrets-removal.md`
- Story residual DT-35: `docs/stories/story-2.1-remove-sa-json-secret.md`
- Public API: `https://api.github.com/repos/tjsasakifln/extra-cli` (visibility public)
- HEAD confirmado: `432da028f1fed7d70d9d489e689cf3afa350571d`

---

## 9. Resumo curto para handoff

| Métrica | Valor |
|---------|-------|
| **CRITICAL open** | **1** (proposta comercial) |
| **HIGH open** | **6** (2× planilha, intel pack, 2× deploy password defaults, contando pack como 1) |
| **Remediation desde CONTINUE-02** | **0** no tree público |
| **Novos materiais comerciais** | **0** (dívida antiga intacta) |
| **Cloud API secrets no HEAD** | **nenhum confirmado** |
| **Executive risk** | **HIGH** |
| **Phase 2 next** | WP0 decisão humana → S1+S2 untrack → S3 fail-closed → S4 ignore gates |

*Nenhum valor de segredo, DSN completo, e-mail pessoal, telefone, preço ou conteúdo comercial integral foi reproduzido neste documento. Nenhuma remediação automática foi aplicada.*
