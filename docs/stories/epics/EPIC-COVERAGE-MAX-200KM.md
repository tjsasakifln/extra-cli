# EPIC-COVERAGE-MAX-200KM — Radar Exaustivo e Produção VPS

**Criado:** 2026-07-15 | **Autor:** AIOX Master (Orion)
**Status:** Active | **Risk:** HIGH-RISK
**Depende de:** GP-01 (Golden Path concluído), EPIC-MASTER-B2G-READINESS (Fase 0 concluída)

---

## Problema Econômico

A Extra Construtora opera num raio de 200 km de Florianópolis. Existem 1.093 entes
públicos neste raio que publicam editais e contratos. Hoje, o sistema encontra dados
para apenas **67 entes (6.1%)** — quase todos prefeituras. As outras 1.026 entidades
(incluindo secretarias, autarquias, fundações, consórcios e órgãos do judiciário)
estão invisíveis para o sistema.

Cada edital de obra ou serviço de engenharia não detectado é uma oportunidade perdida.
Cada contrato não monitorado impede análise de concorrência e preços praticados.

**Custo da inação:** perda sistemática de oportunidades em 93.9% dos compradores
públicos no raio operacional.

---

## Hipótese

Com correções cirúrgicas no pipeline de cobertura existente, expansão seletiva para
fontes agregadoras de alto retorno e operação contínua em VPS, é possível elevar o
recall para >80% em 4 ondas de implementação.

---

## Escopo (IN)

1. Universo canônico de entes no raio de 200 km versionado e auditável
2. Reconciliação automatizada contra planilha de alvos
3. Cobertura PNCP: editais, contratos, atas e anexos com execução comprovada
4. Fontes estaduais: DOM-SC, DOE-SC, PCP, TCE-SC (expansão para municípios)
5. Portais de transparência municipais com adapter parametrizado
6. Deduplicação cross-source
7. Métricas de recall, freshness e source health com gates fail-closed
8. Provisionamento VPS idempotente com smoke test
9. Backup, restore e disaster recovery testados
10. Observabilidade com alertas de perda de cobertura

## Fora de Escopo (OUT)

- Frontend ou dashboard (CLI first — Constitution Art. I)
- Expansão para outros estados além de SC
- Acompanhamento de execução de obras
- Integração com CRM ou ERP
- Módulo de precificação automática
- IA generativa para análise de editais (adiado para V2)

---

## Métricas-Alvo

| Métrica | Baseline (15/Jul) | Alvo |
|---------|-------------------|------|
| Recall entes com dados | 6.1% | >80% |
| Recall prefeituras | 36.8% | >95% |
| Recall secretarias (via CNPJ prefeitura) | 0% | >70% |
| Contratos no banco | 0 | >50.000 |
| Fontes com dados operacionais | 1 | >5 |
| Freshness médio | Desconhecido | <48h para fontes críticas |
| Cobertura de anexos | 0% | >50% para editais |

---

## Ondas

| Onda | Nome | Stories | Recall gain estimado |
|------|------|---------|---------------------|
| 1 | Instrumentação | CM-01 a CM-05 | Baseline (0%) |
| 2 | Correções de alto retorno | CM-06 a CM-08, CM-13 | +35% (6% → 41%) |
| 3 | Expansão de fontes | CM-09 a CM-12 | +35% (41% → 76%) |
| 4 | Produção VPS | CM-15 a CM-20 | +4% (76% → 80%) |

---

## Stories (20)

