# C2 — Fórmulas canônicas de cobertura (DoD §4.1 × código)

**Story:** PE-C2-01  
**Data:** 2026-07-16  
**Fonte canônica de requisito:** `DOD.md` §1 (meta 95%), §3.2 (denominador raio 200 km), §4.1 (fórmulas)  
**Escopo desta auditoria:** comparação documental + gaps; **sem alteração de código de produção** (risco alto em denominadores/gates).

---

## 1. Fórmulas canônicas (DoD)

### 1.1 Meta mínima (DoD cabeçalho + §4.1)

> Cobertura operacional auditável de **95% para editais** e **95% para contratos**, calculadas **separadamente** sobre os entes do raio de 200 km da planilha canônica.

Regras explícitas:

| Regra | DoD |
|-------|-----|
| Gates separados | `capability_monitoring_coverage(open_tenders) >= 95%` e `…(historical_contracts) >= 95%` |
| Proibido mascarar | média entre as duas coberturas **não** substitui cada gate |
| Fonte saudável ≠ outra capability | fonte de editais não prova contratos e vice-versa |
| Fora do raio | **não** entra no denominador das metas de 95% |
| Presença ≠ cobertura | `data_presence` é descritiva; nunca se chama “cobertura” |
| Zero legítimo | ente sem registros só cobre com `success_zero` válido |
| Freshness no numerador | `stale` e `unknown` **não** contam no numerador |

### 1.2 Fórmulas textuais (DoD §4.1)

```text
universe_resolution =
  entes com identidade válida e decisão de raio
  / total de linhas válidas da planilha
→ meta: 100%

source_applicability_resolution =
  pares ente × fonte × capacidade classificados applicable|not_applicable
  / total de pares que exigem decisão
→ meta: 100%

capability_monitoring_coverage(capability) =
  entes aplicáveis com ao menos uma combinação obrigatória de fontes
  consultada integralmente, fresca e sem blocker
  / entes aplicáveis
→ meta: >= 95% por capability (open_tenders | historical_contracts)

data_presence =
  entes com ao menos um registro encontrado
  / entes aplicáveis
→ métrica descritiva apenas

active_snapshot_integrity =
  registros ativos vistos no último snapshot completo
  ou reconfirmados depois dele
  / registros exibidos como ativos
→ meta: 100%
```

---

## 2. Mapeamento código × fórmula

| Fórmula DoD | Implementação | Path | Gate ≥95%? | Separado editais/contratos? |
|-------------|---------------|------|------------|------------------------------|
| `universe_resolution` | `CanonicalUniverse` / seed planilha; readiness reporta resolved/unresolved | `scripts/lib/universe.py`, `scripts/consulting_readiness.py` | Meta 100% no DoD; readiness **falha** se unresolved > 0 (não é % explícita de universe_resolution) | N/A |
| `source_applicability_resolution` | regras + MV (`source_applicability_rules`, `mv_entity_source_applicability`) | `db/migrations/040_coverage_model_expansion.sql` | **Não** como gate de % no Python de readiness | Parcial (por capability na view) |
| `capability_monitoring_coverage` | **Parcial:** numerador = entes com evidence em `{success_with_data, success_zero}` (qualquer source), **sem** exigir freshness no numerador | `scripts/coverage_truth.py` `compute_metrics`, `scripts/consulting_readiness.py` `compute_readiness` | `consulting_readiness`: default **0.95**; `coverage_truth`: **só reporta** | **Não** no gate principal (métrica agregada “monitoring”) |
| `capability_monitoring_coverage` por capacidade | view SQL `v_coverage_manifest` (capability × source) | `db/migrations/040_coverage_model_expansion.sql` | Não é gate de exit code sozinha | Sim (agrupa por `capability`) |
| `data_presence` | bid_presence / contract_presence / open_tenders counts | `coverage_truth.py`, `consulting_readiness.py` | Não (descritivo) | Sim (métricas separadas) |
| `active_snapshot_integrity` | snapshot tracking / membership | `db/migrations/039_source_snapshot_tracking.sql` (+ código de reconciliação) | Não auditado neste doc como gate 100% | N/A |
| Manifesto por capacidade (contratos) | % entidades com contratos / winners / expiring | `scripts/contract_intel/cli.py` `cmd_manifesto` | `READINESS_THRESHOLD = 0.95` | Capacidades de **contrato**, não editais |

### 2.1 Fórmula efetiva no readiness (código)

```text
# scripts/consulting_readiness.py — compute_readiness
denominator_conservative = |resolved_within_radius| + |unresolved|
numerator                = |entities com evidence state ∈ {success_with_data, success_zero}|
coverage_pct             = numerator / denominator_conservative
passed                   = coverage_pct >= threshold  (default 0.95)
                           AND unresolved == 0
```

Observações:

- Denominador **conservador** inclui unresolved (alinhado a “não esconder incerteza”).
- **Não** exige que a evidência esteja `fresh` para entrar no numerador (divergência DoD §4.3: stale/unknown não contam).
- **Não** calcula dois gates `open_tenders` vs `historical_contracts`; reporta open tenders / contracts como **presença de dados**, não como `capability_monitoring_coverage`.

### 2.2 Fórmula efetiva no Coverage Truth

```text
# scripts/coverage_truth.py — compute_metrics
monitoring_coverage_pct =
  |entities_monitored| / |entities_within_radius|   # se há entity-level evidence
  | None ("unverified") se ledger entity-level vazio
  | 0.0 se n_entities == 0
```

