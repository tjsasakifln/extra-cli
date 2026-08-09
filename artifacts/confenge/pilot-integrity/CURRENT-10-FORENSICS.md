# CURRENT-10-FORENSICS — CONFENGE pilot integrity

Generated: 2026-08-09T21:10:30Z
Source sample: `warmbly/docs/confenge/COPY-SAMPLE-2026-08-10.md`
Local contracts: `postgresql://…@127.0.0.1:5433/pncp_datalake` (subset)
Universe: `artifacts/confenge/full-run/full-national-20260808T035130Z`

## Summary

| Metric | Value |
|--------|------:|
| Leads | 10 |
| TRUE_TARGET | 2 |
| TARGET_REQUIRES_RESEARCH | 2 |
| FALSE_TARGET | 6 |
| All Warmbly service | REAJUSTE_14133 (10/10) |
| EMAIL_SEND_READY after structural fix | 0 |

## Root causes (proven)

1. **ICP false positives in universe / contact path**
   - `POSSIBLE_ENGINEERING_FIT` + any weak relevant contract admitted firms (PEIXOTO, VISOMES, RODO).
   - Several sample CNPJs were **not in** confenge-universe-v1 (ROSA, MILAN, MS, ISOMEDICAL, TRACADO filial) but still received contacts and EMAIL_SEND_READY labels via contact-enrichment `real-1000` / frozen cohort.
   - `send_readiness._pass_contract_count` **fell back to total portfolio size**, inflating evidence for metrology/commerce suppliers.

2. **REAJUSTE monoculture**
   - Warmbly sample accounts all had `ServiceCode=REAJUSTE_14133` with empty `why_you` / `micro_offer`.
   - Full-national intelligence feed actually exported multi-service codes (`auditoria_orcamento_bdi`, `gestao_monitoramento_contratual`, …) for true constructors — so Warmbly path (or a reajuste campaign feed) **overwrote/defaulted** to REAJUSTE_14133 independent of upstream specialty for this sample.
   - Playbook aliases did not cover all extra-cli `service_id`s; unknown services did not hard-fail before this fix.

3. **Copy degradation**
   - Strategy compose used generic portfolio fact + reajuste hypothesis template.
   - Subjects defaulted to `Contrato <empresa>`.
   - No COPY_CONTEXT_READY gate — empty micro_offer still produced drafts.

## Per-lead lineage

### ROSA IMOVEIS LTDA. (`00172255000131`)

| Field | Value |
|-------|-------|
| Human class | **FALSE_TARGET** |
| Service decision | **SERVICE_WRONG** |
| target_fit_class | `TARGET_OUT_OF_SCOPE` (conf=0.85) |
| sector_fit / activity | `UNKNOWN` / `OTHER` |
| In universe (2026-08-08) | False |
| Execution contracts (triaged) | 0 |
| Local DB contracts | 1 |
| Recomputed primary service | `reforco_temporario_backoffice` |
| Feed export service | `n/a` |
| Warmbly sample service | `REAJUSTE_14133` |
| EMAIL_SEND_READY after fix | `False` |
| Reasons | target_fit:OUT_OF_SCOPE, not_universe_member, target_fit_class:TARGET_OUT_OF_SCOPE, service_code:reforco_temporario_backoffice, copy_context_not_ready, copy_context_incomplete, missing:why_this_account, missing:micro_offer_code |

**Why REAJUSTE_14133:** Warmbly account.ServiceCode=REAJUSTE_14133; empty micro_offer/why_you; generic portfolio template; likely feed/import default or reajuste campaign path, not recomputed primary=reforco_temporario_backoffice

