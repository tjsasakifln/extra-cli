#!/usr/bin/env node
'use strict';

/**
 * Claude Code PreToolUse hook for Constitution Article II.
 *
 * Blocks remote Git/GitHub publication commands unless the active agent is
 * @devops. The hook is intentionally dependency-free so it can run from a
 * freshly installed AIOX package on macOS, Linux, WSL, and Windows.
 */

const fs = require('fs');

const path = require('path');

const REMOTE_OPERATION_PATTERNS = [
  {
    pattern: /\bgit\s+push\b/i,
    operation: 'git push',
  },
  {
    pattern: /\bgh\s+pr\s+create\b/i,
    operation: 'gh pr create',
  },
  {
    pattern: /\bgh\s+pr\s+merge\b/i,
    operation: 'gh pr merge',
  },
  {
    pattern: /\bgit\s+tag\b/i,
    operation: 'git tag',
  },
  {
    pattern: /\bgh\s+release\s+create\b/i,
    operation: 'gh release create',
  },
];

/** Força bloqueada — NUNCA permitir, mesmo @devops */
const FORCE_PUSH_PATTERN = /\bgit\s+push\s+(-f|--force|--force-with-lease)\b/i;

const DEVOPS_AGENT_ALIASES = new Set([
  'devops',
  '@devops',
  'github-devops',
  '@github-devops',
  'aiox-devops',
  '@aiox-devops',
]);

function readStdin() {
  try {
    return fs.readFileSync(0, 'utf8');
  } catch {
    return '';
  }
}

function parseInput(rawInput) {
  try {
    return JSON.parse(rawInput || '{}');
  } catch {
    return null;
  }
}

function normalizeCommand(command) {
  return String(command || '')
    .replace(/\\\r?\n/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function getCommandScopedAgent(command) {
  const match = String(command || '').match(
    /(?:^|\s)(?:export\s+)?(?:AIOX_ACTIVE_AGENT|AIOX_AGENT|ACTIVE_AGENT|CLAUDE_AGENT_NAME)=["']?(@?[a-z0-9-]+)["']?/i,
  );

  return match ? match[1].toLowerCase() : '';
}

function getActiveAgent(command) {
  const candidates = [
    process.env.AIOX_ACTIVE_AGENT,
    process.env.AIOX_AGENT,
    process.env.ACTIVE_AGENT,
    process.env.CLAUDE_AGENT_NAME,
    process.env.CLAUDE_CODE_AGENT,
    process.env.AIOX_CURRENT_AGENT,
    getCommandScopedAgent(command),
  ];

  return String(candidates.find(Boolean) || '').toLowerCase();
}

function isDevOpsAgent(agent) {
  return DEVOPS_AGENT_ALIASES.has(String(agent || '').toLowerCase());
}

function findRemoteOperation(command) {
  const normalized = normalizeCommand(command);
  return REMOTE_OPERATION_PATTERNS.find(({ pattern }) => pattern.test(normalized)) || null;
}

function isForcePush(command) {
  return FORCE_PUSH_PATTERN.test(normalizeCommand(command || ''));
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
      const statusMatch = content.match(/^Status:\s*(.+)$/m);
      const qaMatch = content.match(/^QA Verdict:\s*(.+)$/im) ||
                      content.match(/^QA Veredito:\s*(.+)$/im) ||
                      content.match(/^\*\*QA Gate:\*\*\s*(.+)$/im);
      if (statusMatch) {
        const status = statusMatch[1].trim();
        const qaVerdict = qaMatch ? qaMatch[1].trim() : null;
        return { file: storyFile, path: storyPath, status, qaVerdict };
      }
    } catch (_) {}
  }
  return null;
}

function checkStoryGates(projectRoot) {
  const story = findActiveStory(projectRoot);
  if (!story) {
    return { ok: false, reason: 'Nenhuma story ativa encontrada em docs/stories/.' };
  }
  if (story.status !== 'Done') {
    return { ok: false, reason: `Story "${story.file}" com status "${story.status}". Requer "Done" (fechada pelo @po).` };
  }
  if (story.qaVerdict && (story.qaVerdict === 'FAIL')) {
    return { ok: false, reason: `Story "${story.file}" com QA FAIL. Corrija e reexecute QA gate.` };
  }
  return { ok: true, reason: `Story "${story.file}" — Done. Gates OK.` };
}

function getCwdFromInput(input) {
  return input?.cwd || process.cwd();
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

function main() {
  const rawInput = readStdin();
  const input = parseInput(rawInput);

  if (!input) {
    emitDecision(
      'deny',
      'Hook failed to parse PreToolUse input. Blocking remote Git operation for safety; retry via @devops.',
    );
    return;
  }

  const command = input?.tool_input?.command || '';
  const cwd = getCwdFromInput(input);

  // Force push: BLOQUEADO SEMPRE (salvo procedimento autorizado)
  if (isForcePush(command)) {
    emitDecision(
      'deny',
      '❌ BLOQUEIO: git push --force / --force-with-lease proibido.\n\nPolicy: force push requer procedimento de autorização explícito.\nDesabilite temporariamente este hook apenas com autorização documentada.',
    );
    return;
  }

  const operation = findRemoteOperation(command);

  if (!operation) {
    return;
  }

  const activeAgent = getActiveAgent(command);
  if (!isDevOpsAgent(activeAgent)) {
    emitDecision(
      'deny',
      `${operation.operation} is exclusive to @devops (Constitution Article II). Current agent: ${activeAgent || '@unknown'}.`,
    );
    return;
  }

  // @devops confirmado — verificar gates de story
  const gateCheck = checkStoryGates(cwd);
  if (!gateCheck.ok) {
    emitDecision(
      'deny',
      `❌ GATE BLOQUEADO: ${gateCheck.reason}\n\nPré-condições para push:\n  1. Story fechada pelo @po (status Done)\n  2. QA veredito aceitável (PASS, CONCERNS ou WAIVED)\n  3. Lint, typecheck, testes e build passam\n\nExecute /pre-push ou os gates manualmente antes do push.`,
    );
    return;
  }

  // Tudo OK
}

if (require.main === module) {
  main();
}

module.exports = {
  DEVOPS_AGENT_ALIASES,
  REMOTE_OPERATION_PATTERNS,
  findRemoteOperation,
  getActiveAgent,
  isDevOpsAgent,
  normalizeCommand,
  isForcePush,
  findActiveStory,
  checkStoryGates,
};
