# Relatorio de Debito Tecnico -- Extra Consultoria

**Preparado por:** @analyst (Atlas)
**Data:** Julho 2026
**Classificacao:** Confidencial -- Uso Interno
**Documento Fonte:** `docs/prd/technical-debt-assessment.md` (FINAL v1.0, validado por @architect, @data-engineer e @qa)

---

## Executive Summary

### Situacao Atual

A Extra Consultoria opera uma plataforma de inteligencia em licitacoes publicas que monitora 2.085 orgaos de Santa Catarina em 5+ fontes de dados abertos. O sistema e 100% funcional e ja processou 3.7M+ registros de contratos e licitacoes em um banco de 4.1 GB. Porem, sua construcao priorizou entrega sobre qualidade -- e hoje o time enfrenta 4 problemas criticos que ameacam a continuidade do negocio.

O maior risco e a ausencia total de backup: 2+ anos de dados de licitacoes (4.1 GB) estao em uma unica maquina, sem nenhuma copia de seguranca. Uma falha de disco significaria perda irreversivel de todo o DataLake. Alem disso, o codigo nao tem testes automatizados (zero -- 0% de cobertura em 64 mil linhas), o que torna qualquer modificacao um voo cego. As migrations do banco de dados estao completamente divergentes do schema real -- nao e possivel recriar o ambiente a partir do codigo. E o modulo principal de crawl (BidsCrawler) tem imports quebrados que podem ter tornado a captura de dados do PNCP inoperante.

Foram identificados 38 problemas no total. Destes, **4 sao criticos** (risco imediato de perda de dados ou parada do sistema), **9 sao graves** (risco em semanas), **18 sao moderados** e **7 sao leves**. A resolucao completa exige 140 a 170 horas de trabalho tecnico especializado, com investimento estimado entre R$ 21.000 e R$ 25.500, distribuido em 10 a 11 semanas.

Nao resolver agora significa acumular risco: cada mes sem backup e uma roleta-russa com os dados do negocio, cada nova fonte de dados demora 3-5 dias para integrar, e cada novo contratado leva 2-3 semanas para ser produtivo.

### Numeros-Chave

| Metrica | Valor |
|---------|-------|
| Total de Problemas Identificados | 38 |
| Problemas Criticos (risco imediato) | 4 |
| Problemas Graves (risco em semanas) | 9 |
| Esforco Total para Resolver | 140-170 horas |
| Investimento Necessario | R$ 21.000 -- R$ 25.500 |
| Prazo Recomendado | 10-11 semanas (com sobreposicao de fases) |

### Recomendacao

**Resolver agora.** O custo de nao agir supera em 4x a 6x o investimento necessario. Um unico incidente de perda de dados (probabilidade alta, dado que nao ha backup) ja justificaria o investimento completo. Recomenda-se aprovacao do orcamento total de R$ 21.000 -- R$ 25.500 e inicio imediato da Fase 0 (Emergencia), que resolve os 2 riscos mais criticos em 8 horas de trabalho (R$ 1.200).

---

## Analise de Custos

### Custo de RESOLVER

| Categoria | Horas | Investimento (R$150/h) |
|-----------|-------|------------------------|
| Infraestrutura & Seguranca | 46 | R$ 6.900 |
| Qualidade de Codigo | 48 | R$ 7.200 |
| Performance & Robustez | 29 | R$ 4.350 |
| Documentacao & Padronizacao | 11.5 | R$ 1.725 |
| **TOTAL (minimo)** | **134.5** | **R$ 20.175** |
| **TOTAL (com margem de 10-20%)** | **140-170** | **R$ 21.000 -- R$ 25.500** |

**Detalhamento por categoria:**

