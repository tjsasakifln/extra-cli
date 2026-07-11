# Investigacao TCE-SC e-Sfinge -- Relatorio Tecnico

> **Data:** 2026-07-10
> **Autor:** Dex (Dev Agent)
> **Missao:** Investigation Phase 0 para Story 001.2 (TCE-SC e-Sfinge Crawler)
> **Contexto:** Determinar estrategia de acesso ao portal e-Sfinge do TCE-SC para
>   coleta de dados de licitacoes e contratos dos 295 municipios de SC.

---

## 1. Resumo Executivo

O **e-Sfinge (Sistema de Fiscalizacao Integrada de Gestao)** do TCE-SC e um sistema
interno usado pelos municipios catarinenses para reportar dados fiscais,
orçamentarios e de licitacoes ao Tribunal de Contas. Existem evidencias de que
o sistema possui **Web Services REST e SOAP documentados**, mas estes nao estao
acessiveis publicamente -- a documentacao esta em um Confluence corporativo com
acesso anonimo restrito.

**Alternativas encontradas:**
- **SCMWeb Transparency** -- JSON API funcional, mas limitada a dados do TCE-SC
- **Farol TCE/SC** -- Dashboard Qlik Sense com dados de licitacoes/contratos
- **APIs de Dados Abertos** -- Listas de municipios e unidades gestoras

**Veredito:** Estrategia **Hibrida (B + C)** -- A implementacao deve usar o
SCMWeb como fonte principal para dados do TCE-SC, complementado por solicitacao
formal de acesso ao e-Sfinge REST API para dados consolidados dos municipios.

---

## 2. URLs Investigadas

### 2.1 e-Sfinge (Sistema Principal)

| URL | Status | Observacao |
|-----|--------|------------|
| `https://e-sfinge.tce.sc.gov.br/` | **NAO RESOLVE** | Domínio inexistente -- antigo URL do sistema |
| `https://manualesfinge.tcesc.tc.br/` | **200 OK** | Confluence com documentacao; acesso anonimo limitado |
| `https://esfinge.tcesc.tc.br/` | NAO RESOLVE | |
| `https://esfinge.tce.sc.gov.br/esfinge/` | NAO RESOLVE | |
| `https://app.esfinge.tcesc.tc.br/` | NAO RESOLVE | |

**Confluence Sidebar confirma existencia de:**
- `e-Sfinge Web Service (REST)`
- `e-Sfinge Web Service (SOAP)`
- `Consulta Publica`
- `e-Sfinge Web` (aplicacao web)

O conteudo destas paginas esta bloqueado para acesso anonimo (requer login).

### 2.2 Portais e Servicos Acessiveis

| URL | Status | Descricao |
|-----|--------|-----------|
| `https://www.tce.sc.gov.br/` | 200 OK | Site institucional (Drupal 9) |
| `https://transparencia.tcesc.tc.br/` | 200 OK | Portal da Transparencia (TCE/SC) |
| `https://servicos.tcesc.tc.br/` | 200 OK | Portal de Servicos |
| `https://servicos.tcesc.tc.br/farol_externo/` | 200 OK | Farol TCE/SC (Qlik dashboards) |
| `https://paineistransparencia.tce.sc.gov.br/` | 200 OK | Paineis Transparencia (Qlik Sense) |
| `https://www.scmweb.com.br/processos/` | 200 OK | SCMWeb -- Sistema de Transparencia |
| `https://virtual.tce.sc.gov.br/pwa/` | 200 OK | TCE Virtual (consulta processual) |
| `https://radardatransparencia.atricon.org.br/` | 200 OK | Radar Transparencia (ATRICON) |

---

## 3. Analise Detalhada por Fonte

### 3.1 SCMWeb -- JSON API de Licitacoes

**URL Base:** `https://www.scmweb.com.br/processos/index.php?pg=transparencia&p285`

**Endpoints descobertos:**

```
# Licitacoes (JSON export)
GET ?pg=transparencia&p285&page=licitacoes&export=json&type=licitacoes

# Contratos (JSON export)
GET ?pg=transparencia&p285&page=contratos&export=json&type=contratos

# Detalhes da licitacao
GET ?pg=transparencia&p285&page=licitacao_detalhes&id={id}
```

