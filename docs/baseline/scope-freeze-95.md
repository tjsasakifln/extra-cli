# Scope Freeze — Meta 95% (Editais e Contratos Separados)

**Story:** PE-G0-02 (task G0.3 do plano executivo)  
**Epic:** EPIC-PLANO-EXECUTIVO-30D  
**Data da decisão:** 2026-07-16  
**HEAD de referência:** `1f7aa7c` (`epic/plano-executivo-30d`)  
**Documento complementar:** `docs/baseline/rebaseline-2026-07-16.md`  
**Fontes canônicas:** `DOD.md`, `extra-consultoria-plano-executivo.html`, `docs/stories/epics/epic-plano-executivo-30d/EPIC-PLANO-EXECUTIVO-30D.md`

---

## 1. Decisão formal (autoridade de meta)

### 1.1 Meta canônica (AUTORIDADE)

A partir desta data, a **única meta de cobertura que define “pronto”** para o produto Extra Consultoria é a do **Definition of Done**:

> Cobertura operacional **auditável** de **≥ 95% para editais** e **≥ 95% para contratos**, **calculadas separadamente**, sobre os entes da planilha canônica marcados como pertencentes ao **raio de 200 km**.

Fundamento textual (`DOD.md` cabeçalho e §4):

- Meta mínima: 95% editais **e** 95% contratos, **separados**.
- Fórmula alvo: `capability_monitoring_coverage(open_tenders)` e `capability_monitoring_coverage(historical_contracts)`.
- **Proibido** usar a média das duas para mascarar a pior.
- Fonte saudável em uma capacidade **não** prova a outra.
- Entes fora do raio **não** entram no denominador das metas de 95%.
- Presença de registros no banco **não** é cobertura.

### 1.2 Meta legada EPIC-COVERAGE-MAX-200KM (SUBORDINADA)

O epic `EPIC-COVERAGE-MAX-200KM` (`docs/stories/epics/EPIC-COVERAGE-MAX-200KM.md`) define, entre outras, a hipótese/alvo:

| Métrica legada | Alvo no epic (15/07) | Status após freeze |
|---------------|----------------------|--------------------|
| Recall entes com dados | **> 80%** | **Subordinado** à meta DoD 95% |
| Contratos no banco | > 50.000 (contagem absoluta) | Indicador auxiliar; **não** substitui 95% auditável por ente aplicável |
| Ondas 1–4 “chegar a 80%” | Planejamento interno do epic | Pode continuar como **marco intermediário de execução**, nunca como declaração de DoD |

**Regra de subordinção:**

1. Stories e métricas do EPIC-COVERAGE-MAX-200KM **continuam válidas como backlog de cobertura**.
2. Atingir **>80%** de recall/data_presence **não** autoriza claims de “cobertura do projeto”, `LOCAL_READY` ou entrega comercial.
3. Qualquer comunicação externa, README, proposta, relatório ou handoff que cite “meta do projeto” deve usar **95% editais + 95% contratos (separados)**.
4. Reduzir a meta canônica de 95% para 80% (ou unificar editais/contratos) **exige decisão formal de Tiago** registrada em revisão do `DOD.md` + atualização do plano HTML — **não** pode ser feita por story de implementação.

### 1.3 R-02 — conflito 80% × 95% — RESOLVIDO

| Campo | Valor |
|-------|-------|
| ID | **R-02** |
| Descrição | Conflito de meta: epic de cobertura (15/07) busca **>80%**; DoD e plano executivo exigem **≥95%** editais e **≥95%** contratos, separados |
| Onde aparecia | `extra-consultoria-plano-executivo.html` (alerta “Conflito de meta que altera o caminho crítico”); `EPIC-COVERAGE-MAX-200KM.md`; handoffs EPIC-COVERAGE-MAX-200KM |
| Decisão | **Resolvido em favor do DoD** |
| Efeito | 95% dual (editais \| contratos) é gate; >80% é legado/subordinado |
| Data | 2026-07-16 |
| Story | PE-G0-02 / G0.3 |
| Reversão | Somente por alteração formal do `DOD.md` autorizada por Tiago |

**Status R-02:** `RESOLVED` (favor DoD).

---