- **Infraestrutura & Seguranca (46h, R$ 6.900):** Backup automatizado diario, correcao de imports quebrados, pipeline CI/CD, observabilidade e alertas, healthcheck unificado, renovacao automatica de API keys, senha removida do codigo fonte, hardening de rede do banco de dados.
- **Qualidade de Codigo (48h, R$ 7.200):** Suite de testes (0% para 60%+ de cobertura), refatoracao do modulo principal (687 linhas para modulos menores), consolidacao de crawlers duplicados, type hints, remocao de estado global mutavel, schema validation de YAMLs, padronizacao de imports e constantes.
- **Performance & Robustez (29h, R$ 4.350):** Otimizacao de queries com indexes (consultas de 30-60s para <1s), correcao do HNSW index de similaridade vetorial (hoje inutilizado), reconstrucao completa das migrations do banco, soft-delete em vez de DELETE fisico, TTL enforcement em tabelas de enriquecimento.
- **Documentacao & Padronizacao (11.5h, R$ 1.725):** Runbook operacional, guia de setup, troubleshooting, limpeza de dead code, constraints de integridade, padronizacao de logging e output.

### Custo de NAO RESOLVER (Riscos Acumulados)

| Risco de Negocio | Probabilidade | Impacto | Custo Potencial |
|------------------|---------------|---------|-----------------|
| Perda total do DataLake (sem backup, 4.1 GB) | Alta | Critico | R$ 30.000 -- R$ 80.000 (re-crawling de 2+ anos + oportunidade perdida) |
| Falha em crawlers (imports quebrados, dados desatualizados) | Alta | Alto | Perda de oportunidades de negocio com dados obsoletos |
| Vulnerabilidade de credenciais (senha em texto puro no GitHub) | Media | Alto | R$ 10.000 -- R$ 50.000 (contencao de vazamento + compliance) |
| Lentidao em consultas (3.7M registros, full table scans) | Media | Medio | Horas de analista perdidas esperando queries |
| Impossibilidade de escalar time (sem docs, sem testes) | Alta | Alto | R$ 15.000 -- R$ 30.000/ano em baixa produtividade de novos devs |
| Falha de infra sem monitoramento (downtime silencioso) | Baixa | Critico | Dias de coleta perdida sem alerta |

**Custo potencial estimado de nao agir: R$ 55.000 -- R$ 160.000+**

---

## Impacto no Negocio

### Velocidade de Entrega

- **Tempo para adicionar nova fonte de dados:** 3-5 dias (atual) -> 4-8 horas (apos resolucao)
- **Bugs em producao:** Sem testes hoje, cada deploy e um risco. Com cobertura >= 60%, reducao estimada de 70-80% de bugs silenciosos.
- **Onboarding de novo desenvolvedor:** 2-3 semanas (atual) -> 2-3 dias (apos documentacao e CI/CD)

### Confiabilidade

| Aspecto | Hoje | Apos Resolucao |
|---------|------|----------------|
| Risco de perda de dados | **ALTO** -- zero backup | Baixo -- backup diario automatizado com retention de 7+4 |
| Cobertura de testes | **0%** -- 64K linhas sem testes | >= 60% nos modulos core, >= 30% no geral |
| Crawlers com resume | **0** -- se cair, perde progresso | Todos os crawlers com checkpoint e resume automatico |
| Deploy seguro | **Nao existe** -- tudo via SSH manual | CI/CD com lint + typecheck + testes por PR |

### Seguranca

| Aspecto | Hoje | Apos Resolucao |
|---------|------|----------------|
| Senhas no codigo fonte | **SIM** -- versionadas no git | Nao -- migradas para .env + pgpass |
| Backup automatizado | **NAO** | Sim -- diario via systemd timer |
| Monitoramento e alertas | **NAO** | Sim -- logging estruturado, metricas, alertas |
| Hardening de rede | **NAO** -- porta 54399 exposta | Sim -- firewall, fail2ban, acesso restrito |

### Escalabilidade

| Aspecto | Hoje | Apos Resolucao |
|---------|------|----------------|
| Capacidade de consulta | Full table scans em 3.7M registros (30-60s) | Queries sub-segundo com indexes otimizados |
| Fontes de dados | 1 funcional (PNCP), 1+ com problemas | 6+ fontes integradas com crawlers modulares |
| Carga de novos orgaos | Manual, sem padronizacao | Pipeline automatizado com schema validation |
| Expansao do time | Inviavel sem documentacao | Onboarding em dias com runbook e setup guide |

---

## Plano de Resolucao Recomendado

### Fase 0: Emergencia (Semana 1)
**Investimento: R$ 1.200 (8 horas)**

