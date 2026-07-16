# Rebaseline HEAD — 2026-07-16

**Story:** PE-G0-02 (tasks G0.2 do plano executivo)  
**Epic:** EPIC-PLANO-EXECUTIVO-30D  
**Data do rebaseline:** 2026-07-16  
**Autoridade de meta:** `DOD.md` (ver também `docs/baseline/scope-freeze-95.md`)  
**Regra:** nenhuma métrica inventada; ausência de evidência = `UNKNOWN`.

---

## 1. HEAD e branch

| Campo | Valor |
|-------|-------|
| Branch ativa | `epic/plano-executivo-30d` |
| HEAD (full) | `1f7aa7c324a205c26876dece906c442b3aa84787` |
| HEAD (short) | `1f7aa7c` |
| Mensagem do commit HEAD | `feat: publish data foundation pipeline changes` |
| Origem da branch | criada a partir de HEAD do wave DATA-FOUNDATION (`epic/data-foundation-wave0` → mesmo SHA `1f7aa7c`) |
| `main` no momento do rebaseline | `32eb4425c1b6c08878811394824e88a8d7167358` — `feat: golden path completo — fetch→persistência→PDF/Excel` |

**Leitura:** o plano executivo 30d está à frente de `main` pelos commits de DATA-FOUNDATION (resume PNCP + publish pipeline). O rebaseline usa o HEAD da campanha, não o de `main`.

---

## 2. Commits recentes relevantes (cadeia até HEAD)

Equivalente a `git log` via `.git/logs/HEAD` / refs (leitura de objetos git no workspace):

| SHA (short) | Mensagem | Relevância |
|-------------|----------|------------|
| `1f7aa7c` | feat: publish data foundation pipeline changes | Publicação do pipeline DATA-FOUNDATION no HEAD da campanha |
| `eb2160a` | fix: make PNCP backfill resumable and reconcilable | Resume/reconciliação de backfill PNCP |
| `32eb442` | feat: golden path completo — fetch→persistência→PDF/Excel | Golden path ponta a ponta (também HEAD de `main`) |
| `b194f42` | fix: safe_int for PNCP modalidade_id/esfera_id + handoff refresh | Correção de upsert PNCP (strings → int) |
| `70a4755` | fix: SOURCE_BLOCKERS dom_sc updated + handoff refresh | Ajuste de blockers de fonte |
| `2b49be2` | feat: CM-09 — ComprasGov V3 validation (unblocked federal source) | Validação fonte federal |
| `9a6698a` | fix: CM-08 — PNCP API page size correction + contracts crawl infrastructure | Infra de crawl de contratos PNCP |
| `12096cc` | feat: PCP server-side UF filtering — 15x SC coverage boost | Filtro UF no PCP |
| `19bfa21` | fix: CM-07 — bootstrap DB + PCP 365d expansion + SOURCE_BLOCKERS correction | Bootstrap local + expansão PCP |

Commits de governança adjacentes (não alteram capacidade de cobertura por si): `d644794` (untrack `.env*`), `73b8592` (artefatos CM-07), handoffs `660ad91`, `cc1969a`, `eca7629`.

---

## 3. Estado epic DATA-FOUNDATION

Fonte: `.aiox/epic-DATA-FOUNDATION-state.yaml` (atualizado `2026-07-16T13:30:00Z`).

| Campo | Valor |
|-------|-------|
| `epic_id` | `DATA-FOUNDATION` |
| `status` | `IN_PROGRESS` |
| `current_wave` | `5` |
| Wave 0 Foundation | `DONE` / gate `PASS` |
| Wave 1 Core Engine | `DONE` / gate `PASS` / `total_tests: 61` |
| Wave 2 Source Adapters | `DONE` / gate `PASS` |
| Wave 3 Backfill + Coverage Truth | `DONE` / gate `PASS` |
| Wave 4 Chaos + Recall + Audit | `DONE` / gate `PASS` — evidência: 89 tests (72 + 17 chaos/unit/integration); stories DF-401…DF-404 `Done` |
| Wave 5 Integração + Push | `IN_PROGRESS` / gate `PENDING` — DF-501, DF-502, DF-503 ainda `PENDING` |
| Wave 6 Ledger Final | `PENDING` |

**Implicação para o rebaseline:** há implementação e testes de foundation no repositório; **não** há gate de cobertura DoD (≥95% editais / ≥95% contratos) atingido. Wave 5+6 não fechadas → release DATA-FOUNDATION ainda não publicado formalmente.

Critique QA da missão: `docs/qa/MISSÃO-DATA-FOUNDATION-critique.md` — veredito **APPROVED WITH CONCERNS** (média 4.5), não substitui evidência de cobertura no banco.

---

## 4. Baseline de dados local (snapshot técnico)

Fonte: `docs/baseline/DATA-FOUNDATION-baseline-2026-07-16.md` (gerado `2026-07-16T08:23:34`).

