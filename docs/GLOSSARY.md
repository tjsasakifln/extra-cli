# Glossário — Extra Consultoria

Definições canônicas compartilhadas por README, PRD, DOD e relatórios.
Atualizado: 2026-07-18 (campanha ADVANCE-30D).

| Termo | Definição |
|-------|-----------|
| **Universo canônico** | Entes da planilha `Extra - alvos de licitação. R-0.xlsx` no raio de 200 km. Denominador fixo **1.093** quando a seed bate. |
| **Cobertura operacional** | Entes com ≥1 fonte oficial passando todos os estágios do pipeline (mapped→recent_evidence) dentro do SLA. **Não** é presença de linhas no banco. |
| **Sinal comercial** | Entes com ≥1 oportunidade OPEN/UPCOMING/RECENT casada. **Não** é cobertura. |
| **Freshness** | Verificação dentro da janela SLA por capability (`config/coverage_slas.yaml`). |
| **Recall** | TP / positivos na amostra-ouro estratificada independente — nunca contagem bruta do DB. |
| **`READY` (métrica)** | Métrica executada e validada sobre inputs atuais; existência de código ≠ READY. |
| **`NOT_READY`** | Métrica indisponível com motivo explícito. |
| **`BLOCKED`** | Impedido por dependência externa/técnica. |
| **GO / REVIEW / NO_GO** | Recomendação comercial determinística; GO rebaixado a REVIEW se perfil Extra incompleto. |
| **Valor estimado / homologado / contratado / pago / global** | Semânticas distintas (`scripts/lib/value_semantics.py`); não confundir com preço praticado. |
| **LOCAL_READY** | Gate DoD §35.1 — só com prova canônica completa. |
| **PRE_VPS_FINAL_READY** | Offline gates + canary live + PG + revisão adversarial. |
| **Single-user CLI** | Ferramenta pessoal de Tiago; sem SaaS multi-tenant nesta fase. |

## Contagens que não devem ser misturadas

| Contagem | Significado |
|----------|-------------|
| **1.093** | Universo raio 200 km (denominador de cobertura) |
| **~2.085** | Referência histórica/estadual SC em docs legados — **não** é o denominador de cobertura operacional |
