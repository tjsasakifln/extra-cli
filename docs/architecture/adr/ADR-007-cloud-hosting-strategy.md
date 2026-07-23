# ADR-007: Estratégia de Hospedagem em Nuvem

**Status:** Proposed
**Date:** 2026-07-15
**Decision by:** @architect (Aria) + @devops (Gage)

---

## 1. Contexto

A Extra Consultoria opera atualmente com datalake local (PostgreSQL em WSL/Windows). O plano de evolução prevê migração para infraestrutura em nuvem dedicada, com os seguintes direcionadores:

1. **Volume de dados:** após backfill completo e ciclos de coleta, espera-se mais de 4 milhões de contratos, centenas de milhares de editais e oportunidades, com crescimento contínuo.
2. **Execução contínua:** crawlers concorrentes, geração periódica de relatórios, manutenção de dados normalizados, históricos e registros de auditoria.
3. **Independência operacional:** o sistema deve executar 24/7 independentemente do ambiente local do desenvolvedor.
4. **Claude Code local:** o Claude Code será utilizado exclusivamente no ambiente local do desenvolvedor para interagir via CLI com os serviços em nuvem (SSH, Git, GitHub CLI, Ansible, OpenTofu/Terraform quando aplicável). Não será instalado nem executado na VPS.

### Restrição geográfica do PNCP — hipótese não comprovada

Existia uma premissa implícita de que a VPS precisaria estar no Brasil porque a API do PNCP poderia bloquear requisições originadas do exterior. Esta hipótese **não foi comprovada**.

**Evidências disponíveis:**

1. Não foi identificada, até o momento, restrição geográfica oficial documentada para consultas públicas da API do PNCP.
2. Existem inconsistências históricas no projeto relacionadas às versões e URLs da API do PNCP (migração v1→v2→v3, mudanças de schema, paginação).
3. Problemas anteriormente interpretados como possível bloqueio geográfico podem ter sido causados por endpoints obsoletos, parâmetros incorretos, mudanças de schema, paginação ou rate limiting.
4. O código atualmente utiliza `https://pncp.gov.br/api/consulta/v3` como endpoint canônico (story TD-8.3, settings.py L55).

**Teste de validação requerido:**

Antes da contratação definitiva de infraestrutura estrangeira, deve ser realizado um teste operacional comparativo da API do PNCP a partir de:
- Uma máquina no Brasil (controle);
- Uma máquina na costa leste dos Estados Unidos;
- Opcionalmente, uma máquina na Europa.

O teste deve usar o crawler real do projeto (`monitor.py --source pncp --mode full`), não apenas `curl` isolado. Devem ser registrados: status HTTP, latência, timeouts, respostas 403, 429 e 5xx, quantidade de registros, paginação e consistência do schema.

---

## 2. Volume Esperado e Dimensionamento de Referência

| Métrica | Estimativa |
|---------|-----------|
| Contratos | 4M+ após backfill |
| Editais/Oportunidades | Centenas de milhares |
| Fontes de dados | 5+ (crescimento contínuo) |
| Crawlers concorrentes | Sim |
| Relatórios periódicos | Sim |
| Dados normalizados, históricos e auditoria | Sim |

### Dimensionamento de referência inicial

| Recurso | Especificação |
|---------|--------------|
| RAM | 32 GB |
| CPU | Boa disponibilidade sustentada, preferencialmente dedicada |
| Armazenamento | ~1 TB NVMe, com possibilidade de expansão |
| PostgreSQL | 16 (versão canônica inicial) |
| SO | Ubuntu 24.04 LTS |

Este dimensionamento é uma referência de implantação inicial, não uma promessa de suficiência permanente. O crescimento real deve ser monitorado (disco, dead tuples, autovacuum, bloat) para orientar expansões futuras.

**4 milhões de registros não exigem arquitetura distribuída.** PostgreSQL em máquina única bem dimensionada é adequado. Não há necessidade comprovada de Kubernetes, Kafka, Redis, Elasticsearch ou filas distribuídas.

---

## 3. Opções Consideradas

### Opção A: Netcup Root Server (PREFERENCIAL)

Configuração equivalente ao RS 4000:
- CPU dedicada
- 32 GB RAM
- ~1 TB NVMe
- Localização preferencial na costa leste dos EUA (condicionada aos testes com PNCP)

**Prós:**
- Melhor custo-benefício para recursos dedicados
- CPU dedicada (não compartilhada)
- Grande capacidade de armazenamento NVMe
- Recursos adequados ao volume esperado

**Contras:**
- Sem API de infraestrutura (provisionamento manual ou via console)
- Sem CLI oficial para automação
- Sem suporte nativo a Terraform/OpenTofu
- Menor maturidade de ecossistema DevOps
- Localização nos EUA depende de validação do PNCP

