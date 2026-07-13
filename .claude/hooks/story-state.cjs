#!/usr/bin/env node
'use strict';

/**
 * story-state.cjs — Shared story state utility.
 *
 * Provides evidence-based story state validation for hooks.
 * Replaces fragile markdown regex with structured JSON state.
 *
 * Used by: no-story-no-edit.cjs, enforce-git-push-authority.cjs,
 *          db-destructive-guard.cjs
 */

const fs = require('fs');
const path = require('path');

// ─── CONSTANTS ───────────────────────────────────────────────────────────────

const STATE_DIR = '.aiox/state/stories';

const VALID_STATUSES = new Set([
  'Draft', 'Ready', 'InProgress', 'InReview', 'Done',
]);

const VALID_RISK_LEVELS = new Set([
  'FAST', 'STANDARD', 'HIGH-RISK',
]);

const VALID_QA_VERDICTS = new Set([
  'PENDING', 'PASS', 'CONCERNS', 'FAIL', 'WAIVED',
]);

const VALID_GATE_VALUES = new Set([
  'PENDING', 'PASS', 'FAIL', 'NA',
]);

/** Files NEVER allowed to be FAST — always require explicit protocol maintenance */
const PROTOCOL_PROTECTED_PATTERNS = [
  /^CLAUDE\.md$/,
  /^\.claude\/CLAUDE\.md$/,
  /^\.claude\/settings\.json$/,
  /^\.claude\/settings\.local\.json$/,
  /^\.claude\/hooks\//,
  /^\.claude\/rules\//,
  /^\.claude\/skills\//,
  /^\.aiox-core\/constitution\.md$/,
  /^\.aiox-core\/.*authority/i,
];

/** Code extensions requiring story */
const CODE_EXTENSIONS = new Set([
  '.py', '.js', '.ts', '.tsx', '.jsx', '.sql', '.yaml', '.yml',
  '.toml', '.cfg', '.ini', '.json', '.sh', '.bash', '.zsh',
  '.html', '.css', '.scss', '.less', '.vue', '.svelte',
]);

/** FAST patterns — trivial changes not requiring story */
const FAST_PATTERNS = [
  /^README\.md$/i,
  /^CHANGELOG/i,
  /^CONTRIBUTING/i,
  /^LICENSE$/i,
  /^\.gitignore$/,
  /^\.prettierrc/,
  /^\.editorconfig$/,
  /^\.env\.example$/,
  /^docs\/(?!stories\/|prd\/|architecture\/).*\.md$/i,
];

/**
 * What CANNOT be FAST under any circumstance.
 * Each entry: { pattern: RegExp, label: string }
 */
