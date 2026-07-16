# Ledger de evidências — DoD

> **Story:** PE-G0-03 (tasks G0.4, G0.5)  
> **Epic:** EPIC-PLANO-EXECUTIVO-30D  
> **Fonte canônica de critérios:** [`DOD.md`](../../../DOD.md) (raiz do repositório)  
> **Data de ativação:** 2026-07-16  
> **Natureza:** artefato operacional versionado — não depende de histórico de chat

---

## 1. Propósito

O ledger registra **evidência verificável** para cada seção e item do `DOD.md`, alinhado à convenção do próprio DoD:

- item só vira `[x]` com evidência;
- implementação parcial → `PARTIAL` (sem marcar concluído);
- dependência externa → `BLOCKED` (visível até resolução ou mudança formal de escopo);
- story AIOX `Done` **não** aceita automaticamente o requisito equivalente no DoD.

Objetivo: reconstruir o estado de cada requisito **sem depender** de conversa com agente de IA (DoD §1 / §32).

---

## 2. Estrutura deste diretório

| Arquivo | Função |
|---------|--------|
| [`README.md`](./README.md) | Como usar o ledger (este documento) |
| [`evidence-index.md`](./evidence-index.md) | Índice por seção do DoD (ROL 1/2/3 + contrato + gates) |
| [`raci-kickoff.md`](./raci-kickoff.md) | Papéis, RACI, WIP limits e escalonamento (G0.5) |
| [`GATE-0-BASELINE-LOCKED.md`](./GATE-0-BASELINE-LOCKED.md) | Manifesto do gate `BASELINE_LOCKED` (G0.1–G0.5) |
| `GATE-1-LOCAL-FOUNDATION.md` | Manifesto GATE-1 (story PE-L1-04 — futuro) |
| `evidence/` *(opcional)* | Anexos por run (JSON, logs, dumps) quando o path no índice apontar para cá |

Paths de evidência **preferidos** fora deste diretório (já usados no projeto):

- `docs/baseline/` — rebaseline, freeze de meta 95%
- `docs/audits/`, `docs/coverage-truth/`, `docs/qa/gates/`
- `docs/operations/`, `docs/ops/`
- `output/` — artefatos gerados por scripts (não versionar binários grandes; registrar path + data no índice)

---

## 3. Alinhamento com `DOD.md`

### 3.1 Estados permitidos (ledger e índice)

| Status | Significado | Pode marcar item DoD `[x]`? |
|--------|-------------|----------------------------|
| `OPEN` | Sem evidência ou trabalho não iniciado | Não |
| `PARTIAL` | Útil com limitações explícitas; incompleto | Não |
| `DONE` | Evidência verificável + validação | Sim |
| `BLOCKED` | Impedido por dependência externa/técnica | Não |
| `NOT_APPLICABLE` | Só com redação condicional ou decisão formal de Tiago | N/A (com justificativa) |

Estes estados espelham DoD §1 (estados/aplicabilidade) e §25 (READY / PARTIAL / NOT_READY / BLOCKED).

### 3.2 Tipos de evidência aceitos (DoD §1 — convenção)

Um item só pode ir a `DONE` com **pelo menos um** de:

1. teste automatizado reproduzível;
2. comando documentado com exit code `0`;
3. relatório JSON / CSV / Excel / PDF / Markdown gerado pelo sistema;
4. consulta SQL com resultado esperado;
5. execução em ledger, manifest ou tabela de runs;
6. log datado e correlacionável;
7. validação manual registrada por Tiago;
8. commit ou PR identificável;
9. teste de restauração/recuperação executado;
10. comparação com fonte oficial na mesma data/período.

**Anti-padrões (nunca promover a DONE):**

- código presente no HEAD sem execução comprovada;
- teste unitário isolado no lugar de ponta a ponta, quando o item exige e2e;
- “tem linha no banco” como prova de cobertura;
- claim de README/handoff sem artefato no HEAD.

### 3.3 Onde registrar

| Nível | Onde | Quando |
|-------|------|--------|
| Item do DoD | Checkbox + `Evidência: …` no próprio `DOD.md` | No momento do aceite do item |
| Seção agregada | Linha em [`evidence-index.md`](./evidence-index.md) | Sempre que o status da seção mudar |
| Gate da campanha | `GATE-*-*.md` neste diretório | Ao fechar ou reavaliar o gate |
| Story AIOX | `docs/stories/...` + `.aiox/state/stories/*.json` | Ciclo SDC normal |

