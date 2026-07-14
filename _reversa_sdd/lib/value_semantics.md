# Lib — Value Semantics (Semântica de Valores)

> Gerado pelo Writer em 2026-07-13T16:30:00Z | doc_level: completo | Base: e9729e1

**Módulo:** `scripts/lib/value_semantics.py` (257 linhas)
**Dependência:** HARD — contract_intel, coverage (commercial metrics), relatórios financeiros
**Referência externa:** ADR-015 (Semantic Value Stages), plano-mestre §14 (P1-01 Preço Praticado), ADR-002

---

## Interface

### Enum ValorSemantica

```python
class ValorSemantica(Enum):
    ESTIMADO = "valor_estimado"       # Edital — o que o governo espera pagar
    HOMOLOGADO = "valor_homologado"   # Resultado da licitação — valor homologado
    CONTRATADO = "valor_contratado"   # Contrato assinado — teto máximo
    PAGO = "valor_pago"               # Empenho efetivo — o que foi pago
    GLOBAL = "valor_global"           # PNCP default — NÃO é preço praticado
```

### Mapeamento Fonte-Estágio

```python
SOURCE_VALUE_TYPES: dict[str, dict[str, ValorSemantica]] = {
    "pncp": {
        "bids":      ValorSemantica.ESTIMADO,    # pncp_raw_bids.valor_total_estimado
        "contracts": ValorSemantica.CONTRATADO,  # pncp_supplier_contracts.valor_global
    },
    "compras_gov": {
        "bids": ValorSemantica.HOMOLOGADO,        # 🟡 NÃO INGERIDO — documentado para futuro
    },
    "tce_sc": {
        "contracts": ValorSemantica.PAGO,          # 🟡 NÃO INGERIDO — documentado para futuro
    },
}
```

### Rótulos para Output

```python
VALOR_SEMANTICA_LABELS: dict[ValorSemantica, str] = {
    ValorSemantica.ESTIMADO:    "Valor estimado (edital)",
    ValorSemantica.HOMOLOGADO:  "Valor homologado (resultado da licitação)",
    ValorSemantica.CONTRATADO:  "Valor contratado (contrato assinado)",
    ValorSemantica.PAGO:        "Valor pago (empenhos efetivos)",
    ValorSemantica.GLOBAL:      "Valor global PNCP (não diferenciado)",
}
```

### Funções Públicas

| Função | Retorno | Descrição |
|--------|---------|-----------|
| `calculate_desagio(valor_estimado, valor_homologado, semantica)` | `dict \| None` | Calcula deságio entre valor estimado e valor homologado/contratado |
| `compute_bid_contract_desagio(valor_estimado, valor_global_contrato)` | `dict \| None` | Calcula deságio entre bid estimado e contrato (PNCP) |
| `aggregate_contract_values(contracts, value_field)` | `dict[str, float]` | Estatísticas agregadas sobre valores contratuais |
| `coluna_para_semantica(column_name)` | `ValorSemantica \| None` | Mapeia nome de coluna do banco para semântica |
| `rotulo_valor(column_name)` | `str` | Rótulo legível para uma coluna de valor |

### Estrutura de Retorno — Deságio

```python
{
    "valor_estimado": 1_000_000.0,
    "valor_homologado": 850_000.0,
    "desconto_absoluto": 150_000.0,
    "desagio_percentual": 15.0,
    "semantica": "estimado→contratado",
}
```

### Estrutura de Retorno — Aggregate

```python
{
    "total": 5_000_000.0,
    "avg": 500_000.0,
    "median": 450_000.0,
    "min": 100_000.0,
    "max": 1_200_000.0,
    "count": 10,
    "semantica": "valor_contratado (valor_global PNCP)",
}
```

---

## Fluxo Principal

### 1. Cálculo de Deságio

```
calculate_desagio(valor_estimado, valor_homologado, semantica)
├── Validar inputs (None → None, <=0 → None)
├── desconto = valor_estimado - valor_homologado
├── percentual = (desconto / valor_estimado) * 100.0
├── Arredondar para 2 casas decimais
└── Retornar dict com valor_estimado, valor_homologado, desconto_absoluto, desagio_percentual, semantica
```

