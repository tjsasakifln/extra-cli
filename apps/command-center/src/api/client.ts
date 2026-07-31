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

let csrfToken: string | null = null;

async function ensureCsrf(): Promise<string> {
  if (csrfToken) return csrfToken;
  const res = await fetch("/api/csrf", { credentials: "include" });
  if (!res.ok) throw new Error("Falha ao obter token CSRF");
  const data = await res.json();
  csrfToken = data.csrf_token as string;
  return csrfToken;
}

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers || {});
  if (init.method && init.method !== "GET") {
    const token = await ensureCsrf();
    headers.set("X-CC-CSRF", token);
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(path, { ...init, headers, credentials: "include" });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || body.message || detail;
    } catch {
      /* ignore */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json() as Promise<T>;
}

export const client = {
  health: () => api<Record<string, unknown>>("/api/health"),
  overview: () => api<Record<string, unknown>>("/api/overview"),
  onboarding: () => api<Record<string, unknown>>("/api/onboarding"),
  capabilities: (category?: string) =>
    api<{ capabilities: Capability[] }>(
      category ? `/api/capabilities?category=${encodeURIComponent(category)}` : "/api/capabilities",
    ),
  capability: (id: string) => api<Capability>(`/api/capabilities/${encodeURIComponent(id)}`),
  jobs: () => api<{ jobs: Job[] }>("/api/jobs"),
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
  search: (q: string) =>
    api<{ query: string; results: Array<{ type: string; id: string; label: string; detail: string; href: string }> }>(
      `/api/search?q=${encodeURIComponent(q)}`,
    ),
  artifact: (path: string) => api<Record<string, unknown>>(`/api/artifacts?path=${encodeURIComponent(path)}`),
  recentArtifacts: () => api<{ recent: Array<Record<string, unknown>> }>("/api/artifacts?recent=true"),
  decisions: () => api<{ decisions: Array<Record<string, unknown>> }>("/api/decisions"),
  reviews: (status = "pending") =>
    api<{ reviews: Array<Record<string, unknown>>; count: number }>(
      `/api/reviews?status=${encodeURIComponent(status)}`,
    ),
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
};