- `entities_monitored` = entes com ≥1 par (entity, source) em `success_with_data|success_zero`.
- Freshness reportada à parte (`COVERAGE_WINDOW_DAYS`, default **90**), **não** desconta o numerador.
- `bid_presence` e `contract_presence` são métricas **separadas** e rotuladas como presença (alinhado em espírito a `data_presence`).

---

## 3. Constantes de limiar (paths)

### 3.1 Operacionais (métrica de negócio)

| Constante | Valor | Path | Alinha DoD 95%? |
|-----------|-------|------|-----------------|
| `DEFAULT_THRESHOLD` | `0.95` | `scripts/consulting_readiness.py:45` | Sim (default gate) |
| `READINESS_THRESHOLD` | `0.95` | `scripts/contract_intel/cli.py:36` | Sim (manifesto capacidades contrato) |
| CLI `--threshold` | default 0.95 | `consulting_readiness.py` argparse | Sim |
| Stretch em relatório backfill | `>= 95%` | `scripts/pipeline/backfill_multi_source.py` (~446) | Cosmético de relatório |

### 3.2 Legado / cosmético / outro domínio (NÃO confundir com meta 95%)

| Constante / uso | Valor | Path | Natureza |
|-----------------|-------|------|----------|
| `[coverage_gate] threshold` | **80** | `.coveragerc:22`, lido por `scripts/coverage_gate.py:82` | **Cobertura de linhas de código** (pytest/coverage.py), **não** cobertura de entes |
| fallback `getint(..., 80)` | 80 | `scripts/coverage_gate.py:82` | Idem |
| Cor HTML município “good” | `m_pct >= 80` | `scripts/coverage/validate_coverage.py:595` | **UI color** no HTML de validação; não gate de produto |
| Filtro JS `pct >= 80` | 80 | mesmo arquivo (~738) | UI |
| `COVERAGE_WINDOW_DAYS` | **90** (env) | `coverage_truth.py:36`, `consulting_readiness.py:46` | Janela de “fresh” via `entity_coverage.last_seen_at` — **≠** SLA DoD 24h/7d |

**Decisão de não alterar código nesta story:**  
Trocar 80→95 em `coverage_gate` / `.coveragerc` quebraria o significado (é line coverage).  
Trocar 80→95 na cor HTML é cosmético e confunde legados.  
Ajustar numerador de monitoring para filtrar freshness ou split por capability é **mudança de semântica de gate** → story dedicada + testes, não “alinhamento pequeno”.

---

## 4. Gaps prioritários (fórmulas)

| ID | Severidade | Gap | Evidência |
|----|------------|-----|-----------|
| C2-F1 | **P0** | Gate principal **não** é `capability_monitoring_coverage` por `open_tenders` e `historical_contracts` separados | `compute_readiness` / `compute_metrics` usam monitoring agregado |
| C2-F2 | **P0** | Numerador de monitoring **não** exclui evidência stale/unknown (DoD §4.3) | success states contam sem checar `freshness_status` / idade do run |
| C2-F3 | **P1** | `coverage_truth` não aplica threshold 95% (só reporta; pode imprimir “unverified”) | ausência de exit code de meta 95% |
| C2-F4 | **P1** | Janela de freshness de report = 90d (`COVERAGE_WINDOW_DAYS`), desalinhada de 24h/7d do DoD | constantes em coverage_truth / consulting_readiness |
| C2-F5 | **P2** | UI/legacy 80% em `validate_coverage` e line-coverage gate 80% podem ser lidos como “meta de cobertura” | paths na §3.2 |
| C2-F6 | **P2** | `source_applicability_resolution = 100%` não é gate Python de readiness | depende de DB/MV e processo |
| C2-F7 | **P2** | `scripts/coverage/calculator.py` ainda usa `entity_coverage.is_covered` (legado) misturando presença/flag, não evidence ledger | calculator.py |

---

## 5. Scripts auditados (resumo de papel)

| Script | Papel | Relação com DoD 95% |
|--------|-------|---------------------|
| `scripts/coverage_truth.py` | Relatório “Coverage Truth” + JSON/MD | Fórmula parcial de monitoring; sem gate 95% |
| `scripts/consulting_readiness.py` | Gate de readiness comercial | Default **95%** em métrica agregada de monitoring |
| `scripts/coverage_gate.py` | Gate de **line coverage** de módulos Python | **Fora** do domínio de cobertura de entes |
| `scripts/coverage/calculator.py` | Report legado via `entity_coverage` | Não é a fórmula canônica DoD |
| `scripts/coverage/validate_coverage.py` | Validação/HTML | Cosmético 80% |
| `scripts/contract_intel/cli.py` | Manifesto de capacidades de contrato | Threshold 95% por capacidade de **contratos** |
| `scripts/freshness_gate.py` | Gate fail-closed de ingestão | Ver `c2-success-zero-freshness.md` |

---

## 6. Conclusão

- **DoD canônico:** 95% **por capability** (editais e contratos), denominador raio 200 km, success_zero + freshness no numerador.
- **Código mais próximo do gate 95%:** `consulting_readiness.py` (`DEFAULT_THRESHOLD = 0.95`) e `contract_intel` manifesto.
- **Principal desalinhamento:** monitoring **agregado** + **sem** filtro de freshness no numerador + **sem** dois gates capability.
- **80 no repositório de “coverage”:** quase sempre **line coverage** ou cor HTML — documentar, **não** “corrigir” para 95% sem redesign.

**Follow-ups sugeridos (fora desta story):**  
story de implementação HIGH-RISK para (1) split open_tenders/historical_contracts no readiness, (2) exclusão stale/unknown do numerador, (3) alinhar janelas de freshness report × SLA.
