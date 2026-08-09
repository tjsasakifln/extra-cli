# CURRENT-10-FORENSICS — CONFENGE pilot integrity

Generated: 2026-08-09T21:50:10Z
Source: `warmbly/docs/confenge/COPY-SAMPLE-2026-08-10.md`
Local contracts: `postgresql://…@127.0.0.1:5433/pncp_datalake` (subset)
Universe: `artifacts/confenge/full-run/full-national-20260808T035130Z`

## Summary

| Metric | Value |
|--------|------:|
| Leads | 10 |
| TRUE_TARGET | 2 |
| TARGET_REQUIRES_RESEARCH | 2 |
| FALSE_TARGET | 6 |
| Warmbly service monoculture | REAJUSTE_14133 (10/10) |
| EMAIL_SEND_READY after structural fix | 0 |

## Root causes (proven)

1. **ICP false positives** — POSSIBLE_ENGINEERING_FIT + weak relevant contracts admitted non-execution suppliers; several sample CNPJs absent from universe but contact-enriched via frozen cohort.
2. **pass_contract_count fallback** to total portfolio size inflated evidence.
3. **REAJUSTE monoculture** — Warmbly accounts held ServiceCode=REAJUSTE_14133 with empty why_you/micro_offer.
4. **Copy degradation** — no COPY_CONTEXT_READY; template portfolio→reajuste→recorte.

## Per-lead lineage

### ROSA IMOVEIS LTDA. (`00172255000131`)

| Field | Value |
|-------|-------|
| Human class | **FALSE_TARGET** |
| Service decision | **SERVICE_WRONG** |
| target_fit | `TARGET_OUT_OF_SCOPE` conf=0.85 |
| sector / activity | `UNKNOWN` / `OTHER` |
| In universe | False |
| Exec contracts | 0 |
| Recomputed primary | `diagnostico_contratual_b2g` |
| Warmbly sample | `REAJUSTE_14133` |
| EMAIL_SEND_READY after fix | `False` |

**Why REAJUSTE_14133:** Warmbly sample ServiceCode=REAJUSTE_14133 with empty why_you/micro_offer; recomputed primary=diagnostico_contratual_b2g; root causes: (1) possible-fit ICP, (2) pass_count total fallback, (3) Warmbly/account layer REAJUSTE default or reajuste-campaign feed, (4) missing COPY_CONTEXT_READY gate.

