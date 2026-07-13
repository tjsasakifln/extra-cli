# Avaliacao de Aderencia ao Proposito

Data: 2026-07-12

## Escopo real desta fase

Objetivo do projeto nesta fase:

- buscar editais de licitacoes abertas
- manter historico de contratos para analise
- mapear concorrentes e vencedores historicos
- apoiar leitura de precos praticados
- operar em datalake local enquanto a infraestrutura VPS/Supabase/cron nao e a fonte principal

Fora de escopo por enquanto:

- acompanhamento de obras
- monitoramento de execucao contratual em campo
- workflows operacionais de obra

## Veredito atual

O projeto ja possui base tecnica reutilizavel, mas **ainda nao atende de forma confiavel o proposito operacional** porque o requisito mais importante nesta fase, **freshness auditavel de editais e contratos historicos**, nao esta garantido de ponta a ponta.

Em termos praticos:

- editais abertos: capacidade parcial
- contratos historicos: capacidade parcial
- concorrentes/vencedores: capacidade parcial
- precos praticados/desagio: nao pronto
- freshness confiavel: nao pronto

## O que o projeto ja tem de util

- schema local PostgreSQL com tabelas para bids, contratos, cobertura e runs
- crawlers para PNCP e outras fontes candidatas
- manifests e CLIs para cobertura, oportunidades e contratos
- evidencias recentes de health/freshness para oportunidades via `opportunity-source-health.csv`
- testes para regras centrais de cobertura, status e readiness

## Gaps que impedem uso confiavel agora

### 1. Freshness de editais nao esta provada por universo-fonte

- O datalake local pode conter registros antigos ou incompletos.
- Parte dos manifests mede presenca de dados, nao prova de coleta fresca por ente e por fonte.
- Ainda existe diferenca entre "ha registro no banco" e "o ente foi efetivamente monitorado no periodo".

### 2. Freshness de contratos historicos nao esta operacionalizada

- O projeto tem historico de contratos, mas nao ha garantia consistente de recarga incremental recente por janela-alvo.
- Para uso consultivo, historico sem data de atualizacao auditavel por fonte perde valor analitico rapidamente.

### 3. Cobertura de 95% no raio de 200 km nao esta atingida

- A propria documentacao recente indica cobertura real bem abaixo da meta para dados persistidos no raio.
- Algumas fontes existem no codigo, mas nao estao provadas como ativas/frescas no ambiente local.

### 4. Preco praticado ainda nao esta pronto

- O sistema consegue expor valor contratual agregado e alguns sinais auxiliares.
- Isso nao equivale a preco praticado comparavel por item/lote.
- Desagio real continua dependente de linkage edital → proposta/homologacao → contrato.

### 5. Inteligencia competitiva ainda e incompleta

- Vencedores historicos existem parcialmente.
- Win rate real continua indisponivel sem rastrear propostas enviadas pela propria empresa.
- O que hoje e confiavel e mais proximo de market share historico do que win rate.

## Ordem recomendada para fechar gaps

### P0. Freshness auditavel

- definir SLA operacional local:
  - editais abertos PNCP: <= 24h
  - contratos historicos PNCP: <= 7 dias para incremental
  - fontes complementares: status explicito `fresh`, `stale`, `never`, `blocked`
- publicar `last_success_at`, `max_data_publicacao`, `max_data_assinatura/data_publicacao` por fonte
- falhar o gate quando houver fonte critica stale no ambiente local

### P0. Separar claramente quatro conceitos

- cobertura monitorada
- presenca de dados persistidos
- freshness de coleta
- prontidao comercial

Sem isso, o projeto parece mais pronto do que realmente esta.

### P1. Reativar pipeline minimo viavel de freshness

- PNCP editais incremental diario/multiplas ondas
- PNCP contratos incremental com checkpoint
- regeneracao automatica de manifests apos carga
- evidencias por run para provar coleta real

### P1. Consolidar cobertura real do raio de 200 km

- medir quais entes do raio possuem:
  - monitoramento fresco
  - pelo menos um edital recente
  - pelo menos um contrato historico
- rankear fontes por ganho marginal real, nao por expectativa

### P2. Concorrencia e precos

- expor market share/award share como entrega oficial
- manter win rate como `not_ready`
- manter desagio/preco praticado como `not_ready` ate existir linkage confiavel

## Quick win validado neste commit

- readiness comercial agora usa status semantico consistente `not_ready` em vez de misturar indisponibilidade estrutural com erro tecnico
- `win_rate` fica exposto tambem no topo de `commercial_metrics`, simplificando consumo por CLI e manifests
- teste de integracao do manifesto deixa de assumir falsamente que o datalake local contem oportunidades frescas

## Proximo bloco de implementacao sugerido

1. Criar um gate unico de freshness para o datalake local.
2. Marcar PNCP editais e PNCP contratos como fontes criticas.
3. Falhar com exit code nao-zero quando uma fonte critica estiver `stale` ou `never`.
4. Exportar um manifesto unico com:
   - `last_success_at`
   - `freshness_status`
   - `records_last_24h`
   - `records_last_7d`
   - `latest_business_date`

Sem esse bloco, qualquer analise de editais ou contratos continua dependente de base potencialmente obsoleta.
