# Coverage Final Report

> **Story:** COVERAGE-3.4 | **Gerado em:** 2026-07-11 20:02

## Resumo

| Metrica | Valor |
|---------|-------|
| **Cobertura final** | **39.7%** (827/2085) |
| **Entes cobertos** | 827 |
| **Entes descobertos** | 1258 |
| **Total municipios** | 296 |
| **Municipios com descobertos** | 278 |
| **Fontes ativas** | 4 |

## Cobertura por Fonte

| Fonte | Entes |
|-------|-------|
| pncp | 771 |
| ciga_ckan | 152 |
| compras_gov | 74 |
| pcp | 63 |

## Cobertura por Natureza Juridica

| Natureza Juridica | Total | Cobertos | % |
|-------------------|-------|----------|---|
| Órgão Público do Poder Executivo Municipal | 454 | 64 | 14.1% |
| Município | 403 | 392 | 97.3% |
| Órgão Público do Poder Legislativo Municipal | 335 | 186 | 55.5% |
| Fundação Pública de Direito Público Municipal | 275 | 77 | 28.0% |
| Autarquia Municipal | 174 | 83 | 47.7% |
| Consórcio Público de Direito Público (Associação Pública) | 112 | 61 | 54.5% |
| Órgão Público do Poder Executivo Estadual ou do Distrito Federal | 100 | 24 | 24.0% |
| Autarquia Federal | 81 | 63 | 77.8% |
| Órgão Público do Poder Judiciário Estadual | 79 | 2 | 2.5% |
| Fundo Público da Administração Direta Estadual ou do Distrito Federal | 63 | 15 | 23.8% |
| Sociedade de Economia Mista | 62 | 10 | 16.1% |
| Órgão Público do Poder Executivo Federal | 51 | 21 | 41.2% |
| Empresa Pública | 38 | 21 | 55.3% |
| Autarquia Estadual ou do Distrito Federal | 15 | 9 | 60.0% |
| Serviço Social Autônomo | 15 | 0 | 0.0% |
| Órgão Público do Poder Judiciário Federal | 10 | 6 | 60.0% |
| Fundação Pública de Direito Público Estadual ou do Distrito Federal | 10 | 6 | 60.0% |
| Fundação Pública de Direito Público Federal | 10 | 6 | 60.0% |
| Órgão Público Autônomo Municipal | 9 | 2 | 22.2% |
| Fundação Pública de Direito Privado Municipal | 6 | 3 | 50.0% |
| Órgão Público Autônomo Estadual ou do Distrito Federal | 4 | 4 | 100.0% |
| Órgão Público do Poder Legislativo Estadual ou do Distrito Federal | 2 | 2 | 100.0% |
| Fundo Público da Administração Indireta Estadual ou do Distrito Federal | 2 | 0 | 0.0% |
| Órgão Público Autônomo Federal | 2 | 2 | 100.0% |
| Consórcio Público de Direito Privado | 2 | 0 | 0.0% |
| Fundação Pública de Direito Privado Federal | 1 | 0 | 0.0% |
| Órgão Público do Poder Legislativo Federal | 1 | 1 | 100.0% |
| Fundo Público da Administração Direta Federal | 1 | 0 | 0.0% |
| Estado ou Distrito Federal | 1 | 0 | 0.0% |

## Entes Descobertos por Causa Raiz

```
  Sem Dados Publicos             | ######################################### (541)
  Nao Investigado                | ############################## (401)
  Sem Obrigacao Legal 14133      | ############ (167)
  Dom Sc Sem Api Key             | ########### (149)
```

## Top 10 Municipios com Pior Cobertura

| Municipio | Total | Cobertos | Descobertos |
|-----------|-------|----------|-------------|
| SANTA CATARINA | 562 | 193 | 369 |
| JOINVILLE | 40 | 11 | 29 |
| BLUMENAU | 39 | 10 | 29 |
| FLORIANOPOLIS | 23 | 4 | 19 |
| SAO JOSE | 16 | 3 | 13 |
| CHAPECO | 16 | 4 | 12 |
| CRICIUMA | 14 | 5 | 9 |
| ITAJAI | 17 | 8 | 9 |
| BALNEARIO DE PICARRAS | 12 | 3 | 9 |
| RIO DO SUL | 18 | 10 | 8 |

## Recomendacoes

### Fazer Agora (Alto Impacto, Baixo Esforco)
1. **Contratar API key DOM-SC** (R$0-500/ano) — potencial +50-100 entes (especialmente orgaos municipais que publicam apenas no DOM-SC)

