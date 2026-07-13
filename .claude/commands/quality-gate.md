# /quality-gate — Gate de Qualidade Pre-Commit/Push

## Propósito

Gate rápido que roda formatadores, linters e type checkers sobre arquivos modificados.
Foco em velocidade (arquivo único ou diff, não projeto inteiro).

## Como Funciona

Roda análise em 3 camadas, para na primeira que falhar:

### Camada 1 — Formatação (rápida)

```bash
# Python
ruff format --check "$FILE"

# Se ECC_QUALITY_GATE_FIX=true → aplica formatação
ruff format "$FILE"
```

### Camada 2 — Lint (média)

```bash
ruff check "$FILE"
```

### Camada 3 — Type Check (lenta, opcional)

```bash
mypy "$FILE" --strict
```

## Uso

### Manual (arquivo específico)

```bash
# Check apenas
python -c "
import subprocess, sys
file = '$1'
results = {}
# ruff format
r = subprocess.run(['ruff', 'format', '--check', file], capture_output=True)
results['format'] = r.returncode == 0
# ruff check
r = subprocess.run(['ruff', 'check', file], capture_output=True)
results['lint'] = r.returncode == 0
# report
for check, passed in results.items():
    print(f'{'✅' if passed else '❌'} {check}')
sys.exit(0 if all(results.values()) else 1)
"
```

### Via hook PreToolUse (automático)

Configurar em `.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/quality-gate.sh"
          }
        ]
      }
    ]
  }
}
```

## Variáveis de Ambiente

| Variável | Efeito |
|----------|--------|
| `ECC_QUALITY_GATE_FIX=true` | Aplica correções de formatação automaticamente |
| `ECC_QUALITY_GATE_STRICT=true` | Falha de formatação = falha do gate |
| `SKIP_QUALITY_GATE=1` | Pula o gate completamente |

## Cobertura por Tipo de Arquivo

| Extensão | Formatação | Lint | Type Check |
|----------|-----------|------|------------|
| `.py` | `ruff format` | `ruff check` | `mypy` |
| `.yaml`, `.yml` | — | `yamllint` | — |
| `.json` | `python -m json.tool` | — | — |
| `.md` | — | — | — |

## Saída

```
🔍 Quality Gate: scripts/crawl/monitor.py
✅ format  (ruff)
✅ lint    (ruff check — 0 issues)
✅ types   (mypy — Success)
━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ PASS — all gates cleared
```

```
🔍 Quality Gate: scripts/intel_pipeline.py
✅ format  (ruff)
❌ lint    (ruff check — 3 issues)
   scripts/intel_pipeline.py:42: F841 variable 'x' unused
   scripts/intel_pipeline.py:87: E501 line too long (98 > 88)
   scripts/intel_pipeline.py:156: B006 mutable default arg
━━━━━━━━━━━━━━━━━━━━━━━━━━
❌ FAIL — fix lint issues before commit
```

## Integração com /code-review

`/quality-gate` → gate rápido (formatação + lint).  
`/code-review` → review completo (segurança + padrões + testes).

Rode `/quality-gate` antes de cada commit.  
Rode `/code-review` antes de cada push/PR.