**Status:** Candidata preferencial, sujeita a validação técnica (PNCP), comercial (preços, SLAs) e operacional (teste de acesso, latência).

### Opção B: Hetzner Cloud (ALTERNATIVA)

**Prós:**
- API de infraestrutura madura
- CLI oficial (`hcloud`)
- Integração com Terraform/OpenTofu
- Redes privadas, volumes, firewalls, snapshots
- Provisionamento automatizado
- Localização na Europa (Nuremberg, Helsinque) ou EUA (Ashburn)

**Contras:**
- Custo-benefício inferior ao Netcup para recursos dedicados
- vCPU compartilhada nos planos CX
- Planos dedicados (CCX) têm custo mais elevado
- Localização Europa → latência maior para o Brasil

**Status:** Alternativa viável, especialmente quando automação de infraestrutura (Terraform/OpenTofu) for valorizada.

### Opção C: Hetzner como baseline obrigatório (REJEITADA)

Documentos antigos mencionam Hetzner como baseline obrigatório. Esta premissa é removida. Hetzner permanece como alternativa, não como requisito.

---

## 4. Decisão

**Adotar Netcup Root Server (tipo RS 4000 ou equivalente) como candidata preferencial, condicionada a:**

1. Teste operacional comparativo da API PNCP a partir dos EUA (costa leste) vs. Brasil.
2. Validação comercial: preços, SLAs, suporte, política de expansão de disco.
3. Validação operacional: teste de acesso SSH, latência, estabilidade.
4. Disponibilidade de recursos no momento da contratação.

**Hetzner Cloud permanece como alternativa** quando automação de infraestrutura, snapshots, redes privadas ou múltiplas máquinas forem prioritários.

**Não fixar fornecedor definitivo nesta ADR.** A decisão final depende dos resultados dos testes com o PNCP e da disponibilidade comercial no momento da contratação.

---

## 5. Consequências

- Documentação deixa de presumir Hetzner como fornecedor obrigatório.
- Documentação deixa de presumir que a VPS precisa estar no Brasil.
- Documentação registra a necessidade de teste comparativo do PNCP como pré-condição para escolha de região.
- Dimensionamento de referência sobe de ~4 GB RAM / 40 GB SSD para 32 GB RAM / ~1 TB NVMe.
- Scripts de provisionamento específicos da Hetzner (`deploy/provision-vps.sh`) permanecem como implementação existente, mas a documentação operacional deve evoluir para ser provider-agnostic.
- Referências a Storage Box da Hetzner são substituídas por estratégia de backup desacoplada de provedor.

---

## 6. Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|--------------|---------|-----------|
| API PNCP bloquear IPs estrangeiros | Desconhecida (a testar) | Alto | Teste comparativo antes da contratação. Plano B: VPS no Brasil. |
| Netcup não ter disponibilidade no momento | Média | Médio | Hetzner como alternativa. Outros provedores (OVH, Linode) como fallback. |
| 1 TB ser insuficiente a médio prazo | Média | Médio | Monitorar crescimento. Expandir disco ou adicionar volume separado para raw data. |
| CPU dedicada ser superdimensionada | Baixa | Baixo | Melhor sobrar do que faltar. Crawlers concorrentes + PostgreSQL + relatórios consomem CPU. |

---

## 7. Condições para Revisão

Esta ADR deve ser revisada quando:
1. O teste comparativo do PNCP em múltiplas regiões for concluído.
2. Um fornecedor for selecionado definitivamente.
3. O volume real de dados após backfill completo for conhecido.
4. O custo operacional real do primeiro mês estiver disponível.

---

## 8. Referências

- Story TD-8.3: PNCP API v3 Migration (`docs/stories/epics/epic-td-003-reversa-remediation/story-TD-8.3-pncp-api-v3-migration.md`)
- PNCP API Research: `docs/research/pncp-api-2026-07-12.md`
- VPS Production Readiness Audit: `docs/audits/vps-production-readiness-2026-07.md`
- ADR-008: Infrastructure as Code Strategy (`docs/architecture/adr/ADR-008-infrastructure-as-code-strategy.md`)
- Cloud Deployment Plan: `docs/ops/cloud-deployment-plan.md`

## Amendment 2026-07-23 (runtime fact)

Operational host is **Netcup RS 2000 G12** with **Debian 13**, **PostgreSQL 17**, **16 GB RAM** (not Ubuntu 24.04 / PG16 / 32 GB reference). Pending-provider language is superseded for the contracts cutover path. Full ADR rewrite may follow; this amendment is the canonical runtime until then.
