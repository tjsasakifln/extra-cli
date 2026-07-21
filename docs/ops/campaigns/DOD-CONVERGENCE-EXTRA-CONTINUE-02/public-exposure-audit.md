# Public Exposure Audit — DOD-CONVERGENCE-EXTRA-CONTINUE-02

| Campo | Valor |
|-------|--------|
| **Auditor** | Subagent D (public repository exposure) |
| **Data** | 2026-07-21 |
| **Repo** | `tjsasakifln/extra-cli` |
| **Branch auditada** | `origin/main` (HEAD público confirmado) |
| **Worktree local** | `/mnt/d/extra-consultoria-dod-conv` |
| **Modo** | READ-ONLY (sem remediação automática, sem rewrite de histórico) |
| **Risk level executivo** | **HIGH** |

---

## 1. Veredito executivo

| Dimensão | Resultado |
|----------|-----------|
| **Risk level** | **HIGH** |
| **Secrets (API keys / tokens cloud / PEM)** | **Nenhum confirmado no HEAD** |
| **Secrets (senhas fracas hardcoded residual)** | **Potential / residual** (defaults de dev em deploy/seed) |
| **Material comercial / cliente** | **Confirmado exposto em repositório público** |
| **PII / contatos** | **Confirmado** (proposta + dossiê intel) |
| **Seguro continuar multi-campanha no repo público?** | **Condicional — ver §7** |
| **BLOCKED_HUMAN?** | **SIM — comercial/confidencialidade + residual de senha fraca** (não bloqueia 100% do código; bloqueia push de mais material comercial e exige remediação humana) |

**Resumo em uma linha:** não há chave de API/cloud viva óbvia no HEAD, mas o repo **público** expõe proposta comercial com preço e contatos, dossiê de intel com QSA/e-mail/telefone, planilhas de alvos do cliente e defaults fracos de senha local em scripts de install — risco **HIGH**, não CRITICAL.

---

## 2. Confirmação de visibilidade do repositório

| Item | Evidência |
|------|-----------|
| Full name | `tjsasakifln/extra-cli` |
| Visibility | **`public`** (`private: false`, badge “Public” no GitHub) |
| Default branch | `main` |
| API | `GET https://api.github.com/repos/tjsasakifln/extra-cli` → `visibility: "public"` |
| Clone público | `https://github.com/tjsasakifln/extra-cli.git` |
| Stars/forks | 0 / 0 (baixa atenção atual, **não** reduz exposição legal/comercial) |
| Tamanho | ~29.5 MB reportados pela API |
| Commits em main | ~297 |

Qualquer arquivo no tree de `main` é baixável sem autenticação (raw.githubusercontent.com / git clone).

---

## 3. Escopo e método (read-only)

1. Confirmação de visibilidade via GitHub API + UI.
2. Inventário de tree em `main` e worktree local.
3. Busca por padrões de segredo: `BEGIN PRIVATE KEY`, `ghp_`, `sk_live`, `xoxb-`, `AKIA`, `Bearer …`, passwords hardcoded em `.py/.sh/.yml`.
4. Inspeção de `.env.example`, `.gitignore`, pre-commit (detect-secrets/AWS).
5. Leitura controlada de PDF comercial, JSON de intel e seed da planilha (sem ecoar valores de segredo).
6. Commits de introdução de planilha / proposta / intel (histórico).
7. Revisão de docs internos já existentes (`docs/td-001/secrets-removal.md`, reviews de DB/QA).

**Não feito (deliberado):** rewrite de histórico, remoção automática, rotação automática, impressão de valores secretos.

---

## 4. Secrets

### 4.1 Classificação

| Status | Detalhe |
|--------|---------|
| **Confirmed live cloud/API secret** | **Não encontrado** no HEAD (sem PEM, sem `ghp_`, sem `sk_live`, sem `xoxb-`, sem `AKIA`, sem JWT de serviço, sem `.env` com valores reais versionado) |
| **Potential / residual** | Defaults de senha local fraca embutidos em scripts de **install/provision/seed** (tipo: local Postgres password default) |
| **Historical** | Mesma classe de senha local documentada em histórico (`docs/td-001/secrets-removal.md` cita commit `352dac5` e remoção parcial TD-1.2) |
| **Placeholder only** | `.env.example` com placeholders (`<password>`, chaves vazias) — aceitável |

