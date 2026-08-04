# Human desk review — top 30 leads (campanha 2026-08-04)

**Tipo:** revisão humana de sessão (não gerada por template de código).
**Escopo:** leitura de `objeto_contrato` + URL PNCP + valores/ranking do run.
**Não é** parecer jurídico nem prova de elegibilidade de reajuste.

- Revisados: **30**
- Falsos positivos de objeto: **3**
- Reclassificar (NOT_ELIGIBLE): **3**
- Mantidos na fila (com lacunas/ressalvas): **27**
- Keep rate (não-FP reclass): **0.9**

Companheiro máquina: `automated_object_triage.json` (não confundir com esta revisão).

## #1 `04892707000100-2-000047/2024` — **MANTER_NA_FILA_COM_LACUNAS**

- Empresa: CASTILHO ENGENHARIA E EMPREENDIMENTOS S/A (CNPJ `92779503****`) · UF=PR · score=18.87
- Órgão: SUP. REG. DO DNIT NO ESTADO DE SERGIPE
- Valor PNCP: R$ 1,215,600,074.34
- Classificação pipeline: `LEGAL_REGIME_UNKNOWN` · data_base_status=`PROXY_PROSPECTION_ONLY`
- FP: **False** · incerteza: **alta**
- Documento consultado: https://pncp.gov.br/app/contratos/04892707000100/2024/47
- Objeto (trecho): EXECUÇÃO DOS SERVIÇOS NECESSÁRIOS DE MANUTENÇÃO RODOVIÁRIA (CONSERVAÇÃO/RECUPERAÇÃO) NA BR-235/SE, TRECHO: LARGO LEITE NETO (ARACAJU)-DIV.SE/BA. SUB TRECHO: LARGO LEITE NETO (ARACAJU)-ENTR.BR-101(A);ENTR.BR-101(B)-DIV. SE/BA. SEGMENTO: KM-0,0 AO KM-6,2; KM-8,3 AO KM114,8. EXTENSÃ
- Notas:
  - Manutenção/recuperação BR-235/SE sob DNIT (empreitada material) — objeto de engenharia rodoviária por escopo, não mera locação.
  - UF do fornecedor no lead=PR enquanto o trecho é SE: normal em contratos DNIT nacionais; não invalida o objeto.
  - Valor > R$ 1,2 bi parece atípico para um único lote — validar se PNCP consolidou aditivos/valores anuais antes de qualquer estimativa financeira.
  - Sem data-base de orçamento nem índice no snapshot: prospecção apenas. Próximo doc: edital PATO + contrato + planilha orçamentária.

## #2 `82951344000140-2-000038/2024` — **PRIORIZAR_SUL_SC**

- Empresa: GAIA RODOVIAS LTDA. (CNPJ `03257777****`) · UF=SC · score=18.64
- Órgão: Secretaria de Estado da Infraestrutura e Mobilidade
- Valor PNCP: R$ 71,525,912.91
- Classificação pipeline: `LEGAL_REGIME_UNKNOWN` · data_base_status=`PROXY_PROSPECTION_ONLY`
- FP: **False** · incerteza: **alta**
- Documento consultado: https://pncp.gov.br/app/contratos/82951344000140/2024/38
- Objeto (trecho): EXECUÇÃO DOS SERVIÇOS DE MANUTENÇÃO (CONSERVAÇÃO/RECUPERAÇÃO) DE RODOVIAS PAVIMENTADAS E ESTRADAS NÃO PAVIMENTADAS SOB A JURISDIÇÃO DA COORDENADORIA REGIONAL EXTREMO OESTE – SIE/CREXT - LOTE 01.
- Notas:
  - SIE/SC — manutenção de rodovias/estradas Lote 01 Extremo Oeste: encaixa no ICP regional CONFENGE.
  - Vigência até 2026-10-10 (~67 dias restantes na as-of 2026-08-04): urgência comercial real para abrir diálogo antes do encerramento.
  - Interregno proxy desde 2024-04-08 já superou 12 meses, mas data-base legal do orçamento continua MISSING/PROXY.
  - Sem telefone/e-mail no enrich — abordagem via site/órgão ou busca cadastral adicional.

## #3 `95423000000100-2-000001/2022` — **REBAIXAR_PRIORIDADE_PPP**

- Empresa: SAUDE PINHAIS SPE LTDA (CNPJ `48430801****`) · UF=PR · score=18.18
- Órgão: Fundo Municipal de Saúde
- Valor PNCP: R$ 1,204,059,732.33
- Classificação pipeline: `LEGAL_REGIME_UNKNOWN` · data_base_status=`PROXY_PROSPECTION_ONLY`
- FP: **False** · incerteza: **muito_alta**
- Reclassificar para: `RESEARCH_REQUIRED`
- Documento consultado: https://pncp.gov.br/app/contratos/95423000000100/2022/1
- Objeto (trecho): CONCORRÊNCIA PÚBLICA PARA CELEBRAÇÃO DE CONTRATO DE PARCERIA PÚBLICO-PRIVADA, NA MODALIDADE CONCESSÃO ADMINISTRATIVA, DESTINADA À CONSTRUÇÃO, EQUIPAGEM E OPERACIONALIZAÇÃO DE SERVIÇOS "BATA CINZA" NO NOVO HOSPITAL MUNICIPAL DE PINHAIS/PR.
- Notas:
  - PPP/concessão administrativa hospitalar (construção + equipagem + operacionalização 'bata cinza') até 2058 — não é contrato típico de reajuste de empreitada com construtora PME.
  - SPE Saude Pinhais: contraparte comercial é SPE de concessão, não construtora civil clássica; fit CONFENGE para 'pleito de reajuste de obra' é fraco.
  - Pode haver reajuste no componente de obras da concessão, mas a oferta e o interlocutor mudam (estruturação de PPP).
  - Decisão: manter no radar só se CONFENGE quiser vertical PPP; senão excluir da fila de reajuste ordinário de construção.

## #4 `82951344000140-2-000036/2024` — **PRIORIZAR_SUL_SC**