- Setup de backup automatico diario (pg_dump + Hetzner Storage Box, retention 7+4)
- Correcao de imports quebrados no BidsCrawler (ou documentacao como dead code)
- **Resultado:** Sistema para de perder dados imediatamente. Risco critico de perda do DataLake eliminado.

### Fase 1: Quick Wins (Semanas 1-2)
**Investimento: R$ 1.500 (10 horas)**

- Otimizacao de queries: GIN index + correcao HNSW
- Remocao de senha hardcoded do codigo fonte
- Inicio da suite de testes (modulo transformer.py, funcao pura)
- **Resultado:** Performance 10-50x mais rapida em consultas. Seguranca basica estabelecida.

### Fase 2: Fundacao Tecnica (Semanas 2-4)
**Investimento: R$ 2.850 (19 horas)**

- Reconstrucao completa das migrations (pg_dump --schema-only como baseline)
- Criacao de tabela _migrations para tracking
- Aplicacao de migrations pendentes adaptadas ao schema real
- Auditoria de divergencias schema vs codigo Python
- **Resultado:** Ambiente reproduzivel. Onboarding possivel. Deploy seguro.

### Fase 3: Refactoring Seguro (Semanas 3-6)
**Investimento: R$ 4.200 (28 horas)**

- Expansao da suite de testes (entity matching, loader, intel pipeline)
- Refatoracao do monitor.py (687 linhas -> modulos SRP)
- Consolidacao de crawlers PNCP (escolher sync ou async, remover duplicado)
- **Resultado:** Codigo mantivel. Testes protegem contra regression. Um crawler, nao dois.

### Fase 4: Qualidade de Codigo (Semanas 5-7)
**Investimento: R$ 3.000 (20 horas)**

- Type hints nos modulos core (incluindo funcao de 341 linhas)
- Remocao de estado global mutavel (cache IBGE)
- Centralizacao de constantes, schema validation YAML
- Padronizacao de upsert de contratos
- **Resultado:** Codigo profissional. PEP 8 compliant. YAML validado. Bugs mais faceis de encontrar.

### Fase 5: Resiliencia & Observabilidade (Semanas 7-10)
**Investimento: R$ 5.700 (38 horas)**

- CI/CD pipeline (GitHub Actions: lint + typecheck + tests)
- Logging estruturado (JSON, correlation IDs, metricas)
- Healthcheck unificado do sistema
- Soft-delete em vez de DELETE fisico
- Hardening de rede do PostgreSQL
- **Resultado:** Sistema profissional, monitorado, com deploy automatizado. Zero regressoes.

### Fase 6: Documentacao e Polish (Semanas 10-11)
**Investimento: R$ 1.725 (11.5 horas)**

- Runbook operacional, guia de setup, troubleshooting
- Limpeza de dead code e referencias a tabelas inexistentes
- Constraints de integridade, padronizacao de logging
- **Resultado:** Time autossuficiente. Qualquer desenvolvedor consegue operar o sistema.

### Cronograma Visual

```
Semana:   1  2  3  4  5  6  7  8  9  10 11
Fase 0   [==]
Fase 1   [====]
Fase 2       [======]
Fase 3          [==========]
Fase 4                [======]
Fase 5                      [==========]
Fase 6                            [====]
```

---

## ROI da Resolucao

### Investimento vs Retorno

| Cenaro | Investimento | Retorno Esperado | ROI |
|--------|-------------|------------------|-----|
| **Minimo** (apenas Criticos + Altos, 60-80h) | R$ 9.000 -- R$ 12.000 | R$ 50.000+ (riscos evitados) | **4:1 a 5:1** |
| **Recomendado** (resolucao completa, 140-170h) | R$ 21.000 -- R$ 25.500 | R$ 100.000+ (riscos evitados + ganhos de produtividade) | **4:1 a 5:1** |

### Ganhos Quantificaveis

