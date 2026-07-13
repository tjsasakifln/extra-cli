#!/usr/bin/env node
'use strict';

/**
 * enforce-git-push-authority.cjs — PreToolUse hook v2.0.
 *
 * Bloqueia operações remotas de Git/GitHub sem evidências reais de gates.
 * NÃO confia em env vars como autorização — usa estado estruturado.
 */

const fs = require('fs');
const path = require('path');
const { checkPushGate } = require('./story-state.cjs');

const REMOTE_OPERATION_PATTERNS = [
  { pattern: /\bgit\s+push\b/i,             operation: 'git push' },
  { pattern: /\bgh\s+pr\s+create\b/i,       operation: 'gh pr create' },
  { pattern: /\bgh\s+pr\s+merge\b/i,        operation: 'gh pr merge' },
  { pattern: /\bgit\s+tag\b/i,              operation: 'git tag' },
  { pattern: /\bgh\s+release\s+create\b/i,  operation: 'gh release create' },
];

const FORCE_PUSH_PATTERN = /\bgit\s+push\s+(-f|--force|--force-with-lease)\b/i;

// ── PROTOCOL PROTECTION CHECK ────────────────────────────────────────────────

const PROTOCOL_FILES = [
  /^CLAUDE\.md$/,
  /^\.claude\/CLAUDE\.md$/,
  /^\.claude\/hooks\//,
  /^\.claude\/rules\//,
  /^\.claude\/settings/,
  /^\.aiox-core\/constitution\.md$/,
];

function wereProtocolFilesModified() {
  try {
    const { execSync } = require('child_process');
    const changed = execSync('git diff --name-only HEAD', { encoding: 'utf8', timeout: 5000 }).trim();
    if (!changed) return false;
    const files = changed.split('\n');
    return files.some(f => PROTOCOL_FILES.some(p => p.test(f)));
  } catch (_) { return true; } // safety: block if can't verify
}

// ── HOOK HELPERS ─────────────────────────────────────────────────────────────

function readStdin() {
  try { return fs.readFileSync(0, 'utf8'); }
  catch { return ''; }
}

function parseInput(raw) {
  try { return JSON.parse(raw || '{}'); }
  catch { return null; }
}

function normalizeCommand(command) {
  return String(command || '')
    .replace(/\\\r?\n/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function findRemoteOperation(command) {
  const n = normalizeCommand(command);
  return REMOTE_OPERATION_PATTERNS.find(({ pattern }) => pattern.test(n)) || null;
}

function isForcePush(command) {
  return FORCE_PUSH_PATTERN.test(normalizeCommand(command || ''));
}

function emitDecision(permissionDecision, permissionDecisionReason) {
  process.stdout.write(JSON.stringify({
    hookSpecificOutput: {
      hookEventName: 'PreToolUse',
      permissionDecision,
      permissionDecisionReason,
    },
  }));
}

// ── MAIN ─────────────────────────────────────────────────────────────────────

function main() {
  const input = parseInput(readStdin());
  if (!input) {
    emitDecision('deny', 'Hook: failed to parse input. Blocking for safety.');
    return;
  }

  const command = input?.tool_input?.command || '';
  const cwd = input?.cwd || process.cwd();

  // 1. Force push: NEVER allowed
  if (isForcePush(command)) {
    emitDecision('deny', [
      '❌ BLOQUEIO: git push --force / --force-with-lease PROIBIDO.',
      '',
      'Policy: force push requer procedimento de autorização documentado.',
      'NÃO é permitido em nenhuma circunstância normal.',
    ].join('\n'));
    return;
  }

  // 2. Only intercept remote operations
  const operation = findRemoteOperation(command);
  if (!operation) return;

  // 3. Check protocol files weren't modified (hook integrity)
  if (wereProtocolFilesModified()) {
    emitDecision('deny', [
      '❌ BLOQUEIO: Arquivos de protocolo modificados durante implementação.',
      '',
      'Arquivos em .claude/hooks/, .claude/rules/, CLAUDE.md foram alterados.',
      'Push NÃO é permitido com hooks modificados — risco de bypass.',
      '',
      'Ação: Reverta alterações nos arquivos de protocolo antes do push.',
      'Manutenção de protocolo deve ocorrer em sessão separada.',
    ].join('\n'));
    return;
  }

  // 4. Evidence-based gate check (does NOT trust env vars)
  const gateResult = checkPushGate(cwd);
  if (!gateResult.ok) {
    emitDecision('deny', [
      '❌ GATE BLOQUEADO: ' + gateResult.reason,
      '',
      'Pré-condições EVIDENCE-BASED para push:',
      '  1. Story com status "Done" em .aiox/state/stories/',
      '  2. po_closed: true',
      '  3. qa_verdict: PASS, CONCERNS ou WAIVED',
      '  4. gates.lint, gates.tests: PASS',
      '  5. reviewed_commit === HEAD (código não alterado após QA)',
      '  6. Working tree limpa (git status --porcelain vazio)',
      '  7. publication_authorized: true',
      '  8. Nenhum arquivo de protocolo modificado',
      '',
      'NOTA: Identidade declaratória de agente NÃO é usada como autorização.',
      'Apenas evidências reais no state file são consideradas.',
    ].join('\n'));
    return;
  }

  // All gates passed — allow
}

if (require.main === module) main();

module.exports = {
  REMOTE_OPERATION_PATTERNS,
  findRemoteOperation,
  normalizeCommand,
  isForcePush,
  checkPushGate,
  wereProtocolFilesModified,
};
