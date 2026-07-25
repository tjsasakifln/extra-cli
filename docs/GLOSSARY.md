# Glossário — Extra Consultoria

Definições canônicas compartilhadas por README, PRD, DOD e relatórios.  
**Atualizado:** 2026-07-25

| Termo | Definição |
|-------|-----------|
| **Universo canônico** | Entes da planilha `Extra - alvos de licitação. R-0.xlsx` no raio de 200 km. Denominador fixo **1.093** quando a seed bate. |
| **Cobertura operacional** | Entes com evidência válida por **capability**, estágios do pipeline, SLA e proveniência. **Não** é presença de linhas no banco. |
| **Capability** | Dimensão de cobertura medida separadamente (ex.: `open_tenders`, `historical_contracts`). ADR-028 / ADR-030. |
| **Dual coverage** | Spine de medição por capability com set equality ao universo canônico + regras fail-closed (ADR-030). |
| **Sinal comercial** | Entes com ≥1 oportunidade OPEN/UPCOMING/RECENT casada. **Não** é cobertura. |
| **Freshness** | Verificação dentro da janela SLA por capability/fonte (`config/coverage_slas.yaml`). |
| **Recall** | TP / positivos na amostra-ouro estratificada independente — nunca contagem bruta do DB. |
| **Entity source registry** | Registro canônico de fontes por ente (ADR-019); existência de registro ≠ fonte operacional. |
| **Workspace CLI** | Facade diária `python3 -m scripts.workspace` (ADR-017). |
| **Weekly cycle** | Ciclo semanal canônico `make extra-weekly` / `scripts.ops.weekly_cycle --strict`. |
| **Golden path** | Pipeline de validação técnica fail-closed (`scripts.golden_path`). |
| **`READY` (métrica)** | Métrica executada e validada sobre inputs atuais; existência de código ≠ READY. |
| **`NOT_READY`** | Métrica ou gate indisponível com motivo explícito. |
| **`BLOCKED`** | Impedido por dependência externa/técnica/calendário (ex.: soak 7d). |
| **`ACCEPTED` (DOD)** | Item do DOD com evidência + integração main + CI conforme harness — só então `[x]`. |
| **Soak** | Observação contínua por N dias (ex.: 7) sem fabricar dias no tracker. |
| **Host de record** | VPS operacional de referência (Netcup / `ec-prod`); host ≠ gate `VPS_OPERATIONAL`. |
| **GO / REVIEW / NO_GO** | Recomendação comercial determinística; GO rebaixado a REVIEW se perfil Extra incompleto. |
| **Valor estimado / homologado / contratado / pago / global** | Semânticas distintas (`scripts/lib/value_semantics.py`); não confundir. |
| **LOCAL_READY** | Gate DoD — só com prova canônica completa. |
| **PRE_VPS_FINAL_READY** | Fase histórica de gates offline+canary pré-host; não confundir com estado atual do Netcup. |
| **VPS_OPERATIONAL** | Gate DoD pós-VPS — exige evidências agregadas (backup, soak, etc.), não só “há SSH”. |
| **PROJECT_DONE** | Projeto integralmente concluído (róis DOD). |
| **force-next** | Ranking obrigatório da campanha ROI: `squads/extra-dod-roi/scripts/cli.py force-next`. |
| **Single-user CLI** | Ferramenta pessoal de Tiago; sem SaaS multi-tenant nesta fase. |

## Contagens que não devem ser misturadas

| Contagem | Significado |
|----------|-------------|
| **1.093** | Universo raio 200 km (denominador de cobertura) |
| **~2.085** | Referência histórica/estadual SC em docs legados — **não** é o denominador de cobertura operacional |
| **~4,4M** | Ordem de grandeza de linhas de contratos históricos na VPS (campanha HC) — não é “cobertura %” |
| **95%** | Meta por capability (editais e contratos **separados**), só com medição dual/auditável |
