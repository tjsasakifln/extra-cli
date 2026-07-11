#!/usr/bin/env node
'use strict';

/**
 * Pre-Push Gate Hook — Bloqueia git commit/push sem validação local recente.
 *
 * Protocolo:
 * - Lê JSON do stdin (evento PreToolUse do Claude Code)
 * - Intercepta chamadas Bash contendo `git commit` ou `git push`
 * - Verifica se `.claude/.pre-push-passed` existe e tem < 5 minutos
 * - Se estiver ausente/stale: deny com instrução para rodar /pre-push
 * - Se estiver fresco: allow
 *
 * State file: .claude/.pre-push-passed (touch após validação bem-sucedida)
 * TTL: 300 segundos (5 minutos)
 *
 * @module pre-push-gate-hook
 */

const fs = require('fs');
const path = require('path');

/** Máximo de idade do state file (ms). */
const STATE_TTL_MS = 5 * 60 * 1000; // 5 minutos

/** Regex para detectar git commit ou git push. */
const GIT_PUSH_COMMIT_RE = /\bgit\s+(push|commit)\b/;

/** Regex para detectar que o agente está executando validação (não bloquear). */
const VALIDATION_RUNNING_RE = /\b(pre-push|prepush|pytest|npm test|npm run build|npx tsc|ruff check|mypy)\b/;

/**
 * Lê todo o stdin como JSON.
 * @returns {Promise<object>}
 */
function readStdin() {
  return new Promise((resolve, reject) => {
    let data = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('error', (e) => reject(e));
    process.stdin.on('data', (chunk) => { data += chunk; });
    process.stdin.on('end', () => {
      try { resolve(JSON.parse(data)); }
      catch (e) { reject(e); }
    });
  });
}

/**
 * Verifica se o state file de validação está fresco.
 * @param {string} projectRoot — caminho absoluto da raiz do projeto
 * @returns {{fresh: boolean, ageSec: number|null, exists: boolean}}
 */
function checkValidationState(projectRoot) {
  const stateFile = path.join(projectRoot, '.claude', '.pre-push-passed');

  try {
    const stat = fs.statSync(stateFile);
    const ageMs = Date.now() - stat.mtimeMs;
    const ageSec = Math.round(ageMs / 1000);
    const fresh = ageMs < STATE_TTL_MS;
    return { fresh, ageSec, exists: true };
  } catch (e) {
    // Arquivo não existe ou não pode ser lido
    return { fresh: false, ageSec: null, exists: false };
  }
}

/**
 * Decide se deve bloquear com base no comando e estado de validação.
 * @param {string} command — o comando bash completo
 * @param {string} projectRoot — raiz do projeto
 * @returns {{block: boolean, reason: string}|null} null se não for git push/commit
 */
function evaluate(command, projectRoot) {
  // Só intercepta git push ou git commit
  if (!GIT_PUSH_COMMIT_RE.test(command)) {
    return null;
  }

  // Não bloquear se o agente está rodando validação junto com o commit
  // (ex: "cd backend && pytest ... && git commit ...")
  if (VALIDATION_RUNNING_RE.test(command)) {
    return null;
  }

  const state = checkValidationState(projectRoot);

  if (state.fresh) {
    return { block: false, reason: `✅ Pre-push validado há ${state.ageSec}s — permitido.` };
  }

  if (state.exists) {
    const min = Math.floor(state.ageSec / 60);
    const sec = state.ageSec % 60;
    return {
      block: true,
      reason: [
        `❌ PRE-PUSH GATE: Validação expirada (${min}m${sec}s atrás).`,
        '',
        'ANTES de git commit/push, execute:',
        '  1. /pre-push (matriz determinística do CLAUDE.md)',
        '  2. touch .claude/.pre-push-passed',
        '',
        'Policy: zero push sem validação local. CI não é teste gratuito.',
      ].join('\n'),
    };
  }

  return {
    block: true,
    reason: [
      '❌ PRE-PUSH GATE: Nenhuma validação local detectada.',
      '',
      'ANTES de git commit/push, execute:',
      '  1. /pre-push (matriz determinística do CLAUDE.md)',
      '  2. touch .claude/.pre-push-passed',
      '',
      'Docs-only? Touch .claude/.pre-push-passed diretamente (skip válido).',
      'Policy: zero push sem validação local. CI não é teste gratuito.',
    ].join('\n'),
  };
}

/**
 * Main hook pipeline.
 */
async function main() {
  const input = await readStdin();

  const toolName = input && input.tool_name;
  if (toolName !== 'Bash') return;

  const toolInput = input.tool_input;
  if (!toolInput) return;

  const command = toolInput.command;
  if (!command || typeof command !== 'string') return;

  const cwd = input.cwd || process.cwd();
  const result = evaluate(command, cwd);
  if (!result) return; // Não é git push/commit — ignora

  const output = JSON.stringify({
    hookSpecificOutput: {
      permissionDecision: result.block ? 'deny' : 'allow',
      permissionDecisionReason: result.reason,
    },
  });

  const flushed = process.stdout.write(output);
  if (!flushed) {
    await new Promise((resolve) => process.stdout.once('drain', resolve));
  }
}

/**
 * Safe exit — no-op inside Jest workers.
 * @param {number} code
 */
function safeExit(code) {
  if (process.env.JEST_WORKER_ID) return;
  process.exit(code);
}

/** Entry point runner. */
function run() {
  const timer = setTimeout(() => safeExit(0), 4000);
  timer.unref();
  main()
    .then(() => safeExit(0))
    .catch(() => {
      // Silent exit — nunca bloqueia por erro interno
      safeExit(0);
    });
}

if (require.main === module) run();

module.exports = { readStdin, main, evaluate, checkValidationState, run,
  STATE_TTL_MS, GIT_PUSH_COMMIT_RE, VALIDATION_RUNNING_RE };