- Empresa: CEGE ENGENHARIA LTDA (CNPJ `04484014****`) · UF=PR · score=17.99
- Órgão: Secretaria de Estado da Infraestrutura e Mobilidade
- Valor PNCP: R$ 60,605,734.80
- Classificação pipeline: `LEGAL_REGIME_UNKNOWN` · data_base_status=`PROXY_PROSPECTION_ONLY`
- FP: **False** · incerteza: **alta**
- Documento consultado: https://pncp.gov.br/app/contratos/82951344000140/2024/36
- Objeto (trecho): Execução dos serviços de Manutenção (Conservação/Recuperação) de Rodovias Pavimentadas e Estradas  Não  Pavimentadas  sob  a  jurisdição  da  Coordenadoria  Regional  Extremo  Oeste –SIE –CREXT (Lote  03)
- Notas:
  - Mesmo programa SIE/SC Extremo Oeste, Lote 03 — CEGE Engenharia; irmão do lead #2 (GAIA, Lote 01).
  - Útil para abordagem em cacho: mesma secretaria, mesma natureza de objeto, lotes distintos.
  - Vigência até 2026-10-23 — janela curta; pedir contrato e planilha orçamentária em paralelo ao #2.
  - UF no registro=PR (sede) vs execução SC — priorizar contato com base na sede e obra em SC.

## #5 `04892707000100-2-000324/2023` — **PRIORIZAR_SUL_SC**

- Empresa: SETEP CONSTRUCOES S.A (CNPJ `83665141****`) · UF=SC · score=17.98
- Órgão: SUP. REG. DO DNIT NO ESTADO DE SANTA CATARINA
- Valor PNCP: R$ 59,699,324.43
- Classificação pipeline: `LEGAL_REGIME_UNKNOWN` · data_base_status=`PROXY_PROSPECTION_ONLY`
- FP: **False** · incerteza: **alta**
- Documento consultado: https://pncp.gov.br/app/contratos/04892707000100/2023/324
- Objeto (trecho): TERMO DE CONTRATO, SOB O REGIME DE EMPREITADA POR PREÇO UNITÁRIO, QUE FAZEM ENTRE SI O DEPARTAMENTO NACIONAL DE INFRAESTRUTURA DE TRANSPORTES E A EMPRESA SETEP CONSTRUÇÕES S.A. S.A., PARA EXECUÇÃO DOS SERVIÇOS NECESSÁRIOS DE MANUTENÇÃO RODOVIÁRIA (CONSERVAÇÃO/RECUPERAÇÃO) NA RODO
- Notas:
  - SETEP em contrato DNIT/SC BR-282 e BR-470 — empreitada por preço unitário, texto de termo de contrato no objeto.
  - Assinatura proxy 2023-08-25: interregno bem maduro (~709 dias); um dos melhores candidatos SC se a cláusula de reajuste existir.
  - Empresa de construção com nome forte no Sul — ICP alto se porte for PME/médio e não captive de grandes consultorias internas.
  - Documento prioritário: termo de contrato integral (já mencionado no objeto) + apostilas + medições DNIT.

## #6 `04892707000100-2-000045/2024` — **MANTER_COM_ALERTA_VALOR**

- Empresa: HWN ENGENHARIA LTDA (CNPJ `19256565****`) · UF=MG · score=17.89
- Órgão: SUP. REG. DO DNIT NO ESTADO DO MARANHÃO
- Valor PNCP: R$ 2,161,038,594.95
- Classificação pipeline: `LEGAL_REGIME_UNKNOWN` · data_base_status=`PROXY_PROSPECTION_ONLY`
- FP: **False** · incerteza: **alta**
- Documento consultado: https://pncp.gov.br/app/contratos/04892707000100/2024/45
- Objeto (trecho): CONTRATAÇÃO DE EMPRESA ESPECIALIZADA PARA EXECUÇÃO DOS SERVIÇOS NECESSÁRIOS DE MANUTENÇÃO RODOVIÁRIA (CONSERVAÇÃO/RECUPERAÇÃO) NA RODOVIA: BR - 226/MA, TRECHO: (DIV. PI/MA) - DIV. MA/TO, SUBTRECHO: ENTR. BR-135 (B) PRESIDENTE DUTRA - BARRA DO CORDA, SEGMENTO: KM 204,10 - KM 299,8
- Notas:
  - Manutenção BR-226/MA sob DNIT — objeto de engenharia rodoviária legítimo.
  - Valor ~R$ 2,16 bi no campo valor_total exige auditoria de dado (possível agregação/erro de escala no PNCP) antes de qualquer pitch de ticket.
  - Fornecedor HWN com telefone empresarial no enrich — canal utilizável se o valor for confirmado como materialmente relevante.
  - Não usar valor PNCP como 'base reajustável' sem medições.

## #7 `04892707000100-2-000005/2024` — **MANTER_NA_FILA_COM_LACUNAS**

- Empresa: L PEREIRA & CIA LTDA (CNPJ `12316402****`) · UF=AL · score=17.89
- Órgão: SUP. REG. DO DNIT NO ESTADO DE ALAGOAS
- Valor PNCP: R$ 1,170,269,773.63
- Classificação pipeline: `LEGAL_REGIME_UNKNOWN` · data_base_status=`PROXY_PROSPECTION_ONLY`
- FP: **False** · incerteza: **alta**
- Documento consultado: https://pncp.gov.br/app/contratos/04892707000100/2024/5
- Objeto (trecho): EXECUÇÃO DOS SERVIÇOS NECESSÁRIOS DE MANUTENÇÃO RODOVIÁRIA (CONSERVAÇÃO/RECUPERAÇÃO) NA RODOVIA BR-101/AL, SEGMENTO: KM 130,30 - KM 248,4,  SOBRE JURISDIÇÃO DA SUPERINTENDÊNCIA REGIONAL DO DNIT NO ESTADO DE ALAGOAS, NO ÂMBITO DO PLANO ANUAL DE TRABALHO E ORÇAMENTO - PATO, CONFORM
- Notas:
  - BR-101/AL, manutenção rodoviária PATO — padrão DNIT recorrente no funil.
  - L Pereira & Cia com telefone no enrich; ticket alto (~R$ 1,17 bi) também pede validação de escala.
  - Objeto não cita Lei 14.133 — regime UNKNOWN permanece.
  - Ação: baixar edital PATO/AL e contrato no portal DNIT/PNCP antes de cold call.

