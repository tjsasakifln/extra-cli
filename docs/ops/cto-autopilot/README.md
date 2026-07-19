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

## Timer systemd user (opcional, desabilitado por padrão)

Arquivos de exemplo:

- `docs/ops/cto-autopilot/systemd-user.example.service`
- `docs/ops/cto-autopilot/systemd-user.example.timer`

O serviço de exemplo executa um ciclo **live conservador** (`run-once` **sem** `--dry-run`).
**Não** habilite sem ação explícita de Tiago.

```bash
# Ativar (manual)
mkdir -p ~/.config/systemd/user
# ajustar WorkingDirectory/EnvironmentFile nos units
cp docs/ops/cto-autopilot/systemd-user.example.service ~/.config/systemd/user/cto-autopilot.service
cp docs/ops/cto-autopilot/systemd-user.example.timer ~/.config/systemd/user/cto-autopilot.timer
systemctl --user daemon-reload
systemctl --user enable --now cto-autopilot.timer   # só após validação

# Pausar
systemctl --user stop cto-autopilot.timer
systemctl --user disable cto-autopilot.timer
python3 -m scripts.cto.cli pause

# Logs
journalctl --user -u cto-autopilot.service -n 100 --no-pager

# Rollback
systemctl --user disable --now cto-autopilot.timer
rm -f ~/.config/systemd/user/cto-autopilot.{service,timer}
systemctl --user daemon-reload
```

## Recuperação / resume real

`resume` continua idempotentemente a partir de PREPARING|EXECUTING|VERIFYING|REVIEWING|REPAIRING,
preservando session/worktree/decision/tentativas/evidências no diretório do ciclo.
Não imprime apenas `resume_target`.

```bash
python3 -m scripts.cto.cli status
python3 -m scripts.cto.cli resume --dry-run --mock --skip-tests
python3 -m scripts.cto.cli resume   # live mid-cycle
python3 -m scripts.cto.cli observe
```

## Publicação (publisher separado)

Após ACCEPT, o componente `scripts/cto/publisher.py` (nunca o Grok executor):

1. commit local controlado se necessário  
2. push da branch do ciclo  
3. abre/atualiza **draft PR**  
4. registra PR/commit na Issue + ledger  
5. consulta CI  
6. entra em `WAITING_HUMAN` com link da PR  

**Merge só com autorização de Tiago.** Sem merge automático.

```bash
python3 -m scripts.cto.cli publish --dry-run
```

## Códigos de saída

| Código | Significado |
|--------|-------------|
| 0 | OK / ciclo limpo |
| 10 | WAITING_HUMAN (ex.: draft PR pronta) |
| 11 | BLOCKED |
| 12 | FAILED |
| 13 | ROLLBACK |
| 2 | lock |
| 3 | budget/pause |

BLOCKED/FAILED/WAITING_HUMAN **não** são reportados como sucesso operacional genérico.

Estado: `output/cto/current/state.json`  
Ledger: `output/cto/current/ledger.jsonl`  
Ciclos: `output/cto/cycles/<cycle-id>/`

## Testes

```bash
python3 -m pytest tests/cto -q
```

CI não chama DeepSeek real.
