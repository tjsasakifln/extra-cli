# Contract Intelligence — Requirements (v1.0)

> Gerado pelo Writer em 2026-07-13 | doc_level: completo | Base: 249340d
> **Fontes brownfield:** plano-mestre §7 (P0-03), §12 (P0-08), §13 (P0-09); epic-technical-debt.md stories 1.3, 1.4

## Visão Geral

Contract Intelligence Truth v1 — consulta de contratos históricos, ranking de fornecedores e inteligência de concorrentes para o universo-alvo de 1.093 entes no raio de 200 km de Florianópolis. Opera sobre PostgreSQL views canônicas, com readiness manifest por capability e exit code padronizado.

## Responsabilidades

- Consulta de contratos históricos (3 anos) por ente, CNPJ ou UF
- Ranking de fornecedores (quantidade, valor, ticket médio, concentração geográfica)
- Contratos expirando em 90-180 dias (vigência confiável)
- Manifest de readiness por capability (historical_contracts, competitor_winners, expiring_contracts)
- Target universe: 1.093 entes dentro do raio com distância Haversine medida

## Regras de Negócio

- **Regra CI-01:** `valor_global` NÃO é "preço praticado" — é valor contratual (CONTRATADO, não PAGO). 🟢 `cli.py:14`
- **Regra CI-02:** Readiness threshold 95% — exit code ≠ 0 abaixo disso. 🟢 `cli.py:36`
- **Regra CI-03:** Denominador conservador: entidades sem contrato contam no denominador. 🟢 `cli.py:15`
- **Regra CI-04:** Entidades sem coordenadas são flagadas, nunca incluídas silenciosamente. 🟢 `target_universe.py:11`
- **Regra CI-05:** Duplicatas de CNPJ-base são contadas e reportadas, nunca deduplicadas silenciosamente. 🟢 `target_universe.py:12`
- **Regra CI-06:** Raio de 200 km explícito e reproduzível com Haversine. 🟢 `target_universe.py:13`
- **Regra CI-07:** Contratos só são classificados como "ativos" com: fim efetivo ≥ hoje, sem rescisão, status compatível, última atualização dentro do SLA. Caso contrário: `vigencia_desconhecida`. 🟡 `plano-mestre §13`

🔴 **LACUNA (plano-mestre §12):** Checkpoint parcial de contratos — janela com erro após alguma página é marcada como concluída. Upsert usa `DO NOTHING`, impedindo atualização de contratos alterados.
🔴 **LACUNA (plano-mestre §7):** Target universe ainda não é autoridade única. `consulting_readiness.py` mantém carregador duplicado. Views analíticas ainda filtram por `sc_public_entities.raio_200km`.

## Requisitos Funcionais

| ID | Requisito | Prioridade | Critério de Aceite |
|----|-----------|-----------|-------------------|
| RF-CI01 | `historical` — contratos 3 anos com filtros: ente, CNPJ, UF, período | Must | Query retorna colunas canônicas (16 campos) |
| RF-CI02 | `suppliers` — ranking top 15: quantidade, valor, ticket, órgãos, municípios, HHI | Must | Reproduzível, rastreável, usa `v_contracts_canonical` |
| RF-CI03 | `expiring` — contratos vincendos em 90-180 dias com vigência confiável | Must | Fim efetivo ≥ hoje, sem rescisão |
| RF-CI04 | `manifesto` — readiness por capability (JSON/CSV) com denominadores conservadores | Must | Exit code ≠ 0 se < 95% |
| RF-CI05 | Target universe: seed spreadsheet → 1.093 entes, Haversine, flags para sem-coord/duplicata | Must | Reproduzível com mesma seed |
| RF-CI06 | Excluir própria EXTRA do ranking competitivo | Must | EXTRA em seção separada |
| RF-CI07 | Versão canônica de contratos: atualizar em vez de `DO NOTHING` | Must | 🔴 Correção pendente (P0-08) |
| RF-CI08 | Market share, award share, HHI com nomes reais de colunas | Must | 🔴 Correção pendente (P0-09) |

## Requisitos Não Funcionais

| Tipo | Requisito inferido | Evidência | Confiança |
|------|--------------------|----------|-----------|
| Performance | Índices: órgão+data, fornecedor+data, source+source_id | `plano-mestre §12` | 🟡 |
| Auditabilidade | Todo run registra universe_run_id, git_sha, seed_sha256 | `cli.py`, `target_universe.py` | 🟢 |
| Portabilidade | PostgreSQL views como camada canônica; SQLite apenas fixture | `cli.py:9-10` | 🟢 |

## Critérios de Aceitação

```gherkin
Dado o universo-alvo de 1.093 entes no raio de 200km
Quando `contract_intel historical` é executado
Então contratos são retornados com colunas canônicas (16 campos)
E período padrão é 3 anos

Dado um fornecedor com 50 contratos no período
Quando `contract_intel suppliers` é executado
Então ranking inclui quantidade, valor total, ticket médio, órgãos
E EXTRA não aparece no ranking competitivo

Dado um contrato sem vigência confiável
Quando `contract_intel expiring` é executado
Então contrato NÃO aparece na lista de vincendos
E status é `vigencia_desconhecida`
```

## Prioridade (MoSCoW)

| Requisito | MoSCoW | Justificativa |
|-----------|--------|---------------|
| Target universe | Must | Fundação de todas as métricas |
| Contratos históricos | Must | Dados para concorrentes e preços |
| Ranking fornecedores | Must | Produto principal da consultoria |
| Manifest readiness | Must | Gate de qualidade |
| Correção checkpoint/DO NOTHING | Must | 🔴 P0-08 blocker |
| Contratos expirando | Should | P1-02, útil mas secundário |