**Schema (Licitacoes):**
```json
{
  "Numero": "0001",
  "Modalidade": "Inexigibilidade",
  "Objeto": "",
  "Data_Abertura": "13/01/2026",
  "Valor_Estimado": "41138.80",
  "Status": "FINALIZADA / HOMOLOGADA",
  "Ano": "2026"
}
```

**Schema (Contratos):**
```json
{
  "Numero": "01/2026",
  "Contratado": "C DIAS LTDA",
  "CNPJ": "1672499000146",
  "Objeto": "",
  "Valor": "749889.96",
  "Status": "Vigente"
}
```

**Filtros disponiveis:**
- `ano` (2021-2026)
- `modalidade` (codigo numerico, carregado via JS)
- `status` (carregado via JS)
- `unidade_gestora` (carregado via JS -- 240+ opcoes)
- `cod_empresa` (CNPJ)
- `data_inicio`, `data_fim` (date range)
- `search` (texto livre)
- `pn` (paginacao)
- `tem_aditivo` (com/sem aditivos)

**Export formats:** JSON, CSV, XLSX, PDF

**Limitação:** O parametro `p285` parece ser um identificador fixo do TCE-SC
como orgao. Os ~90 registros retornados para 2026 sao provavelmente apenas
licitacoes do proprio TCE-SC, **nao dos 295 municipios**.

### 3.2 Farol TCE/SC -- Qlik Sense Dashboard

**URL:** `https://servicos.tcesc.tc.br/farol_externo/`

**App Licitacoes:** `AppLicitacoesExterno`
- URL: `https://paineistransparencia.tce.sc.gov.br/extensions/AppLicitacoesExterno/index.html`
- Qlik App ID: `107d8f10-9431-404d-a267-5db6011dd28d`
- Framework: Qlik Sense (Incodata)
- Dashboards: dash01.html a dash07.html

**Funcionalidade:** Dashboard interativo com KPIs, graficos e tabelas de
licitacoes e contratos. Construido sobre Qlik Sense, consome dados do
e-Sfinge via ETL. Nao expoe API publica para extracao programatica.

**Apps relacionados no Farol:**
- `AppLicitacoesExterno` -- Licitacoes e Contratos
- `AppObrasExterno` -- Obras
- `PainelDePrecos` -- Cotacoes / Precos
- `AppReceitasDoEstadoExterno` -- Receitas Estaduais
- `appReceitasMunicipaisExterno` -- Receitas Municipais
- `appDespesasMunicipaisExternoNovo` -- Despesas Municipais
- `AppPessoalOnlineExterno` -- Pessoal

### 3.3 Open Data APIs (Dados Abertos)

**URL Base:** `https://servicos.tcesc.tc.br/endpoints-portal-transparencia/`

**Endpoints disponiveis:**

```json
// GET /municipios.php
// Retorna: [{ "codigo_municipio": 420005, "nome_municipio": "Abdon Batista" }, ...]
// Total: 295 municipios de SC com codigos IBGE

// GET /unidades-gestoras.php
// Retorna: [{ "codigo_unidade": 54116, "nome_unidade": "...",
//             "sigla_unidade": null, "nome_municipio": "Abdon Batista" }, ...]
// Total: ~2000+ unidades gestoras de todos os municipios
```

**Utilidade:** Estas APIs sao EXCELENTES para:
1. Vincular entidades no `entity_coverage` (codigos IBGE corretos)
2. Mapear unidades gestoras para municipios
3. Referencia para queries no SCMWeb (se aceitar codigo_unidade como filtro)

### 3.4 Portal da Transparencia TCE/SC

**URL:** `https://transparencia.tcesc.tc.br/`

**Nota:** Este portal mostra dados de gastos do proprio TCE-SC (receitas, despesas,
pessoal, diarias, licitacoes, contratos), NAO dados consolidados dos municipios.
Usa PowerBI embarcado para visualizacao. Nao tem API publica.