| ID | Título | Onda | Dependências | Asymmetric Score | Status |
|----|--------|------|-------------|------------------|--------|
| CM-01 | Universo canônico de entes no raio de 200 km | 1 | — | — | ✅ DONE (Agente B) |
| CM-02 | Importador e normalizador da planilha de alvos | 1 | CM-01 | 85 | Ready |
| CM-03 | Reconciliação golden dataset e taxonomia de misses | 1 | CM-02 | 90 | Ready |
| CM-04 | Recall, freshness e source health por ente e fonte | 1 | CM-03 | 80 | Draft |
| CM-05 | Detecção fail-closed de zero anômalo e paginação truncada | 1 | CM-04 | 75 | Draft |
| CM-06 | Cobertura PNCP de editais e contratos (correção + backfill) | 2 | CM-05 | 95 | Ready |
| CM-07 | Cobertura DOM-SC e publicações suplementares (validação) | 2 | CM-05 | 70 | Draft |
| CM-08 | Cobertura PCP/TCE-SC com expansão para municípios | 2 | CM-05 | 65 | Draft |
| CM-09 | Framework parametrizado para famílias de portais municipais | 3 | CM-05 | 72 | Draft |
| CM-10 | Reparo do Transparência (detecção + scraping) | 3 | CM-09 | 85 | Draft |
| CM-11 | Segunda fonte/família com maior ganho marginal | 3 | CM-10 | 60 | Draft |
| CM-12 | Coleta de anexos, retificações e republicações | 3 | CM-06 | 55 | Draft |
| CM-13 | Deduplicação multicanal e aliases de compradores | 2 | CM-03 | 92 | ✅ DONE (bb4cad0) |
| CM-14 | Regression suite baseada em oportunidades reais conhecidas | 2 | CM-03 | 68 | Draft |
| CM-15 | Provisionamento idempotente de VPS | 4 | CM-06 | 50 | Draft |
| CM-16 | Operação headless de browser em Linux | 4 | CM-15 | 45 | Draft |
| CM-17 | Systemd, locks, concorrência e recuperação após reboot | 4 | CM-15 | 40 | Draft |
| CM-18 | Backup, restore e disaster recovery comprovados | 4 | CM-17 | 35 | Draft |
| CM-19 | Observabilidade e alertas de perda de cobertura | 4 | CM-04 | 30 | Draft |
| CM-20 | Go-live gate e runbook operacional | 4 | CM-18, CM-19 | 25 | Draft |

---

## Definition of Done do Epic

### Cobertura
- [ ] Universo-alvo canônico versionado (CM-01 ✅)
- [ ] 100% dos entes-alvo com estado de cobertura conhecido
- [ ] Recall mensurado contra planilha de alvos
- [ ] Misses classificados por causa-raiz
- [ ] Cobertura de contratos separada de editais
- [ ] Oportunidades duplicadas entre fontes consolidadas

### Operação
- [ ] Banco persistente com fresh install validado
- [ ] Crawlers incrementais com locks
- [ ] Source health e freshness automatizados
- [ ] Systemd validado com reboot
- [ ] Browser headless validado
- [ ] Backup + restore executados
- [ ] Runbook de incidente

### Qualidade
- [ ] Lint e type checking do caminho crítico
- [ ] Testes unitários e de integração offline
- [ ] Smoke test com fontes reais
- [ ] Regressão contra golden dataset
- [ ] Gates fail-closed para recall, freshness e zero anômalo

---

## Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|--------------|---------|-----------|
| API PNCP mudar sem aviso | Média | Alto | Circuit breaker + alerta + fallback |
| Portais municipais bloquearem crawlers | Alta | Médio | Rate limiting, UA rotation, ética |
| Hetzner não disponível/impedido | Baixa | Alto | Alternativa: qualquer Ubuntu LTS |
| Prazo exceder disponibilidade do sponsor | Média | Alto | Ondas independentes, cada uma entrega valor |

---

## Comandos de Validação

```bash
# Universo
python scripts/opportunity_intel/cli.py targets build --radius-km 200

# Cobertura
python scripts/consulting_readiness.py --radius-km 200 --threshold 0.80

# Reconciliação
python scripts/opportunity_intel/cli.py reconcile --targets config/target_entities_200km.csv

# Source health
python scripts/opportunity_intel/cli.py source-health

# Freshness
python scripts/freshness_gate.py

# Briefing
python scripts/opportunity_intel/cli.py briefing --dias 90

# VPS readiness
python scripts/opportunity_intel/cli.py readiness
```

---

*EPIC-COVERAGE-MAX-200KM — AIOX Master Orion, 2026-07-15*
