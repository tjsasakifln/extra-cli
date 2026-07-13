#!/usr/bin/env node
'use strict';

/**
 * db-destructive-guard.cjs — PreToolUse hook.
 *
 * Bloqueia operações destrutivas em banco de dados sem story HIGH-RISK,
 * snapshot/backup e plano de rollback.
 *
 * Protocolo:
 * - Intercepta Bash com comandos SQL/DB destrutivos
 * - Exige story com nível HIGH-RISK
 * - Exige evidência de snapshot/backup recente
 * - Exige plano de rollback documentado
 * - Bloqueia em ambiente remoto/produção sem autorização explícita
 */

const fs = require('fs');
const path = require('path');

/** Padrões de comando destrutivo em banco */
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

/** Arquivos de migração que são seguros (já passaram por review) */
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

function findHighRiskStory(projectRoot) {
  const storiesDir = path.join(projectRoot, 'docs', 'stories');
  let stories = [];
  try { stories = fs.readdirSync(storiesDir).filter(f => f.endsWith('.md')); }
  catch (_) { return null; }

  for (const storyFile of stories) {
    const storyPath = path.join(storiesDir, storyFile);
    try {
      const content = fs.readFileSync(storyPath, 'utf8');
      const riskMatch = content.match(/^Risk Level:\s*(.+)$/im) ||
                        content.match(/^Nível de Risco:\s*(.+)$/im) ||
                        content.match(/^\*\*Risk:\*\*\s*(.+)$/im);
      const statusMatch = content.match(/^Status:\s*(.+)$/m);

      if (riskMatch && statusMatch) {
        const risk = riskMatch[1].trim().toUpperCase();
        const status = statusMatch[1].trim();
        if ((risk === 'HIGH-RISK' || risk === 'HIGH' || risk === 'CRITICAL' || risk === 'P0') &&
            (status === 'Ready' || status === 'InProgress' || status === 'InReview')) {
          return { file: storyFile, path: storyPath, risk, status };
        }
      }
    } catch (_) {}
  }
  return null;
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

function hasRollbackPlan(projectRoot, storyFile) {
  if (!storyFile) return false;
  const storyPath = path.join(projectRoot, 'docs', 'stories', storyFile);
  try {
    const content = fs.readFileSync(storyPath, 'utf8');
    return /\brollback\b/i.test(content) || /\breversão\b/i.test(content) ||
           /\brollback plan\b/i.test(content) || /\bplano de rollback\b/i.test(content);
  } catch (_) { return false; }
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
  if (isMigrationFile(command)) return;  // migration files são revisadas

  const cwd = input?.cwd || process.cwd();
  const story = findHighRiskStory(cwd);

  if (!story) {
    emitDecision('deny', [
      '❌ BLOQUEIO: Operação destrutiva de banco sem story HIGH-RISK.',
      '',
      `Comando: ${command.substring(0, 150)}`,
      '',
      'Protocolo AIOX: operações DB destrutivas exigem:',
      '  1. Story classificada como HIGH-RISK',
      '  2. Snapshot/backup recente (< 24h)',
      '  3. Plano de rollback documentado na story',
      '',
      'Ação necessária:',
      '  1. @sm cria story HIGH-RISK para esta operação',
      '  2. @data-engineer executa snapshot',
      '  3. @data-engineer documenta rollback',
      '  4. @po valida story',
      '  5. Reexecute com story ativa',
    ].join('\n'));
    return;
  }

  // Verificar snapshot
  if (!hasRecentSnapshot(cwd)) {
    emitDecision('deny', [
      '❌ BLOQUEIO: Snapshot/backup recente não encontrado.',
      '',
      'Operações DB destrutivas exigem snapshot com < 24h.',
      '',
      'Ação necessária:',
      '  1. @data-engineer: execute db-snapshot',
      '  2. Salve em db/snapshots/',
      '  3. Reexecute a operação',
    ].join('\n'));
    return;
  }

  // Verificar rollback
  if (!hasRollbackPlan(cwd, story.file)) {
    emitDecision('deny', [
      '❌ BLOQUEIO: Plano de rollback não documentado na story.',
      '',
      `Story: ${story.file}`,
      '',
      'Ação necessária:',
      '  1. Documente o plano de rollback na story',
      '  2. Inclua: comando de reversão, procedimento, responsável',
      '  3. Reexecute a operação',
    ].join('\n'));
    return;
  }

  // Alerta extra para remote
  if (isRemoteTarget(command)) {
    emitDecision('allow', [
      '⚠️  ALERTA: Operação DB destrutiva em ambiente REMOTO.',
      `Story: ${story.file} (${story.risk})`,
      `Snapshot: verificado. Rollback: documentado.`,
      '',
      'Confirme que esta operação é intencional e autorizada.',
    ].join('\n'));
    return;
  }

  // Tudo OK — permitir
  // (sem output = allow implícito)
}

const timer = setTimeout(() => process.exit(0), 4000);
timer.unref();
main().then(() => process.exit(0)).catch(() => process.exit(0));

module.exports = { isDestructiveDB, findHighRiskStory, hasRecentSnapshot, hasRollbackPlan, isRemoteTarget };
