# CHAMPION BET — Maior Retorno Assimétrico

**Data:** 2026-07-14
**Método:** 5 subagentes paralelos read-only → consolidação → scoring → decisão
**Evidências:** `.reversa/baseline/0{1,2,3,4,5}-*.md`

---

## 1. Matriz de Apostas Avaliadas

| # | Aposta | Usuário | Decisão melhorada | Freq | Valor imediato | Reuso | Dados cumul. | Esforço | Risco | Score |
|---|--------|---------|-------------------|------|---------------|-------|-------------|---------|-------|-------|
| 1 | **Golden Path Operacional** (DB persistente + crawl + briefing) | Tiago | Perseguição (Go/No-Go) | 5 | 4 | 5 | 4 | 1 | 1 | **3000** |
| 2 | Briefing→Decisão Pipeline (briefing + recomendação + ledger) | Tiago | Perseguição + Precificação | 4 | 5 | 5 | 5 | 2 | 2 | **1250** |
| 3 | Correção de Qualidade de Dados (604 entidades + contradições) | Tiago | Confiança na cobertura | 2 | 3 | 4 | 2 | 3 | 2 | **16** |
| 4 | Dossiê Automatizado de Edital | Tiago | Perseguição | 3 | 4 | 2 | 2 | 5 | 5 | **3.8** |
| 5 | Monitoramento Executivo Periódico | Diretoria | Estratégica | 2 | 3 | 4 | 2 | 2 | 1 | **48** |

### Fórmula

```
ASYMMETRIC_RETURN_SCORE =
  (immediate_client_value × usage_frequency × decision_leverage ×
   reuse_of_existing_assets × proprietary_data_compounding × confidence)
  /
  (implementation_effort × operational_complexity × regression_risk × dependency_uncertainty)
```

Escala: 1-5 para cada fator.

---

## 2. Justificativa da CHAMPION_BET

### Aposta Selecionada: **Golden Path Operacional**

> Corrigir infraestrutura de dados (DB persistente, DSN unificado), executar crawl PNCP, popular opportunity_intel, e validar o comando `briefing` com dados reais.

### Por que esta aposta?

**Evidência dos 5 subagentes:**

1. **Valor Comercial** (agente 01): A decisão de perseguição (Go/No-Go) é a mais frequente (diária, 5-10 editais/dia) e uma das de maior valor (R$100K-500K/ano). Tiago gasta 2-4h/dia em busca manual que o sistema já deveria automatizar.

2. **Ativos Reutilizáveis** (agente 02): 23 CLIs implementados, scoring deterministico com 20 regras, ranking GO/REVIEW/NO_GO, radar QW-01 com 8 artefatos de output. Tudo já construído — só não funciona por bloqueio de infraestrutura.

3. **Verdade dos Dados** (agente 03): Banco é tmpfs (VOLÁTIL). 22/27 tabelas vazias. Pipeline nunca rodou. Credenciais não configuradas. Schema existe mas nunca foi povoado com dados reais.

4. **Fricção Operacional** (agente 04): Apenas 1 de 9 comandos funciona (extra_ledger). 6 quebram por falta de senha no DSN. 3 quebram por PYTHONPATH. O sistema inteiro é inútil no estado atual por uma única causa raiz: configuração de banco.

5. **Red Team** (agente 05): NENHUMA das 7 features deveria ser construída antes de estabilizar o baseline. "A feature mais importante é não construir features. É limpar a casa."

### Análise de sensibilidade

| Cenário | Fator alterado | Score resultante |
|---------|---------------|-----------------|
| PNCP API offline | dependency_uncertainty=4 | 750 |
| Crawl retorna <10 oportunidades | immediate_client_value=2 | 1500 |
| DSN fix é trivial (1 linha) | implementation_effort=0.5 | 6000 |
| DB requer migração complexa | implementation_effort=3 | 1000 |

Mesmo no pior cenário (PNCP offline), score=750 ainda supera a aposta #2 em condições normais.

### O gargalo econômico real

O sistema tem ~117K LOC, 14 crawlers, 1.230 testes, 48 migrations, scoring deterministico, ranking, radar, CLI, buyer intel, contract intel, extra ledger — e **zero valor comercial entregue** porque:

1. O banco é volátil (tmpfs)
2. O DSN não tem senha
3. Nenhum crawl foi executado
4. Nenhum pipeline rodou

Resolver isso não é construir nada novo. É destravar o que já existe.

---

## 3. KILL_LIST — O que NÃO será feito

### Features rejeitadas permanentemente (nesta execução)

| Item | Motivo |
|------|--------|
| Dossiê automatizado de edital | P&D de 6-12 meses. PDFs escaneados, formatos inconsistentes entre 2.085 órgãos. Red Team: "provavelmente nunca atinge precisão aceitável" |
| Apoio à preparação de proposta | Excel + conhecimento humano fazem melhor. Precificação depende de custo de insumos, logística, margem estratégica — dados não disponíveis |
| Acompanhamento contratual | PRD exclui. Dados internos de ERP, não públicos. Duplicaria função de ERP existente |
| Monitoramento executivo periódico | Panorama já existe. Só faltam systemd timers. Automatizar o que já funciona é low-prio |
| Inteligência de concorrentes (win rate) | Requer tracking de propostas enviadas. Extra Ledger tem 0 propostas. Impossível sem adoção |