## 2. O que “95%” significa (e o que não significa)

### 2.1 Significa

- Denominador: entes **aplicáveis** no raio 200 km (planilha `Extra - alvos de licitação. R-0.xlsx` / seed reconciliado).
- Numerador: entes com combinação obrigatória de fontes **consultada integralmente**, **fresca**, **sem blocker**, conforme `capability_monitoring_coverage` (DoD §4).
- Duas linhas de gate: editais abertos/monitoráveis **e** contratos históricos — ambas ≥95%.
- Evidência: comando/SQL/relatório/manifest **reproduzível**, com data de corte.

### 2.2 Não significa

- Ter N mil linhas em `pncp_raw_bids` ou `opportunity_intel`.
- Story AIOX `Done` ou commit `feat:`.
- Cobertura de SC inteiro (2.085) no lugar do raio (1.093) sem declarar denominador.
- “Recall de prefeituras >95%” se secretarias/autarquias aplicáveis ficam de fora sem `not_applicable` justificado.
- Média (editais + contratos) / 2.
- Exit code 0 de um radar parcial com claims bloqueados no manifest.

---

## 3. Claims permitidos vs proibidos

### 3.1 Claims **permitidos** (com a formulação cautelosa)

| Claim permitido | Condição |
|-----------------|----------|
| “Existe implementação substancial de crawlers, schema, testes e golden path no repositório.” | Apontar commits/arquivos; não confundir com cobertura |
| “DATA-FOUNDATION waves 0–4 estão DONE no state file; wave 5 em progresso.” | Citar `.aiox/epic-DATA-FOUNDATION-state.yaml` |
| “Snapshot/handoff de DD/MM registrou X% de data_presence no raio.” | Data + fonte + denominador explícitos |
| “Melhor evidência recente de editais no raio ≈ 3,1% (15/07); contratos ≈ 0%.” | Até novo rebaseline com recálculo |
| “Meta canônica do projeto é ≥95% editais e ≥95% contratos, separados.” | Sempre |
| “EPIC-COVERAGE-MAX-200KM usa marco intermediário >80%, subordinado ao DoD.” | Após este freeze |
| “QW-01/readiness saiu PARTIAL / exit 2; claims de 95% estavam bloqueados no manifest.” | Citar run_id |
| “DoD versionado; 2 itens de governança documental aceitos (PE-G0-01).” | Apenas §1 versionamento |
| “Código existente sem execução comprovada não está concluído no DoD.” | Regra DoD §1 |

### 3.2 Claims **proibidos** (até evidência + aceite DoD)

| Claim proibido | Motivo |
|----------------|--------|
| “Já temos 95% de cobertura.” | Sem `capability_monitoring_coverage` ≥95% aceito |
| “Estamos em 80%+, então o DoD está essencialmente ok.” | R-02: 80% ≠ 95%; e 80% ainda **não** está provado no HEAD |
| “Contratos históricos cobertos.” | Evidência recente 0% / ERROR |
| “LOCAL_READY / VPS_OPERATIONAL / PROJECT_DONE.” | Gates §35 NÃO ATINGIDO |
| “Pronto para entregar o diagnóstico completo da proposta.” | §2.5 sem itens aceitos |
| “Cobertura multicanal de 95%.” | Explicitamente bloqueado em manifests QW-01 |
| “Fonte X está em produção e cobre o raio.” | Sem run fresco + entity_coverage auditável |
| “O sistema acompanha obras.” | Fora de escopo |
| “Win rate / deságio / preço pago / todos os licitantes.” | Sem semântica e dados (DoD §25) |
| “Story Done ⇒ requisito DoD Done.” | DoD §1 proíbe automaticamente |

### 3.3 Vocabulário obrigatório (DoD §25 — condensado)

| Status | Significado |
|--------|-------------|
| `READY` | Executado e validado |
| `PARTIAL` | Útil com limitações explícitas |
| `NOT_READY` | Não disponível |
| `BLOCKED` | Impedido por dependência externa/técnica |
| `SOURCE_UNAVAILABLE` | Campo/fonte indisponível — **nunca** zero conveniente |

Código existente ≠ capacidade pronta. Dado antigo ≠ dado atual. Presença ≠ cobertura.