## #8 `04892707000100-2-000339/2024` — **MANTER_COM_ALERTA_VALOR**

- Empresa: LCM CONSTRUCAO E COMERCIO S.A (CNPJ `19758842****`) · UF=MG · score=17.76
- Órgão: SUP. REG. DO DNIT NOS ESTADOS DE GOIAS E DF
- Valor PNCP: R$ 7,071,134,588.42
- Classificação pipeline: `LEGAL_REGIME_UNKNOWN` · data_base_status=`PROXY_PROSPECTION_ONLY`
- FP: **False** · incerteza: **alta**
- Documento consultado: https://pncp.gov.br/app/contratos/04892707000100/2024/339
- Objeto (trecho): CONTRATAÇÃO DE EMPRESA ESPECIALIZADA PARA EXECUÇÃO DOS SERVIÇOS NECESSÁRIOS DE RECUPERAÇÃO E MANUTENÇÃO/CONSERVAÇÃO RODOVIÁRIA NA RODOVIA BR-158/GO, SEGMENTO KM 89,90 AO KM 153,90, SOBRE JURISDIÇÃO DA SUPERINTENDÊNCIA REGIONAL DO DNIT NO ESTADO DE GOIÁS E DISTRITO FEDERAL - SRE-G
- Notas:
  - LCM — recuperação/manutenção rodoviária DNIT GO/DF; empresa aparece várias vezes no top (portfólio DNIT).
  - Valor ~R$ 7,07 bi é extremo: tratar como suspeito de qualidade de dado até prova em contrário.
  - Telefone empresarial presente; preferir abordagem de 'diagnóstico multi-contratos DNIT' em vez de um único super-ticket.
  - Portfólio grande pode reduzir propensão a contratar consultoria externa — aplicar penalidade comercial de 'gigante/volume'.

## #9 `02221962000104-2-000001/2024` — **MANTER_NA_FILA_COM_LACUNAS**

- Empresa: CONSORCIO JAMPA (CNPJ `56608645****`) · UF=PB · score=17.73
- Órgão: SEC DE ESTADO DA INFRAESTRUTURA E DOS RECURSOS HÍDRICOS
- Valor PNCP: R$ 465,500,000.00
- Classificação pipeline: `LEGAL_REGIME_UNKNOWN` · data_base_status=`PROXY_PROSPECTION_ONLY`
- FP: **False** · incerteza: **alta**
- Documento consultado: https://pncp.gov.br/app/contratos/02221962000104/2024/1
- Objeto (trecho): ELABORAÇÃO DO PROJETO BÁSICO E EXECUTIVO E EXECUÇÃO DAS OBRAS DE IMPLANTAÇÃO E PAVIMENTAÇÃO DO COMPLEXO RODOVIÁRIO DE LIGAÇÃO DA BEDELO/SANTA RITA / LUCENA DE LIGAÇÃO (PONTE DO FUTURO)
- Notas:
  - Consórcio Jampa — projeto básico/executivo + implantação/pavimentação do complexo rodoviário de ligação (PB).
  - Objeto misto projeto+execução: ainda é obra material, mas a fatia de reajuste depende do que foi efetivamente executado e medido.
  - Consórcio: identificar empresa líder e contato comercial da SPE/consórcio (não só CNPJ do consórcio).
  - Valor ~R$ 465 mi materialmente interessante se regime 14.133 e índice constarem do edital.

## #10 `04892707000100-2-000346/2024` — **MANTER_NA_FILA_COM_LACUNAS**

