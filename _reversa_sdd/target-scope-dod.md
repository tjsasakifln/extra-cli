# Escopo Almejado — `DOD.md` como fonte canônica

> **Decisão de projeto (2026-07-17):** o arquivo raiz **`DOD.md`** (alias `DoD.md`) é a **definição de escopo almejado** do Extra Consultoria.  
> A extração Reversa (`_reversa_sdd/`) descreve o que o sistema **é**.  
> O `DOD.md` define o que o sistema **deve ser** para ser considerado pronto.  
> 🟢 CONFIRMADO — instrução explícita do owner (Tiago) + conteúdo do documento versionado.

---

## 1. Precedência

| Fonte | Papel | Quando conflita |
|-------|-------|-----------------|
| **`DOD.md`** | Escopo almejado, metas, exclusões, gates de pronto, claims permitidos | **Vence** |
| Proposta comercial (via §2.5 do DOD) | Promessas a provar em capacidade | Subordinada ao DOD |
| Stories AIOX / epics | Fatias de implementação | Não fecham item DOD sem evidência |
| `_reversa_sdd/*` | Estado e regras **as-is** do código | Atualiza-se; não redefine meta |
| ADRs em `docs/architecture/adr/` | Decisões técnicas | Devem servir ao DOD, não ao contrário |
| Agentes/IDE (Claude, Grok, AIOX…) | Aceleradores | **Não** definem “pronto” (DOD §0 / §32) |

**Regra de ouro (DOD):** código existente sem execução comprovada **não** é concluído; presença no banco **não** é cobertura; story `Done` **não** marca item do DOD.

---

## 2. Natureza e contrato (resumo normativo)

| Atributo | Definição almejada |
|----------|-------------------|
| Natureza | Ferramenta **pessoal, single-user** (Tiago) para consultoria à Extra Construtora |
| Forma | CLI, scripts, arquivos — **sem** SaaS/multi-tenant obrigatório |
| Universo canônico | Planilha `Extra - alvos de licitação. R-0.xlsx` |
| Denominador atual | **1.093** entes no raio 200 km (baseline da versão corrente da planilha; **não** constante eterna) |
| Meta mínima | Cobertura operacional auditável **≥95% editais** e **≥95% contratos** (separadas), sobre o universo 200 km |
| Fora de escopo absoluto | Acompanhamento **físico** de obra (medição, diário, fiscalização, avanço físico, etc.) |
| Dentro (admin) | Contratos: publicações, prazos, aditivos, vigência, garantias, renovações, sanções, relicitações |

### 2.1 Incluído (DOD §2.2) — checklist de intenção

- Monitoramento e reconciliação de editais (abertos + histórico quando necessário)  
- Contratos ≥3 anos + incremental  
- Vencedores, órgãos, recorrência, concentração  
- Valores: estimado / homologado / contratado / pago — **semântica explícita**  
- Export + PDF/Excel  
- Operação local → depois VPS  
- Triagem e análise técnica de edital; planilha/composições/BDI quando docs existirem  
- Apoio `GO` / `REVIEW` / `NO_GO` e proposta **sem** assinar/protocolar pela Extra  
- Acompanhamento **administrativo** de contratos  

### 2.2 Excluído (DOD §2.3) — anti-escopo

- Obra física, portal contratada, UI pública, multi-tenant, billing/Stripe  
- K8s/Kafka/Redis/ES sem necessidade comprovada  
- Assinatura/protocolo automático, responsabilidade jurídica/contábil, promessa de vitória  

### 2.3 Proposta comercial (DOD §2.5)

Capacidades verificáveis para entregáveis de diagnóstico (ranking de órgãos, etc.) e perfil canônico Extra — software **suporta** a consultoria humana; não a substitui.

---

## 3. Três róis e três gates

```text
ROL 1 — Estágio atual (local-first)     →  Gate LOCAL_READY
ROL 2 — Pós-VPS                         →  Gate VPS_OPERATIONAL
ROL 3 — Independente de infra           →  (entra nos dois + PROJECT_DONE)

PROJECT_DONE = LOCAL_READY ∧ VPS_OPERATIONAL ∧ ROL3 ∧ utilidade real
```

| Gate | Condições-chave (DOD §35) | Status no DOD |
|------|---------------------------|---------------|
| **LOCAL_READY** | ROL1+ROL3; universo reconciliado; cobertura editais/contratos ≥95%; recall ≥95%; snapshot 100%; golden path; PDF/Excel; backup/restore; aceite Tiago | **NÃO ATINGIDO** |
| **VPS_OPERATIONAL** | ROL2; deploy/hardening/migrate/timers/alertas/backup; 7 dias estáveis; coberturas ≥95% | **NÃO ATINGIDO** |
| **PROJECT_DONE** | Ambos gates + escopo proposta + 5 entregáveis §2.5 + rotina real + agnosticidade §32 | **NÃO ATINGIDO** |

### Gates de campanha ≠ gates §35

Sessões §38–§44 registram progresso operacional (ex.: `LOCAL_RESILIENCE_READY`) **sem** declarar `LOCAL_READY` / 95% / `PROJECT_DONE`.

