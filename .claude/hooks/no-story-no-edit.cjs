#!/usr/bin/env node
'use strict';

/**
 * no-story-no-edit.cjs — PreToolUse hook.
 *
 * Bloqueia Edit/Write/Bash que modifiquem código sem story ativa e validada.
 * Exceções: FAST (typo/doc), read-only, config do próprio protocolo.
 *
 * Protocolo:
 * - Lê JSON do stdin (evento PreToolUse do Claude Code)
 * - Intercepta Edit, Write, Bash (comandos de alteração de código)
 * - Verifica existência de story ativa em docs/stories/
 * - Verifica se story está validada pelo PO (status != Draft)
 * - Permite FAST, investigação read-only, arquivos de protocolo
 */

const fs = require('fs');
const path = require('path');

/** Extensões de código que exigem story */
const CODE_EXTENSIONS = new Set([
  '.py', '.js', '.ts', '.tsx', '.jsx', '.sql', '.yaml', '.yml',
  '.toml', '.cfg', '.ini', '.json', '.sh', '.bash', '.zsh',
  '.html', '.css', '.scss', '.less', '.vue', '.svelte',
]);

/** Arquivos/padrões FAST — não exigem story */
const FAST_PATTERNS = [
  /^README\.md$/i,
  /\.md$/i,  // todos os markdown são FAST por padrão
  /^\.claude\//,   // arquivos do próprio protocolo
  /^\.env\.example$/,
  /^\.gitignore$/,
  /^\.prettierrc/,
  /^\.editorconfig$/,
  /^LICENSE$/i,
  /^CHANGELOG/i,
  /^CONTRIBUTING/i,
];

/** Arquivos que NUNCA são FAST mesmo sendo .md */
const NEVER_FAST = [
  /docs\/stories\//,
  /docs\/prd\//,
  /docs\/architecture\//,
];

/** Padrões de comando Bash que indicam alteração de código */
const CODE_EDIT_BASH_PATTERNS = [
  /\bsed\s+-i\b/,
  /\brm\s+-/,
  /\bmv\s+/,
  /\bcp\s+-.*\.(py|js|ts|sql)\b/,
  /\bgit\s+rm\b/,
  />\s*\S+\.(py|js|ts|sql)/,  // redirecionamento para arquivo de código
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

function isCodeFile(filePath) {
  if (!filePath) return false;
  const ext = path.extname(filePath).toLowerCase();
  if (!CODE_EXTENSIONS.has(ext)) return false;
  return true;
}

function isFastPath(filePath) {
  if (!filePath) return false;
  const normalized = filePath.replace(/\\/g, '/');

  for (const never of NEVER_FAST) {
    if (never.test(normalized)) return false;
  }
  for (const fast of FAST_PATTERNS) {
    if (fast.test(normalized)) return true;
  }
  return false;
}

function findActiveStory(projectRoot) {
  const storiesDir = path.join(projectRoot, 'docs', 'stories');
  let stories = [];
  try { stories = fs.readdirSync(storiesDir).filter(f => f.endsWith('.md')); }
  catch (_) { return null; }

  for (const storyFile of stories) {
    const storyPath = path.join(storiesDir, storyFile);
    try {
      const content = fs.readFileSync(storyPath, 'utf8');
      // Verificar status: Ready, InProgress, InReview
      const statusMatch = content.match(/^Status:\s*(.+)$/m);
      if (statusMatch) {
        const status = statusMatch[1].trim();
        if (status === 'Ready' || status === 'InProgress' || status === 'InReview') {
          return { file: storyFile, path: storyPath, status };
        }
      }
    } catch (_) {}
  }
  return null;
}

function isBashCodeEdit(command) {
  if (!command || typeof command !== 'string') return false;
  return CODE_EDIT_BASH_PATTERNS.some(p => p.test(command));
}

function isCodeEditTool(toolName) {
  return toolName === 'Edit' || toolName === 'Write' || toolName === 'NotebookEdit';
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

  // Bash: verificar comandos de edição de código
  if (toolName === 'Bash') {
    const command = toolInput?.command || '';
    if (!isBashCodeEdit(command)) return;
    // Bash code edit — verificar story
    const story = findActiveStory(cwd);
    if (!story) {
      emitDecision('deny', [
        '❌ BLOQUEIO: Comando de alteração de código sem story ativa.',
        '',
        'Protocolo AIOX seção 4: Story obrigatória antes de código.',
        `Comando: ${command.substring(0, 120)}`,
        '',
        'Ação necessária:',
        '  1. Solicite criação de story ao @sm',
        '  2. Aguarde validação do @po',
        '  3. Reexecute com story ativa',
        '',
        'Exceções: FAST, investigação read-only, arquivos de protocolo.',
      ].join('\n'));
    }
    return;
  }

  // Edit/Write/NotebookEdit: verificar arquivo
  if (isCodeEditTool(toolName)) {
    if (!filePath) return;  // sem arquivo, não podemos verificar

    // FAST: permitir
    if (isFastPath(filePath)) return;

    // Código: verificar story
    if (!isCodeFile(filePath)) return;  // não é código, permitir

    const story = findActiveStory(cwd);
    if (!story) {
      emitDecision('deny', [
        '❌ BLOQUEIO: Edição de código sem story ativa e validada.',
        '',
        `Arquivo: ${filePath}`,
        '',
        'Protocolo AIOX seção 4: Story obrigatória antes de código.',
        'Pré-condições: story com status Ready, InProgress ou InReview.',
        '',
        'Ação necessária:',
        '  1. @sm cria/refina story em docs/stories/',
        '  2. @po valida (status → Ready)',
        '  3. Reexecute a edição',
        '',
        'Exceções FAST: README.md, docs/*.md, .claude/*, .gitignore, LICENSE.',
        'Mudança trivial sem efeito funcional? Classifique como FAST e justifique.',
      ].join('\n'));
    }
    // Story ativa encontrada — permitir
  }
}

const timer = setTimeout(() => process.exit(0), 4000);
timer.unref();
main().then(() => process.exit(0)).catch(() => process.exit(0));

module.exports = { isCodeFile, isFastPath, findActiveStory, isBashCodeEdit };
