# Inventario Geografico de Entes Publicos — Raio 200km de Florianopolis

**Data de geracao:** 2026-07-15
**Origem:** Florianopolis (lat=-27.5954, lon=-48.548)
**Raio:** 200.0 km (faixa de tolerancia: 190 a 220 km para revisao manual)
**Fonte:** `Extra - alvos de licitacao. R-0.xlsx` (sheet: Entes Publicos SC)
**Metodo:** Distancia geodesica via formula de haversine
**Gerado por:** Agente B — Inventario Geografico e Entidades-Alvo

---

## 1. Resumo Estatistico

| Metrica | Valor |
|---------|-------|
| Total de entidades na planilha | 2085 |
| Com coordenadas validas | 1481 |
| Sem coordenadas (N/D) | 604 |
| **Dentro do raio (<=200 km)** | **1093** |
| Limítrofes (190-220 km) — revisar | 31 |
| Fora do raio (>220 km) | 357 |
| Municipios unicos dentro do raio | 95 |
| Entidades estaduais (Santa Catarina) | 513 |
| Discrepancias seed vs haversine | 0 |
| Duplicatas de CNPJ roots | 1 |
| Entidades sem CNPJ | 0 |

O universo canonico (constante `CANONICAL_UNIVERSE = 1093` em `scripts/lib/universe.py`) e confirmado pelo calculo haversine independente com **0 discrepancias** acima de 1 km.

---

## 2. Top 30 Municipios por Quantidade de Entidades

| # | Municipio | Entidades |
|---|-----------|----------|
| 1 | JOINVILLE                      |   36 |
| 2 | BLUMENAU                       |   35 |
| 3 | FLORIANOPOLIS                  |   22 |
| 4 | BRUSQUE                        |   16 |
| 5 | RIO DO SUL                     |   14 |
| 6 | PORTO BELO                     |   13 |
| 7 | NAVEGANTES                     |   10 |
| 8 | LAGUNA                         |   10 |
| 9 | ITAPEMA                        |    9 |
| 10 | BARRA VELHA                    |    9 |
| 11 | ARAQUARI                       |    9 |
| 12 | CAMPO ALEGRE                   |    9 |
| 13 | LAGES                          |    9 |
| 14 | SANTO AMARO DA IMPERATRIZ      |    8 |
| 15 | GUARAMIRIM                     |    8 |
| 16 | ILHOTA                         |    7 |
| 17 | PENHA                          |    7 |
| 18 | ORLEANS                        |    7 |
| 19 | LAURO MULLER                   |    7 |
| 20 | URUSSANGA                      |    7 |
| 21 | RIO NEGRINHO                   |    7 |
| 22 | TIJUCAS                        |    6 |
| 23 | GAROPABA                       |    6 |
| 24 | NOVA TRENTO                    |    6 |
| 25 | IMBITUBA                       |    6 |
| 26 | GASPAR                         |    6 |
| 27 | INDAIAL                        |    6 |
| 28 | ITUPORANGA                     |    6 |
| 29 | LONTRAS                        |    6 |
| 30 | AURORA                         |    6 |

---

## 3. Distribuicao por Tipo de Ente (Natureza Juridica)