---

## 4. Volume Estimado

| Fonte | Volume Estimado | Atualizacao |
|-------|----------------|-------------|
| **SCMWeb (TCE-SC apenas)** | ~90 licitacoes/ano | Tempo real |
| **e-Sfinge (295 municipios)** | ~5.000-15.000 licitacoes/mes (estimado) | Diaria (envio municipios) |
| **Open Data APIs** | 295 municipios + ~2.000 unidades | Referencia estatica |

**Nota:** O volume real de licitacoes dos 295 municipios via e-Sfinge nao pode
ser verificado sem acesso a API. Estimativa baseada em: 295 municipios x ~20-50
licitacoes/mes cada = 5.900-14.750/mes.

---

## 5. Estrategia Recomendada

### 5.1 Opcao A: Solicitacao Formal de Acesso a API e-Sfinge (Preferencial)

**Fundamentacao:** O TCE-SC e orgao publico sujeito a Lei de Acesso a Informacao
(Lei 12.527/2011). Os dados de licitacoes sao publicos. O Confluence comprova
que a API REST existe.

**Acao:** Solicitar formalmente ao TCE-SC:
- Credenciais de acesso a API REST do e-Sfinge
- Documentacao dos endpoints

**Risco:** Tempo de resposta imprevisivel (semanas a meses).

### 5.2 Opcao B: SCMWeb + Paginacao por Unidade Gestora (Paralelo)

**Abordagem:** Se o SCMWeb aceitar `unidade_gestora` como parametro via URL,
e possivel iterar sobre todas as ~2000 unidades gestoras para coletar dados
de cada municipio.

**Vantagem:** API JSON ja funcional, sem autenticacao.

**Risco:** O parametro `p285` pode ser fixo (TCE-SC), impedindo consulta a
outros orgaos. Isso precisa ser verificado.

### 5.3 Opcao C: Qlik Sense API (Fallback)

**Abordagem:** Qlik Sense tem APIs REST proprietarias (QPS/QRS) que permitem
exportar dados dos aplicativos. O app ID `107d8f10-9431-404d-a267-5db6011dd28d`
esta identificado.

**Risco:** Qlik Sense geralmente requer autenticacao para acesso a dados.
O endpoint provavelmente exige ticket/session.

### 5.4 Opcao D: PowerBI / Farol (Nao Recomendado)

PowerBI dashboards sao para visualizacao humana, nao para extracao
programatica. Qlik Sense oferece mais possibilidades de exportacao.

### 5.5 Estrategia Recomendada para Story 001.2

```
Fase 1 (2h): Adaptar `transparencia_crawler.py` para usar APIs de Dados Abertos
             (municipios + unidades gestoras) como fonte de referencia.

Fase 2 (4h): Implementar `tce_sc_crawler.py` no padrao adapter.py com:
             - TARGET_URL = "https://www.scmweb.com.br/processos"
             - Endpoint: page=licitacoes&export=json&type=licitacoes
             - Filtros: ano, data_inicio, data_fim
             - Rate limiting: 2s entre requests
             - Checkpoint/resume via checkpoint.py
             - Output schema: pncp_raw_bids com source='tce_sc'
             - NOTA: Dados limitados ao TCE-SC ate confirmacao de acesso
                     a dados municipais agregados

Fase 3 (2h): Se o parametro unidade_gestora for funcional, expandir para
             iterar sobre todas as unidades (~2000) para cobertura completa.

Fase 4 (8h): Se acesso ao e-Sfinge REST API for obtido:
             - Adaptar crawler para usar API real do e-Sfinge
             - Implementar autenticacao
             - Expadir cobertura para dados consolidados dos 295 municipios
```

---

## 6. Riscos e Mitigacoes

| Risco | Probabilidade | Impacto | Mitigacao |
|-------|--------------|---------|-----------|
| SCMWeb `p285` fixo para TCE-SC | Alta | Alto | Usar DOM-SC + PCP como fallback; aguardar acesso e-Sfinge |
| Confluence com documentacao bloqueada | Confirmado | Medio | Solicitar acesso formal ao TCE-SC |
| Qlik Sense requer autenticacao | Alta | Medio | Nao usar como fonte primaria |
| e-Sfinge API requer certificado digital | Media | Alto | Solicitar credenciais formais (LAI) |
| Dados disponiveis apenas em PowerBI | Media | Baixo | Viavel apenas se houver exportacao CSV |