### 4.2 Findings de segredo / credencial (sem valores)

| type | path | commit (se conhecido) | severity | recommended action |
|------|------|------------------------|----------|--------------------|
| Local DB password default (residual) | `deploy/install.sh` | presente em HEAD `main` | **HIGH** (se usado em VPS sem override) | Remover default; exigir `PG_PASSWORD` fail-closed (`${PG_PASSWORD:?}`); nunca default em script de install |
| Local DB password default (residual) | `deploy/provision-vps.sh` | HEAD | **HIGH** (mesmo motivo) | Idem; provision só com secret store / env injetado |
| Local DB password default (residual) | `db/seed/seed_sc_entities.py` | HEAD | **MEDIUM** | Default vazio ou fail se env ausente; documentar em `.env.example` |
| Local DB password default (residual) | `db/seed/001_sc_entities.py` | HEAD | **MEDIUM** | Idem |
| Local DB password default (doc) | `db/seed/README.md` | HEAD | **LOW** | Remover senha literal do README; usar placeholder |
| Historical DSN password | history (`352dac5` per `docs/td-001/secrets-removal.md`) | `352dac5` (doc) | **MEDIUM** | Tratar como **já vazado publicamente se o repo era/é público**; **rotacionar** qualquer senha que já tenha sido reutilizada fora de Docker local; history rewrite **não** é prioridade se a senha for só lab local e já rotacionada |
| Env template | `.env.example` | HEAD | **LOW** | Manter placeholders; garantir que `.env` real permanece gitignored |
| Service-account patterns | `.gitignore` cobre `config/*-sa.json`, `*service-account*.json` | — | **OK** | Manter; validar periodicamente que nenhum SA JSON entrou no tree |
| Pre-commit secrets hooks | `.pre-commit-config.yaml` (detect-aws-credentials etc.) | HEAD | **OK** | Manter habilitado em CI/local |

### 4.3 Instrução de rotação (sem valores)

Se a senha fraca de Postgres local/default **já foi usada** em qualquer host com porta exposta, VPS, dump compartilhado ou CI:

1. Gerar senha forte nova.
2. Alterar role Postgres no host afetado.
3. Atualizar apenas secret store / `.env` **não versionado**.
4. Invalidar sessões / reiniciar serviços que cacheiam DSN.
5. **Não** reescrever histórico só por essa senha se ela for estritamente local e já substituída — o custo/benefício é baixo; foque em **parar defaults no HEAD**.

**API keys (OpenAI, Anthropic, DeepSeek, Exa, DOM_SC, etc.):** não encontradas populadas no tree. Se alguma key real existir apenas em hosts/CI secrets, nenhuma ação de rotação forçada por este scan — mas mantenha rotação se houver suspeita de commit passado não detectado.

---

## 5. Material comercial, planilhas e dados de cliente

### 5.1 Planilha “Extra - alvos de licitação”

| Arquivo | Público em `main`? | Introdução (commit) |
|---------|--------------------|---------------------|
| `Extra - alvos de licitação. R-0.xlsx` | **SIM** | `ceecf7b` (2026-07-10) — commit inicial |
| `Extra - alvos de licitação. R-0.backup.xlsx` | **SIM** | tree de `main` (mesmo núcleo) |

**Conteúdo esperado (via seed, não via dump de células sensíveis):**

- Sheet canônica: `Entes Públicos SC`
- ~2.085 entes públicos de SC (razão social, CNPJ-8, município, IBGE, geo, raio 200 km)
- Uso: seed de `sc_public_entities` / denominador de cobertura

**Pode ser público?**

| Critério | Avaliação |
|----------|-----------|
| Natureza dos registros | Majoritariamente **dados públicos de entes** (CNPJ de órgãos, nomes oficiais) |
| Framing comercial | Nome do arquivo e contexto amarram ao **universo comercial do cliente Extra** |
| Cópia `.backup` | Redundante e desnecessária no remoto público |
| Alternativa já no repo | `config/target_entities_200km.csv` (derivado seed, também público) |