O índice **não substitui** o DoD: é mapa operacional. A verdade do checklist continua em `DOD.md`.

---

## 4. Como usar no dia a dia

### 4.1 Ao iniciar trabalho em um requisito

1. Localizar a seção no `DOD.md` e a linha correspondente em `evidence-index.md`.
2. Confirmar status atual (`OPEN` / `PARTIAL` / `BLOCKED`).
3. Se `BLOCKED`, registrar causa, owner e próximo teste em `raci-kickoff.md` (RAID) ou na story.
4. Criar/atualizar story AIOX se a mudança for de código ou de dados.

### 4.2 Ao produzir evidência

1. Executar o comando/script e capturar saída (path sob `output/`, `docs/`, ou anexo em `docs/ops/ledger/evidence/`).
2. Anotar: **data**, **comando**, **exit code**, **commit** (`git rev-parse --short HEAD`), **path**.
3. Atualizar a linha da seção em `evidence-index.md` (`status`, `evidência path`, `data`).
4. Se o item individual estiver fechado, marcar `[x]` no `DOD.md` com `Evidência: <path ou commit>`.
5. Nunca marcar seção `DONE` se restarem itens obrigatórios `OPEN`/`PARTIAL`/`BLOCKED` nela.

### 4.3 Ao fechar um gate (ex.: GATE-0)

1. Abrir o manifesto (`GATE-0-BASELINE-LOCKED.md`, etc.).
2. Verificar checklist item a item com paths reais no HEAD.
3. Status do manifesto:
   - `LOCKED` / `DONE` — todos os critérios obrigatórios `DONE`;
   - `PARTIAL` — estrutura criada, mas dependências G0 ainda em andamento;
   - `OPEN` — não iniciado;
   - `BLOCKED` — impedimento externo.
4. Atualizar `evidence-index.md` na linha do gate consolidado, se aplicável.

### 4.4 Template de evidência (copiar para story ou anexo)

```markdown
### Evidência — <ID DoD ou seção>

- **Requisito:** <texto curto ou path §X.Y>
- **Status proposto:** DONE | PARTIAL | BLOCKED
- **Data:** YYYY-MM-DD
- **Commit:** <sha curto>
- **Comando / procedimento:**
  ```bash
  <comando>
  ```
- **Exit code / resultado:** 
- **Artefato path:** `path/relativo/ao/repo`
- **Validador:** <papel RACI — ex. QA / Tiago>
- **Limitações (se PARTIAL):** 
- **Causa e próximo teste (se BLOCKED):** 
```

---

## 5. Relação com AIOX e Reversa

| Sistema | Papel |
|---------|--------|
| **DoD + ledger** | Critérios de negócio e evidência de aceite do projeto |
| **AIOX stories/state** | Autorização de mudança de código, QA, PO close, publicação |
| **Reversa** | Documentação do legado (não autoriza push nem marca DoD) |

Uma story `Done` no AIOX é **insumo** de evidência; o aceite no DoD é passo separado (marca no `DOD.md` + linha no índice).

Publicação remota permanece exclusiva de `@devops` com state file válido — o ledger **não** autoriza push.

---

## 6. Manutenção

| Ação | Responsável (R) | Accountable (A) |
|------|-----------------|-----------------|
| Atualizar paths de evidência | Dev / Data Eng | PO |
| Aceitar item no DoD | PO (propõe) | Tiago (aceite final quando aplicável) |
| Veredito de qualidade da evidência | QA | QA |
| Manifesto de gate | PO / Architect | Tiago (gates de projeto) |
| WIP e priorização | PO | Tiago |

Revisão mínima do índice: **a cada story PE-*** fechada** e **ao final de cada gate** da campanha de 30 dias.

---

## 7. Referências

- `DOD.md` — checklist e gates `LOCAL_READY` / `VPS_OPERATIONAL` / `PROJECT_DONE`
- `extra-consultoria-plano-executivo.html` — plano G0–close, RACI operacional
- `docs/stories/epics/epic-plano-executivo-30d/EPIC-PLANO-EXECUTIVO-30D.md`
- `docs/stories/epics/epic-plano-executivo-30d/PE-G0-03-ledger-raci.story.md`
- `.aiox/state/stories/PE-G0-03.json`
