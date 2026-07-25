# Runbook — ciclo local resiliente

> **SNAPSHOT / procedimento local** (fase pré-host e gates offline).  
> Estado operacional atual: [`README.md`](../../README.md) · [`docs/DEVELOPMENT.md`](../DEVELOPMENT.md) · [`DOD.md`](../../DOD.md).  
> Este arquivo **não** autoriza claims `LOCAL_READY` / `VPS_OPERATIONAL` / `PROJECT_DONE`.

Use `make resilience-gate` como entrada oficial. O target não acessa a internet:
valida as units, executa os testes críticos e roda o ciclo com fixtures.

Para diagnóstico consolidado, execute `python3 -m scripts.ops.health`. Para um
teste manual real e consciente, use `python3 -m scripts.ops.resilient_cycle
--live --source pncp` (ou `ciga_dom`, `sc_compras`). Um resultado parcial ou
rate limited é falha operacional esperada, não motivo para editar evidence.

Nunca apague checkpoints para “destravar” a coleta. Preserve o scope e repita o
mesmo comando; páginas completas serão recuperadas do raw. Consulte
`PRE-VPS-READINESS.md` para configuração, troubleshooting e critérios de VPS.
