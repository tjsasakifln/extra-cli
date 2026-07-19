# CTO Autopilot — operação

Sistema operacional autônomo:

1. **Observer** (scripts) coleta estado determinístico  
2. **DeepSeek** decide como CTO (JSON estruturado)  
3. **Grok Build** executa em worktree isolada  
4. **Verifier** independente valida  
5. **CTO Review** aceita / repara / bloqueia / escala  
6. **GitHub Issues** = fila operacional  
7. **`DOD.md`** = contrato canônico  
8. **HTML executivo** = projeção derivada  

## Instalação

```bash
# Dependências já no requirements.txt: httpx, pyyaml, pydantic (opcional), openai
pip install -r requirements.txt

# GitHub CLI autenticado
gh auth status

# DeepSeek
export DEEPSEEK_API_KEY=...
export DEEPSEEK_BASE_URL=https://api.deepseek.com
export DEEPSEEK_MODEL=deepseek-v4-pro
export DEEPSEEK_REASONING_EFFORT=high
```

Ou preencha `.env` (nunca commitar).

## Comandos

```bash
python3 -m scripts.cto.cli doctor
python3 -m scripts.cto.cli bootstrap
python3 -m scripts.cto.cli observe
python3 -m scripts.cto.cli issues-plan
python3 -m scripts.cto.cli issues-sync --dry-run
python3 -m scripts.cto.cli issues-sync --apply   # cria/atualiza Issues
python3 -m scripts.cto.cli decide --dry-run
python3 -m scripts.cto.cli decide
python3 -m scripts.cto.cli run-once --dry-run
python3 -m scripts.cto.cli run-once --mock       # executor mock controlado
python3 -m scripts.cto.cli status
python3 -m scripts.cto.cli pause
python3 -m scripts.cto.cli resume
python3 -m scripts.cto.cli audit
python3 -m scripts.cto.cli refresh-executive
DEEPSEEK_LIVE_TEST=1 python3 -m scripts.cto.cli deepseek-smoke
```

Makefile: `make cto-doctor cto-bootstrap cto-observe cto-decide cto-run-once cto-status cto-audit issues-plan issues-sync executive-refresh`

## Hierarquia de verdade

1. `DOD.md`  
2. ADR  
3. Código testado  
4. Evidência  
5. Issues (fila)  
6. HTML (projeção)  
7. Chats — nunca canônico  

Fechar Issue **não** marca DoD. Checkbox DoD só com evidência objetiva.

## Human gates (somente Tiago)

Merge, deploy, gasto novo, migração destrutiva, mudança de significado do DoD, claim ao cliente, 3ª tentativa de reparo, decisão de produto sem PRD/DoD.

## Fallback DeepSeek

Se indisponível: `BLOCK` / `BLOCKED_CTO_UNAVAILABLE`, sem inventar trabalho, sem usar Grok como CTO.

## Publicação

worktree → branch → commits locais → verify → **draft PR** → CI → revisão → **merge humano**.  
Nenhum agente autônomo faz merge na v1.

## Desativar

```bash
python3 -m scripts.cto.cli pause
# ou remova timers; não há daemon habilitado por padrão
```

## Recuperação

```bash
python3 -m scripts.cto.cli status
python3 -m scripts.cto.cli resume
python3 -m scripts.cto.cli observe
```

Estado: `output/cto/current/state.json`  
Ledger: `output/cto/current/ledger.jsonl`  
Ciclos: `output/cto/cycles/<cycle-id>/`

## Testes

```bash
python3 -m pytest tests/cto -q
```

CI não chama DeepSeek real.
