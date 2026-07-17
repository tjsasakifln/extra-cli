# ADR-021 — Adapter Architecture + PNCP 429 Fail-Closed

| Campo | Valor |
|-------|-------|
| **Status** | Accepted |
| **Data** | 2026-07-17 |
| **Decisores** | Architect, PM, Dev |
| **Epic** | E3 Resilient scheduled collection |
| **Relacionados** | ADR-019, ADR-020, td-3.2 PNCP resilience |

---

## Contexto

Múltiplos crawlers com contratos heterogêneos; PNCP sob rate limit (HTTP 429); casos adversariais de:

- zero resultados ambíguos;
- paginação prematura;
- hashes de conteúdo divergentes (adapter vs transformer);
- sucesso reportado com perda parcial de janela.

Política atual é **parcialmente** fail-open (avança janela / empty_confirmed) sem contrato único.

## Decisão

### 1. Arquitetura de adapter

Todo source implementa contrato canônico:

```text
SourceAdapter
  identity: source_id, capabilities, sla_hours
  fetch(request) -> FetchResult
  normalize(raw) -> list[CanonicalRecord]   # puro, testável
  health() -> SourceHealth
```

`FetchResult` **obrigatório**:

| Campo | Significado |
|-------|-------------|
| `status` | `success` \| `empty_confirmed` \| `partial` \| `rate_limited` \| `auth_blocked` \| `error` |
| `records` | lista raw ou path para raw (ADR-020) |
| `http_statuses` | multiset / samples |
| `pages_fetched` / `pages_expected` | se paginado |
| `resume_token` / checkpoint | para retoma |
| `provenance` | request params, fetched_at, content hashes |

Raw persiste antes de normalize (raw zone). Normalize não faz I/O de rede.

### 2. Fail-closed em 429 e perda

| Situação | Comportamento obrigatório |
|----------|---------------------------|
| HTTP 429 | `status=rate_limited`; **não** marcar janela como success/empty; backoff + checkpoint; alerta |
| 200 + body de erro / HTML inesperado | `status=error` ou `partial`; não empty_confirmed |
| `pages_fetched < pages_expected` sem motivo | `partial`; fail-closed no gate de coverage da janela |
| 0 records + empty_confirmed credível | `empty_confirmed` (único caso de “zero ok”) |
| Auth missing | `auth_blocked`; bindings ESR → blocked |

**Fail-closed** significa: jobs de agregação/coverage/relatório **não** podem declarar `GO` / `success` para uma fatia com `rate_limited` ou `partial` não reconciliado.

### 3. PNCP específico

- Pacing global e por rota; circuit breaker abre em série de 429.
- Janelas de backfill dimensionadas para caber no budget diário.
- Um único `content_hash` canônico pós-normalize (eliminar dual-hash silencioso).
- Path proof de N dias só é `success` se todas as fatias diárias `success|empty_confirmed`.

### 4. Integração ESR (ADR-019)

Adapters preferem **target set** de entidades/bindings quando o modo é coverage-oriented; full national scan é job explícito com budget.

## Alternativas rejeitadas

| Alternativa | Motivo |
|-------------|--------|
| Fail-open “melhor ter algum dado” | Gera falsos 95% e briefings mentirosos |
| Um crawler monólito PNCP só | Já existe dívida; contrato > reescrita total imediata |
| Retry infinito em 429 | Piora ban e mascara falta de budget |

## Consequências

- Refactors incrementais nos adapters (não big-bang).
- Testes de contrato por status enum.
- E3 stories incluem chaos de 429 simulado.
- Observabilidade: contadores rate_limited/partial por fonte/dia.

## Critérios de aceite

- [x] Enum de status documentado e usado nos adapters prioritários (PNCP, SC Compras, CIGA)
- [x] Teste: 429 → não emite evidence success para a fatia
- [x] Checkpoint retoma após rate_limited
- [x] SHA-256 do JSON canônico é a identidade do caminho ADR-021; hashes legados ficam explicitamente fora desse contrato

Implementação de referência: `scripts/crawl/resilience/`; evidência e limites em
`docs/operations/PRE-VPS-READINESS.md`. O aceite é local e não implica ativação
de scheduler ou VPS.

## Referências

- `docs/audits/adversarial-coverage-qa-2026-07.md`
- `docs/architecture/source-acquisition-strategy.md`
- Epic E3