**Contracts:**
- Contratação de serviço técnico especializado de elaboração de Laudo Técnico de Avaliação Imobiliária (LTAI- (NBR) ou PTAM (CRECI)) do imóvel referente à Sede, com observância da ABNT NBR 14.653 (Parte | orgão=CONSELHO REG.REPRES.COMERCIAL NO ESTADO MT | R$4000.0

**target_fit reasons:** name_hard_out_without_execution;name_markers:imoveis,moveis
### MILAN MOVEIS INDUSTRIA E COMERCIO LTDA (`00300400000112`)

| Field | Value |
|-------|-------|
| Human class | **FALSE_TARGET** |
| Service decision | **SERVICE_WRONG** |
| target_fit | `TARGET_OUT_OF_SCOPE` conf=0.85 |
| sector / activity | `UNKNOWN` / `OTHER` |
| In universe | False |
| Exec contracts | 0 |
| Recomputed primary | `diagnostico_contratual_b2g` |
| Warmbly sample | `REAJUSTE_14133` |
| EMAIL_SEND_READY after fix | `False` |

**Why REAJUSTE_14133:** Warmbly sample ServiceCode=REAJUSTE_14133 with empty why_you/micro_offer; recomputed primary=diagnostico_contratual_b2g; root causes: (1) possible-fit ICP, (2) pass_count total fallback, (3) Warmbly/account layer REAJUSTE default or reajuste-campaign feed, (4) missing COPY_CONTEXT_READY gate.

**Contracts:**
- [LICITANET] - AQUISIÇÃO DE CONJUNTOS ESCOLARES DESTINADOS AOS ALUNOS E
PROFESSORES, COMPOSTOS POR MESAS E CADEIRAS, PARA ATENDER A EMTIEF
SEVERINO BATISTA COSTA PERTENCENTE AO MUNICIPIO DE ALTO ALERE  | orgão=MUNICÍPIO DE ALTO ALEGRE DOS PARECIS/RO | R$91832.0

**target_fit reasons:** name_hard_out_without_execution;name_markers:moveis
### MS COMERCIO, SERVICOS E MANUTENCAO DE FROTAS LTDA, (`00328717000167`)

| Field | Value |
|-------|-------|
| Human class | **FALSE_TARGET** |
| Service decision | **SERVICE_WRONG** |
| target_fit | `TARGET_OUT_OF_SCOPE` conf=0.85 |
| sector / activity | `UNKNOWN` / `OTHER` |
| In universe | False |
| Exec contracts | 0 |
| Recomputed primary | `diagnostico_contratual_b2g` |
| Warmbly sample | `REAJUSTE_14133` |
| EMAIL_SEND_READY after fix | `False` |

**Why REAJUSTE_14133:** Warmbly sample ServiceCode=REAJUSTE_14133 with empty why_you/micro_offer; recomputed primary=diagnostico_contratual_b2g; root causes: (1) possible-fit ICP, (2) pass_count total fallback, (3) Warmbly/account layer REAJUSTE default or reajuste-campaign feed, (4) missing COPY_CONTEXT_READY gate.

**Contracts:**
- AQUISIÇÃO DE PEÇAS E SERVIÇOS PARA REVISÃO PREVENTIVA DE 250 HORAS DO VEÍCULO TRATOR YTO NLX754, CHASSI 32323761- PERTENCENTE A SECRETARIA DE AGRICULTURA E DESENVOLVIMENTO RURAL. | orgão=GERAL | R$800.0

**target_fit reasons:** name_hard_out_without_execution;name_markers:frotas,manutencao de frotas
### PEIXOTO COMERCIO IMPORTACAO EXPORTACAO LTDA. (`00384799000167`)

| Field | Value |
|-------|-------|
| Human class | **FALSE_TARGET** |
| Service decision | **SERVICE_WRONG** |
| target_fit | `TARGET_OUT_OF_SCOPE` conf=0.85 |
| sector / activity | `UNKNOWN` / `OTHER` |
| In universe | True |
| Exec contracts | 0 |
| Recomputed primary | `diagnostico_contratual_b2g` |
| Warmbly sample | `REAJUSTE_14133` |
| EMAIL_SEND_READY after fix | `False` |

**Why REAJUSTE_14133:** Warmbly sample ServiceCode=REAJUSTE_14133 with empty why_you/micro_offer; recomputed primary=diagnostico_contratual_b2g; root causes: (1) possible-fit ICP, (2) pass_count total fallback, (3) Warmbly/account layer REAJUSTE default or reajuste-campaign feed, (4) missing COPY_CONTEXT_READY gate.

**Contracts:**
- A necessidade emergencial surgiu em virtude dos pneus não constarem em ATA DE REGISTRO DE PREÇOS e de não possuírem estoque nas forças, sendo que a indisponibilidade acarretará prejuízo a atividade fi | orgão=Secretaria de Estado de Justiça e Segurança Pública | R$236880.0

**target_fit reasons:** name_hard_out_without_execution;name_markers:importacao exportacao,comercio importacao
### Traçado Construções e Serviços Ltda. (`00472805000138`)

| Field | Value |
|-------|-------|
| Human class | **TRUE_TARGET** |
| Service decision | **SERVICE_WRONG** |
| target_fit | `TARGET_CONFIRMED` conf=0.8 |
| sector / activity | `POSSIBLE_ENGINEERING_FIT` / `ENGINEERING_SERVICE_PROVIDER` |
| In universe | True |
| Exec contracts | 7 |
| Recomputed primary | `apoio_licitacoes_propostas` |
| Warmbly sample | `REAJUSTE_14133` |
| EMAIL_SEND_READY after fix | `False` |

**Why REAJUSTE_14133:** Warmbly sample ServiceCode=REAJUSTE_14133 with empty why_you/micro_offer; recomputed primary=apoio_licitacoes_propostas; root causes: (1) possible-fit ICP, (2) pass_count total fallback, (3) Warmbly/account layer REAJUSTE default or reajuste-campaign feed, (4) missing COPY_CONTEXT_READY gate.

**Contracts:**
- Contratação de empresa especializada para execução de obras de pavimentação asfáltica e de passeio com blocos intertratavados, na forma de e | orgão=MUNICÍPIO DE PONTE PRETA - RS | R$276128.31
- Pavimentacao asfaltica nova em CBUQ e sinalizacao Horizontal e Vertical em trecho de estrada municipal  ligacao entre o municipio de Fagunde | orgão=PREFEITURA MUNICIPAL DE FAGUNDES VARELA | R$1556993.2
- CONTRATAÇÃO DE EMPRESA ESPECIALIZADA NO FORNECIMENTO DE MATERIAIS E MÃO DE OBRA PARA EXECUÇÃO DE PAVIMENTAÇÃO ASFÁLTICA, CONFORME ESPECIFICA | orgão=Prefeitura Municipal de Coxilha | R$767502.41
- CONTRATAÇÃO DE EMPRESA ESPECIALIZADA NO FORNECIMENTO DE MATERIAIS E MÃO DE OBRA PARA EXECUÇÃO DE PAVIMENTAÇÃO ASFÁLTICA, CONFORME ESPECIFICA | orgão=Prefeitura Municipal de Coxilha | R$391568.77
- Pavimentação Asfáltica no trecho que interliga o Município de Jacutinga - RS com o Município de Quatro Irmãos  RS, conforme Convênio Adminis | orgão=PM Jacutinga | R$17123125.09

**target_fit reasons:** multi_execution_contracts_triangulation;activity_class_engineering
### Material contracts (from universe portfolio.recent_contracts)

| contrato_id | órgão | UF | valor | objeto (trunc) |
|---|---|---|---:|---|
| 25556619 | MUNICÍPIO DE PONTE PRETA - RS | RS | 276128.31 | Contratação de empresa especializada para execução de obras de pavimentação asfáltica e de passeio c |
| 24417906 | PREFEITURA MUNICIPAL DE FAGUNDES VARELA | RS | 1556993.2 | Pavimentacao asfaltica nova em CBUQ e sinalizacao Horizontal e Vertical em trecho de estrada municip |
| 12484966 | Prefeitura Municipal de Coxilha | RS | 767502.41 | CONTRATAÇÃO DE EMPRESA ESPECIALIZADA NO FORNECIMENTO DE MATERIAIS E MÃO DE OBRA PARA EXECUÇÃO DE PAV |
| 12485054 | Prefeitura Municipal de Coxilha | RS | 391568.77 | CONTRATAÇÃO DE EMPRESA ESPECIALIZADA NO FORNECIMENTO DE MATERIAIS E MÃO DE OBRA PARA EXECUÇÃO DE PAV |
| 5976331 | PM Jacutinga | RS | 17123125.09 | Pavimentação Asfáltica no trecho que interliga o Município de Jacutinga - RS com o Município de Quat |
| 5029550 | Prefeitura Municipal de Quatro Irmãos | RS | 259372.0 | Contratação de Empresa para Execução de Pavimentação Asfáltica na Rua Leão Kwitko (Plano de Ação 090 |
| 15465381 | MUNICIPIO DE IMIGRANTE | RS | 3782835.94 | Constitui objeto da presente licitação a contratação de empresa para a reconstrução da ciclovia loca |

**Triangulation:** name construções + ENGINEERING_SERVICE_PROVIDER + multiple pavimentação asfáltica / CBUQ execution contracts (Ponte Preta, Fagundes Varela, Coxilha, Jacutinga) → TRUE_TARGET confirmed with material objects.

### TRACADO CONSTRUCOES E SERVICOS LTDA (`00472805000308`)

| Field | Value |
|-------|-------|
| Human class | **TARGET_REQUIRES_RESEARCH** |
| Service decision | **SERVICE_WRONG** |
| target_fit | `TARGET_PROBABLE_RESEARCH` conf=0.45 |
| sector / activity | `POSSIBLE_ENGINEERING_FIT` / `OTHER` |
| In universe | False |
| Exec contracts | 1 |
| Recomputed primary | `diagnostico_contratual_b2g` |
| Warmbly sample | `REAJUSTE_14133` |
| EMAIL_SEND_READY after fix | `False` |

**Why REAJUSTE_14133:** Warmbly sample ServiceCode=REAJUSTE_14133 with empty why_you/micro_offer; recomputed primary=diagnostico_contratual_b2g; root causes: (1) possible-fit ICP, (2) pass_count total fallback, (3) Warmbly/account layer REAJUSTE default or reajuste-campaign feed, (4) missing COPY_CONTEXT_READY gate.

**Contracts:**
- Contratação do fornecimento de emulsão asfáltica para a realização de manutenção e conservação da ruas e avenidas do Município, conforme ETP, TR, justificativa, orçamento e documentação, de acordo com | orgão=SECRETARIA MUNICIPAL DE OBRAS | R$25200.0

**target_fit reasons:** possible_or_single_execution_needs_research
### JATOBETON ENGENHARIA LTDA (`00507949000182`)

| Field | Value |
|-------|-------|
| Human class | **TRUE_TARGET** |
| Service decision | **SERVICE_WRONG** |
| target_fit | `TARGET_CONFIRMED` conf=0.82 |
| sector / activity | `STRONG_ENGINEERING_FIT` / `ENGINEERING_SERVICE_PROVIDER` |
| In universe | True |
| Exec contracts | 7 |
| Recomputed primary | `gestao_monitoramento_contratual` (post-spine router) |
| Warmbly sample | `REAJUSTE_14133` |
| EMAIL_SEND_READY after fix | `False` |

**Why REAJUSTE_14133:** Warmbly sample ServiceCode=REAJUSTE_14133 with empty why_you/micro_offer; recomputed primary=gestao_monitoramento_contratual; root causes: (1) possible-fit ICP, (2) pass_count total fallback, (3) Warmbly/account layer REAJUSTE default or reajuste-campaign feed, (4) missing COPY_CONTEXT_READY gate.

**Contracts:**
- CONTRATAÇÃO DE EMPRESA PARA ELABORAÇÃO DOS ESTUDOS, PROJETOS BÁSICO E EXECUTIVO DE ENGENHARIA, EXECUÇÃO DAS OBRAS DE REABILITAÇÃO DE 01 (UMA | orgão=DEPARTAMENTO NACIONAL INFRAEST.DE TRANSPORTES | R$9527127.48
- O OBJETO DO PRESENTE INSTRUMENTO É A CONTRATAÇÃO DE EMPRESA PARA ELABORAÇÃO DOS ESTUDOS, PROJETOS BÁSICO E EXECUTIVO DE ENGENHARIA E EXECUÇÃ | orgão=SUP. REG. DO DNIT NO ESTADO DA PARAIBA | R$6944929.01
- Contratação Semi-Integrada de empresa de engenharia para execução dos serviços necessários para elaboração do projeto executivo de engenhari | orgão=SECRETARIA DE ESTADO DE INFRA-ESTRUTURA | R$14750781.02
- CONTRATAÇÃO DE EMPRESA PARA ELABORAÇÃO DOS ESTUDOS, PROJETOS BÁSICO E EXECUTIVO DE ENGENHARIA, EXECUÇÃO DAS OBRAS DE REABILITAÇÃO DE 03 (TRÊ | orgão=DEPARTAMENTO NACIONAL INFRAEST.DE TRANSPORTES | R$9147685.47
- CONTRATAÇÃO DE EMPRESA PARA ELABORAÇÃO DOS ESTUDOS, PROJETOS BÁSICO E EXECUTIVO DE ENGENHARIA, EXECUÇÃO DAS OBRAS DE REABILITAÇÃO DE 01 (UMA | orgão=DEPARTAMENTO NACIONAL INFRAEST.DE TRANSPORTES | R$8468000.0

**target_fit reasons:** sector_strong_plus_execution_contract
### Material contracts (from universe portfolio.recent_contracts)

| contrato_id | órgão | UF | valor | objeto (trunc) |
|---|---|---|---:|---|
| 547830 | DEPARTAMENTO NACIONAL INFRAEST.DE TRANSPORTES | DF | 9527127.48 | CONTRATAÇÃO DE EMPRESA PARA ELABORAÇÃO DOS ESTUDOS, PROJETOS BÁSICO E EXECUTIVO DE ENGENHARIA, EXECU |
| 350973 | SUP. REG. DO DNIT NO ESTADO DA PARAIBA | PB | 6944929.01 | O OBJETO DO PRESENTE INSTRUMENTO É A CONTRATAÇÃO DE EMPRESA PARA ELABORAÇÃO DOS ESTUDOS, PROJETOS BÁ |
| 325896 | SECRETARIA DE ESTADO DE INFRA-ESTRUTURA | MT | 14750781.02 | Contratação Semi-Integrada de empresa de engenharia para execução dos serviços necessários para elab |
| 8271522 | DEPARTAMENTO NACIONAL INFRAEST.DE TRANSPORTES | DF | 9147685.47 | CONTRATAÇÃO DE EMPRESA PARA ELABORAÇÃO DOS ESTUDOS, PROJETOS BÁSICO E EXECUTIVO DE ENGENHARIA, EXECU |
| 751293 | DEPARTAMENTO NACIONAL INFRAEST.DE TRANSPORTES | DF | 8468000.0 | CONTRATAÇÃO DE EMPRESA PARA ELABORAÇÃO DOS ESTUDOS, PROJETOS BÁSICO E EXECUTIVO DE ENGENHARIA, EXECU |
| 2533498 | EMLURB - AUTARQUIA DE MANUTENÇÃO E LIMPEZA URBANA | PE | 17200000.0 | CONTRATAÇÃO DE EMPRESA ESPECIALIZADA DE ENGENHARIA PARA EXECUÇÃO DE SERVIÇOS DE
RECUPERAÇÃO ESTRUTU |
| 2495375 | EMLURB - AUTARQUIA DE MANUTENÇÃO E LIMPEZA URBANA | PE | 14350000.0 | A CONTRATAÇÃO DE EMPRESA ESPECIALIZADA DE ENGENHARIA PARA EXECUÇÃO DE SERVIÇOS ESPECIAIS DE RECUPERA |

**Triangulation:** ENGINEERING + STRONG_ENGINEERING_FIT + DNIT/EMLURB/infra execution objects → TRUE_TARGET. Service after MessageSpine router: gestão (not invented BDI).

### VISOMES COMERCIAL METROLOGICA LTDA (`00567892000107`)

| Field | Value |
|-------|-------|
| Human class | **FALSE_TARGET** |
| Service decision | **SERVICE_WRONG** |
| target_fit | `TARGET_OUT_OF_SCOPE` conf=0.85 |
| sector / activity | `UNKNOWN` / `OTHER` |
| In universe | True |
| Exec contracts | 0 |
| Recomputed primary | `medicoes_glosas_memoria` |
| Warmbly sample | `REAJUSTE_14133` |
| EMAIL_SEND_READY after fix | `False` |

**Why REAJUSTE_14133:** Warmbly sample ServiceCode=REAJUSTE_14133 with empty why_you/micro_offer; recomputed primary=medicoes_glosas_memoria; root causes: (1) possible-fit ICP, (2) pass_count total fallback, (3) Warmbly/account layer REAJUSTE default or reajuste-campaign feed, (4) missing COPY_CONTEXT_READY gate.

**Contracts:**
- CONTRATAÇÃO DE SERVIÇO DE CALIBRAÇÃO RBC DE 2 (DUAS) LEITORAS DE ELISA, MARCAS TECAN E BIOCHROM, PERTENCENTES AO LABORATÓRIO DIA/LDDV, BEM COMO DE 1 (UM) TERMOCICLADOR CONVENCIONAL PROFLEX, PERTENCENT | orgão=LABORATÓRIO FEDERAL DE DEFESA AGROPECUÁRIA | R$3779.2

**target_fit reasons:** name_hard_out_without_execution;name_markers:metrologica
### RODO SERVICE LTDA (`00688075000450`)

| Field | Value |
|-------|-------|
| Human class | **TARGET_REQUIRES_RESEARCH** |
| Service decision | **SERVICE_WRONG** |
| target_fit | `TARGET_PROBABLE_RESEARCH` conf=0.4 |
| sector / activity | `UNKNOWN` / `OTHER` |
| In universe | False |
| Exec contracts | 0 |
| Recomputed primary | `diagnostico_contratual_b2g` |
| Warmbly sample | `REAJUSTE_14133` |
| EMAIL_SEND_READY after fix | `False` |

**Why REAJUSTE_14133:** Warmbly sample ServiceCode=REAJUSTE_14133 with empty why_you/micro_offer; recomputed primary=diagnostico_contratual_b2g; root causes: (1) possible-fit ICP, (2) pass_count total fallback, (3) Warmbly/account layer REAJUSTE default or reajuste-campaign feed, (4) missing COPY_CONTEXT_READY gate.

**Contracts:**
- Aquisição de dois Ônibus e um veiculo. | orgão=PREFEITURA MUNICIPAL DE MANDAGUAÇU - PR | R$1640000.0

**target_fit reasons:** default_research
### ISOMEDICAL COMERCIAL LTDA (`00757668000188`)

| Field | Value |
|-------|-------|
| Human class | **FALSE_TARGET** |
| Service decision | **SERVICE_WRONG** |
| target_fit | `TARGET_OUT_OF_SCOPE` conf=0.85 |
| sector / activity | `UNKNOWN` / `OTHER` |
| In universe | False |
| Exec contracts | 0 |
| Recomputed primary | `diagnostico_contratual_b2g` |
| Warmbly sample | `REAJUSTE_14133` |
| EMAIL_SEND_READY after fix | `False` |

**Why REAJUSTE_14133:** Warmbly sample ServiceCode=REAJUSTE_14133 with empty why_you/micro_offer; recomputed primary=diagnostico_contratual_b2g; root causes: (1) possible-fit ICP, (2) pass_count total fallback, (3) Warmbly/account layer REAJUSTE default or reajuste-campaign feed, (4) missing COPY_CONTEXT_READY gate.

**Contracts:**
- AQUISIÇÃO DE CONJUNTO CATETER BALÃO, CATETER DIAGNÓSTICO, HASTE PARA HIGIENE ORAL E OUTROS | orgão=ESP-INSTITUTO DANTE PAZZANESE DE CARDIOLOGIA | R$38500.0

**target_fit reasons:** name_hard_out_without_execution;name_markers:isomedical,medical


### Material contracts (from universe portfolio.recent_contracts)

| contrato_id | órgão | UF | valor | objeto (trunc) |
|---|---|---|---:|---|
| 547830 | DEPARTAMENTO NACIONAL INFRAEST.DE TRANSPORTES | DF | 9527127.48 | CONTRATAÇÃO DE EMPRESA PARA ELABORAÇÃO DOS ESTUDOS, PROJETOS BÁSICO E EXECUTIVO DE ENGENHARIA, EXECU |
| 350973 | SUP. REG. DO DNIT NO ESTADO DA PARAIBA | PB | 6944929.01 | O OBJETO DO PRESENTE INSTRUMENTO É A CONTRATAÇÃO DE EMPRESA PARA ELABORAÇÃO DOS ESTUDOS, PROJETOS BÁ |
| 325896 | SECRETARIA DE ESTADO DE INFRA-ESTRUTURA | MT | 14750781.02 | Contratação Semi-Integrada de empresa de engenharia para execução dos serviços necessários para elab |
| 8271522 | DEPARTAMENTO NACIONAL INFRAEST.DE TRANSPORTES | DF | 9147685.47 | CONTRATAÇÃO DE EMPRESA PARA ELABORAÇÃO DOS ESTUDOS, PROJETOS BÁSICO E EXECUTIVO DE ENGENHARIA, EXECU |
| 751293 | DEPARTAMENTO NACIONAL INFRAEST.DE TRANSPORTES | DF | 8468000.0 | CONTRATAÇÃO DE EMPRESA PARA ELABORAÇÃO DOS ESTUDOS, PROJETOS BÁSICO E EXECUTIVO DE ENGENHARIA, EXECU |
| 2533498 | EMLURB - AUTARQUIA DE MANUTENÇÃO E LIMPEZA URBANA | PE | 17200000.0 | CONTRATAÇÃO DE EMPRESA ESPECIALIZADA DE ENGENHARIA PARA EXECUÇÃO DE SERVIÇOS DE
RECUPERAÇÃO ESTRUTU |
| 2495375 | EMLURB - AUTARQUIA DE MANUTENÇÃO E LIMPEZA URBANA | PE | 14350000.0 | A CONTRATAÇÃO DE EMPRESA ESPECIALIZADA DE ENGENHARIA PARA EXECUÇÃO DE SERVIÇOS ESPECIAIS DE RECUPERA |

**Triangulation:** name ENGINEERING + STRONG_ENGINEERING_FIT + multiple DNIT/EMLURB/infra execution objects (reabilitação de OAE/pontes, obras semi-integradas) → TRUE_TARGET confirmed.
**Service after MessageSpine router:** structure-only multi-contract → `gestao_monitoramento_contratual` (not invented PLANILHAS/BDI without budget signals); Warmbly sample was SERVICE_WRONG (REAJUSTE_14133 monoculture).

## Classification policy

- **TRUE_TARGET**: TARGET_CONFIRMED with material execution contracts.
- **TARGET_REQUIRES_RESEARCH**: possible adjacency / insufficient triangulation.
- **FALSE_TARGET**: commerce/fleet/medical/real-estate/metrology without construction execution.
