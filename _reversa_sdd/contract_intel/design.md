# Contract Intelligence — Design Técnico (v1.0)

> Gerado pelo Writer em 2026-07-13 | doc_level: completo | Base: 249340d

## Interface

### CLI

| Comando | Entrada | Saída | Exit |
|---------|---------|-------|------|
| `historical --ente <key> --cnpj <c> --uf SC --years 3` | Filtros | Tabela/CSV 16 colunas | 0/1 |
| `suppliers --top 15 --uf SC` | Top N | Ranking com count, value, ticket, HHI | 0/1 |
| `expiring --days 90` | Janela dias | Contratos com vigência confiável | 0/1 |
| `manifesto --format json` | — | JSON/CSV readiness por capability | 0/1/2 |

### Classes Core

| Símbolo | Assinatura | Retorno | Observação |
|---------|-----------|---------|------------|
| `load_target_universe` | `(seed_path, radius_km)` | `TargetUniverse` | 1.093 entes, Haversine |
| `TargetUniverse.entities` | property | `list[TargetEntity]` | Entes dentro do raio |
| `TargetUniverse.duplicates` | property | `list[dict]` | CNPJ-base duplicados |
| `TargetUniverse.without_coords` | property | `list[dict]` | Entes sem coordenadas |

## Fluxo Principal

1. **Load universe:** `load_target_universe(seed, 200km)` → `TargetUniverse` com 1.093 entes 🟢
2. **Connect DB:** PostgreSQL connection, verificar views canônicas 🟢
3. **Query:** Usar `v_contracts_canonical`, `v_suppliers_canonical` (ou inline SQL se views indisponíveis) 🟢
4. **Compute metrics:** Market share, award share, HHI, concentração geográfica 🟢
5. **Readiness check:** Cada capability ≥ 95% → exit code 0 🟢
6. **Export:** JSON/CSV com metadados de run 🟢

## Fluxos Alternativos

- **SQLite fallback:** Views indisponíveis → queries inline adaptadas (nunca considerado "ready")
- **Sem seed:** Erro fatal, universo não pode ser inferido
- **Ente sem contratos:** Conta no denominador (conservador), não reduz cobertura

## Dependências

| Componente | Relação | Como usa |
|------------|--------|----------|
| `scripts/lib/universe.py` | Hard | CanonicalUniverse como base |
| `scripts/lib/geocode.py` | Hard | Haversine distance |
| PostgreSQL `v_contracts_canonical` | Hard | View canônica de contratos |
| PostgreSQL `v_suppliers_canonical` | Hard | View canônica de fornecedores |
| `db/migrations/026_contract_intel_truth_v1.sql` | Schema | Define schema operacional |

## Decisões de Design

| Decisão | Evidência | Confiança |
|---------|-----------|-----------|
| PostgreSQL views como camada canônica, SQLite apenas fixture | `cli.py:9-10` | 🟢 |
| valor_global = ticket contratual, NÃO preço praticado | `cli.py:14` | 🟢 |
| Denominador sempre inclui entes sem contrato | `cli.py:15` | 🟢 |
| Readiness threshold 95% | `cli.py:36` | 🟢 |
| EXTRA excluída do ranking competitivo | `plano-mestre §13` | 🟡 |

## Riscos e Lacunas

- 🔴 Métricas de competitive intel usam nomes de colunas incompatíveis com migration 026
- 🔴 Checkpoint de backfill marca janelas parciais como concluídas
- 🔴 Upsert com `DO NOTHING` impede atualização de contratos
- 🔴 Carregador de universo duplicado em `consulting_readiness.py`
- 🟡 Views canônicas (`v_contracts_canonical`, etc.) ainda não materializadas