---

## 4. Matriz proposta comercial × capacidade (DoD §2.5)

> A prestação humana da consultoria permanece com Tiago. O software deve produzir dados e artefatos **suficientes e auditáveis**. Estado abaixo reflete **aceite DoD** + evidências do rebaseline — não inventário completo de arquivos de código.

Legenda de capacidade:

| Símbolo | Significado |
|---------|-------------|
| **AUSENTE** | Sem aceite e sem evidência operacional suficiente no rebaseline |
| **PARCIAL** | Código/artefato candidato existe; limitações ou sem aceite DoD |
| **PRONTO** | Item DoD aceito com evidência (nenhum entregável §2.5 neste status) |

### 4.1 Configuração do diagnóstico

| Capacidade (§2.5) | Estado | Notas (evidência / gap) |
|-------------------|--------|-------------------------|
| Perfil canônico Extra versionado | **PARCIAL** | Opportunity intel / configs de setor existem; item DoD não aceito |
| Região e universo monitorado | **PARCIAL** | Planilha + seed 2.085 / 1.093 raio documentados; reconciliação 100% não aceita |
| Tipos de obra / faixas / modalidades / restrições / órgãos prioritários / concorrentes | **AUSENTE→PARCIAL** | UNKNOWN granular; sem aceite DoD |
| Relatórios identificam versão do perfil | **AUSENTE** | Não aceito |

### 4.2 Entregável A — ranking dos órgãos públicos

| Capacidade | Estado | Notas |
|------------|--------|-------|
| Ranking de entes do universo compatíveis com perfil | **AUSENTE** | Depende de contratos/editais auditáveis + perfil |
| Qtd. contratações, valor total, ticket, frequência, modalidade | **AUSENTE** | Contratos no rebaseline ≈ 0% / ERROR |
| Fontes e cobertura no ranking | **AUSENTE** | Coverage truth canônica pendente (PE-C2-01) |
| Zero consultado ≠ não consultado | **PARCIAL** | Conceito no DoD e em designs; não aceito em produção auditável |

### 4.3 Entregável B — 15 concorrentes observáveis

| Capacidade | Estado | Notas |
|------------|--------|-------|
| Seleção justificável de ≥15 vencedores | **AUSENTE** | Sem base de contratos no raio |
| CNPJ, qtd. contratos, valor, órgãos, geo, objetos | **AUSENTE** | |
| Deságio só com pares comparáveis | **AUSENTE** | Claim proibido sem dados |
| Declarar insuficiência em vez de completar com ruído | **PARCIAL** | Regra de linguagem; feature não aceita |

### 4.4 Entregável C — contratos vincendos 90–180 dias

| Capacidade | Estado | Notas |
|------------|--------|-------|
| Identificar vigências na janela | **AUSENTE** | Contratos históricos não cobertos |
| Fonte e data de verificação da vigência | **AUSENTE** | |
| Não incluir silenciosamente sem data | **PARCIAL** | Boa prática em código futuro; não aceito |
| Probabilidade de relicitação | **AUSENTE** | Sem modelo validado → só sinais rotulados se houver |

### 4.5 Entregável D — painel de referências de preços

| Capacidade | Estado | Notas |
|------------|--------|-------|
| Referências só para grupos comparáveis | **AUSENTE** | |
| Mediana, P25, P75, tipos de valor (estimado/homologado/contratado/pago) | **AUSENTE** | Proibido chamar de “preço real praticado” |
| `INSUFFICIENT_SAMPLE` | **PARCIAL** | Conceito DoD; não operacional aceito |

### 4.6 Entregável E — editais abertos e recomendação

| Capacidade | Estado | Notas |
|------------|--------|-------|
| Lista de editais abertos na data de corte | **PARCIAL** | Golden path / opportunity_intel / briefing GP-01 são candidatos; cobertura do universo **não** 95%; freshness/cobertura por ente não aceitas |
| Snapshot completo ou reconfirmação individual | **AUSENTE** | |
| GO / REVIEW / NO_GO vs perfil | **PARCIAL** | Ranking existe em opportunity_intel; não é “recomendação cliente final” aceita |
| Tradução PARTICIPAR / NÃO PARTICIPAR | **AUSENTE** | Claim de recomendação definitiva bloqueado em QW-01 |
| Fatores + links oficiais | **PARCIAL** | Gaps de URL oficial históricos em specs Reversa |

