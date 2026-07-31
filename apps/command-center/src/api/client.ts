export type Capability = {
  id: string;
  name: string;
  description: string;
  category: string;
  availability: string;
  unavailable_reason?: string | null;
  risk: string;
  requires_confirmation: boolean;
  confirmation_phrase?: string | null;
  allow_cancel: boolean;
  params: Array<{
    name: string;
    label: string;
    type: string;
    required: boolean;
    default?: unknown;
    description?: string;
    example?: string;
    choices?: string[];
    advanced?: boolean;
    sensitive?: boolean;
  }>;
  required_env: string[];
  output_roots: string[];
  docs: string[];
  fixture?: boolean;
};

export type Job = {
  job_id: string;
  capability_id: string;
  action: string;
  params: Record<string, unknown>;
  status: string;
  technical_code?: string | null;
  human_message?: string | null;
  attention?: string | null;
  next_action?: string | null;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  duration_ms?: number | null;
  exit_code?: number | null;
  canonical_command: string[];
  artifacts: string[];
  blocker?: string | null;
  code_sha?: string | null;
};

export type ReviewsResponse = {
  reviews: Array<Record<string, unknown>>;
  page_count: number;
  total_count: number;
  limit: number;
  offset: number;
  /** @deprecated use total_count */
  count?: number;
};

export class ApiError extends Error {
  status: number;
  code?: string;
  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

let csrfToken: string | null = null;
const DEFAULT_TIMEOUT_MS = 30_000;

async function ensureCsrf(signal?: AbortSignal): Promise<string> {
  if (csrfToken) return csrfToken;
  const res = await fetchWithTimeout("/api/csrf", { credentials: "include", signal }, 10_000);
  if (!res.ok) throw new ApiError("Falha ao obter token CSRF", res.status);
  const data: unknown = await res.json();
  if (!data || typeof data !== "object" || typeof (data as { csrf_token?: unknown }).csrf_token !== "string") {
    throw new ApiError("Resposta CSRF inválida", res.status);
  }
  csrfToken = (data as { csrf_token: string }).csrf_token;
  return csrfToken;
}

function fetchWithTimeout(
  path: string,
  init: RequestInit,
  timeoutMs = DEFAULT_TIMEOUT_MS,
): Promise<Response> {
  const controller = new AbortController();
  const external = init.signal;
  const onAbort = () => controller.abort();
  if (external) {
    if (external.aborted) controller.abort();
    else external.addEventListener("abort", onAbort, { once: true });
  }
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  return fetch(path, { ...init, signal: controller.signal }).finally(() => {
    clearTimeout(timer);
    if (external) external.removeEventListener("abort", onAbort);
  });
}

function humanizeError(status: number, detail: string): string {
  if (status === 403) return "Ação recusada (CSRF ou permissão). Atualize a página e tente de novo.";
  if (status === 404) return "Recurso não encontrado.";
  if (status === 409) return "Conflito de estado — atualize e tente novamente.";
  if (status === 413) return "Arquivo ou resposta grande demais.";
  if (status === 422) return detail || "Dados inválidos.";
  if (status >= 500) return "Erro interno do painel local. Veja os logs se o problema persistir.";
  return detail || `Erro HTTP ${status}`;
}

async function api<T>(path: string, init: RequestInit = {}, opts?: { timeoutMs?: number; retriedCsrf?: boolean }): Promise<T> {
  const headers = new Headers(init.headers || {});
  const method = (init.method || "GET").toUpperCase();
  if (method !== "GET" && method !== "HEAD") {
    const token = await ensureCsrf(init.signal || undefined);
    headers.set("X-CC-CSRF", token);
    if (!headers.has("Content-Type") && init.body) {
      headers.set("Content-Type", "application/json");
    }
  }
  let res: Response;
  try {
    res = await fetchWithTimeout(
      path,
      { ...init, headers, credentials: "include" },
      opts?.timeoutMs ?? DEFAULT_TIMEOUT_MS,
    );
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError("Tempo esgotado ao falar com o painel local.", 0, "TIMEOUT");
    }
    throw new ApiError("Não foi possível conectar ao painel local.", 0, "NETWORK");
  }

  // One safe CSRF refresh for mutating methods only when server rejects token.
  if (res.status === 403 && method !== "GET" && method !== "HEAD" && !opts?.retriedCsrf) {
    csrfToken = null;
    return api<T>(path, init, { ...opts, retriedCsrf: true });
  }

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body: unknown = await res.json();
      if (body && typeof body === "object") {
        const b = body as { detail?: unknown; message?: unknown };
        if (typeof b.detail === "string") detail = b.detail;
        else if (typeof b.message === "string") detail = b.message;
        else if (b.detail != null) detail = JSON.stringify(b.detail);
      }
    } catch {
      /* ignore */
    }
    throw new ApiError(humanizeError(res.status, detail), res.status);
  }
  return (await res.json()) as T;
}