**Veredito planilha:**  
- **Conteúdo puro de entes públicos:** publicável *se* renomeado/despersonalizado e tratado como open-data seed.  
- **Na forma atual (marca Extra + alvos + backup):** **não recomendado** em repo público — tratar como **asset comercial do engajamento**, preferir privado ou LFS privado / artefato de release autenticado.  
- **Ação:** human decide: (A) tornar repo privado, ou (B) remover xlsx+backup do tree, manter apenas CSV seed sanitizado sem branding de cliente, ou (C) aceitar conscientemente a exposição de universo público com branding Extra.

### 5.2 Proposta comercial e contatos

| type | path | commit | severity | recommended action |
|------|------|--------|----------|--------------------|
| Commercial proposal PDF | `proposta-24515063000149-consultoria.pdf` | `1195495` (2026-07-13) | **CRITICAL (comercial)** | Remover do tree público; mover para storage privado; se já público, assumir vazamento de preço/escopo/contato |
| Personal/commercial contact | mesmo PDF (consultor + telefone) | idem | **HIGH** | Não versionar contatos pessoais em repo público |
| Client decision-maker name | mesmo PDF | idem | **HIGH** | Tratar como PII/comercial; remover |
| Client identity + CNPJ | mesmo PDF + `config/client_profiles/extra.yaml` | vários | **MEDIUM–HIGH** | CNPJ de PJ é público, mas pacote comercial completo não deve ser OSS |

Conteúdo sensível confirmado no PDF (tipos, **sem** reimprimir números/preços aqui além do necessário à classificação):

- Proposta exclusiva para cliente Extra Empreiteira e Construtora  
- Nome do decisor no cliente  
- Contato do consultor  
- Valor de investimento do diagnóstico  
- Escopo comercial e validade  

### 5.3 Dossiê de inteligência / competidor

| type | path | commit | severity | recommended action |
|------|------|--------|----------|--------------------|
| Intel package (JSON/PDF/XLSX) | `data/intel/intel-01721078000168-lcm-contrucoes-ltda-2026-07-11.*` | `e9729e1` / `7bbd13b` (2026-07-11) | **HIGH** | Remover do remoto público; gitignore `data/intel/**`; fixtures de teste sintéticos apenas |
| Competitor contact fields | JSON (email, telefones, QSA nomes) | HEAD | **HIGH** | Mesmo que parte venha de fontes abertas, o **pacote processado** é produto comercial/PII agregado |
| Pipeline checkpoint | `data/intel_pncp_checkpoint.json` | HEAD | **MEDIUM** | Runtime; não precisa versionar |

### 5.4 Perfil operacional do cliente

| type | path | commit | severity | recommended action |
|------|------|--------|----------|--------------------|
| Client operational profile | `config/client_profiles/extra.yaml` | HEAD | **MEDIUM** | Contém CNPJ, sede, preferências de objeto, thresholds; se OSS, sanitizar exemplo anônimo (`example.yaml`) e manter perfil real fora do git |
| Daily briefing client-labeled | `output/briefing-extra-2026-07-14.txt` | HEAD | **MEDIUM** | Runtime output; gitignore / não versionar |
| Plano executivo HTML | `extra-consultoria-plano-executivo.html` | HEAD | **LOW–MEDIUM** | Parece status operacional de campanha; revisar se contém métricas internas sensíveis; preferir docs/ops privados se for status de cliente |

### 5.5 Outros artefatos de dados no público

| type | path | severity | notes / action |
|------|------|----------|----------------|
| SQLite contract intel | `data/contract_intel.db` (~237 KB) | **MEDIUM** | DB binário versionado; preferir schema+seed reproduzível, não blob |
| Entity source registry | `data/entity_source_registry.jsonl` (~4.3 MB) | **LOW–MEDIUM** | Dados de cobertura/fontes; volumoso; avaliar se deve ser release artifact |
| Platform detection dumps | `data/platform_detection_*.json/yaml` | **LOW** | Operacional; ok se só URLs públicas |
| Selenium debug screenshots | `data/selenium_debug/**` | **LOW–MEDIUM** | Pode capturar UI de portais; revisar e gitignore |
| Campaign evidence packs | `docs/ops/campaigns/**/evidence/**` | **LOW–MEDIUM** | Maioria métricas/ops; package fixtures de PDF/XLSX já parcialmente gitignored — manter disciplina |
| CSV seed 200km | `config/target_entities_200km.csv` | **LOW** | Entes públicos; aceitável como seed se política for open-data |