| Selo de campanha | Significado | Implica LOCAL_READY? |
|------------------|-------------|----------------------|
| Ciclo B2G 17/07 | Contrato de medição + fatias | **Não** |
| `LOCAL_RESILIENCE_READY` (§44) | Resiliência local PNCP/CIGA/SC Compras | **Não** |

---

## 4. Cobertura e verdade (DOD §4 + ciclo B2G)

| Conceito | Norma DOD | Estado comprovado (ciclo 17/07) |
|----------|-----------|----------------------------------|
| Denominador | Fixo na planilha/universo 200 km | **1.093** |
| Sinal comercial (M1) | **Não** é cobertura 95% | **116/1.093 (10,61%)** |
| Cobertura operacional (M2) | Estágios + SLA + proveniência; fail-closed | **0/1.093 (0%)** — meta **≥1.039/1.093** |
| Gaps nominais | Cada ente com blocker/próxima ação | 714 pending_collection / 226 pending_live_verification / 153 fragmented |
| Registro ESR 1093 | Existe ≠ operacional | 1093/1093 no registry |

Alinha a ADR-018 e R27–R29 em `_reversa_sdd/domain.md`.

---

## 5. Mapa DoD → módulos do sistema (as-is)

| Bloco DOD | Seções | Módulos / artefatos de código |
|-----------|--------|--------------------------------|
| Universo | §3 | `lib/universe`, seed planilha, migrations target universe |
| Cobertura | §4 | `coverage/*`, `coverage_truth`, `consulting_readiness` |
| Local reprodutível | §5 | docker-compose, bootstrap, tests |
| Schema | §6 | `db/migrations`, `schema/*` |
| Fontes / ESR | §7 | `crawl/registry`, `source_registry` |
| Editais | §8 | crawl PNCP/SC, `opportunity_intel` |
| Contratos | §9 | `contracts` crawler, `contract_intel` |
| Concorrentes | §10 | ranking, buyer_intel, competitive intel |
| Valores | §11 | `lib/value_semantics` |
| Pipeline / reports | §12 | `intel_pipeline`, `reports`, workspace |
| Testes | §13 | `tests/*`, ci_gate, GH Actions |
| Backup local | §14 | scripts backup/restore |
| Aceite | §15 | validação humana Tiago |
| VPS ROL2 | §16–24 | `deploy/*`, systemd, ops |
| Verdade / claims | §25 | dual-metric, fail-closed language |
| Simplicidade / código | §26–27 | ADRs 001–022 |
| Segurança / audit | §28–29 | bandit, secrets, evidence |
| Docs / agnosticidade | §31–32 | DOD próprio, CLAUDE opcional |
| Workspace rotina | §2.4 + B2G | `scripts/workspace` |
| Resiliência pré-VPS | §44 | `crawl/resilience`, `ops/resilient_cycle` |

---

## 6. Gap DoD × realidade (síntese para planejamento)

### Já avançado (evidência no DOD, não gate §35)

- Contrato de medição dual-metric e denominador 1093  
- ESR 1093 + gap report nominal  
- Workspace facade de rotina  
- Ingestão pública DOE/DOM + sample acts  
- CI critical PR verde (não suíte full)  
- `LOCAL_RESILIENCE_READY` (3 fontes prioritárias)  

### Bloqueadores explícitos para LOCAL_READY

| # | Item DOD | Severidade |
|---|----------|------------|
| 1 | Cobertura operacional ≥95% (editais e contratos) | 🔴 |
| 2 | Freshness coverage por entidade dentro de SLAs | 🔴 |
| 3 | Recall independente estratificado ≥95% | 🔴 |
| 4 | Suíte global de testes verde (não só critical) | 🟠 |
| 5 | Aceite manual Tiago + backup/restore local comprovados | 🟠 |
| 6 | Universo: hash planilha / reconciliação total formal | 🟠 |

### Fora do estágio atual (ROL 2)

- VPS, hardening, timers em produção, 7 dias, DR externo  

---

## 7. Implicações para Reversa, AIOX e claims

1. **Reversa** continua documentando o legado/as-is; ao priorizar features, o **alvo** é fechar itens do `DOD.md`.  
2. **Stories AIOX** devem referenciar seção/item do DOD quando implementarem capacidade de escopo.  
3. **Claims à diretoria** só os permitidos no DOD (sessões §38–§44 e §25) — nunca 95% operacional enquanto M2=0.  
4. **`LOCAL_RESILIENCE_READY` ≠ `LOCAL_READY`.**  
5. Alteração de escopo: **primeiro** no `DOD.md`, depois código/specs.  

---

## 8. Referências

| Artefato | Path |
|----------|------|
| Escopo almejado canônico | `/DOD.md` (raiz) |
| Este binding Reversa | `_reversa_sdd/target-scope-dod.md` |
| As-is domínio | `_reversa_sdd/domain.md` |
| As-is arquitetura | `_reversa_sdd/architecture.md` |
| Cobertura contract | ADR-018 / `scripts/coverage/coverage_contract.py` |
| Sessões evidência | `docs/ops/session-*`, DOD §38–§44 |

---

## 9. Histórico desta decisão

| Data | Evento |
|------|--------|
| 2026-07-17 | Owner orienta: considerar `DOD.md` como definição de escopo almejado do projeto; Reversa registra binding formal. |