| Métrica | Valor no snapshot | Status |
|---------|-------------------|--------|
| Tabelas no overview (muitas em 0) | 28 tabelas listadas com count 0 no bloco 1 | Snapshot inconsistente internamente (ver nota) |
| `pncp_raw_bids` (bloco Core) | **295 rows** | Presente no snapshot |
| `supplier_contracts` | **ERROR** | UNKNOWN / falha de query |
| `enriched_entities` | 0 | Sem enrichment |
| `coverage_evidence` | 0 | Sem ledger de evidência populado |
| Freshness `pncp_raw_bids.ingested_at` | 2026-07-16 00:45:36 UTC | Dados recentes no snapshot |
| Órgãos distintos (PNCP profile) | 1 | Extremamente estreito |
| Date range PNCP | 2026-05-18 → 2026-07-13 | Janela curta |
| Last 7 days | 3 records | Baixo volume |
| DB size | 20 MB | Ambiente local enxuto |
| Contract data (seção 8/9) | vazio no relatório | **UNKNOWN / zero no snapshot** |

**Nota de integridade do snapshot:** o bloco 1 lista `pncp_raw_bids: 0` e o bloco 2 lista `295 rows`. Para claims de cobertura **não se usa o bloco 1 sozinho**; a contagem operacional do snapshot é a do Core Table Counts (295), ainda assim **insuficiente e não auditável como cobertura DoD**.

---

## 5. Métricas de handoffs / audits (editais no raio e contratos)

Métricas **históricas documentadas** — **não** reexecutadas como query SQL neste rebaseline (DB local pode estar offline/tmpfs). Cada linha cita fonte; se a fonte for antiga, a métrica é **snapshot datado**, não verdade atual do HEAD.

### 5.1 Handoff sessão goal (2026-07-15) — `.aiox/handoffs/NEXT-SESSION.md`

| Métrica | Valor documentado | Observação |
|---------|-------------------|------------|
| Entes planilha Extra | 2.085 | Universo SC seed |
| Dentro raio 200 km | 1.093 | Denominador canônico do raio |
| Editais — SC total | 171 / 2.085 = **8,2%** | data_presence-like, não `capability_monitoring_coverage` DoD |
| Editais — dentro 200 km | 34 / 1.093 = **3,1%** | Usado no plano HTML como “evidência 15/jul” |
| Contratos | **0%** | Explicitamente zero naquele handoff |
| Bids no banco (handoff) | 1.976 (todos PCP) | Contradiz snapshots posteriores com PNCP; tratar como snapshot de sessão |
| Entidades cobertas | 171 (34 no raio) | |

### 5.2 Handoff CM-07 / goal YAML — `.aiox/handoffs/handoff-goal-2026-07-15.yaml`

| Métrica | Baseline sessão | Resultado sessão |
|---------|-----------------|------------------|
| Seed entities | 0 (DB offline) | 2.085 |
| Raio 200 km | — | 1.093 |
| PCP bids | 0 | 134 |
| Entities covered | 0 | 65 |
| Coverage % (raio) | 0% | **5,9% (65/1.093)** |
| Pipeline | — | `EPIC-COVERAGE-MAX-200KM` |

### 5.3 Epic COVERAGE-MAX-200KM — `docs/stories/epics/EPIC-COVERAGE-MAX-200KM.md`

| Métrica | Baseline 15/jul (documento) | Alvo legado do epic |
|---------|----------------------------|---------------------|
| Recall entes com dados | **6,1%** (67/1.093) | **>80%** (meta subordinada — ver scope-freeze) |
| Contratos no banco | 0 | >50.000 (alvo epic, não DoD) |
| Fontes operacionais | 1 | >5 |

### 5.4 Gap analysis fase 1 — `docs/epic-coverage/gap-analysis-fase1.md` (2026-07-11)

| Métrica | Valor |
|---------|-------|
| Cobertura geral SC | **39,4% (821/2.085)** |
| PNCP | 788 entes (37,8%) |
| CIGA CKAN | 156 (7,5%) |
| PCP | 35 (1,7%) |

**Atenção:** esta cobertura é **mais antiga e metodologicamente distinta** (JOINs bid/contract / entity_coverage rebuild). **Não** pode ser misturada sem recálculo com a série 3,1% / 5,9% / 6,1% de julho/15–16. Para o rebaseline de campanha, a série **mais recente e alinhada ao plano HTML** é a do handoff 15/jul (**3,1% editais no raio; 0% contratos**).

### 5.5 Golden path stories (capacidade ponta a ponta ≠ cobertura DoD)