---

## 6. Tabela consolidada de findings

| type | path | commit (known) | severity | recommended action |
|------|------|----------------|----------|--------------------|
| Commercial proposal | `proposta-24515063000149-consultoria.pdf` | `1195495` | **CRITICAL (comercial)** | Delete from public tree; private storage; assume leaked; no history rewrite required for campaign continuity unless legal counsel requires |
| Client target spreadsheet | `Extra - alvos de licitação. R-0.xlsx` | `ceecf7b` | **HIGH** | Remove or privatize; keep sanitized seed only |
| Spreadsheet backup | `Extra - alvos de licitação. R-0.backup.xlsx` | main tree | **HIGH** | Remove entirely from public |
| Competitor intel package | `data/intel/*` | `e9729e1` / `7bbd13b` | **HIGH** | Remove; gitignore; synthetic fixtures for tests |
| Weak PG password default | `deploy/install.sh` | HEAD | **HIGH** | Fail-closed env; never default password |
| Weak PG password default | `deploy/provision-vps.sh` | HEAD | **HIGH** | Same |
| Weak PG password default | `db/seed/*.py` | HEAD | **MEDIUM** | Empty default / required env |
| Client profile | `config/client_profiles/extra.yaml` | HEAD | **MEDIUM** | Example profile only in public; real profile private |
| Client briefing | `output/briefing-extra-2026-07-14.txt` | HEAD | **MEDIUM** | Untrack; ignore `output/**` client products |
| SQLite DB blob | `data/contract_intel.db` | HEAD | **MEDIUM** | Untrack; generate via seed |
| Historical password in git | history (`352dac5` per docs) | `352dac5` | **MEDIUM** | Rotate if reused; optional history purge later |
| Author personal email in commits | git metadata | all | **LOW** | Expected for public OSS; optional noreply GitHub email |
| `.env` with real secrets | — | — | **NONE found tracked** | Keep ignored |
| PEM / SA JSON / cloud keys | — | — | **NONE found in HEAD** | Keep guards |

---

## 7. Spreadsheet public suitability (decisão explícita)

| Pergunta | Resposta |
|----------|----------|
| Os registros são secretos? | **Não** — entes públicos SC. |
| O arquivo como empacotado é adequado a OSS? | **Não ideal** — branding Extra, “alvos”, backup comercial, amarra estratégia de raio/cliente. |
| Pode permanecer público com aceite consciente? | **Somente se** product owner declarar universo de entes como open seed e renomear/desacoplar do cliente. |
| Recomendação do auditor | **Remover xlsx + backup do remoto público**; manter `config/target_entities_200km.csv` (ou regenerar seed limpo) como artefato de eng; planilha canônica em drive privado versionado fora do GitHub público. |

---

## 8. Pode o coordenador continuar multi-campanha no repo público?

| Trilha | Permitido? | Condição |
|--------|------------|----------|
| Código, testes, migrations, docs de engenharia **sem** novos artefatos de cliente | **SIM** | Não adicionar proposta/intel/xlsx/PII |
| Campaign evidence numérica (JSON de métricas, logs redigidos) | **SIM com higiene** | Sem PDF/XLSX de entrega comercial; respeitar gitignore de fixtures |
| Empacotamento comercial, propostas, dossiês, briefings diários | **NÃO até remediação** | Privado ou outro storage |
| Push que reintroduza secrets/defaults fracos | **NÃO** | Corrigir defaults em story HIGH-RISK separada |
| Tornar o repo privado | **Decisão humana** | Resolve branding comercial de forma ampla; não apaga forks/clones já feitos |

**Conclusão operacional:**  
coordenador **pode continuar** trabalho multi-campanha de **código/ops/DoD** no repo público **somente com barreira de higiene** (não versionar novos outputs de cliente).  
Há **BLOCKED_HUMAN** para remediação de exposição comercial já ocorrida e para remoção de defaults de senha — **não** para parar 100% da engenharia.

---

## 9. Texto exato sugerido para arquivo BLOCKED_HUMAN