---

## 7. Recursos Identificados

### APIs Funcionais (sem autenticacao)

```
# Lista de municipios SC (295)
GET https://servicos.tcesc.tc.br/endpoints-portal-transparencia/municipios.php

# Lista de unidades gestoras (~2000)
GET https://servicos.tcesc.tc.br/endpoints-portal-transparencia/unidades-gestoras.php

# Licitacoes TCE-SC (JSON)
GET https://www.scmweb.com.br/processos/index.php?pg=transparencia&p285&page=licitacoes&export=json&type=licitacoes

# Contratos TCE-SC (JSON)
GET https://www.scmweb.com.br/processos/index.php?pg=transparencia&p285&page=contratos&export=json&type=contratos
```

### Qlik Sense App

```
App ID: 107d8f10-9431-404d-a267-5db6011dd28d
Host: paineistransparencia.tce.sc.gov.br
URL: /extensions/AppLicitacoesExterno/index.html
Provider: Incodata (incodata.com.br)
```

### Tabelas de Download (e-Sfinge historico)

```
URL: https://www.tce.sc.gov.br/tabelas-download-anos-anteriores-e-sfinge
Conteudo: Tabelas de anos anteriores (formato a verificar)
```

---

## 8. Conclusao

A investigacao confirma que:

1. **O e-Sfinge possui REST API documentada** (evidencia no Confluence), mas
   o acesso e restrito. O endpoint base nao foi descoberto.

2. **O SCMWeb fornece JSON API funcional** para dados de licitacoes e contratos
   do TCE-SC, com exportacao em JSON, CSV, XLSX e PDF.

3. **APIs de Dados Abertos** estao disponiveis para dados cadastrais (municipios
   e unidades gestoras) sem autenticacao.

4. **A cobertura dos 295 municipios** via e-Sfinge nao pode ser confirmada sem
   acesso a API real. As fontes DOM-SC + PCP + SC Compras continuam sendo o
   pilar da cobertura municipal.

5. **Estrategia recomendada:** Implementar crawler usando SCMWeb JSON API em
   paralelo com solicitacao formal de acesso ao e-Sfinge REST API. O adapter
   deve seguir o padrao `pncp_crawler_adapter.py` com fallback para
   `dom_sc_crawler.py` (HTML scraping) se necessario.

---

## Apendice A: Comandos uteis para continuidade

```bash
# Testar JSON API de licitacoes (TCE-SC)
curl "https://www.scmweb.com.br/processos/index.php?pg=transparencia&p285&page=licitacoes&export=json&type=licitacoes&ano=2026"

# Testar JSON API de contratos (TCE-SC)
curl "https://www.scmweb.com.br/processos/index.php?pg=transparencia&p285&page=contratos&export=json&type=contratos&ano=2026"

# Testar com filtro de data
curl "https://www.scmweb.com.br/processos/index.php?pg=transparencia&p285&page=licitacoes&export=json&type=licitacoes&data_inicio=2026-01-01&data_fim=2026-06-30"

# Listar municipios
curl "https://servicos.tcesc.tc.br/endpoints-portal-transparencia/municipios.php"

# Listar unidades gestoras
curl "https://servicos.tcesc.tc.br/endpoints-portal-transparencia/unidades-gestoras.php"
```

## Apendice B: Referencias

- Site TCE-SC: https://www.tce.sc.gov.br/
- Manual e-Sfinge: https://manualesfinge.tcesc.tc.br/
- Farol TCE/SC: https://servicos.tcesc.tc.br/farol_externo/
- Portal Transparencia: https://transparencia.tcesc.tc.br/
- APIs Dados Abertos: https://www.tcesc.tc.br/apis-dados-abertos
- Radar ATRICON: https://radardatransparencia.atricon.org.br/
