/** Operational date/time formatting for the consultant UI (pt-BR). */

const DEFAULT_TZ = "America/Sao_Paulo";

function resolveTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || DEFAULT_TZ;
  } catch {
    return DEFAULT_TZ;
  }
}

export function parseInstant(value?: string | null): Date | null {
  if (!value) return null;
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** "31/07/2026 às 12:22" in local/configured timezone. */
export function formatDateTimePt(value?: string | null, timeZone = resolveTimeZone()): string {
  const d = parseInstant(value);
  if (!d) return "—";
  const date = new Intl.DateTimeFormat("pt-BR", {
    timeZone,
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(d);
  const time = new Intl.DateTimeFormat("pt-BR", {
    timeZone,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(d);
  return `${date} às ${time}`;
}

/** Relative "há 5 horas" / "agora" — main surface; ISO goes to title attribute. */
export function formatRelativePt(value?: string | null, now = new Date()): string {
  const d = parseInstant(value);
  if (!d) return "—";
  const diffSec = Math.round((d.getTime() - now.getTime()) / 1000);
  const rtf = new Intl.RelativeTimeFormat("pt-BR", { numeric: "auto" });
  const abs = Math.abs(diffSec);
  if (abs < 60) return rtf.format(Math.trunc(diffSec), "second");
  const mins = Math.trunc(diffSec / 60);
  if (Math.abs(mins) < 60) return rtf.format(mins, "minute");
  const hours = Math.trunc(mins / 60);
  if (Math.abs(hours) < 48) return rtf.format(hours, "hour");
  const days = Math.trunc(hours / 24);
  if (Math.abs(days) < 30) return rtf.format(days, "day");
  return formatDateTimePt(value);
}

export function formatWhen(value?: string | null): { text: string; title: string } {
  const d = parseInstant(value);
  if (!d) return { text: "—", title: "" };
  return {
    text: `${formatDateTimePt(value)} (${formatRelativePt(value)})`,
    title: d.toISOString(),
  };
}
