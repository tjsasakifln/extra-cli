export type AttentionKind =
  | "healthy"
  | "attention"
  | "blocked_external"
  | "blocked_technical"
  | "awaiting_human"
  | "no_data"
  | "running"
  | "partial"
  | "proven";

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
      return "no_data";
    default:
      return "attention";
  }
}

export function attentionLabel(kind: AttentionKind): string {
  const labels: Record<AttentionKind, string> = {
    healthy: "Saudável",
    attention: "Atenção",
    blocked_external: "Bloqueio externo",
    blocked_technical: "Bloqueio técnico",
    awaiting_human: "Aguardando revisão humana",
    no_data: "Sem dados",
    running: "Em andamento",
    partial: "Parcial",
    proven: "Comprovado",
  };
  return labels[kind];
}