### 4.7 Pacote final (PDF + Excel)

| Capacidade | Estado | Notas |
|------------|--------|-------|
| PDF e Excel da mesma run | **PARCIAL** | Commit golden path `32eb442` (fetch→persistência→PDF/Excel); **aceite DoD e reconciliação automática PDF/Excel não feitos** |
| Mesma data de corte / universo / perfil | **AUSENTE** | |
| Detecção de divergência PDF×Excel | **AUSENTE** | |
| Aceite manual de Tiago antes do cliente | **AUSENTE** | Obrigatório DoD |

### 4.8 Síntese da matriz

| Entregável comercial | Capacidade de software (HEAD) | Pode vender como “entregue”? |
|----------------------|-------------------------------|------------------------------|
| A Ranking órgãos | AUSENTE | **Não** |
| B 15 concorrentes | AUSENTE | **Não** |
| C Contratos vincendos | AUSENTE | **Não** |
| D Referências de preços | AUSENTE | **Não** |
| E Editais + recomendação | PARCIAL (triagem técnica candidata) | **Não** como pacote completo |
| Pacote PDF/Excel | PARCIAL (pipeline existe) | **Não** sem aceite + reconciliação |

**Consequência de escopo:** a campanha de 30 dias **não promete** fechar os 95% nem os cinco entregáveis; promete **GATE-0 / GATE-1** e avanço comprovado em C2/K3/Q5 (ver epic plano executivo — “Fora de escopo: EDITAIS_95, CONTRATOS_95, …” nesta wave).

---

## 5. Implicações operacionais

### 5.1 Para stories e epics

| Artefato | Ação |
|----------|------|
| `DOD.md` | Continua checklist de evolução; só `[x]` com evidência |
| `EPIC-COVERAGE-MAX-200KM` | Mantém stories; meta >80% vira **KPI intermediário**, não DoD |
| `EPIC-PLANO-EXECUTIVO-30D` | Já registra subordinção na seção “Meta de cobertura” — **confirmado por este freeze** |
| PE-C2-* | Deve implementar/validar **fórmulas separadas** editais vs contratos |
| PE-K3-* | Contratos como capacidade **independente** do gate de editais |
| README / handoffs / HTML | Alinhar linguagem a este freeze; evitar “meta 80% do projeto” |

### 5.2 Para comunicação e relatórios

1. Sempre declarar **denominador**, **data de corte**, **fórmula**, **fonte**.
2. Sempre reportar **duas** coberturas (editais | contratos), nunca só uma “cobertura geral” como proxy do DoD.
3. Marcos 20% / 50% / 80% são **burn-up de execução**, não “quase DoD”.
4. Blockers externos (DOM-SC credencial, VPS Brasil, API instável) permanecem **visíveis** — não viram `NOT_APPLICABLE` para contornar promessa.

### 5.3 O que este freeze **não** faz

- Não marca nenhum item de cobertura do DoD como aceito.
- Não altera código de crawlers.
- Não autoriza push/`PROJECT_DONE`.
- Não recalcula coverage live (ver rebaseline: live = UNKNOWN se não executado).
- Não cancela o EPIC-COVERAGE-MAX-200KM.

---

## 6. Registro de decisão (resumo executivo)

```text
DECISÃO G0.3 / R-02
Data: 2026-07-16
Branch: epic/plano-executivo-30d @ 1f7aa7c
Autoridade: DOD.md ≥95% editais E ≥95% contratos (separados, raio 200 km)
Legado: EPIC-COVERAGE-MAX-200KM meta >80% = subordinada / intermediária
Resolução R-02: FAVOR DoD
Proposta comercial §2.5: nenhum entregável A–E PRONTO; E e pacote PARCIAL no máximo
Próximo gate campanha: BASELINE_LOCKED (ainda requer G0.4–G0.5 / PE-G0-03)
```

---

*Documento de freeze de escopo PE-G0-02. Alterações futuras de meta exigem revisão formal do DoD.*
