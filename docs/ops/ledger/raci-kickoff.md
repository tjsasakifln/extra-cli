# RACI kick-off — EPIC-PLANO-EXECUTIVO-30D

> **Story:** PE-G0-03 (task G0.5)  
> **Data do kick-off documentado:** 2026-07-16  
> **Fontes:** `extra-consultoria-plano-executivo.html` (RACI operacional), `DOD.md`, protocolo AIOX  
> **Convenção:** **R** = executa · **A** = accountable (aceite) · **C** = consultado · **I** = informado

---

## 1. Papéis

| Papel | Quem (projeto) | Autoridade principal |
|-------|----------------|----------------------|
| **Tiago** | Tiago Sasaki — dono / usuário único | Aceite de escopo, meta 95%, blockers externos, `PROJECT_DONE`, validação manual DoD |
| **PO** | Pax (@po) | Validação/fechamento de story, priorização do backlog da campanha, reconciliação DoD ↔ stories |
| **Dev** | Dex (@dev) | Implementação, commits locais, atualização de File List / state `files_modified` |
| **QA** | Quinn (@qa) | Veredito independente PASS/CONCERNS/FAIL/WAIVED; não é o implementador |
| **Data Eng** | Dara (@data-engineer) | Schema, migrations, integridade de dados, universo/seed, queries de cobertura |
| **DevOps** | Gage (@devops) | Push, PR, release, timers/CI, MCP infra — **exclusivo** para remoto |
| **Architect** | Aria (@architect) | Decisões de arquitetura, impacto sistêmico, HIGH-RISK, gates de desenho |

> Em operação single-user, Tiago pode acumular PO/QA humanos de negócio; agentes AIOX **não** fundem papéis de veredito (QA ≠ Dev).

---

## 2. Matriz RACI por entrega da campanha

| Decisão / entrega | Tiago | PO | Dev | QA | Data Eng | DevOps | Architect |
|-------------------|-------|----|-----|----|----------|--------|-----------|
| Autoridade do DoD / mudança de escopo DoD | **A** | R | C | C | C | I | C |
| Versionar DoD + plano (G0.1) | A | C | **R** | C | I | I | C |
| Rebaseline HEAD (G0.2) | I | **A** | R | C | C | I | C |
| Freeze meta 95% / claims (G0.3) | **A** | R | C | C | C | I | C |
| Ledger de evidências (G0.4) | I | **A** | R | C | C | I | C |
| RACI / WIP / escalonamento (G0.5) | **A** | R | C | C | C | C | C |
| Manifesto GATE-0 `BASELINE_LOCKED` | A | **R** | C | C | C | I | C |
| Ambiente local + migrations (L1) | I | A | R | C | **R**/C | I | C |
| Universo canônico / registry (L1.2/L1.4) | C | A | C | C | **R** | I | C |
| Golden path / resume / backup local | I | A | **R** | C | C | I | C |
| Fórmulas de cobertura (C2) | C | A | R | C | **R** | I | C |
| Runtime fontes PNCP/PCP/ComprasGov | I | A | **R** | C | C | I | C |
| Schema/semântica contratos (K3) | C | A | C | C | **R** | I | **C** |
| Testes caminho crítico (Q5) | I | A | R | **A**/C | C | I | C |
| Veredito QA de story | I | I | I | **A/R** | C | I | C |
| Fechamento de story (po_closed) | I | **A/R** | I | C | I | I | I |
| Push / PR → main | I | C | I | C | I | **A/R** | C |
| Aceite manual estágio atual (DoD §15) | **A/R** | C | I | C | I | I | I |
| Gate DoD `LOCAL_READY` / `PROJECT_DONE` | **A** | R | C | C | C | C | C |
| Provisionamento VPS / credenciais | **A** | C | I | I | C | **R** | C |
| Decisão arquitetural HIGH-RISK | C | C | C | C | C | C | **A/R** |

---

## 3. WIP limits (limites de trabalho em progresso)

Objetivo: proteger o caminho crítico G0 → L1 → evidência de cobertura, sem paralelismo caótico.

| Fila | Limite | Regra |
|------|--------|--------|
| Stories `InProgress` (campanha PE-*) | **2** | Só abrir a 3ª se for FAST ou desbloqueio de BLOCKED no caminho crítico |
| Stories HIGH-RISK `InProgress` | **1** | Ex.: PE-G0-02, migrations, auth/dados sensíveis |
| Gates de campanha abertos simultâneos | **1** em fechamento | Não declarar GATE-1 enquanto GATE-0 estiver `OPEN` sem manifesto PARTIAL justificado |
| Itens DoD em “aceitação pendente Tiago” | **5** | Fila de aceite humano; acima disso, PO prioriza batch |
| Fontes externas em investigação runtime | **3** | C2.x: foco PNCP, PCP, ComprasGov antes de novas fontes |
| PRs abertos (@devops) | **1** por wave | Evita publicação fora de ordem de gates |

### Política de puxar trabalho

