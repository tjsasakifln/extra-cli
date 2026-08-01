export type AttentionKind =
  | "healthy"
  | "attention"
  | "blocked_external"
  | "blocked_technical"
  | "awaiting_human"
  | "no_data"
  | "running"
  | "partial"
  | "proven"
  | "unknown";

const KNOWN_ATTENTION = new Set<AttentionKind>([
  "healthy",
  "attention",
  "blocked_external",
  "blocked_technical",
  "awaiting_human",
  "no_data",
  "running",
  "partial",
  "proven",
  "unknown",
]);

const HUMAN: Record<string, string> = {
  QUEUED: "Na fila — a execução ainda não começou.",
  VALIDATING: "Validando parâmetros e pré-requisitos.",
  RUNNING: "Em execução — acompanhe o progresso nos logs.",
  CANCELLING: "Cancelamento solicitado — aguardando o processo encerrar.",
  CANCELLED: "Cancelado por você antes de concluir.",
  SUCCEEDED: "Concluído com sucesso e com evidências registradas.",
  SUCCEEDED_WITH_WARNINGS: "Concluído, mas com avisos que merecem revisão.",
  PARTIAL: "Conclusão parcial — parte do trabalho ficou pendente.",
  BLOCKED_EXTERNAL: "Bloqueado por dependência externa (rede, fonte ou credencial).",
  BLOCKED_HUMAN: "Automação pronta, mas ainda precisa da sua decisão humana.",
  FAILED: "Falhou por erro técnico — revise os logs e a próxima ação.",
  TIMED_OUT: "Tempo esgotado — a execução foi interrompida por timeout.",
  UNAVAILABLE: "Ainda não disponível nesta versão do repositório.",
  BLOCKED_INSUFFICIENT_HUMAN_LABELS:
    "A automação foi concluída, mas o ranking ainda precisa da sua avaliação antes de qualquer uso comercial.",
  READY_FOR_HUMAN_ACCEPTANCE: "Pronto para revisão humana — nada foi aceito automaticamente.",
  SUCCESS_ZERO: "Executou sem erro, porém não encontrou itens (resultado zero).",
};

export function translateStatus(code?: string | null, fallback?: string | null): string {
  if (fallback) return fallback;
  if (!code) return "Status não informado.";
  if (HUMAN[code]) return HUMAN[code];
  const upper = code.toUpperCase();
  for (const [key, msg] of Object.entries(HUMAN)) {
    if (upper.includes(key) || key.includes(upper)) return msg;
  }
  return `Estado técnico: ${code}. Revise os detalhes e a evidência associada.`;
}

export function attentionFromState(state?: string | null): AttentionKind {
  switch (state) {
    case "SUCCEEDED":
      return "proven";
    case "SUCCEEDED_WITH_WARNINGS":
    case "CANCELLED":
      return "attention";
    case "PARTIAL":
      return "partial";
    case "BLOCKED_EXTERNAL":
      return "blocked_external";
    case "BLOCKED_HUMAN":
    case "BLOCKED_INSUFFICIENT_HUMAN_LABELS":
    case "READY_FOR_HUMAN_ACCEPTANCE":
      return "awaiting_human";
    case "FAILED":
    case "TIMED_OUT":
      return "blocked_technical";
    case "RUNNING":
    case "QUEUED":
    case "VALIDATING":
    case "CANCELLING":
      return "running";
    case "UNAVAILABLE":
    case "SUCCESS_ZERO":
      return "no_data";
    case null:
    case undefined:
    case "":
      return "unknown";
    default:
      return "unknown";
  }
}

/** Safe parse of API/attention kind strings — never blind-casts arbitrary values. */
export function normalizeAttentionKind(value?: string | null): AttentionKind {
  if (!value) return "unknown";
  const key = value.trim().toLowerCase().replace(/-/g, "_") as AttentionKind;
  if (KNOWN_ATTENTION.has(key)) return key;
  // Map overview attention kinds
  if (value.includes("awaiting") || value.includes("human") || value.includes("blocked_human")) {
    return "awaiting_human";
  }
  if (value.includes("blocked_external") || value.includes("external")) return "blocked_external";
  if (value.includes("blocked_technical") || value.includes("failed") || value.includes("timeout")) {
    return "blocked_technical";
  }
  if (value.includes("running") || value.includes("job_running")) return "running";
  if (value.includes("partial")) return "partial";
  if (value.includes("no_data") || value.includes("missing")) return "no_data";
  if (value.includes("healthy") || value.includes("proven")) return "healthy";
  if (value.includes("attention") || value.includes("job_attention") || value.includes("profile")) {
    return "attention";
  }
  return "unknown";
}

export function attentionLabel(kind: AttentionKind): string {
  const labels: Record<AttentionKind, string> = {
    healthy: "Saudável",
    attention: "Atenção",
    blocked_external: "Bloqueio externo",
    blocked_technical: "Bloqueio técnico",
    awaiting_human: "Aguardando decisão humana",
    no_data: "Sem dados",
    running: "Em andamento",
    partial: "Parcial",
    proven: "Comprovado",
    unknown: "Status desconhecido",
  };
  return labels[kind] ?? labels.unknown;
}

/** CSS class segment for status tokens (matches --status-* tokens). */
export function attentionTokenClass(kind: AttentionKind): string {
  const safe = KNOWN_ATTENTION.has(kind) ? kind : "unknown";
  return `status-${safe}`;
}