export const client = {
  health: (signal?: AbortSignal) => api<Record<string, unknown>>("/api/health", { signal }),
  overview: (signal?: AbortSignal) => api<Record<string, unknown>>("/api/overview", { signal }),
  onboarding: () => api<Record<string, unknown>>("/api/onboarding"),
  capabilities: (category?: string) =>
    api<{ capabilities: Capability[] }>(
      category ? `/api/capabilities?category=${encodeURIComponent(category)}` : "/api/capabilities",
    ),
  capability: (id: string) => api<Capability>(`/api/capabilities/${encodeURIComponent(id)}`),
  workflowPreflight: (id: string, dataMode = "REAL") =>
    api<Record<string, unknown>>(
      `/api/workflows/${encodeURIComponent(id)}/preflight?data_mode=${encodeURIComponent(dataMode)}`,
    ),
  workspaces: () =>
    api<{ workspaces: Array<{ id: string; label: string; client_id: string }> }>("/api/workspaces"),
  jobs: (workspaceId?: string) =>
    api<{ jobs: Job[] }>(
      workspaceId ? `/api/jobs?workspace_id=${encodeURIComponent(workspaceId)}` : "/api/jobs",
    ),
  job: (id: string) => api<{ job: Job }>(`/api/jobs/${encodeURIComponent(id)}`),
  jobLogs: (id: string, afterId = 0) =>
    api<{ logs: Array<{ id: number; ts: string; stream: string; level: string; message: string }> }>(
      `/api/jobs/${encodeURIComponent(id)}/logs?after_id=${afterId}`,
    ),
  startJob: (capability_id: string, params: Record<string, unknown>, confirmation?: string) =>
    api<{ job: Job }>("/api/jobs", {
      method: "POST",
      body: JSON.stringify({ capability_id, params, confirmation, actor: "local-user" }),
    }),
  cancelJob: (id: string) =>
    api<{ job: Job }>(`/api/jobs/${encodeURIComponent(id)}/cancel`, { method: "POST", body: "{}" }),
  search: (q: string, signal?: AbortSignal) =>
    api<{
      query: string;
      results: Array<{ type: string; id: string; label: string; detail: string; href: string }>;
    }>(`/api/search?q=${encodeURIComponent(q)}`, { signal }),
  artifact: (path: string) => api<Record<string, unknown>>(`/api/artifacts?path=${encodeURIComponent(path)}`),
  recentArtifacts: () => api<{ recent: Array<Record<string, unknown>> }>("/api/artifacts?recent=true"),
  decisions: () => api<{ decisions: Array<Record<string, unknown>> }>("/api/decisions"),
  reviews: (status = "pending", limit = 50, offset = 0) =>
    api<ReviewsResponse>(
      `/api/reviews?status=${encodeURIComponent(status)}&limit=${limit}&offset=${offset}`,
    ),
  reconcileReviews: () =>
    api<{ ok: boolean; created: number; total_pending: number }>("/api/reviews/reconcile", {
      method: "POST",
      body: "{}",
    }),
  reviewConfirmation: (itemId: string) =>
    api<{
      item_id: string;
      sensitive: boolean;
      confirmation_phrase: string;
      found: boolean;
      title?: string;
    }>(`/api/reviews/${encodeURIComponent(itemId)}/confirmation`),
  enqueueReview: (body: Record<string, unknown>) =>
    api<Record<string, unknown>>("/api/reviews", { method: "POST", body: JSON.stringify(body) }),
  saveDecision: (body: Record<string, unknown>) =>
    api<Record<string, unknown>>("/api/decisions", { method: "POST", body: JSON.stringify(body) }),
  workflows: () => api<{ workflows: Array<Record<string, unknown>> }>("/api/workflows"),
  workflow: (id: string) => api<Record<string, unknown>>(`/api/workflows/${encodeURIComponent(id)}`),
  jobManifest: (id: string) =>
    api<{ path: string; valid: boolean; errors: string[]; manifest: Record<string, unknown> }>(
      `/api/jobs/${encodeURIComponent(id)}/manifest`,
    ),
  previewXlsx: (path: string, sheet?: string, offset = 0, limit = 100) => {
    const qs = new URLSearchParams({ path, offset: String(offset), limit: String(limit) });
    if (sheet) qs.set("sheet", sheet);
    return api<{
      sheets: string[];
      sheet: string;
      headers: string[];
      rows: Array<Record<string, unknown>>;
      total_rows: number;
      offset: number;
      limit: number;
      path: string;
      name?: string;
    }>(`/api/artifacts/preview-xlsx?${qs.toString()}`);
  },
  exportBundle: (path: string) =>
    api<Record<string, unknown>>("/api/export-bundle", {
      method: "POST",
      body: JSON.stringify({ path, include_logs: false }),
    }),
  compareRuns: (current: string, previous?: string, workflow_id?: string) => {
    const qs = new URLSearchParams({ current });
    if (previous) qs.set("previous", previous);
    if (workflow_id) qs.set("workflow_id", workflow_id);
    return api<{
      ok: boolean;
      has_previous: boolean;
      message?: string;
      diff?: Record<string, unknown>;
      previous_path?: string;
      current_path?: string;
    }>(`/api/runs/compare?${qs.toString()}`);
  },
  recentByWorkflow: (workflow_id: string, limit = 10) =>
    api<{ workflow_id: string; runs: Array<Record<string, unknown>> }>(
      `/api/runs/recent-by-workflow?workflow_id=${encodeURIComponent(workflow_id)}&limit=${limit}`,
    ),
};
