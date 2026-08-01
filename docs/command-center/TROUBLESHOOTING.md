# Troubleshooting

| Sintoma | Causa | Ação |
|---------|-------|------|
| API sobe mas UI JSON | `dist/` ausente | `cd apps/command-center && npm run build` |
| 403 em POST | CSRF | UI chama `/api/csrf` com credentials |
| Capability indisponível | módulo ausente no branch | esperado; reavaliar após rebase |
| Porta em uso | outro processo em 8765 | `CC_PORT=8766` |
| Browser não abre | headless | ignore; abra URL manualmente |