| Metrica | Antes | Depois | Impacto no Negocio |
|---------|-------|--------|--------------------|
| Tempo para adicionar fonte de dados | 3-5 dias | 4-8 horas | 6x-10x mais rapido |
| Risco de perda de dados | Alto (sem backup) | Baixo (backup diario) | Tranquilidade operacional |
| Tempo de onboarding de novo dev | 2-3 semanas | 2-3 dias | Contratacao e expansao viraveis |
| Cobertura de testes | 0% | 60%+ (core) | Deploys sem medo de regressao |
| Crawlers com resume | 0 | Todos | Zero dados perdidos em falhas |
| Tempo de consulta (3.7M registros) | 30-60s (full scan) | <1s (com indexes) | Analises em tempo real |
| Senhas no codigo fonte | Sim | Nao | Seguranca profissional |
| CI/CD | Inexistente | Lint + test + typecheck | Qualidade garantida por PR |

### Payback Estimado

**3-4 meses** considerando apenas a economia de tempo da equipe tecnica (onboarding mais rapido, menos bugs, menos retrabalho).

**Imediato** considerando riscos evitados. Um unico incidente de perda de dados (probabilidade alta, dado que nao ha backup) custaria R$ 30.000 -- R$ 80.000 em re-crawling e oportunidade perdida -- valor que ja supera o investimento completo.

---

## Riscos de Nao Agir

### Cenario 1: Perda de Dados (Probabilidade: Alta)
Sem backup automatizado, 4.1 GB de dados de licitacoes de 2+ anos de crawling estao vulneraveis a falha de disco, erro humano ou incidente no servidor Hetzner.
**Custo estimado:** R$ 30.000 -- R$ 80.000 (re-crawling + oportunidade perdida durante o periodo sem dados)

### Cenario 2: Brecha de Seguranca (Probabilidade: Media)
Senha do banco de producao em texto puro em multiplos scripts versionados no git. Se o repositorio for comprometido (publico ou acesso indevido), o banco com 4.1 GB de dados fica exposto.
**Custo estimado:** R$ 10.000 -- R$ 50.000 (contencao + notificacao + possivel compliance)

### Cenario 3: Impossibilidade de Escalar (Probabilidade: Alta)
Sem documentacao, testes e CI/CD, cada novo desenvolvedor leva 3-4 semanas para ser produtivo. Cada nova fonte de dados leva 3-5 dias para integrar. O sistema atual nao escala com o negocio.
**Custo estimado:** R$ 15.000 -- R$ 30.000/ano em produtividade perdida

### Cenario 4: Deploy Quebra Producao (Probabilidade: Media)
Sem testes e sem CI/CD, toda alteracao manual via SSH carrega risco de quebrar o sistema em producao. Ja existem 2 crawlers concorrentes que podem estar divergindo em resultados.
**Custo estimado:** R$ 5.000 -- R$ 20.000 por incidente (diagnostico + correcao + dados perdidos)

---

## Proximos Passos

1. [ ] **Aprovar orcamento** de R$ 21.000 -- R$ 25.500
2. [ ] **Definir sprint inicial** (Fase 0 + Fase 1: R$ 2.700, 18 horas)
3. [ ] **Alocar time tecnico** (1-2 devs por 10-11 semanas)
4. [ ] **Iniciar Fase 0** (setup de backup + correcao de imports)
5. [ ] **Revisao mensal** de progresso contra os criterios de sucesso

---

## Anexos

- [Assessment Tecnico Completo](../prd/technical-debt-assessment.md) -- 38 debitos detalhados, 521 linhas
- [System Architecture](../architecture/system-architecture.md) -- Documentacao do sistema (606 linhas)
- [Database Schema](../../supabase/docs/SCHEMA.md) -- Estrutura do banco documentada
- [Database Audit](../../supabase/docs/DB-AUDIT.md) -- Auditoria detalhada de schema, seguranca e performance
- [DB Specialist Review](../prd/db-specialist-review.md) -- Revisao especializada do @data-engineer
- [QA Review](../prd/qa-review.md) -- Quality gate com 7.5/10 e 5 gaps identificados

---

*Documento gerado por Atlas (Business Analyst) em 2026-07-11.*
*Fase 9 do workflow Brownfield Discovery, framework AIOX.*
*Dados extraidos de `docs/prd/technical-debt-assessment.md` (FINAL v1.0).*
*Proximo passo: Fase 10 (Criacao de Epic + Stories por @pm).*