### 2. Deságio Bid→Contrato (PNCP)

```
compute_bid_contract_desagio(valor_estimado, valor_global_contrato)
└── Delegar para calculate_desagio(semantica="estimado→contratado")
```

### 3. Agregação

```
aggregate_contract_values(contracts, value_field="valor_global")
├── Filtrar valores > 0
├── Ordenar
├── Calcular: total, avg, median, min, max, count
└── Retornar dict com semantica fixa "valor_contratado (valor_global PNCP)"
```

### 4. Mapeamento Coluna → Semântica

```
coluna_para_semantica(column_name)
├── "valor_total_estimado" ou "valor_estimado" → ESTIMADO
├── "valor_homologado" → HOMOLOGADO
├── "valor_global" → CONTRATADO
├── "valor_pago" → PAGO
└── outro → None
```

---

## Regras de Negócio

| # | Regra | Severidade |
|---|-------|-----------|
| RN-V01 | **`valor_global` do PNCP NÃO é "preço praticado"** — é o valor contratual máximo assinado (semântica CONTRATADO). Usar como "preço praticado" gera métricas inválidas. | 🔴 |
| RN-V02 | **Deságio só é válido entre estágios da MESMA licitação.** Comparar `valor_total_estimado` de um bid com `valor_global` de um contrato não relacionado é inválido. | 🔴 |
| RN-V03 | **5 estágios imutáveis**: ESTIMADO → HOMOLOGADO → CONTRATADO → PAGO. GLOBAL é indiferenciado e não pertence à cadeia. | 🔴 |
| RN-V04 | **Novas fontes devem declarar seu estágio semântico** antes da ingestão no `SOURCE_VALUE_TYPES`. Fontes sem declaração são BLOCKED para métricas financeiras. | 🟡 |
| RN-V05 | **`aggregate_contract_values()`** usa `valor_global` como default. Toda agregação DEVE explicitar qual coluna está agregando e qual semântica isso representa. | 🟡 |

---

## Dependências

| Dependência | Tipo | Uso |
|------------|------|-----|
| `enum` | stdlib | ValorSemantica |
| `statistics` | stdlib | (disponível, mas aggregate usa implementação manual) |
| ADR-015 | doc | Decisão arquitetural dos 5 estágios semânticos |
| plano-mestre §14 | doc | P1-01 Preço Praticado — dependente deste módulo |

---

## Riscos e Lacunas

| # | Risco/Lacuna | Status | Impacto |
|---|-------------|--------|---------|
| 🔴 L-V01 | **PREÇO PRATICADO NÃO IMPLEMENTADO.** O cálculo de preço praticado requer matching item-a-item entre proposta homologada e contrato assinado. Nenhum pipeline atual faz esse matching. `valor_global` é usado como proxy, o que é semanticamente incorreto (RN-V01). | 🔴 NÃO IMPLEMENTADO | Bloqueia P1-01 (preço praticado). Métricas comerciais ficam em NOT_READY. |
| 🟡 L-V02 | **Fontes complementares não ingeridas.** ComprasGov (HOMOLOGADO) e TCE/SC (PAGO) estão documentadas em `SOURCE_VALUE_TYPES` mas sem pipeline de ingestão. | 🟡 | Deságio real (estimado→pago) indisponível. |
| 🟢 L-V03 | Cálculo de deságio com proteção contra inputs inválidos (None, <=0). | 🟢 RESOLVIDO | ADR-015 implementado corretamente. |
| 🟡 L-V04 | **`coluna_para_semantica()` mapeia `valor_global` para CONTRATADO.** Isto é correto para PNCP contracts, mas `valor_global` também existe em outras tabelas com semântica diferente. | 🟡 | Risco de falsa semântica se mesma coluna existir em tabela diferente. |
| 🟡 L-V05 | **Não há validação de consistência** entre o `SOURCE_VALUE_TYPES` declarado e a coluna real no banco. Se a coluna for renomeada, o mapeamento quebra silenciosamente. | 🟡 | Teste de integração necessário para cada fonte. |