| Story | Status | Evidência relevante |
|-------|--------|---------------------|
| GP-01 | Done, QA PASS, po_closed | 298 opp. importadas; 150 AEC no raio; 83 órgãos; R$179,5M estimado — **não** prova 95% |
| MAX-W1-01 | InReview, QA PASS | 200 registros PNCP; briefing CLI; 47 migrations — **não** prova 95% |
| CM-06 | InProgress | ACs de cobertura/contratos **BLOCKED** (API PNCP inacessível no ambiente de validação documentado) |
| CM-08 | Done, CONCERNS | Validação page size / infra contratos; po_closed=false |
| CM-13 | Done | 459 entity aliases; dedup multicanal |

### 5.6 QW-01 run manifest (amostra 2026-07-13)

`output/qw-01/qw01-20260713T135656Z-44d39e82/run_manifest.json`:

- `readiness`: **PARTIAL**
- `exit_code`: **2** (abaixo do threshold de monitoring)
- `claims_explicitly_blocked`: cobertura multicanal 95%; recomendação definitiva; preço pago/deságio real; conjunto completo de licitantes

---

## 6. Gaps vs `DOD.md`

### 6.1 Aceite formal de itens do checklist

| Fonte | Aceitos | Total inventariado | Observação |
|-------|---------|--------------------|------------|
| `DOD.md` grep `- [x]` | **2** | checklist completo do arquivo | Apenas §1 linhas 21–22 (versionamento do documento — PE-G0-01) |
| Plano HTML `ep-data` | 2 com `accepted:true` (DOD-0001, DOD-0002) | **~1340** critérios (`D.dodItems.length` no plano; contagem exata do JSON = **UNKNOWN sem parse completo** nesta sessão) | Card estático do HTML ainda diz “0%” em um painel — **inconsistência cosmética** com o JSON que já marca 2 aceitos |
| Gates §35 | `LOCAL_READY` / `VPS_OPERATIONAL` / `PROJECT_DONE` | todos **NÃO ATINGIDO** | Explicitamente desmarcados no DoD |

**Síntese alinhada ao plano executivo:** progresso de aceite DoD ≈ **2 / ~1340** (governança documental). Itens de cobertura, contratos, recall, VPS e PROJECT_DONE: **0 aceitos com evidência de execução no HEAD**.

### 6.2 Metas de cobertura (DoD §4 / §15 / §35)

| Requisito DoD | Estado no rebaseline |
|---------------|----------------------|
| `capability_monitoring_coverage(open_tenders) >= 95%` | **NÃO ACEITO** — melhor evidência recente de “editais no raio” ~**3,1%** (handoff 15/jul), metodologia ≠ fórmula canônica completa |
| `capability_monitoring_coverage(historical_contracts) >= 95%` | **NÃO ACEITO** — evidência recente **0%** / `supplier_contracts` ERROR no snapshot 16/jul |
| Coberturas calculadas **separadamente** | Regra **em vigor** no texto DoD; implementação de fórmula canônica única ainda **não aceita** (PE-C2-01 Ready) |
| `universe_resolution = 100%` | **NÃO ACEITO** |
| Recall editais relevantes ≥95% (amostra-ouro) | **NÃO ACEITO** / UNKNOWN se amostra-ouro existe e está versionada |
| Golden path + PDF/Excel + resume | Implementação candidata existe (commits `32eb442`, `eb2160a`); **aceite DoD pendente** (evidência de reexecução no HEAD da campanha não registrada neste rebaseline) |
| VPS operacional | **NÃO ACEITO** |
| PROJECT_DONE | **NÃO ACEITO** |

### 6.3 Proposta comercial (§2.5) — gap de alto nível

Entregáveis A–E e pacote PDF/Excel: **nenhum item marcado `[x]` no DoD**. Código/artefatos parciais podem existir; **sem aceite com evidência = não pronto para promessa comercial**.

---

## 7. Claims que NÃO podem ser afirmados ainda

Lista operacional de claims **proibidos** até evidência reproduzível no HEAD + aceite DoD (detalhamento de linguagem em `scope-freeze-95.md` e DoD §25):

1. **“Cobertura de 95% de editais”** (ou “quase 95%”, “pronto para o gate 95%”).
2. **“Cobertura de 95% de contratos”** / “contratos históricos cobertos no raio”.
3. **“Cobertura multicanal de 95%”** (já bloqueado em QW-01 manifests).
4. **Média** entre editais e contratos para “esconder” a pior dimensão.
5. **`data_presence` como se fosse `capability_monitoring_coverage`**.
6. **“LOCAL_READY” / “VPS_OPERATIONAL” / “PROJECT_DONE”** atingidos.
7. **Operação contínua em VPS de produção** como fato (provisionamento/credenciais/smoke no HEAD: não aceitos).
8. **“Meta >80% do EPIC-COVERAGE-MAX-200KM é a meta do projeto”** — subordinada; ver freeze.
9. **Win rate, deságio real, preço efetivamente pago, conjunto completo de licitantes** sem dados comparáveis e metodologia.
10. **Recomendação definitiva de participação** sem triagem humana / perfil versionado aceito.
11. **Acompanhamento de obras** (fora de escopo DoD).
12. **Fonte X “ativa em produção”** apenas porque existe crawler ou story Done sem run auditável no ledger.
13. **Números de coverage de datas diferentes fundidos** (ex.: 39,4% de 11/jul + 3,1% de 15/jul) sem recálculo unificado.
14. **295 / 1.976 / 298 / 200 registros no banco = cobertura do universo de 1.093 entes no raio**.
15. **Qualquer afirmação comercial da §2.5** (ranking de órgãos, 15 concorrentes, contratos vincendos, painel de preços, GO/NO_GO cliente) como **entregue**.