| Tipo | Quantidade |
|------|-----------|
| Órgão Público do Poder Executivo Municipal                   |  179 |
| Fundação Pública de Direito Público Municipal                |  119 |
| Órgão Público do Poder Executivo Estadual ou do Distrito Federal |   99 |
| Órgão Público do Poder Legislativo Municipal                 |   98 |
| Município                                                    |   95 |
| Órgão Público do Poder Judiciário Estadual                   |   78 |
| Autarquia Municipal                                          |   61 |
| Fundo Público da Administração Direta Estadual ou do Distrito Federal |   61 |
| Sociedade de Economia Mista                                  |   59 |
| Autarquia Federal                                            |   57 |
| Órgão Público do Poder Executivo Federal                     |   44 |
| Consórcio Público de Direito Público (Associação Pública)    |   37 |
| Empresa Pública                                              |   34 |
| Autarquia Estadual ou do Distrito Federal                    |   15 |
| Serviço Social Autônomo                                      |   15 |
| Fundação Pública de Direito Público Estadual ou do Distrito Federal |   10 |
| Fundação Pública de Direito Público Federal                  |    8 |
| Órgão Público do Poder Judiciário Federal                    |    7 |
| Fundação Pública de Direito Privado Municipal                |    4 |
| Consórcio Público de Direito Privado                         |    2 |
| Fundo Público da Administração Indireta Estadual ou do Distrito Federal |    2 |
| Órgão Público Autônomo Estadual ou do Distrito Federal       |    2 |
| Estado ou Distrito Federal                                   |    1 |
| Órgão Público do Poder Legislativo Estadual ou do Distrito Federal |    1 |
| Órgão Público do Poder Legislativo Federal                   |    1 |
| Fundação Pública de Direito Privado Federal                  |    1 |
| Órgão Público Autônomo Municipal                             |    1 |
| Fundo Público da Administração Direta Federal                |    1 |
| Órgão Público Autônomo Federal                               |    1 |

### Tipos Simplificados

| Tipo | Quantidade |
|------|-----------|
| Secretaria Municipal                |  179 |
| Fundacao Municipal                  |  123 |
| Orgao Estadual                      |   99 |
| Camara Municipal                    |   98 |
| Prefeitura Municipal                |   95 |
| Poder Judiciario Estadual           |   78 |
| Fundo Estadual                      |   63 |
| Autarquia Municipal                 |   61 |
| Sociedade de Economia Mista         |   59 |
| Autarquia Federal                   |   57 |
| Orgao Federal                       |   44 |
| Consorcio Publico                   |   39 |
| Empresa Publica                     |   34 |
| Autarquia Estadual                  |   15 |
| Servico Social Autonomo             |   15 |
| Fundacao Estadual                   |   10 |
| Fundacao Federal                    |    9 |
| Poder Judiciario Federal            |    7 |
| Orgao Autonomo                      |    4 |
| Governo Estadual                    |    1 |
| Assembleia Legislativa              |    1 |
| Camara Federal                      |    1 |
| Fundo Federal                       |    1 |

---

## 4. Entidades Limítrofes (190-220 km) — Revisao Recomendada

31 entidades em 5 municipios estao na faixa de tolerancia:

| Municipio | Entidade | Distancia |
|-----------|----------|----------|
| CURITIBANOS                    | CONSORCIO INTERMUNICIPAL DE SERVICOS DE ACOLHIMENT |  203.7 km |
| CURITIBANOS                    | CAMARA MUNICIPAL DE VEREADORES DE CURITIBANOS      |  203.7 km |
| CURITIBANOS                    | MUNICIPIO DE CURITIBANOS                           |  203.7 km |
| CURITIBANOS                    | FUNDACAO MINICIPAL DE ESPORTES DE CURITIBANOS      |  203.7 km |
| CURITIBANOS                    | INSTITUTO DE PREVIDENCIA SOCIAL SERVIDORES PUBLICO |  203.7 km |
| CURITIBANOS                    | CONSELHO MUNICIPAL DE DEFESA DO MEIO AMBIENTE      |  203.7 km |
| CURITIBANOS                    | CONSORCIO INTERMUNICIPAL DO CONTESTADO - COINCO    |  203.7 km |
| SANTA ROSA DO SUL              | SECRETARIA MUNICIPAL DA EDUCACAO, CULTURA E TURISM |  205.2 km |
| SANTA ROSA DO SUL              | MUNICIPIO DE SANTA ROSA DO SUL                     |  205.2 km |
| SANTA ROSA DO SUL              | CAMARA MUNICIPAL DE VEREADORES DE SANTA ROSA DO SU |  205.2 km |
| SANTA ROSA DO SUL              | SERVICO AUTONOMO MUNICIPAL DE AGUA E ESGOTO SAMAE  |  205.2 km |
| SANTA ROSA DO SUL              | CONSORCIO INTERMUNICIPAL DE SAUDE E ASSISTENCIA SO |  205.2 km |
| MAFRA                          | MUNICIPIO DE MAFRA                                 |  206.6 km |
| MAFRA                          | MAFRA SECRETARIA DE ADMINISTRACAO                  |  206.6 km |
| MAFRA                          | MAFRA SECRETARIA MUNICIPAL DE FINANCAS             |  206.6 km |
| MAFRA                          | MAFRA CAMARA DE VEREADORES                         |  206.6 km |
| MAFRA                          | INSTITUTO DE PREVIDENCIA  DO MUNICIPIO DE MAFRA    |  206.6 km |
| MAFRA                          | PLANO DE ASSISTENCIA A SAUDE DOS SERVIDORES MUNICI |  206.6 km |
| MAFRA                          | DEFESA CIVIL                                       |  206.6 km |
| MAFRA                          | CONSORCIO DE DESENVOLVIMENTO ECONOMICO DO PLANALTO |  206.6 km |
| MAFRA                          | CONSORCIO INTERMUNICIPAL DE MOBILIDADE URBANA - CI |  206.6 km |
| PAPANDUVA                      | MUNICIPIO DE PAPANDUVA                             |  208.0 km |
| PAPANDUVA                      | PAPANDUVA CAMARA DE VEREADORES                     |  208.0 km |
| PAPANDUVA                      | INSTITUTO DE PREVIDENCIA SOCIAL DOS SERVIDORES DO  |  208.0 km |
| PAPANDUVA                      | SERVICO AUTONOMO MUNICIPAL DE AGUA E ESGOTO - SAMA |  208.0 km |
| PAPANDUVA                      | SECRETARIA DE EDUCACAO DE PAPANDUVA                |  208.0 km |
| MONTE CASTELO                  | MUNICIPIO DE MONTE CASTELO                         |  209.2 km |
| MONTE CASTELO                  | MONTE CASTELO CAMARA DE VEREADORES                 |  209.2 km |
| MONTE CASTELO                  | FUNDO MUNICIPAL DE SAUDE                           |  209.2 km |
| MONTE CASTELO                  | FUNDACAO MUNICIPAL DE ESPORTES DE MONTE CASTELO    |  209.2 km |
| MONTE CASTELO                  | SECRETARIA DE EDUCACAO, CULTURA E ESPORTES DE MONT |  209.2 km |

### Municipios limítrofes que merecem revisao:

- **Curitibanos** (203.7 km) — 7 entidades, ~3.7 km fora do raio
- **Santa Rosa do Sul** (205.2 km) — 5 entidades, ~5.2 km fora
- **Mafra** (206.6 km) — 9 entidades, ~6.6 km fora
- **Papanduva** (208.0 km) — 5 entidades, ~8.0 km fora
- **Monte Castelo** (209.2 km) — 5 entidades, ~9.2 km fora

---

## 5. Entidades Problematicas

### 5.1 Sem Coordenadas (N/D)

604 entidades nao possuem coordenadas geograficas (marcadas como "N/D" na planilha). Todas estas entidades foram classificadas como "NAO" (fora do raio) pela flag original.

Distribuicao por municipio (top 15):

| Municipio | Entidades sem coord |
|-----------|---------------------|
| CHAPECO                        |   16 |
| TUBARAO                        |   16 |
| SAO JOSE                       |   15 |
| ITAJAI                         |   15 |
| CRICIUMA                       |   14 |
| JARAGUA DO SUL                 |   13 |
| BALNEARIO CAMBORIU             |   13 |
| BALNEARIO DE PICARRAS          |   12 |
| ICARA                          |   12 |
| CACADOR                        |   11 |
| SAO BENTO DO SUL               |   11 |
| SAO MIGUEL DO OESTE            |   10 |
| TIMBO                          |   10 |
| PALHOCA                        |   10 |
| CONCORDIA                      |    9 |