### Infraestrutura rejeitada

| Item | Motivo |
|------|--------|
| Provisionar VPS Hetzner | Requer credenciais. Sem valor imediato. Local-first funciona |
| Migrar para Supabase | PRD diz "evoluir para Hetzner+Supabase quando fluxo local validado". Não validado |
| Backfill de 3 anos | Perfeccionismo. Dados antigos com schema diferente. Backfill útil = 12 meses |
| Geocodificar 604 entidades | Importante mas não bloqueia o golden path. Fazer depois |
| Corrigir 15 contradições de manifest | Importante mas não bloqueia o golden path. Fazer depois |
| Ativar 8 systemd timers | Só faz sentido com VPS provisionada |
| Integrar DOM-SC, DOE-SC, PCP | Bloqueados por credenciais externas |
| Migrations de schema adicionais | 48 migrations aplicadas. Suficiente para o golden path |

### Qualidade rejeitada

| Item | Motivo |
|------|--------|
| 100% test coverage | Meta é 85%+ nos módulos novos/alterados. Não elevar repo inteiro |
| MyPy zero erros | 769 erros. Meta é <50 nos caminhos críticos |
| Refatorar módulos estáveis | Não mexer no que funciona |
| Reorganizar pastas | Estética. Zero valor comercial |

### Anti-padrões explicitamente evitados

- Features para "futuros clientes"
- Abstrações para necessidades hipotéticas
- Relatórios que não serão usados em decisão real
- Dashboard genérico
- Documentação ornamental
- Trocar tecnologia sem blocker comprovado

---

## 4. Epic e Stories

### EPIC-GOLDEN-PATH-OPERACIONAL (novo, enxuto)

**Objetivo:** Fazer o sistema funcionar ponta a ponta com dados reais e gerar o primeiro briefing utilizável para a Extra.

**Métrica de sucesso:** Tiago executa 1 comando e obtém oportunidades priorizadas em <30s.

| ID | Story | Métrica de valor | Esforço |
|----|-------|-----------------|---------|
| GP-01 | Infraestrutura: DB persistente + DSN unificado | Elimina 6/9 comandos quebrados | XS |
| GP-02 | Crawl PNCP: popular opportunity_intel com dados reais | Primeiros dados de negócio no sistema | M |
| GP-03 | Golden path: validar briefing com dados reais | Briefing funcional em <30s | S |
| GP-04 | Productização: documentar, medir, publicar | Tiago consegue reproduzir sozinho | S |

---

## 5. Decisões de Design

1. **Persistência:** Volume Docker em vez de tmpfs. `docker-compose.local.yml` já tem estrutura para persistência.
2. **DSN:** Centralizar no `.env` com `DATABASE_URL`. Scripts leem `DATABASE_URL` → fallback `LOCAL_DATALAKE_DSN` → fallback hardcoded.
3. **Crawl:** PNCP apenas. Uma fonte, bem executada, é melhor que 8 fontes pela metade.
4. **Briefing:** Output Markdown. Sem PDF, sem Excel, sem dashboard. Clareza > formatação.

---

## 6. Riscos Residuais

| Risco | Prob | Impacto | Mitigação |
|-------|------|---------|-----------|
| PNCP API offline/rate-limited | Baixa | Alto | Fallback: usar dados existentes + aviso de stale |
| Dados insuficientes para SC (poucas oportunidades no raio 200km) | Média | Médio | Explicitar cobertura. Não inventar dados |
| Container reiniciado perde dados (persistência falha) | Baixa | Alto | Validar volume mount após setup |
| Script quebra em PYTHONPATH diferente | Média | Baixo | Documentar PYTHONPATH. Wrap em script de entrada |

---

## 7. Próximos Passos (ordenados por novo ASYMMETRIC_RETURN_SCORE)

1. **Golden Path Operacional** ← ESTA EXECUÇÃO
2. **Usar Extra Ledger de verdade** (registrar 1 decisão/semana) — dado proprietário começa a acumular
3. **Corrigir 604 entidades sem coordenadas** — desbloqueia cobertura confiável
4. **Ativar sistema de alertas** (Telegram ou similar) — "edital relevante apareceu"
5. **Pipeline de Preço Praticado** — quando base limpa + Extra Ledger com dados de propostas

---

## 8. Métricas Antes vs Depois (a medir)

| Métrica | Antes | Depois (alvo) |
|---------|-------|---------------|
| Comandos CLI funcionais | 1/9 (11%) | 5/9 (56%) |
| Tempo para lista de oportunidades | ∞ (não funciona) | <30s |
| Oportunidades no banco | 0 | >50 |
| Etapas manuais para briefing | ∞ | 1 comando |
| Fontes de dados ativas | 0 | 1 (PNCP) |
| Dados persistentes | Não (tmpfs) | Sim (volume) |
| Decisões registradas no Ledger | 1 | 1+ (habilitado) |

---

*Decisão tomada com base em 5 investigações paralelas independentes. Execução iniciada imediatamente.*