1. **Prioridade 0:** desbloquear G0 (BASELINE_LOCKED).  
2. **Prioridade 1:** L1 foundation (fresh install, universo, golden path, restore).  
3. **Prioridade 2:** C2 / K3 / Q5 com evidência no ledger — **sem** prometer 95%.  
4. Trabalho cosmético/doc não-DoD só se WIP &lt; limite.

### Anti-WIP

- Proibido iniciar feature de cobertura com ledger/G0 incompletos **e** sem story Ready.  
- Proibido “story sombra” sem state em `.aiox/state/stories/`.  
- Proibido Dev autoaplicar QA para liberar slot de WIP.

---

## 4. Critérios de escalonamento

### 4.1 Matriz de severidade

| Nível | Gatilho | Tempo máximo antes de escalar | Escala para |
|-------|---------|-------------------------------|-------------|
| **E1 — Story** | QA FAIL; AC ambíguo; lint/test falhando na story | Imediato no handoff | Dev (fix) → QA re-gate; se 2 FAIL → PO |
| **E2 — Gate campanha** | Critério G0/L1 sem evidência na data planejada; G0.1/G0.2 parados &gt; 2 dias úteis | 1 dia útil após detecção | PO → Tiago se impacto em prazo 30d |
| **E3 — Dados / cobertura** | Divergência de fórmula; meta 80% vs 95%; denominador errado | Imediato (não aceitar claim) | Data Eng + PO; Architect se sistêmico; **Tiago** se mudar meta |
| **E4 — Externo / BLOCKED** | Credencial VPS, DOM-SC, API fonte, PNCP geo-block | Registrar no índice no mesmo dia; reteste em ≤ 5 dias úteis | Tiago (A) + DevOps/Dev (R de teste) |
| **E5 — Segurança / produção** | Secret exposto, destruição de dados, push indevido | Imediato | DevOps + Architect; Tiago informado |
| **E6 — Processo AIOX** | Código sem story; push sem state; QA pelo implementador | Interromper na hora | Corrigir curso (protocolo §9); sem exceção |

### 4.2 Sinais de alerta (RAID leve)

| ID | Risco / issue | Owner | Mitigação |
|----|---------------|-------|-----------|
| R-02 | Conflito meta 80% × 95% | PO / Tiago | Freeze G0.3: DoD 95% é autoridade |
| R-G0 | G0.1/G0.2 incompletos bloqueiam narrativa de baseline | PO | GATE-0 permanece PARTIAL; sem `LOCKED` prematuro |
| R-EV | Marcar DoD sem path de evidência | QA / PO | Ledger + recusa de `[x]` |
| R-PUB | Push sem gates | DevOps | Hooks + state file; Dev nunca push |
| R-VPS | V6.2 sem credenciais | Tiago | ROL2 BLOCKED consciente; não fake-green |

### 4.3 Procedimento de escalonamento

```
1. Registrar no evidence-index (status BLOCKED/PARTIAL) + story state
2. Owner R tenta desbloquear no prazo da tabela
3. Se estourar prazo → notificar A (PO ou Tiago conforme matriz)
4. Decisão de escopo / meta / aceite externo → somente Tiago
5. Decisão técnica sistêmica → Architect; dados → Data Eng
6. Nunca silenciar BLOCKED no gate (DoD §1)
```

---

## 5. Cadência sugerida (30 dias úteis)

| Ritual | Frequência | Participantes | Saída |
|--------|------------|---------------|-------|
| Kick-off G0 (este doc) | Uma vez | Tiago, PO, Dev, QA, Data Eng, DevOps, Architect | RACI + WIP + ledger ativos |
| Sync caminho crítico | 2× por semana | PO + Dev (+ Data Eng se L1/C2) | Atualizar índice + bloqueios |
| Gate review | Ao completar tasks do gate | PO + QA + Architect (se HIGH-RISK) | Manifesto GATE-* atualizado |
| Aceite DoD batch | Sob demanda / semanal | Tiago + PO | `[x]` + evidência no DoD |
| Publicação | Após stories Done + QA + PO close | DevOps | PR/main com state válido |

---

## 6. Definition of Done deste kick-off (G0.5)

- [x] Papéis nomeados (Tiago, PO, Dev, QA, Data Eng, DevOps, Architect)
- [x] Matriz RACI das entregas G0 e principais L1/C2/K3/Q5
- [x] WIP limits numéricos
- [x] Critérios e procedimento de escalonamento
- [ ] Leitura/confirmação formal de Tiago (aceite humano — opcional para PARTIAL do G0.5; obrigatório para considerar governança “fechada” no DoD §33)

**Status G0.5:** `PARTIAL` (documento versionado; confirmação humana de Tiago pendente)

---

## 7. Referências

- [`README.md`](./README.md) — uso do ledger  
- [`evidence-index.md`](./evidence-index.md) — status por seção  
- [`GATE-0-BASELINE-LOCKED.md`](./GATE-0-BASELINE-LOCKED.md)  
- `.claude/rules/aiox-project-operating-protocol.md`  
- `.claude/rules/agent-authority.md`  