```text
BLOCKED_HUMAN — security + commercial confidentiality
Campaign: DOD-CONVERGENCE-EXTRA-CONTINUE-02
Repo: tjsasakifln/extra-cli (PUBLIC)
Date: 2026-07-21

Reason:
1) Public tree contains client commercial proposal PDF (pricing, decision-maker
   name, consultant contact) at proposta-24515063000149-consultoria.pdf
   (introduced ~commit 1195495).
2) Public tree contains client target spreadsheets
   "Extra - alvos de licitação. R-0.xlsx" and ".backup.xlsx" (since ceecf7b).
3) Public tree contains competitor intel package under data/intel/* with
   contact/QSA fields (package product, not raw public dump only).
4) Residual weak local Postgres password defaults remain in
   deploy/install.sh, deploy/provision-vps.sh, db/seed/* (HIGH if used on VPS).

Required human actions (no auto-remediation by agents):
A) Decide: make repo private OR delete commercial/intel/xlsx from tracking.
B) Move commercial PDFs/spreadsheets/intel packages to private storage.
C) Expand .gitignore: data/intel/, *.backup.xlsx, proposta-*.pdf,
   output/briefing-*, Extra - alvos*.xlsx (if not open-seed policy).
D) Replace password defaults in deploy/seed with fail-closed env vars.
E) Rotate any password that was ever used outside pure local Docker.
F) Do NOT rewrite git history unless legal/counsel requires; prefer delete
   + private storage + accept residual history for non-production local passwords.

Until A–D acknowledged, agents must not push new client commercial artifacts
to this public repository. Code/ops tracks may continue with hygiene.
```

---

## 10. Controles positivos já existentes

- `.env`, `*.pem`, `*.key`, `*.dump`, vários outputs runtime no `.gitignore`
- Pre-commit com detecção de AWS credentials / private keys  
- CI com `bandit` e `pip-audit` (README)  
- `.env.example` com placeholders  
- TD-1.2 documentou remoção parcial de DSNs hardcoded em `settings`/scripts  
- Package fixtures de PDF/XLSX em campanhas parcialmente ignorados  

Esses controles **não** impediram o versionamento de proposta/planilha/intel — gap de **política de conteúdo**, não só de secret scanning.

---

## 11. Recomendações priorizadas (human / @devops — sem auto-fix)

| Prio | Ação | Owner |
|------|------|-------|
| P0 | Remover do tracking público: proposta PDF, planilhas Extra R-0 (+backup), `data/intel/*` | humano + @devops |
| P0 | Decidir: **repo private** vs **OSS sanitizado** | product owner |
| P0 | Rotacionar senha se default de install/provision já foi usado em host real | humano |
| P1 | Fail-closed `PG_PASSWORD` / DSN em `deploy/*` e `db/seed/*` | story HIGH-RISK |
| P1 | gitignore reforçado + pre-commit path hooks para `proposta-`, `data/intel`, `*.xlsx` raiz | @devops |
| P1 | Substituir perfil real por `extra.example.yaml` no público | @dev + PO |
| P2 | Desversionar `data/contract_intel.db` e briefings `output/` | @dev |
| P2 | Política escrita: “single-client commercial materials never on public remote” | PO |
| P3 | Avaliar history purge (BFG/filter-repo) **só** se counsel exigir | humano |

---

## 12. Veredito final para o coordenador

| Item | Valor |
|------|-------|
| **Executive risk** | **HIGH** |
| **Secrets confirmed (cloud/API)** | **None found** |
| **Secrets residual (weak local password defaults)** | **Potential — remediate** |
| **Commercial/PII exposure** | **Confirmed on public main** |
| **Safe to continue multi-campaign work?** | **Yes for code/ops hygiene tracks; No for new commercial packaging; Human remediation required for already-public client materials** |
| **BLOCKED_HUMAN** | **Yes — see §9** |

**Não é CRITICAL** (não há chave de produção viva confirmada no HEAD).  
**Não é LOW/MEDIUM** (proposta + contatos + intel + planilhas cliente em repo público são exposição material).

---

*Fim do relatório. Nenhum segredo em valor claro foi impresso neste documento. Nenhuma remediação automática foi aplicada.*