### 5.2 Duplicatas de CNPJ

1 CNPJ root(s) aparece(m) multiplas vezes:

- **00394494** (4x):
  - MINISTERIO DA JUSTICA E SEGURANCA PUBLICA          (SANTA CATARINA)
  - SUPERINTENDENCIA REGIONAL DO DPF EM SANTA CATARINA (FLORIANOPOLIS)
  - SUPERINTENDENCIA REG.POL.RODOV.FED. EM SANTA CATAR (FLORIANOPOLIS)
  - UNIVERSIDADE CORPORATIVA DA POLICIA RODOVIARIA FED (FLORIANOPOLIS)

### 5.3 Entidades sem CNPJ

Nenhuma entidade possui CNPJ ausente ou invalido.

---

## 6. Entidades Estaduais (Santa Catarina)

513 entidades de ambito estadual (municipio = "SANTA CATARINA") estao dentro do raio, distribuídas por tipo:

  - Orgao Estadual: 99
  - Poder Judiciario Estadual: 78
  - Fundo Estadual: 63
  - Autarquia Federal: 57
  - Sociedade de Economia Mista: 56
  - Orgao Federal: 41
  - Empresa Publica: 33
  - Consorcio Publico: 20
  - Autarquia Estadual: 15
  - Servico Social Autonomo: 15
  - Fundacao Estadual: 10
  - Fundacao Federal: 9
  - Poder Judiciario Federal: 7
  - Orgao Autonomo: 4
  - Fundacao Municipal: 2
  - Governo Estadual: 1
  - Assembleia Legislativa: 1
  - Camara Federal: 1
  - Fundo Federal: 1

---

## 7. Potenciais Lacunas

1. **604 entidades sem coordenadas** — todas marcadas como NAO. Se alguma estiver dentro do raio geografico, esta sendo incorretamente excluida. Recomenda-se geolocalizacao destas entidades.
2. **5 municipios limítrofes** (CURITIBANOS, MAFRA, MONTE CASTELO, PAPANDUVA, SANTA ROSA DO SUL) — 31 entidades a 203-209 km. Dependendo da tolerancia adotada, podem ser incluidas ou excluidas.
3. **1 duplicata(s) de CNPJ** — 00394494(4x). No caso do Ministerio da Justica/PF, trata-se de subordinacao hierarquica esperada, mas deve ser monitorado.

---

## 8. Cross-Reference com CanonicalUniverse

| Fonte | Entidades dentro do raio |
|-------|--------------------------|
| `scripts/lib/universe.py` (CANONICAL_UNIVERSE) | 1093 |
| Haversine independente (esta auditoria) | 1093 |
| Discrepancias | 0 |

O `load_canonical_universe()` carrega exatamente 2085 linhas, resolve 100% delas e reporta 1093 entidades dentro do raio — **consistente com esta auditoria**.

---

## 9. Metodologia

- **Coordenadas de origem:** Florianopolis (lat=-27.5954, lon=-48.548) — centro aproximado do municipio.
- **Formula de distancia:** Haversine (modelo esferico, raio terrestre = 6371 km).
- **Classificacao:**
  - DENTRO: distancia calculada <= 200.0 km
  - LIMITROFE: >200 a 220 km (faixa de revisao para entes proximos ao limite)
  - FORA: > 220 km
  - SEM_COORD: coordenadas marcadas como N/D
- **Validacao:** Comparacao com flag "Raio 200km?" da planilha seed — 0 discrepancias.
- **Ferramentas:** Python 3, openpyxl, haversine implementation nativa.

---

*Gerado por Agente B (Inventario Geografico) em 2026-07-15.*
*Framework: AIOX — Auditoria Read-Only.*