- Empresa: LCM CONSTRUCAO E COMERCIO S.A (CNPJ `19758842****`) · UF=MG · score=17.68
- Órgão: DEPART.NACIONAL DE INFRA-ESTR. DE TRANSPORTE
- Valor PNCP: R$ 967,983,261.00
- Classificação pipeline: `LEGAL_REGIME_UNKNOWN` · data_base_status=`PROXY_PROSPECTION_ONLY`
- FP: **False** · incerteza: **alta**
- Documento consultado: https://pncp.gov.br/app/contratos/04892707000100/2024/346
- Objeto (trecho): EXECUÇÃO DOS SERVIÇOS NECESSÁRIOS DE MANUTENÇÃO RODOVIÁRIA (CONSERVAÇÃO/RECUPERAÇÃO) NA RODOVIA BR267/MS; TRECHO: DIVISA SP/MS – FRONTEIRA BRASIL/PARAGUAI; SUBTRECHO: INÍCIO PISTA DUPLA (GUIA LOPES DA LAGUNA) – INÍCIO PONTE S/ RIO PERDIDO; SEGMENTO: KM 473,00 - KM 577,80;  SNV (V
- Notas:
  - Segundo contrato LCM no top — BR-267/MS manutenção; reforça padrão portfólio DNIT da mesma empresa.
  - Não duplicar outreach: consolidar leads LCM em um único dossiê de fornecedor com N contratos.
  - Valor ~R$ 968 mi ainda alto; cruzar com extrato PNCP/contratos.gov se disponível.
  - Mesmas lacunas de data-base/índice/regime.

## #11 `82951344000140-2-000037/2024` — **PRIORIZAR_SUL_SC**

- Empresa: GAIA RODOVIAS LTDA. (CNPJ `03257777****`) · UF=SC · score=17.66
- Órgão: Secretaria de Estado da Infraestrutura e Mobilidade
- Valor PNCP: R$ 88,771,692.69
- Classificação pipeline: `LEGAL_REGIME_UNKNOWN` · data_base_status=`PROXY_PROSPECTION_ONLY`
- FP: **False** · incerteza: **alta**
- Documento consultado: https://pncp.gov.br/app/contratos/82951344000140/2024/37
- Objeto (trecho): EXECUÇÃO DOS SERVIÇOS DE MANUTENÇÃO (CONSERVAÇÃO/RECUPERAÇÃO) DE RODOVIAS PAVIMENTADAS E ESTRADAS NÃO PAVIMENTADAS SOB A JURISDIÇÃO DA COORDENADORIA REGIONAL EXTREMO OESTE – SIE/CREXT - LOTE 02.
- Notas:
  - GAIA novamente — Lote 02 SIE/SC, mesma assinatura 2024-04-08 e vigência curta 2026-10-10.
  - Junto com #2 forma pacote de dois lotes GAIA na mesma secretaria — abordagem única com dois instrumentos.
  - Ticket ~R$ 88,8 mi (este) + ~R$ 71,5 mi (#2) justifica pitch de diagnóstico de carteira SC.
  - Urgência de vigência é o principal gatilho comercial, não o valor teórico de reajuste (ainda desconhecido).

## #12 `22934889000117-2-000004/2024` — **RECLASSIFICAR**

- Empresa: EDUCA NOVA LIMA SPE S/A (CNPJ `54116810****`) · UF=MG · score=17.57
- Órgão: Secretaria Municipal de Administracao
- Valor PNCP: R$ 1,243,322,202.89
- Classificação pipeline: `LEGAL_REGIME_UNKNOWN` · data_base_status=`PROXY_PROSPECTION_ONLY`
- FP: **True** · incerteza: **media**
- Reclassificar para: `NOT_ELIGIBLE`
- Documento consultado: https://pncp.gov.br/app/contratos/22934889000117/2024/4
- Objeto (trecho): CONCESSAO ADMINISTRATIVA, DA PRESTACAO DE SERVICOS DE APOIO, NAO PEDAGOGICOS DE OPERACAO, MANUTENCAO, AMPLIACAO, REFORMA E EXECUCAO DAS OBRAS DE IMPLANTACAO DAS UNIDADES DE ENSINO DA REDE MUNICIPAL DE EDUCACAO, COMPREENDENDO CRECHES, ESCOLAS INFANTIS, DE ENSINO FUNDAMENTAL I E II
- Notas:
  - EDUCA NOVA LIMA SPE — concessão administrativa de serviços de apoio NÃO pedagógicos (operação, manutenção, ampliação, reforma de escolas).
  - Embora cite ampliação/reforma, o núcleo é PPP de operação escolar de longo prazo (até 2054), não empreitada de construção civil isolada.
  - Fora do ICP CONFENGE para reajuste de obra de engenharia em sentido estrito nesta campanha.
  - FP de classificador por tokens de reforma/ampliação em contexto de concessão de serviços.

## #13 `00394429000100-2-002232/2023` — **RECLASSIFICAR**

- Empresa: PRATT & WHITNEY CANADA DO BRASIL LTDA (CNPJ `02278560****`) · UF=MG · score=17.57
- Órgão: CENTRO LOGISTICO DA AERONAUTICA
- Valor PNCP: R$ 550,770,213.46
- Classificação pipeline: `LEGAL_REGIME_UNKNOWN` · data_base_status=`PROXY_PROSPECTION_ONLY`
- FP: **True** · incerteza: **baixa**
- Reclassificar para: `NOT_ELIGIBLE`
- Documento consultado: https://pncp.gov.br/app/contratos/00394429000100/2023/2232
- Objeto (trecho): CONTRATAÇÃO DE SERVIÇOS DE SUPORTE LOGÍSTICO PARA 06 MOTORES DA FABRICANTE PRATT & WHITNEY CANADA (P&WC), MODELO PW206B2, SENDO 04 INSTALADOS E 02 DE RESERVA, QUE EQUIPAM A FROTA DE DUAS AERONAVES VH-35 DA FORÇA AÉREA BRASILEIRA, A SEREM PAGOS SOB DEMANDA, POR EXECUÇÃO INDIRETA, 
- Notas:
  - PRATT & WHITNEY — suporte logístico a motores de aeronaves (PW206B2): zero relação com construção civil.
  - Falso positivo grave: classificador capturou 'engenharia' implícita ou termos fracos sem obra material.
  - Excluir imediatamente da fila comercial e usar como caso de regressão no classificador (aeronáutica/logística).
  - Não contatar.

## #14 `35854176000195-2-000010/2024` — **MANTER_NA_FILA_COM_LACUNAS**

- Empresa: CONSTRUTORA MERCURE LTDA (CNPJ `07649419****`) · UF=AM · score=17.57
- Órgão: UNIVERSIDADE FEDERAL DE RONDONOPOLIS
- Valor PNCP: R$ 362,310,717.79
- Classificação pipeline: `LEGAL_REGIME_UNKNOWN` · data_base_status=`PROXY_PROSPECTION_ONLY`
- FP: **False** · incerteza: **alta**
- Documento consultado: https://pncp.gov.br/app/contratos/35854176000195/2024/10
- Objeto (trecho): CONTRATAÇÃO DA EXECUÇÃO DAS OBRAS PARA A CONSTRUÇÃO DO PRÉDIO ADMINISTRATIVO DA UNIVERSIDADE FEDERAL DE RONDONÓPOLIS, NAS CONDIÇÕES ESTABELECIDAS NO TERMO DE REFERÊNCIA.
- Notas:
  - Construtora Mercure — construção do prédio administrativo da UFR em Rondonópolis: obra de edificação clássica.
  - Bom exemplo de objeto limpo de edificação (diferente dos lotes DNIT de manutenção).
  - Ticket ~R$ 362 mi; se PME, fit CONFENGE melhor que LCM/gigantes de volume DNIT.
  - Pedir contrato/edital da universidade e planilha orçamentária (SINAPI costuma aparecer em obras federais — mas só se constar no instrumento).

## #15 `04892707000100-2-000408/2024` — **MANTER_COM_ALERTA_VALOR**

- Empresa: TOP ENGENHARIA LTDA (CNPJ `14448260****`) · UF=BA · score=17.39
- Órgão: SUP. REGIONAL DO DNIT NO ESTADO DA BAHIA
- Valor PNCP: R$ 2,339,846,945.33
- Classificação pipeline: `LEGAL_REGIME_UNKNOWN` · data_base_status=`PROXY_PROSPECTION_ONLY`
- FP: **False** · incerteza: **alta**
- Documento consultado: https://pncp.gov.br/app/contratos/04892707000100/2024/408
- Objeto (trecho): O OBJETO DO PRESENTE INSTRUMENTO É A EXECUÇÃO DOS SERVIÇOS NECESSÁRIOS DE MANUTENÇÃO RODOVIÁRIA (CONSERVAÇÃO/RECUPERAÇÃO) NA RODOVIA BR-116/BA;  TRECHO: DIV. PE/BA (INÍCIO PONTE SOBRE O RIO SÃO FRANCISCO) - DIV. BA/MG; SUBTRECHO: ENTR. BR-410(TUCANO) -ENTR. BR-324(B)/BA-502/BA-50
- Notas:
  - TOP Engenharia — manutenção rodoviária DNIT/BA; valor ~R$ 2,34 bi no PNCP (validar escala).
  - Objeto standard DNIT; pouca diferenciação comercial além do ticket e da maturidade temporal.
  - Sem contatos no enrich — priorizar BrasilAPI/OpenCNPJ offline se for entrar no top de outreach.
  - Mesmas lacunas documentais de regime/data-base/índice.

## #16 `04892707000100-2-000336/2024` — **MANTER_NA_FILA_COM_LACUNAS**

- Empresa: CBC CONSTRUTORA BRASIL CENTRAL LTDA (CNPJ `02164137****`) · UF=TO · score=17.35
- Órgão: SUP. REG. DO DNIT NOS ESTADOS DE GOIAS E DF
- Valor PNCP: R$ 355,016,104.00
- Classificação pipeline: `LEGAL_REGIME_UNKNOWN` · data_base_status=`PROXY_PROSPECTION_ONLY`
- FP: **False** · incerteza: **alta**
- Documento consultado: https://pncp.gov.br/app/contratos/04892707000100/2024/336
- Objeto (trecho): EXECUÇÃO DOS SERVIÇOS DE CONSERVAÇÃO E MANUTENÇÃO DA RODOVIA FEDERAL BR-158/GO, COM VISTAS A EXECUÇÃO DE PLANO DE TRABALHO E ORÇAMENTO – P.A.T.O., NO TRECHO: DIV MT/GO – DIV GO/MS, SUBTRECHO: ENTR BR-070(A) (DIV MT/GO) (ARAGARÇAS) - ENTR GO-060(A)/188(A) (PIRANHAS), SEGMENTO: KM 
- Notas:
  - CBC Construtora Brasil Central — conservação/manutenção BR-158/GO sob DNIT.
  - Nome e objeto alinhados a construtora de infraestrutura; ticket ~R$ 355 mi mais crível que super-bilhões do funil.
  - Sede TO no lead — regional Centro-Norte; secundário vs Sul/SC mas válido no ranking nacional.
  - Ação: confirmar se empresa tem gestão contratual própria ou usa consultorias; sem depreciação pública.

## #17 `04892707000100-2-000423/2024` — **MANTER_NA_FILA_COM_LACUNAS**

- Empresa: HWN ENGENHARIA LTDA (CNPJ `19256565****`) · UF=MG · score=17.13
- Órgão: SUP. REG. DO DNIT NO ESTADO DO PIAUI
- Valor PNCP: R$ 1,552,438,576.67
- Classificação pipeline: `LEGAL_REGIME_UNKNOWN` · data_base_status=`PROXY_PROSPECTION_ONLY`
- FP: **False** · incerteza: **alta**
- Documento consultado: https://pncp.gov.br/app/contratos/04892707000100/2024/423
- Objeto (trecho): SERVIÇOS DE ENGENHARIA PARA MANUTENÇÃO (CONSERVAÇÃO / RECUPERAÇÃO) NA RODOVIA BR-135/PI, CONFORME CONDIÇÕES, QUANTIDADES, EXIGÊNCIAS E ESPECIFICAÇÕES DISCRIMINADAS NOS PROJETOS E ESTABELECIDAS NO EDITAL, SEUS ANEXOS E NA PROPOSTA DA CONTRATADA.
- Notas:
  - Segundo contrato HWN no top — BR-135/PI manutenção; consolidar com #6 em dossiê único do fornecedor.
  - Valor ~R$ 1,55 bi também pede checagem de escala PNCP.
  - Não multiplica contatos: um único relacionamento comercial HWN cobre ambos os instrumentos.
  - Lacunas iguais (regime/data-base/índice).

## #18 `04892707000100-2-000169/2024` — **MANTER_NA_FILA_COM_LACUNAS**

- Empresa: ARTELESTE CONSTRUCOES LTDA (CNPJ `75911438****`) · UF=PR · score=17.01
- Órgão: SUP. REG. DO DNIT NO EST.DO RIO GRANDE DO SUL
- Valor PNCP: R$ 41,300,000.00
- Classificação pipeline: `LEGAL_REGIME_UNKNOWN` · data_base_status=`PROXY_PROSPECTION_ONLY`
- FP: **False** · incerteza: **alta**
- Documento consultado: https://pncp.gov.br/app/contratos/04892707000100/2024/169
- Objeto (trecho): ELABORAÇÃO DOS ESTUDOS, PROJETOS BÁSICO E EXECUTIVO DE ENGENHARIA E EXECUÇÃO DA OBRA DE REABILITAÇÃO DE 04 (QUATRO) OBRAS DE ARTE ESPECIAIS, LOCALIZADAS NAS RODOVIAS BR-158/RS E BR-293/RS, NO ÂMBITO DO PROGRAMA DE MANUTENÇÃO E REABILITAÇÃO DE ESTRUTURAS - PROARTE.
- Notas:
  - ARTELESTE — estudos/projetos + execução de reabilitação de 4 obras (DNIT); misto projeto+obra.
  - Ticket ~R$ 41,3 mi mais próximo de ticket consultável CONFENGE do que bilionários DNIT.
  - Confirmar se a execução material já iniciou e se medições existem; reajuste só alcança parcelas executadas conforme cláusula.
  - UF PR no lead com obra possivelmente multi-UF — verificar trechos no contrato.

## #19 `04892707000100-2-000359/2024` — **MANTER_NA_FILA_COM_LACUNAS**

- Empresa: CASTILHO ENGENHARIA E EMPREENDIMENTOS S/A (CNPJ `92779503****`) · UF=PR · score=16.94
- Órgão: SUP. REG. DO DNIT NO ESTADO DO PARANA
- Valor PNCP: R$ 36,150,000.00
- Classificação pipeline: `LEGAL_REGIME_UNKNOWN` · data_base_status=`PROXY_PROSPECTION_ONLY`
- FP: **False** · incerteza: **alta**
- Documento consultado: https://pncp.gov.br/app/contratos/04892707000100/2024/359
- Objeto (trecho): EXECUÇÃO DOS SERVIÇOS NECESSÁRIOS DE MANUTENÇÃO RODOVIÁRIA (CONSERVAÇÃO/RECUPERAÇÃO) NAS RODOVIAS BR-163/PR (SEGMENTO ENTRE OS MUNICÍPIOS DE MARECHAL CÂNDIDO RONDON/PR E GUAÍRA/PR, INCLUSIVE PONTE AYRTON SENNA E ACESSO) E BR-272/PR (SEGMENTO ENTRE OS MUNICÍPIOS DE FRANCISCO ALVES
- Notas:
  - Terceiro instrumento CASTILHO no top — manutenção BR-163/PR; consolidar com #1 e #25.
  - Ticket ~R$ 36,2 mi (este) é o mais 'humano' dos três CASTILHO; usar como âncora de conversa se #1 tiver valor PNCP suspeito.
  - Empresa recorrente DNIT: maturidade interna de gestão contratual pode ser alta (penalidade comercial leve).
  - Mesmas lacunas documentais.

## #20 `04892707000100-2-000445/2023` — **PRIORIZAR_SUL_SC**

- Empresa: CONSTRUCOES SCHOROEDER EIRELI    - (CNPJ `10249046****`) · UF=SC · score=16.78
- Órgão: SUP. REG. DO DNIT NO ESTADO DE SANTA CATARINA
- Valor PNCP: R$ 171,072,604.27
- Classificação pipeline: `LEGAL_REGIME_UNKNOWN` · data_base_status=`PROXY_PROSPECTION_ONLY`
- FP: **False** · incerteza: **alta**
- Documento consultado: https://pncp.gov.br/app/contratos/04892707000100/2023/445
- Objeto (trecho): TERMO DE CONTRATO, SOB O REGIME DE EMPREITADA POR PREÇO UNITÁRIO, QUE FAZEM ENTRE SI O DEPARTAMENTO NACIONAL DE INFRAESTRUTURA DE TRANSPORTES E O CONSÓRCIO  SCHOROEDER-SULCATARINENSE CREMA BR-470, PARA EXECUÇÃO PARA EXECUÇÃO DE SERVIÇOS DO PROJETO CONSTANTE DO PROGRAMA CREMA NA R
- Notas:
  - Construções Schoroeder (EIRELI) — DNIT/SC empreitada preço unitário; UF SC no lead.
  - Ticket ~R$ 171 mi e vigência longa até 2029 — menos urgência de encerramento que SIE/SC 2026.
  - EIRELI sugere porte menor que LCM/CASTILHO — melhor aderência a consultoria externa, sem afirmação depreciativa.
  - Priorizar recuperação do termo de contrato citado no objeto.

## #21 `04892707000100-2-000467/2024` — **MANTER_NA_FILA_COM_LACUNAS**

- Empresa: CONSTRUTORA LUIZ COSTA LTDA (CNPJ `00779059****`) · UF=RN · score=16.77
- Órgão: DEPARTAMENTO NACIONAL INFRAEST.DE TRANSPORTES
- Valor PNCP: R$ 393,742,699.39
- Classificação pipeline: `LEGAL_REGIME_UNKNOWN` · data_base_status=`PROXY_PROSPECTION_ONLY`
- FP: **False** · incerteza: **alta**
- Documento consultado: https://pncp.gov.br/app/contratos/04892707000100/2024/467
- Objeto (trecho): Elaboração dos projetos básico e executivo de engenharia e execução das obras de duplicação, restauração e melhoramentos, na rodovia/UF: BR-381/MG - (Lote 8A).
- Notas:
  - Construtora Luiz Costa — projetos + execução de duplicação/restauração (DNIT/RN).
  - Objeto de obra rodoviária de maior complexidade (duplicação) vs só conservação — potencial de cláusula de reajuste setorial (SICRO) se existir no edital.
  - Não inventar SICRO: só usar se o instrumento trouxer.
  - Ticket ~R$ 394 mi; bom candidato nacional se regime 14.133 for comprovado.

## #22 `76416965000121-2-000079/2024` — **MANTER_NA_FILA_COM_LACUNAS**

- Empresa: AUDAX - PREMOTEC (CNPJ `57361893****`) · UF=SC · score=16.76
- Órgão: SEED - Secretaria de Estado da Educação
- Valor PNCP: R$ 22,957,462.00
- Classificação pipeline: `LEGAL_REGIME_UNKNOWN` · data_base_status=`PROXY_PROSPECTION_ONLY`
- FP: **False** · incerteza: **alta**
- Documento consultado: https://pncp.gov.br/app/contratos/76416965000121/2024/79
- Objeto (trecho): Contratação Integrada de empresa especializada em engenharia e/ou arquitetura para elaboração de projetos básico, legal e executivo de arquitetura, projetos complementares de engenharia, aprovação nos órgãos competentes, As Built e execução da obra da Unidade Nova Escolar Pinheir
- Notas:
  - AUDAX-PREMOTEC — contratação integrada engenharia/arquitetura com projetos + (provável) obra; texto cortado no objeto.
  - Ticket ~R$ 23 mi — faixa em que consultoria CONFENGE pode ser economicamente viável para a empresa.
  - UF SC — entra em SUL_SC_PRIORITY.
  - Ler edital completo: se for só projeto sem execução, reclassificar depois; com base no trecho atual, ainda há indício de obra.

## #23 `82951344000140-2-000040/2024` — **PRIORIZAR_SUL_SC**

- Empresa: PLANATERRA-TERRAPLENAGEM E PAVIMENTACAO LTDA (CNPJ `82743832****`) · UF=SC · score=16.69
- Órgão: Secretaria de Estado da Infraestrutura e Mobilidade
- Valor PNCP: R$ 83,115,904.13
- Classificação pipeline: `LEGAL_REGIME_UNKNOWN` · data_base_status=`PROXY_PROSPECTION_ONLY`
- FP: **False** · incerteza: **alta**
- Documento consultado: https://pncp.gov.br/app/contratos/82951344000140/2024/40
- Objeto (trecho): CONTRATAÇÃO DE EMPRESA PARA EXECUÇÃO DO REMANESCENTE DO CONTRATO CT-039/2021, COM PROJETO REVISADO (CT-054/2021), PARA PRESTAÇÃO DE SERVIÇOS ESPECIALIZADOS DE ENGENHARIA PARA EXECUÇÃO DE RESTAURAÇÃO COM AUMENTO DE CAPACIDADE DA RODOVIA SC-283, TRECHO ÁGUAS DE CHAPECÓ - SÃO CARLOS
- Notas:
  - PLANATERRA — remanescente CT-039/2021 SC-283 (Águas de Chapecó–Palmitos), restauração com aumento de capacidade ~20 km.
  - Obra rodoviária SC clara; vigência até 2026-12-17 (urgência moderada).
  - Remanescente de contrato antigo pode ter histórico de aditivos/apostilas — pedir sequência completa.
  - Bom caso de storytelling comercial: obra estadual SC com continuidade contratual.

## #24 `92883834000100-2-000028/2024` — **RECLASSIFICAR**

- Empresa: POLIGRAPH SISTEMAS E REPRESENTACOES LTDA (CNPJ `85200665****`) · UF=SC · score=16.64
- Órgão: ERS-DEPARTAMENTO AUT. DE ESTRADAS DE RODAGEM
- Valor PNCP: R$ 23,241,681.22
- Classificação pipeline: `LEGAL_REGIME_UNKNOWN` · data_base_status=`PROXY_PROSPECTION_ONLY`
- FP: **True** · incerteza: **baixa**
- Reclassificar para: `NOT_ELIGIBLE`
- Documento consultado: https://pncp.gov.br/app/contratos/92883834000100/2024/28
- Objeto (trecho): Contratação de empresa de TI para licenciamento de software e prestação de serviços de sustentação e suporte à solução de modernização da gestão de custos, contratos de obras, indicadores, autorizações de trânsito, faixa de domínio, georreferenciamento, manutenção rodoviária, mei
- Notas:
  - POLIGRAPH — empresa de TI: licenciamento de software e sustentação de sistema de gestão de custos/contratos/obras do DAER/RS.
  - Não executa obra; apenas software de gestão. FP por menção a 'obras' e 'manutenção rodoviária' no objeto do sistema.
  - Excluir da fila; adicionar regressão: software/licenciamento + gestão de obras ≠ construção.
  - Não contatar como lead de reajuste.

## #25 `04892707000100-2-000436/2024` — **MANTER_NA_FILA_COM_LACUNAS**

- Empresa: CASTILHO ENGENHARIA E EMPREENDIMENTOS S/A (CNPJ `92779503****`) · UF=PR · score=16.56
- Órgão: SUP. REGIONAL DO DNIT NO ESTADO DA BAHIA
- Valor PNCP: R$ 64,999,999.00
- Classificação pipeline: `LEGAL_REGIME_UNKNOWN` · data_base_status=`PROXY_PROSPECTION_ONLY`
- FP: **False** · incerteza: **alta**
- Documento consultado: https://pncp.gov.br/app/contratos/04892707000100/2024/436
- Objeto (trecho): EXECUÇÃO DOS SERVIÇOS NECESSÁRIOS DE MANUTENÇÃO RODOVIÁRIA (CONSERVAÇÃO/RECUPERAÇÃO) NA RODOVIA BR-116/BA.  TRECHO: DIV. PE/BA (INÍCIO PONTE SOBRE O RIO SÃO FRANCISCO) - DIV. BA/MG; SUBTRECHO: ENTR. BR-235 - ENTR. BR-410 (TUCANO); SEGMENTO: KM 155,20 - KM 277,10; EXTENSÃO:  121.9
- Notas:
  - CASTILHO — BR-116/BA manutenção; quarto instrumento CASTILHO no universo ampliado (consolidar).
  - Ticket ~R$ 65 mi razoável; assinatura 2024-10-01 → interregno ainda recente (~307 dias de atraso proxy) mas >12m desde base proxy.
  - Mesma estratégia de dossiê multi-contrato CASTILHO.
  - Lacunas documentais inalteradas.

## #26 `04892707000100-2-000493/2024` — **MANTER_NA_FILA_COM_LACUNAS**

- Empresa: LCM CONSTRUCAO E COMERCIO S.A (CNPJ `19758842****`) · UF=MG · score=16.42
- Órgão: SUP. REG. DO DNIT NO EST.DO RIO GRANDE DO SUL
- Valor PNCP: R$ 405,546,040.48
- Classificação pipeline: `LEGAL_REGIME_UNKNOWN` · data_base_status=`PROXY_PROSPECTION_ONLY`
- FP: **False** · incerteza: **alta**
- Documento consultado: https://pncp.gov.br/app/contratos/04892707000100/2024/493
- Objeto (trecho): EXECUÇÃO DOS SERVIÇOS EMERGENCIAIS NA RODOVIA BR-470/RS DO KM 253,5 AO KM 287,3, SOB JURISDIÇÃO DA UNIDADE LOCAL DE PASSO FUNDO/RS.
- Notas:
  - LCM — serviços emergenciais BR-470/RS; natureza material de recuperação rodoviária.
  - Emergencial pode ter regras distintas de reajuste/periodicidade — ler cláusula com cuidado (não assumir anualidade automática sem texto).
  - Consolidar com demais LCM; telefone já conhecido no enrich.
  - Valor ~R$ 406 mi.

## #27 `04892707000100-2-000494/2024` — **PRIORIZAR_SUL_SC**

- Empresa: PLANATERRA-TERRAPLENAGEM E PAVIMENTACAO LTDA (CNPJ `82743832****`) · UF=SC · score=16.42
- Órgão: SUP. REG. DO DNIT NO EST.DO RIO GRANDE DO SUL
- Valor PNCP: R$ 66,820,500.00
- Classificação pipeline: `LEGAL_REGIME_UNKNOWN` · data_base_status=`PROXY_PROSPECTION_ONLY`
- FP: **False** · incerteza: **alta**
- Documento consultado: https://pncp.gov.br/app/contratos/04892707000100/2024/494
- Objeto (trecho): EXECUÇÃO DOS SERVIÇOS EMERGENCIAIS NA RODOVIA BR-290 - KM 106,5 AO KM 107,5 - ACESSO ELDORADO DO SUL, SOB A JURISDIÇÃO DA UNIDADE LOCAL DE SÃO LEOPOLDO/RS.
- Notas:
  - PLANATERRA — emergencial BR-290 acesso Eldorado do Sul (trecho curto 1 km) sob DNIT/RS; fornecedor SC.
  - Ticket ~R$ 66,8 mi; emergencial + trecho curto: volume de reajuste potencial pode ser pequeno mesmo se elegível.
  - Combinar no outreach com #23 (mesmo fornecedor, obra SC-283) para eficiência comercial.
  - Verificar se emergencial já foi integralmente medido (risco CLOSED).

## #28 `00394460000141-2-001189/2024` — **MANTER_NA_FILA_COM_LACUNAS**

- Empresa: EMBRACOL ENGENHARIA DE OBRAS LTDA (CNPJ `05901551****`) · UF=SC · score=16.42
- Órgão: SUP.REGIONAL RECEITA FEDERAL 2A.RF/PA
- Valor PNCP: R$ 51,301,845.15
- Classificação pipeline: `LEGAL_REGIME_UNKNOWN` · data_base_status=`PROXY_PROSPECTION_ONLY`
- FP: **False** · incerteza: **alta**
- Documento consultado: https://pncp.gov.br/app/contratos/00394460000141/2024/1189
- Objeto (trecho): OBRA DE ENGENHARIA PARA EXECUÇÃO DA OBRA DE CONSTRUÇÃO DO EDIFÍCIO SEDE DAS UNIDADES DA RECEITA FEDERAL DO BRASIL EM BELÉM, EM TERRENO DA UNIÃO, SITUADO NA AV. JÚLIO CÉSAR, S/Nº - ESQUINA COM A AV. BRIGADEIRO PROTÁSIO - BAIRRO SOUZA – MUNICÍPIO DE BELÉM/PA
- Notas:
  - EMBRACOL — construção do edifício-sede RFB em Belém (edificação federal clássica).
  - Objeto limpo de construção de edifício; melhor tipicidade de reajuste por índice de construção do que manutenção DNIT genérica.
  - Ticket ~R$ 51,3 mi; UF sede SC no lead com obra no PA — contato na sede SC.
  - Duplicado conceitualmente com #29 (mesmo objeto, outro CNPJ de órgão): ver nota do par.

## #29 `00394460007073-2-000022/2024` — **MARCAR_DUPLICATA_DE_#28**

- Empresa: EMBRACOL ENGENHARIA DE OBRAS LTDA (CNPJ `05901551****`) · UF=SC · score=16.42
- Órgão: SUP.REGIONAL RECEITA FEDERAL 2A.RF/PA
- Valor PNCP: R$ 51,301,845.15
- Classificação pipeline: `LEGAL_REGIME_UNKNOWN` · data_base_status=`PROXY_PROSPECTION_ONLY`
- FP: **False** · incerteza: **alta**
- Documento consultado: https://pncp.gov.br/app/contratos/00394460007073/2024/22
- Objeto (trecho): OBRA DE ENGENHARIA para Execução da Obra de Construção do Edifício Sede das Unidades da Receita Federal do Brasil em Belém, em terreno da União, situado na Av. Júlio César, s/nº - Esquina com a Av. Brigadeiro Protásio - Bairro Souza – Município de Belém/PA
- Notas:
  - Mesmo objeto e valor e datas que #28 (edifício RFB Belém / EMBRACOL) — órgão com CNPJ diferente (unidade administrativa).
  - Tratar como duplicata do mesmo instrumento econômico: um dossiê, um outreach.
  - Não contar duas vezes no ranking de carteira nem no forecast de receita.
  - Confirmar no PNCP se são o mesmo contrato republicado ou instrumentos distintos formalmente.

## #30 `15126437000143-2-006208/2024` — **MANTER_NA_FILA_COM_LACUNAS**

- Empresa: CONSORCIO NOVO HUL (CNPJ `57615211****`) · UF=SE · score=16.41
- Órgão: HOSPITAL UNIV. MONS. JOÃO B. DE CARVALHO D.
- Valor PNCP: R$ 955,200,000.00
- Classificação pipeline: `LEGAL_REGIME_UNKNOWN` · data_base_status=`PROXY_PROSPECTION_ONLY`
- FP: **False** · incerteza: **alta**
- Documento consultado: https://pncp.gov.br/app/contratos/15126437000143/2024/6208
- Objeto (trecho): CONTRATAÇÃO DE EMPRESA DE ENGENHARIA PARA EXECUÇÃO DA CONSTRUÇÃO DO CAEPI (CENTRO ADMINISTRATIVO DE ENSINO, PESQUISA E IMAGENS) DO HOSPITAL UNIVERSITÁRIO MONSENHOR JOÃO BATISTA DE CARVALHO DALTRO – HUL
- Notas:
  - CONSÓRCIO NOVO HUL — construção do CAEPI do hospital universitário (edificação).
  - Objeto de obra de construção civil inequívoco; ticket ~R$ 955 mi (validar se é valor total da obra).
  - Consórcio: identificar líderes e RT; contato via telefone enrich se empresarial.
  - Hospital público federal/universitário: regime 14.133 precisa constar do edital — não inferir por ano.