**Contract evidence (sample):**
- Contratação de serviço técnico especializado de elaboração de Laudo Técnico de Avaliação Imobiliária (LTAI- (NBR) ou PTAM (CRECI)) do imóvel referente à Sede, com observância da ABNT NBR 14.653 (Parte | orgão=CONSELHO REG.REPRES.COMERCIAL NO ESTADO MT | R$4000.0

**target_fit reasons:** name_hard_out_without_execution, name_markers:imoveis,moveis
### MILAN MOVEIS INDUSTRIA E COMERCIO LTDA (`00300400000112`)

| Field | Value |
|-------|-------|
| Human class | **FALSE_TARGET** |
| Service decision | **SERVICE_WRONG** |
| target_fit_class | `TARGET_OUT_OF_SCOPE` (conf=0.85) |
| sector_fit / activity | `UNKNOWN` / `OTHER` |
| In universe (2026-08-08) | False |
| Execution contracts (triaged) | 0 |
| Local DB contracts | 1 |
| Recomputed primary service | `reforco_temporario_backoffice` |
| Feed export service | `n/a` |
| Warmbly sample service | `REAJUSTE_14133` |
| EMAIL_SEND_READY after fix | `False` |
| Reasons | target_fit:OUT_OF_SCOPE, not_universe_member, target_fit_class:TARGET_OUT_OF_SCOPE, service_code:reforco_temporario_backoffice, copy_context_not_ready, copy_context_incomplete, missing:why_this_account, missing:micro_offer_code |

**Why REAJUSTE_14133:** Warmbly account.ServiceCode=REAJUSTE_14133; empty micro_offer/why_you; generic portfolio template; likely feed/import default or reajuste campaign path, not recomputed primary=reforco_temporario_backoffice

**Contract evidence (sample):**
- [LICITANET] - AQUISIÇÃO DE CONJUNTOS ESCOLARES DESTINADOS AOS ALUNOS E
PROFESSORES, COMPOSTOS POR MESAS E CADEIRAS, PARA ATENDER A EMTIEF
SEVERINO BATISTA COSTA PERTENCENTE AO MUNICIPIO DE ALTO ALERE  | orgão=MUNICÍPIO DE ALTO ALEGRE DOS PARECIS/RO | R$91832.0

**target_fit reasons:** name_hard_out_without_execution, name_markers:moveis
### MS COMERCIO, SERVICOS E MANUTENCAO DE FROTAS LTDA, (`00328717000167`)

| Field | Value |
|-------|-------|
| Human class | **FALSE_TARGET** |
| Service decision | **SERVICE_WRONG** |
| target_fit_class | `TARGET_OUT_OF_SCOPE` (conf=0.85) |
| sector_fit / activity | `UNKNOWN` / `OTHER` |
| In universe (2026-08-08) | False |
| Execution contracts (triaged) | 0 |
| Local DB contracts | 1 |
| Recomputed primary service | `reforco_temporario_backoffice` |
| Feed export service | `n/a` |
| Warmbly sample service | `REAJUSTE_14133` |
| EMAIL_SEND_READY after fix | `False` |
| Reasons | target_fit:OUT_OF_SCOPE, not_universe_member, target_fit_class:TARGET_OUT_OF_SCOPE, service_code:reforco_temporario_backoffice, copy_context_not_ready, copy_context_incomplete, missing:why_this_account, missing:micro_offer_code |

**Why REAJUSTE_14133:** Warmbly account.ServiceCode=REAJUSTE_14133; empty micro_offer/why_you; generic portfolio template; likely feed/import default or reajuste campaign path, not recomputed primary=reforco_temporario_backoffice

**Contract evidence (sample):**
- AQUISIÇÃO DE PEÇAS E SERVIÇOS PARA REVISÃO PREVENTIVA DE 250 HORAS DO VEÍCULO TRATOR YTO NLX754, CHASSI 32323761- PERTENCENTE A SECRETARIA DE AGRICULTURA E DESENVOLVIMENTO RURAL. | orgão=GERAL | R$800.0

**target_fit reasons:** name_hard_out_without_execution, name_markers:frotas,manutencao de frotas
### PEIXOTO COMERCIO IMPORTACAO EXPORTACAO LTDA. (`00384799000167`)

| Field | Value |
|-------|-------|
| Human class | **FALSE_TARGET** |
| Service decision | **SERVICE_WRONG** |
| target_fit_class | `TARGET_OUT_OF_SCOPE` (conf=0.85) |
| sector_fit / activity | `UNKNOWN` / `OTHER` |
| In universe (2026-08-08) | True |
| Execution contracts (triaged) | 0 |
| Local DB contracts | 1 |
| Recomputed primary service | `diagnostico_contratual_b2g` |
| Feed export service | `n/a` |
| Warmbly sample service | `REAJUSTE_14133` |
| EMAIL_SEND_READY after fix | `False` |
| Reasons | target_fit:OUT_OF_SCOPE, target_fit_class:TARGET_OUT_OF_SCOPE, service_code:diagnostico_contratual_b2g, copy_context_not_ready, copy_context_incomplete, missing:why_this_account, missing:micro_offer_code, missing:evidence_ids |

**Why REAJUSTE_14133:** Warmbly account.ServiceCode=REAJUSTE_14133; empty micro_offer/why_you; generic portfolio template; likely feed/import default or reajuste campaign path, not recomputed primary=diagnostico_contratual_b2g

**Contract evidence (sample):**
- A necessidade emergencial surgiu em virtude dos pneus não constarem em ATA DE REGISTRO DE PREÇOS e de não possuírem estoque nas forças, sendo que a indisponibilidade acarretará prejuízo a atividade fi | orgão=Secretaria de Estado de Justiça e Segurança Pública | R$236880.0

**target_fit reasons:** name_hard_out_without_execution, name_markers:importacao exportacao,comercio importacao
### Traçado Construções e Serviços Ltda. (`00472805000138`)

| Field | Value |
|-------|-------|
| Human class | **TRUE_TARGET** |
| Service decision | **SERVICE_WRONG** |
| target_fit_class | `TARGET_CONFIRMED` (conf=0.8) |
| sector_fit / activity | `POSSIBLE_ENGINEERING_FIT` / `ENGINEERING_SERVICE_PROVIDER` |
| In universe (2026-08-08) | True |
| Execution contracts (triaged) | 7 |
| Local DB contracts | 0 |
| Recomputed primary service | `apoio_licitacoes_propostas` |
| Feed export service | `auditoria_orcamento_bdi` |
| Warmbly sample service | `REAJUSTE_14133` |
| EMAIL_SEND_READY after fix | `False` |
| Reasons | service_code:apoio_licitacoes_propostas, copy_context_not_ready, copy_context_incomplete, missing:why_this_account, missing:observed_fact, missing:micro_offer_code, missing:evidence_ids, missing:cta |

**Why REAJUSTE_14133:** Warmbly account.ServiceCode=REAJUSTE_14133; empty micro_offer/why_you; generic portfolio template; likely feed/import default or reajuste campaign path, not recomputed primary=apoio_licitacoes_propostas

**Contract evidence (sample):**
- Contratação de empresa especializada para execução de obras de pavimentação asfáltica e de passeio com blocos intertratavados, na forma de empreitada global, co | orgão=MUNICÍPIO DE PONTE PRETA - RS | R$276128.31
- Pavimentacao asfaltica nova em CBUQ e sinalizacao Horizontal e Vertical em trecho de estrada municipal  ligacao entre o municipio de Fagundes Varela ate a divis | orgão=PREFEITURA MUNICIPAL DE FAGUNDES VARELA | R$1556993.2
- CONTRATAÇÃO DE EMPRESA ESPECIALIZADA NO FORNECIMENTO DE MATERIAIS E MÃO DE OBRA PARA EXECUÇÃO DE PAVIMENTAÇÃO ASFÁLTICA, CONFORME ESPECIFICAÇÕES DEFINIDAS NO ME | orgão=Prefeitura Municipal de Coxilha | R$767502.41
- CONTRATAÇÃO DE EMPRESA ESPECIALIZADA NO FORNECIMENTO DE MATERIAIS E MÃO DE OBRA PARA EXECUÇÃO DE PAVIMENTAÇÃO ASFÁLTICA, CONFORME ESPECIFICAÇÕES DEFINIDAS NO ME | orgão=Prefeitura Municipal de Coxilha | R$391568.77
- Pavimentação Asfáltica no trecho que interliga o Município de Jacutinga - RS com o Município de Quatro Irmãos  RS, conforme Convênio Administrativo nº AJ/CN/003 | orgão=PM Jacutinga | R$17123125.09

**target_fit reasons:** multi_execution_contracts_triangulation, activity_class_engineering
### TRACADO CONSTRUCOES E SERVICOS LTDA (`00472805000308`)

| Field | Value |
|-------|-------|
| Human class | **TARGET_REQUIRES_RESEARCH** |
| Service decision | **SERVICE_WRONG** |
| target_fit_class | `TARGET_PROBABLE_RESEARCH` (conf=0.45) |
| sector_fit / activity | `POSSIBLE_ENGINEERING_FIT` / `OTHER` |
| In universe (2026-08-08) | False |
| Execution contracts (triaged) | 1 |
| Local DB contracts | 1 |
| Recomputed primary service | `reforco_temporario_backoffice` |
| Feed export service | `n/a` |
| Warmbly sample service | `REAJUSTE_14133` |
| EMAIL_SEND_READY after fix | `False` |
| Reasons | target_fit:OUT_OF_SCOPE, not_universe_member, target_fit_class:TARGET_PROBABLE_RESEARCH, service_code:reforco_temporario_backoffice, copy_context_not_ready, copy_context_incomplete, missing:why_this_account, missing:micro_offer_code |

**Why REAJUSTE_14133:** Warmbly account.ServiceCode=REAJUSTE_14133; empty micro_offer/why_you; generic portfolio template; likely feed/import default or reajuste campaign path, not recomputed primary=reforco_temporario_backoffice

**Contract evidence (sample):**
- Contratação do fornecimento de emulsão asfáltica para a realização de manutenção e conservação da ruas e avenidas do Município, conforme ETP, TR, justificativa, orçamento e documentação, de acordo com | orgão=SECRETARIA MUNICIPAL DE OBRAS | R$25200.0

**target_fit reasons:** possible_or_single_execution_needs_research
### JATOBETON ENGENHARIA LTDA (`00507949000182`)

| Field | Value |
|-------|-------|
| Human class | **TRUE_TARGET** |
| Service decision | **SERVICE_WRONG** |
| target_fit_class | `TARGET_CONFIRMED` (conf=0.8) |
| sector_fit / activity | `POSSIBLE_ENGINEERING_FIT` / `ENGINEERING_SERVICE_PROVIDER` |
| In universe (2026-08-08) | True |
| Execution contracts (triaged) | 7 |
| Local DB contracts | 0 |
| Recomputed primary service | `auditoria_orcamento_bdi` |
| Feed export service | `auditoria_orcamento_bdi` |
| Warmbly sample service | `REAJUSTE_14133` |
| EMAIL_SEND_READY after fix | `False` |
| Reasons | service_code:auditoria_orcamento_bdi, copy_context_not_ready, copy_context_incomplete, missing:why_this_account, missing:observed_fact, missing:micro_offer_code, missing:evidence_ids, missing:cta |

**Why REAJUSTE_14133:** Warmbly account.ServiceCode=REAJUSTE_14133; empty micro_offer/why_you; generic portfolio template; likely feed/import default or reajuste campaign path, not recomputed primary=auditoria_orcamento_bdi

**Contract evidence (sample):**
- CONTRATAÇÃO DE EMPRESA PARA ELABORAÇÃO DOS ESTUDOS, PROJETOS BÁSICO E EXECUTIVO DE ENGENHARIA, EXECUÇÃO DAS OBRAS DE REABILITAÇÃO DE 01 (UMA) OBRA DE ARTE ESPEC | orgão=DEPARTAMENTO NACIONAL INFRAEST.DE TRANSPORTES | R$9527127.48
- O OBJETO DO PRESENTE INSTRUMENTO É A CONTRATAÇÃO DE EMPRESA PARA ELABORAÇÃO DOS ESTUDOS, PROJETOS BÁSICO E EXECUTIVO DE ENGENHARIA E EXECUÇÃO DAS OBRAS DE REABI | orgão=SUP. REG. DO DNIT NO ESTADO DA PARAIBA | R$6944929.01
- Contratação Semi-Integrada de empresa de engenharia para execução dos serviços necessários para elaboração do projeto executivo de engenharia e Execução de obra | orgão=SECRETARIA DE ESTADO DE INFRA-ESTRUTURA | R$14750781.02
- CONTRATAÇÃO DE EMPRESA PARA ELABORAÇÃO DOS ESTUDOS, PROJETOS BÁSICO E EXECUTIVO DE ENGENHARIA, EXECUÇÃO DAS OBRAS DE REABILITAÇÃO DE 03 (TRÊS) OBRAS DE ARTE ESP | orgão=DEPARTAMENTO NACIONAL INFRAEST.DE TRANSPORTES | R$9147685.47
- CONTRATAÇÃO DE EMPRESA PARA ELABORAÇÃO DOS ESTUDOS, PROJETOS BÁSICO E EXECUTIVO DE ENGENHARIA, EXECUÇÃO DAS OBRAS DE REABILITAÇÃO DE 01 (UMA) OBRA DE ARTE ESPEC | orgão=DEPARTAMENTO NACIONAL INFRAEST.DE TRANSPORTES | R$8468000.0

**target_fit reasons:** multi_execution_contracts_triangulation, activity_class_engineering
### VISOMES COMERCIAL METROLOGICA LTDA (`00567892000107`)

| Field | Value |
|-------|-------|
| Human class | **FALSE_TARGET** |
| Service decision | **SERVICE_WRONG** |
| target_fit_class | `TARGET_OUT_OF_SCOPE` (conf=0.85) |
| sector_fit / activity | `UNKNOWN` / `OTHER` |
| In universe (2026-08-08) | True |
| Execution contracts (triaged) | 0 |
| Local DB contracts | 1 |
| Recomputed primary service | `medicoes_glosas_memoria` |
| Feed export service | `n/a` |
| Warmbly sample service | `REAJUSTE_14133` |
| EMAIL_SEND_READY after fix | `False` |
| Reasons | target_fit:OUT_OF_SCOPE, target_fit_class:TARGET_OUT_OF_SCOPE, service_code:medicoes_glosas_memoria, copy_context_not_ready, copy_context_incomplete, missing:why_this_account, missing:micro_offer_code, missing:evidence_ids |

**Why REAJUSTE_14133:** Warmbly account.ServiceCode=REAJUSTE_14133; empty micro_offer/why_you; generic portfolio template; likely feed/import default or reajuste campaign path, not recomputed primary=medicoes_glosas_memoria

**Contract evidence (sample):**
- CONTRATAÇÃO DE SERVIÇO DE CALIBRAÇÃO RBC DE 2 (DUAS) LEITORAS DE ELISA, MARCAS TECAN E BIOCHROM, PERTENCENTES AO LABORATÓRIO DIA/LDDV, BEM COMO DE 1 (UM) TERMOCICLADOR CONVENCIONAL PROFLEX, PERTENCENT | orgão=LABORATÓRIO FEDERAL DE DEFESA AGROPECUÁRIA | R$3779.2

**target_fit reasons:** name_hard_out_without_execution, name_markers:metrologica
### RODO SERVICE LTDA (`00688075000450`)

| Field | Value |
|-------|-------|
| Human class | **TARGET_REQUIRES_RESEARCH** |
| Service decision | **SERVICE_WRONG** |
| target_fit_class | `TARGET_PROBABLE_RESEARCH` (conf=0.4) |
| sector_fit / activity | `UNKNOWN` / `OTHER` |
| In universe (2026-08-08) | False |
| Execution contracts (triaged) | 0 |
| Local DB contracts | 1 |
| Recomputed primary service | `reforco_temporario_backoffice` |
| Feed export service | `n/a` |
| Warmbly sample service | `REAJUSTE_14133` |
| EMAIL_SEND_READY after fix | `False` |
| Reasons | target_fit:OUT_OF_SCOPE, not_universe_member, target_fit_class:TARGET_PROBABLE_RESEARCH, service_code:reforco_temporario_backoffice, copy_context_not_ready, copy_context_incomplete, missing:why_this_account, missing:micro_offer_code |

**Why REAJUSTE_14133:** Warmbly account.ServiceCode=REAJUSTE_14133; empty micro_offer/why_you; generic portfolio template; likely feed/import default or reajuste campaign path, not recomputed primary=reforco_temporario_backoffice

**Contract evidence (sample):**
- Aquisição de dois Ônibus e um veiculo. | orgão=PREFEITURA MUNICIPAL DE MANDAGUAÇU - PR | R$1640000.0

**target_fit reasons:** default_research
### ISOMEDICAL COMERCIAL LTDA (`00757668000188`)

| Field | Value |
|-------|-------|
| Human class | **FALSE_TARGET** |
| Service decision | **SERVICE_WRONG** |
| target_fit_class | `TARGET_OUT_OF_SCOPE` (conf=0.85) |
| sector_fit / activity | `UNKNOWN` / `OTHER` |
| In universe (2026-08-08) | False |
| Execution contracts (triaged) | 0 |
| Local DB contracts | 1 |
| Recomputed primary service | `reforco_temporario_backoffice` |
| Feed export service | `n/a` |
| Warmbly sample service | `REAJUSTE_14133` |
| EMAIL_SEND_READY after fix | `False` |
| Reasons | target_fit:OUT_OF_SCOPE, not_universe_member, target_fit_class:TARGET_OUT_OF_SCOPE, service_code:reforco_temporario_backoffice, copy_context_not_ready, copy_context_incomplete, missing:why_this_account, missing:micro_offer_code |

**Why REAJUSTE_14133:** Warmbly account.ServiceCode=REAJUSTE_14133; empty micro_offer/why_you; generic portfolio template; likely feed/import default or reajuste campaign path, not recomputed primary=reforco_temporario_backoffice

**Contract evidence (sample):**
- AQUISIÇÃO DE CONJUNTO CATETER BALÃO, CATETER DIAGNÓSTICO, HASTE PARA HIGIENE ORAL E OUTROS | orgão=ESP-INSTITUTO DANTE PAZZANESE DE CARDIOLOGIA | R$38500.0

**target_fit reasons:** name_hard_out_without_execution, name_markers:isomedical,medical


## Classification policy applied

- **TRUE_TARGET**: TARGET_CONFIRMED with material execution contracts (pavimentação, engenharia de obras, etc.).
- **TARGET_REQUIRES_RESEARCH**: possible adjacency / insufficient triangulation.
- **FALSE_TARGET**: name+contracts show commerce/fleet/medical/real-estate/metrology without construction execution.

Name alone was never used as sole disqualifier when execution evidence existed.
