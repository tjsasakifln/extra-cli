import { describe, expect, it } from "vitest";
import {
  attentionFromState,
  attentionLabel,
  attentionTokenClass,
  normalizeAttentionKind,
  translateStatus,
} from "./status";

describe("translateStatus", () => {
  it("maps BLOCKED_INSUFFICIENT_HUMAN_LABELS to human text", () => {
    const msg = translateStatus("BLOCKED_INSUFFICIENT_HUMAN_LABELS");
    expect(msg).toMatch(/avaliação/i);
    expect(msg).not.toMatch(/^exit_code/);
  });

  it("prefers explicit fallback message", () => {
    expect(translateStatus("FAILED", "Falha local de teste")).toBe("Falha local de teste");
  });
});

describe("attentionFromState", () => {
  it("distinguishes human block from technical failure", () => {
    expect(attentionFromState("BLOCKED_HUMAN")).toBe("awaiting_human");
    expect(attentionFromState("FAILED")).toBe("blocked_technical");
    expect(attentionFromState("SUCCEEDED")).toBe("proven");
  });

  it("maps unknown states to unknown (never blind cast)", () => {
    expect(attentionFromState("TOTALLY_WEIRD")).toBe("unknown");
    expect(attentionFromState(null)).toBe("unknown");
  });
});

describe("normalizeAttentionKind", () => {
  it("never returns an unmapped CSS class key", () => {
    expect(normalizeAttentionKind("not-a-real-kind")).toBe("unknown");
    expect(attentionLabel("unknown")).toBe("Status desconhecido");
    expect(attentionTokenClass("unknown")).toBe("status-unknown");
  });

  it("maps overview kinds safely", () => {
    expect(normalizeAttentionKind("job_running")).toBe("running");
    expect(normalizeAttentionKind("awaiting_human")).toBe("awaiting_human");
  });
});
