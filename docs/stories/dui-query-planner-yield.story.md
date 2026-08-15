# DUI-QP-01 — Query planner por yield real

Status: InReview
Risk: STANDARD

## Problem

Public search planejava queries sem instrumentar yield downstream. Volume de SERP não é o norte.

## Scope IN

Planner/benchmark em módulo próprio; famílias COMPANY/PERSON/ROLE/DOCUMENT/SITE_PATH; early-stop; adaptive budget; cache query+backend+policy; SearXNG primary / DDGS comparação; report versionado; policy v2 consumível por #393.

## Scope OUT

Rewrite de crawler, pattern engine, document miner, corroboration, Warmbly, web-cfg, SmartLic.

## AC

1. Cada query carrega família, backend, account/person, result count, useful URL, observed/identity yield, latency, failure, cache.
2. Família sem yield é reduzida; early-stop e adaptive budget valem; sem query duplicada.
3. Operador sem suporte não executa como sucesso; fallback nunca silencioso.
4. Benchmark 30 depois 100 (ou as contas reais disponíveis) produz query-yield-report e policy v2.
5. Testes: reproducibility, backend failure, unsupported operator, cache, early stop, budget, duplicate.

## DoD

Ver `docs/commercial-intelligence/query-yield-report.v2.md`.