const NEVER_FAST = [
  { pattern: /auth/i, label: 'authentication' },
  { pattern: /authorization/i, label: 'authorization' },
  { pattern: /security/i, label: 'security' },
  { pattern: /secret|credential|password|token|api[_\s]?key/i, label: 'secrets' },
  { pattern: /\bdata\b.*\bmigration|migration.*\bdata\b/i, label: 'data migration' },
  { pattern: /\bdrop\b/i, label: 'DROP operation' },
  { pattern: /\btruncate\b/i, label: 'TRUNCATE operation' },
  { pattern: /\bdelete\b/i, label: 'DELETE operation' },
  { pattern: /\bdeploy\b/i, label: 'deployment' },
  { pattern: /\bproduction\b|\bprod\b/i, label: 'production' },
  { pattern: /\binfra/i, label: 'infrastructure' },
  { pattern: /\bpayment|billing|invoice/i, label: 'payments' },
  { pattern: /api\s*contract|contract\s*api/i, label: 'API contracts' },
  { pattern: /\bdependencies\b/i, label: 'dependencies' },
  { pattern: /\.(py|js|ts|sql|sh)$/, label: 'executable code' },
  { pattern: /\bCI\/CD\b|\bci\b.*\bcd\b|\bgithub\s*actions\b|\.github\/workflows/i, label: 'CI/CD' },
  { pattern: /^\.claude\//, label: 'protocol files' },
  { pattern: /^\.aiox-core\//, label: 'framework files' },
  { pattern: /scripts\//, label: 'scripts' },
  { pattern: /config\//, label: 'configuration' },
];

// ─── PROTOCOL PROTECTED ──────────────────────────────────────────────────────

function isProtocolProtected(filePath) {
  if (!filePath) return false;
  const normalized = String(filePath).replace(/\\/g, '/');
  return PROTOCOL_PROTECTED_PATTERNS.some(p => p.test(normalized));
}

// ─── STORY STATE ─────────────────────────────────────────────────────────────

function getStateDir(projectRoot) {
  return path.join(projectRoot, STATE_DIR);
}

function getStoryStatePath(projectRoot, storyId) {
  return path.join(getStateDir(projectRoot), `${storyId}.json`);
}

function readStoryState(projectRoot, storyId) {
  const filePath = getStoryStatePath(projectRoot, storyId);
  try {
    const raw = fs.readFileSync(filePath, 'utf8');
    return JSON.parse(raw);
  } catch (_) {
    return null;
  }
}

function findActiveStoryState(projectRoot) {
  const stateDir = getStateDir(projectRoot);
  let files = [];
  try { files = fs.readdirSync(stateDir).filter(f => f.endsWith('.json')); }
  catch (_) { return null; }

  for (const file of files) {
    const state = readStoryState(projectRoot, file.replace('.json', ''));
    if (!state) continue;
    if (state.status === 'Ready' || state.status === 'InProgress' || state.status === 'InReview') {
      return { ...state, _id: file.replace('.json', '') };
    }
  }
  return null;
}

function findAnyStoryState(projectRoot) {
  const stateDir = getStateDir(projectRoot);
  let files = [];
  try { files = fs.readdirSync(stateDir).filter(f => f.endsWith('.json')); }
  catch (_) { return null; }

  for (const file of files) {
    const state = readStoryState(projectRoot, file.replace('.json', ''));
    if (!state) continue;
    return { ...state, _id: file.replace('.json', '') };
  }
  return null;
}

// ─── VALIDATION ──────────────────────────────────────────────────────────────

const TRANSITIONS = {
  'Draft': ['Ready'],
  'Ready': ['InProgress'],
  'InProgress': ['InReview'],
  'InReview': ['InProgress', 'Done'],
  'Done': [],
};

function isValidTransition(from, to) {
  if (!VALID_STATUSES.has(from) || !VALID_STATUSES.has(to)) return false;
  return (TRANSITIONS[from] || []).includes(to);
}

function validateStoryState(state) {
  const errors = [];

  if (!state.story_id) errors.push('Missing story_id');
  if (!VALID_STATUSES.has(state.status)) errors.push(`Invalid status: ${state.status}`);
  if (!VALID_RISK_LEVELS.has(state.risk_level)) errors.push(`Invalid risk_level: ${state.risk_level}`);
  if (!VALID_QA_VERDICTS.has(state.qa_verdict)) errors.push(`Invalid qa_verdict: ${state.qa_verdict}`);

  // Impossible combinations
  if (state.status === 'Done' && state.qa_verdict === 'FAIL')
    errors.push('IMPOSSIBLE: status Done with qa_verdict FAIL');
  if (state.po_closed === true && state.qa_verdict === 'FAIL')
    errors.push('IMPOSSIBLE: po_closed true with qa_verdict FAIL');
  if (state.publication_authorized === true) {
    const gates = state.gates || {};
    const pending = Object.entries(gates).filter(([, v]) => v === 'PENDING');
    if (pending.length > 0)
      errors.push(`IMPOSSIBLE: publication_authorized with gates pending: ${pending.map(([k]) => k).join(', ')}`);
    if (state.po_closed !== true)
      errors.push('IMPOSSIBLE: publication_authorized without po_closed');
  }
  if (state.qa_verdict === 'PASS' && !state.reviewed_commit)
    errors.push('IMPOSSIBLE: qa_verdict PASS without reviewed_commit');

  return errors;
}

function checkPushGate(projectRoot) {
  const state = findAnyStoryState(projectRoot);
  if (!state) {
    return { ok: false, reason: 'Nenhum state file encontrado em .aiox/state/stories/.' };
  }
  if (state.status !== 'Done') {
    return { ok: false, reason: `Story "${state.story_id}" status "${state.status}". Requer "Done".` };
  }
  if (state.qa_verdict === 'FAIL') {
    return { ok: false, reason: `Story "${state.story_id}" QA FAIL.` };
  }
  if (state.po_closed !== true) {
    return { ok: false, reason: `Story "${state.story_id}" não fechada pelo PO (po_closed: false).` };
  }

  // Check gates
  const gates = state.gates || {};
  const failed = Object.entries(gates).filter(([, v]) => v === 'FAIL');
  if (failed.length > 0) {
    return { ok: false, reason: `Gates FAIL: ${failed.map(([k]) => k).join(', ')}.` };
  }

  // Check reviewed_commit matches HEAD
  if (state.reviewed_commit) {
    try {
      const { execSync } = require('child_process');
      const head = execSync('git rev-parse HEAD', { cwd: projectRoot, encoding: 'utf8', timeout: 5000 }).trim();
      if (head !== state.reviewed_commit) {
        return { ok: false, reason: `reviewed_commit (${state.reviewed_commit.substring(0, 7)}) != HEAD (${head.substring(0, 7)}). Código alterado após QA.` };
      }
    } catch (_) {
      return { ok: false, reason: 'Não foi possível verificar HEAD.' };
    }
  }

  // Check working tree
  try {
    const { execSync } = require('child_process');
    const status = execSync('git status --porcelain', { cwd: projectRoot, encoding: 'utf8', timeout: 5000 }).trim();
    if (status) {
      return { ok: false, reason: 'Working tree não está limpa. Commit ou stash as alterações antes do push.' };
    }
  } catch (_) {
    return { ok: false, reason: 'Não foi possível verificar working tree.' };
  }

  if (state.publication_authorized !== true) {
    return { ok: false, reason: 'publication_authorized não está ativo.' };
  }

  return { ok: true, reason: `Story "${state.story_id}" — todos os gates passaram.` };
}

// ─── RISK CLASSIFICATION ─────────────────────────────────────────────────────

function validateRiskClassification(riskLevel, requestOrFilePath) {
  const str = String(requestOrFilePath || '');

  // HIGH-RISK: always
  const HIGH_RISK_TRIGGERS = [
    /\bauth\b/i, /\bauthentication\b/i, /\bauthorization\b/i, /\bautorização\b/i,
    /\bsecurity\b/i, /\bsegurança\b/i, /\bcrypto\b/i, /\bencrypt\b/i,
    /\bsecret\b/i, /\bcredential\b/i, /\bpassword\b/i, /\btoken\b/i, /\bapi[_\s]?key\b/i,
    /\bpersonal\s*data\b/i, /\bdados\s*pessoais\b/i, /\bPII\b/i,
    /\bdatabase\b/i, /\bmigration\b/i, /\bschema\b/i, /\bDDL\b/i, /\bDROP\b/i,
    /\bdelete\b/i, /\btruncate\b/i, /\bexcluir\b/i,
    /\bpayment\b/i, /\bpagamento\b/i, /\bbilling\b/i,
    /\binfrastructure\b/i, /\binfra\b/i, /\bCI\/CD\b/i, /\bgithub\s*actions\b/i,
    /\bproduction\b/i, /\bprod\b/i, /\bprodução\b/i, /\bdeploy\b/i,
    /\barchitecture\b/i, /\barquitetura\b/i, /\bpublic\s*contract\b/i,
    /\bdependencies\b/i, /\bdependências\b/i, /\bbreaking\s*change\b/i,
    /\.claude\//, /\.aiox-core\//,
  ];

  if (riskLevel === 'FAST') {
    for (const trigger of HIGH_RISK_TRIGGERS) {
      if (trigger.test(str)) {
        return { valid: false, reason: `FAST não pode incluir: conteúdo que dispara "${trigger.source}". Classificação mínima: STANDARD.` };
      }
    }
    // FAST also cannot edit code files
    if (/\.(py|js|ts|sql|sh|yml|yaml|toml|cfg)$/.test(str)) {
      return { valid: false, reason: 'FAST não permite edição de código executável. Mínimo: STANDARD.' };
    }
  }

  return { valid: true };
}

// ─── FAST DETECTION ──────────────────────────────────────────────────────────

function isFastPath(filePath) {
  if (!filePath) return false;

  // PROTOCOL-PROTECTED: NEVER fast
  if (isProtocolProtected(filePath)) return false;

  const normalized = String(filePath).replace(/\\/g, '/');

  for (const fast of FAST_PATTERNS) {
    if (fast.test(normalized)) return true;
  }
  return false;
}

function isCodeFile(filePath) {
  if (!filePath) return false;
  const ext = path.extname(filePath).toLowerCase();
  return CODE_EXTENSIONS.has(ext);
}

// ─── EXPORTS ─────────────────────────────────────────────────────────────────

module.exports = {
  // Constants
  PROTOCOL_PROTECTED_PATTERNS,
  VALID_STATUSES,
  VALID_RISK_LEVELS,
  VALID_QA_VERDICTS,
  VALID_GATE_VALUES,
  TRANSITIONS,
  NEVER_FAST,
  CODE_EXTENSIONS,
  FAST_PATTERNS,

  // Protocol protection
  isProtocolProtected,

  // Story state
  getStateDir,
  getStoryStatePath,
  readStoryState,
  findActiveStoryState,
  findAnyStoryState,

  // Validation
  isValidTransition,
  validateStoryState,
  checkPushGate,
  validateRiskClassification,

  // FAST detection
  isFastPath,
  isCodeFile,
};
