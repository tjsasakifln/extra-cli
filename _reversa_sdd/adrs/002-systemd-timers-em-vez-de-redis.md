# ADR-002: Systemd Timers em vez de Redis/ARQ

**Status:** Aceito
**Data:** 2026-07-10
**Decisor:** Tiago Sasaki
**Fonte:** `docs/architecture/architecture.md`, commit `c062f0a`

---

## Contexto

O sistema original usava ARQ (async task queue com Redis) para scheduling de crawlers. Na migração para standalone, o Redis era uma dependência adicional que precisava ser mantida.

## Decisão

**Usar systemd timers nativos do Linux para scheduling, removendo Redis e ARQ.**

## Justificativa

- Ubuntu 24.04 já tem systemd — zero dependências adicionais
- 13 timers com schedules escalonados cobrem todas as necessidades
- `RandomizedDelaySec=300` evita picos de carga
- Template `onfailure@.service` provê notificação de falhas
- Single-user: não precisa de fila distribuída

## Consequências

- ✅ Stack simplificada: sem Redis, sem ARQ
- ✅ systemd é nativo, estável e bem documentado
- ✅ `journalctl` provê logs centralizados
- ❌ Sem retry automático (mitigado por próximos disparos do timer)
- ❌ Sem dashboard de fila (não necessário para single-user)
