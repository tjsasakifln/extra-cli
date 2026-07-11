# Config — Design

> Gerado pelo Writer em 2026-07-11T22:30:00Z | doc_level: completo

## Settings Architecture
```
.env → config/settings.py → os.getenv() com defaults → módulos Python
```

## Sector Config Structure (YAML)
```yaml
engenharia:
  cnae_prefixes: [4120, 4211, 4212, ...]  # 17 prefixes
  sector_hints: [construção, obra, pavimentação, ...]
  heuristic_patterns:
    strong_compat: [...], strong_incompat: [...], weak_compat: [...]
  cross_sector_exclusions: [...]
  cnae_gate_threshold: 0.45
  weight_profile: {hab: 0.25, fin: 0.25, geo: 0.15, prazo: 0.15, comp: 0.20}
  llm_fallback: {enabled: true, confidence_threshold: 0.40, model: gpt-4.1-nano}
```

## Logging JSON Format
```json
{"timestamp": "...", "level": "INFO", "module": "crawl.pncp",
 "correlation_id": "a1b2c3d4e5f6", "message": "...", "extra_data": {...}}
```
contextvar-based correlation_id: thread-safe + async-safe.

## Abbreviations
18 public admin abbreviations (SEC→SECRETARIA, MUN→MUNICIPIO, PM→PREFEITURA MUNICIPAL, etc.). Word-boundary regex, longest-first ordering.

🟢 CONFIRMADO
