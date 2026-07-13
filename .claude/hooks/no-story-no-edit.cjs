#!/usr/bin/env node
'use strict';

/**
 * no-story-no-edit.cjs — PreToolUse hook v2.0.
 *
 * Bloqueia Edit/Write/Bash que modifiquem código sem story ativa.
 * PROTOCOL-PROTECTED: bloqueia alteração de arquivos de enforcement.
 * Usa estado estruturado (.aiox/state/stories/) como fonte primária.
 */

const fs = require('fs');
const path = require('path');
const {
  isProtocolProtected,
  findActiveStoryState,
  isFastPath,
  isCodeFile,
} = require('./story-state.cjs');

const CODE_EDIT_BASH_PATTERNS = [
  /\bsed\s+-i\b/,
  /\brm\s+-/,
  /\bmv\s+/,
  /\bcp\s+-.*\.(py|js|ts|sql)\b/,
  /\bgit\s+rm\b/,
  />\s*\S+\.(py|js|ts|sql)/,
];

function readStdin() {
  return new Promise((resolve) => {
    let data = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', (chunk) => { data += chunk; });
    process.stdin.on('end', () => {
      try { resolve(JSON.parse(data)); }
      catch (_) { resolve({}); }
    });
    process.stdin.on('error', () => resolve({}));
  });
}

function isBashCodeEdit(command) {
  if (!command || typeof command !== 'string') return false;
  return CODE_EDIT_BASH_PATTERNS.some(p => p.test(command));
}

function isCodeEditTool(toolName) {
  return toolName === 'Edit' || toolName === 'Write' || toolName === 'NotebookEdit';
}

function getMaintenanceSessionActive(projectRoot) {
  try {
    const sentinel = path.join(projectRoot, '.aiox', 'state', '.maintenance-session');
    if (!fs.existsSync(sentinel)) return false;
    const stat = fs.statSync(sentinel);
    const ageMin = (Date.now() - stat.mtimeMs) / 60000;
    return ageMin < 30; // 30 min TTL
  } catch (_) { return false; }
}

function emitDecision(decision, reason) {
  process.stdout.write(JSON.stringify({
    hookSpecificOutput: {
      hookEventName: 'PreToolUse',
      permissionDecision: decision,
      permissionDecisionReason: reason,
    },
  }));
}

async function main() {
  const input = await readStdin();
  const toolName = input?.tool_name;
  if (!toolName) return;

  const toolInput = input?.tool_input || {};
  const filePath = toolInput?.file_path || '';
  const cwd = input?.cwd || process.cwd();

  // ── Bash commands ──────────────────────────────────────────────────────
  if (toolName === 'Bash') {
    const command = toolInput?.command || '';
    if (!isBashCodeEdit(command)) return;

    const story = findActiveStoryState(cwd);
    if (!story) {
      emitDecision('deny', [
        '❌ BLOQUEIO: Comando de alteração de código sem story ativa.',
        '',
        `Comando: ${command.substring(0, 120)}`,
        '',
        'Ação: @sm cria story → @po valida → reexecute.',
      ].join('\n'));
    }
    return;
  }

  // ── Edit/Write/NotebookEdit ────────────────────────────────────────────
  if (!isCodeEditTool(toolName)) return;
  if (!filePath) return;

  // ── PROTOCOL-PROTECTED check (runs BEFORE any other check) ─────────────
  if (isProtocolProtected(filePath)) {
    const maintenance = getMaintenanceSessionActive(cwd);
    if (!maintenance) {
      emitDecision('deny', [
        '❌ BLOQUEIO: Arquivo PROTOCOL-PROTECTED.',
        '',
        `Arquivo: ${filePath}`,
        '',
        'Arquivos de enforcement (.claude/hooks/, .claude/rules/, .claude/settings*,',
        '.aiox-core/constitution.md, CLAUDE.md) NÃO podem ser alterados durante',
        'tarefas normais (FAST, STANDARD ou HIGH-RISK).',
        '',
        'Para manutenção do protocolo:',
        '  1. Abra uma sessão SEPARADA (não esta implementação)',
        '  2. Digite: INICIAR MANUTENÇÃO DO PROTOCOLO AIOX',
        '  3. Faça as alterações necessárias',
        '  4. Execute TODOS os testes dos hooks',
        '  5. Encerre a manutenção explicitamente',
        '',
        'Policy: enforcement não pode ser modificado por implementação funcional.',
      ].join('\n'));
      return;
    }
    // Maintenance mode active — allow but log
    // (audit log would go here in production)
    return;
  }

  // ── FAST path ──────────────────────────────────────────────────────────
  if (isFastPath(filePath)) return;
  if (!isCodeFile(filePath)) return;

  // ── Story check via structured state ───────────────────────────────────
  const story = findActiveStoryState(cwd);
  if (!story) {
    emitDecision('deny', [
      '❌ BLOQUEIO: Edição de código sem story ativa.',
      '',
      `Arquivo: ${filePath}`,
      '',
      'Protocolo AIOX: Story obrigatória antes de código.',
      'Story deve estar em .aiox/state/stories/ com status Ready/InProgress/InReview.',
      '',
      'Ação: @sm cria story → @po valida → state file criado → reexecute.',
    ].join('\n'));
  }
  // Story ativa — permitido
}

const timer = setTimeout(() => process.exit(0), 4000);
timer.unref();
main().then(() => process.exit(0)).catch(() => process.exit(0));

module.exports = { isProtocolProtected, isFastPath, isCodeFile, getMaintenanceSessionActive };
