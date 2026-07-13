#!/usr/bin/env node
'use strict';

/**
 * db-destructive-guard.cjs — PreToolUse hook v2.0.
 *
 * Bloqueia operações DB destrutivas sem story HIGH-RISK + snapshot + rollback.
 * Usa estado estruturado (.aiox/state/stories/) como fonte primária.
 */

const fs = require('fs');
const path = require('path');
const {
  findAnyStoryState,
  VALID_RISK_LEVELS,
} = require('./story-state.cjs');

const DESTRUCTIVE_DB_PATTERNS = [
  /\bDROP\s+(TABLE|DATABASE|SCHEMA|INDEX|VIEW|FUNCTION|TRIGGER|COLUMN)\b/i,
  /\bTRUNCATE\s+(TABLE\s+)?/i,
  /\bDELETE\s+FROM\b/i,
  /\bALTER\s+TABLE\b.*\bDROP\b/i,
  /\bALTER\s+TABLE\b.*\bRENAME\b/i,
  /\bREVOKE\b/i,
  /\bsupabase\s+db\s+push\b/i,
  /\bsupabase\s+db\s+reset\b/i,
  /\bsupabase\s+db\s+remote\s+commit\b/i,
  /\bdocker\s+exec\b.*\bpsql\b/i,
  /\bpsql\b.*\b-d\b/i,
  /\bpython.*\bexecute\b.*\bDROP\b/i,
  /\bpython.*\bcursor\.execute\b/i,
];

const MIGRATION_FILE_PATTERN = /db\/migrations\/\d{3}_.*\.sql$/;

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

function isDestructiveDB(command) {
  if (!command || typeof command !== 'string') return false;
  return DESTRUCTIVE_DB_PATTERNS.some(p => p.test(command));
}

function isMigrationFile(command) {
  if (!command || typeof command !== 'string') return false;
  return MIGRATION_FILE_PATTERN.test(command);
}

function hasRecentSnapshot(projectRoot) {
  const snapshotDir = path.join(projectRoot, 'db', 'snapshots');
  try {
    const files = fs.readdirSync(snapshotDir);
    const now = Date.now();
    const DAY_MS = 24 * 60 * 60 * 1000;
    for (const f of files) {
      const stat = fs.statSync(path.join(snapshotDir, f));
      if (now - stat.mtimeMs < DAY_MS) return true;
    }
  } catch (_) {}
  return false;
}

function isRemoteTarget(command) {
  if (!command || typeof command !== 'string') return false;
  return /\bremote\b/i.test(command) ||
         /\bproduction\b/i.test(command) ||
         /\bprod\b/i.test(command) ||
         /\bsupabase\s+db\s+push\b/i.test(command) ||
         /\bsupabase\s+db\s+remote\b/i.test(command) ||
         /\b--linked\b/i.test(command);
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
  if (input?.tool_name !== 'Bash') return;

  const command = input?.tool_input?.command || '';
  if (!isDestructiveDB(command)) return;
  if (isMigrationFile(command)) return;

  const cwd = input?.cwd || process.cwd();
  const story = findAnyStoryState(cwd);

  // Check HIGH-RISK story
  if (!story || story.risk_level !== 'HIGH-RISK') {
    emitDecision('deny', [
      '❌ BLOQUEIO: Operação DB destrutiva sem story HIGH-RISK.',
      '',
      `Comando: ${command.substring(0, 150)}`,
      '',
      'Requer:',
      '  1. Story com risk_level: "HIGH-RISK" em .aiox/state/stories/',
      '  2. Snapshot/backup recente (< 24h) em db/snapshots/',
      '  3. Plano de rollback documentado (rollback_plan no state file)',
      '',
      story ? `Story atual: ${story.story_id} (${story.risk_level})` : 'Nenhuma story encontrada.',
    ].join('\n'));
    return;
  }

  // Check snapshot
  if (!hasRecentSnapshot(cwd) && !story.snapshot_evidence) {
    emitDecision('deny', [
      '❌ BLOQUEIO: Sem snapshot/backup recente.',
      'Execute snapshot (@data-engineer: db-snapshot) antes de continuar.',
    ].join('\n'));
    return;
  }

  // Check rollback plan
  if (!story.rollback_plan) {
    emitDecision('deny', [
      '❌ BLOQUEIO: rollback_plan ausente no state file.',
      'Documente o plano de reversão antes de continuar.',
    ].join('\n'));
    return;
  }

  // Remote warning
  if (isRemoteTarget(command)) {
    emitDecision('allow', [
      '⚠️  ALERTA: Operação DB destrutiva em ambiente REMOTO.',
      `Story: ${story.story_id} (${story.risk_level})`,
      'Snapshot: verificado. Rollback: documentado.',
      'Confirme que esta operação é intencional.',
    ].join('\n'));
    return;
  }
}

const timer = setTimeout(() => process.exit(0), 4000);
timer.unref();
main().then(() => process.exit(0)).catch(() => process.exit(0));

module.exports = { isDestructiveDB, hasRecentSnapshot, isRemoteTarget };