### Planejar (Alto Impacto, Alto Esforco)
1. **Certificado ICP-Brasil para TCE-SC e-Sfinge** (R$300-800/ano) — potencial +30-50 entes (portais que exigem certificado digital)
1. **Executar Fase 1 (stories 1.1-1.11): Fontes sem autenticacao** — potencial +500-700 entes (CIGA CKAN expandido, PCP, SC Dados Abertos, matching hierarquico)
1. **Executar Fase 2 (stories 2.1-2.4): Fontes com credenciais** — potencial +200-300 entes (MiDES, SC Compras, DOE-SC)
1. **Executar Fase 3 (stories 3.1-3.3): Scraping + backfill** — potencial +100-200 entes (Selenium para portais JS, portais individuais, backfill multi-source)

### Baixa Prioridade (Baixo Impacto)
1. **Entidades sem obrigacao legal 14.133** (167 entes) — Aceitar como cobertura legitima. Nenhuma acao necessaria.

## Viabilidade de 100% de Cobertura

**Status: INVIALVEL** no cenario atual sem investimento adicional.

### Analise

A cobertura atual de 39.7% (827/2085) esta aquem da meta de 95%+.
As principais barreiras sao:

1. **Fontes limitadas:** Apenas 4 fontes ativas cobrindo
   827 entes.
2. **Fases 1-3 nao executadas:** As stories de expansao de cobertura
   (1.1 a 3.3) ainda nao foram implementadas. Cada fase adiciona novas
   fontes que potencialmente cobrem centenas de entes adicionais.
3. **Entes sem obrigacao legal:** Entes do tipo Servico Social Autonomo
   e Consorcio Publico de Direito Privado nao sao abrangidos pela Lei 14.133.

### Teto Realista

| Cenario | Cobertura Estimada | Acoes Necessarias |
|---------|--------------------|-------------------|
| Atual (somente fontes ativas) | 39.7% | Nenhuma |
| + Fase 1 (Quick Wins + fontes abertas) | ~75% | Stories 1.1-1.11 |
| + Fase 2 (fontes com credenciais) | ~90% | Stories 2.1-2.4 |
| + Fase 3 (scraping pesado + backfill) | ~95% | Stories 3.1-3.3 |
| + Residual (ICP-Brasil, DOM-SC API) | ~97-98% | Investimento em API keys |
| **100%** | **INVIALVEL** | Entes extintos/sem obrigacao legal tornam 100% impossivel |

**Conclusao:** O teto realista viavel e de ~97-98% apos execucao completa
de todas as fases mais investimento em API keys (DOM-SC, ICP-Brasil).
100% e inviavel devido a entes extintos e sem obrigacao legal.

## Reuniao de Encerramento do Epic

### Tempo Total Estimado

| Fase | Stories | Horas Estimadas |
|------|---------|-----------------|
| Fase 1 — Fontes Abertas | 11 stories | ~35h |
| Fase 2 — Credenciais | 4 stories | ~20h |
| Fase 3 — Scraping + Residual | 4 stories | ~23h |
| **Total** | **19 stories** | **~78h** |

### Cobertura Final vs Target

| Fase | Target | Atual | Diferenca |
|------|--------|-------|-----------|
| Atual (pre-fases) | 47% | 39.7% | -7.3pp |
| Apos Fase 1 | 75% | — | — |
| Apos Fase 2 | 90% | — | — |
| Apos Fase 3 | 95%+ | — | — |

### Licoes Aprendidas (preliminares)

1. **Cobertura inicial subestimada:** A cobertura real de 39.7% (827/2085)
   e menor que os 47% estimados inicialmente. Parte da diferenca pode ser
   devida a entes do estado (SC) e orgaos estaduais que requerem fontes
   especificas.
2. **Dependencia de fontes externas:** PNCP cobre principalmente municipios
   e orgaos municipais. Entes estaduais e federais requerem fontes
   adicionais (DOE-SC, SC Compras, ComprasGov).
3. **Necessidade de backfill:** O hiato de 1258 entes descobertos evidencia
   que as stories de expansao (1.1-3.3) sao pre-requisito para esta
   validacao.

### Pendentes Conhecidos

- [ ] Executar COVERAGE-1.1 a COVERAGE-3.3 (expansao de fontes)
- [ ] Revisar COVERAGE-3.4 apos execucao do backfill (COVERAGE-3.3)
- [ ] Contratar API key DOM-SC (custo: R$0-500/ano)
- [ ] Avaliar certificado ICP-Brasil para TCE-SC (custo: R$300-800/ano)

### Decisao

**Epic em andamento — fases de implementacao necessarias antes da
validacao final.** Recomenda-se executar as stories de expansao (Fases 1-3)
e entao revisitar esta story de validacao com o backfill concluido.

---
*Gerado em: 2026-07-11 20:02*