---

## 8. Estado das frentes do plano executivo (stories AIOX)

| Story | Tasks | Status state file | Nota |
|-------|-------|-------------------|------|
| PE-G0-01 | G0.1 | InProgress | DoD versionado; 2 itens §1 aceitos |
| **PE-G0-02** | **G0.2, G0.3** | **este rebaseline** | Produz este arquivo + scope-freeze |
| PE-G0-03 | G0.4, G0.5 | Ready | Ledger + RACI |
| PE-L1-* | L1.x | Ready/Draft | Fundação local |
| PE-C2-01 | C2.1, C2.2 | Ready | Fórmulas de cobertura |
| PE-K3-01 | K3.1 | Ready | Schema contratos |
| PE-Q5-01 | Q5.1 | Ready | Testes críticos |
| PE-CLOSE-01 | close | Draft | Publicação |

---

## 9. Comandos / leituras executadas e resultados

Nesta sessão de rebaseline **não** houve `git push` nem marcação de gates DoD de cobertura.

| Ação | Resultado |
|------|-----------|
| Ler `.git/HEAD` | `ref: refs/heads/epic/plano-executivo-30d` |
| Ler `.git/refs/heads/epic/plano-executivo-30d` | `1f7aa7c324a205c26876dece906c442b3aa84787` |
| Ler `.git/refs/heads/main` | `32eb4425c1b6c08878811394824e88a8d7167358` |
| Ler `.git/logs/HEAD` (últimas entradas) | Cadeia golden path → PNCP resume → data foundation → checkout plano-executivo-30d |
| Ler `.aiox/epic-DATA-FOUNDATION-state.yaml` | Waves 0–4 DONE; wave 5 IN_PROGRESS; status epic IN_PROGRESS |
| Ler `docs/baseline/DATA-FOUNDATION-baseline-2026-07-16.md` | 295 pncp_raw_bids; contracts ERROR; coverage_evidence 0 |
| Ler handoffs `NEXT-SESSION.md`, `handoff-goal-2026-07-15.yaml`, `handoff-cm13-wave2-2026-07-15.yaml` | Métricas 3,1% / 0% contratos / 5,9% CM-07 / aliases CM-13 |
| Ler `DOD.md` + grep `- [x]` | **2** itens aceitos (versionamento) |
| Ler `EPIC-PLANO-EXECUTIVO-30D.md`, `PE-G0-02-rebaseline-freeze.story.md` | Meta 95% canônica; G0.3 subordina >80% |
| Ler `EPIC-COVERAGE-MAX-200KM.md` | Alvo legado recall >80% |
| Ler states GP-01, MAX-W1-01, CM-06, CM-08, PE-G0-01 | Conforme tabelas acima |
| Ler QW-01 `run_manifest.json` | exit 2; claims 95% bloqueados |
| `python scripts/coverage_truth.py` / SQL live | **NÃO EXECUTADO** nesta sessão → qualquer coverage “agora” = **UNKNOWN** além dos snapshots citados |
| Marcar itens DoD de cobertura | **NÃO FEITO** (sem evidência) |

---

## 10. Conclusão do rebaseline

1. **HEAD da campanha:** `1f7aa7c` em `epic/plano-executivo-30d`, com DATA-FOUNDATION waves 0–4 done e wave 5 aberta.  
2. **Capacidade de software:** golden path e resume PNCP existem como commits; testes de chaos/foundation documentados.  
3. **Capacidade de cobertura auditável DoD:** **não comprovada**. Melhor âncora recente de editais no raio ≈ **3,1%**; contratos ≈ **0%**.  
4. **Aceite DoD:** **2 / ~1340** (só governança documental).  
5. **Próximo passo GATE-0:** PE-G0-03 (ledger + RACI) e, em paralelo de governança, **scope-freeze-95.md** (G0.3).  
6. **Próximo passo de verdade de dados:** PE-C2 + reexecução instrumentada de coverage no ambiente com DB estável (não confundir com aceite 95%).

---

*Documento gerado para PE-G0-02. Não autoriza publicação, não marca DoD de cobertura, não substitui QA gate.*
