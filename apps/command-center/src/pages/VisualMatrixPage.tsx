/**
 * Deterministic visual matrix for Playwright (A3).
 * Not a production nav item — only /__visual_matrix.
 */
import { useState } from "react";
import { StatusBadge } from "../components/StatusBadge";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { SkeletonState } from "../components/SkeletonState";
import type { AttentionKind } from "../lib/status";

const KINDS: AttentionKind[] = [
  "healthy",
  "running",
  "attention",
  "awaiting_human",
  "blocked_technical",
  "blocked_external",
  "partial",
  "no_data",
  "proven",
  "unknown",
];

export function VisualMatrixPage() {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  return (
    <div data-testid="visual-matrix" className="stack" style={{ gap: 24 }}>
      <header className="page-header">
        <h1>Matriz visual de componentes</h1>
        <p className="muted">Página de regressão determinística (não é fluxo comercial).</p>
      </header>

      <section className="panel" aria-labelledby="status-matrix">
        <h2 id="status-matrix">StatusBadge (todos)</h2>
        <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
          {KINDS.map((k) => (
            <StatusBadge key={k} attention={k} />
          ))}
          <StatusBadge state="TOTALLY_WEIRD" />
        </div>
      </section>

      <section className="panel" aria-labelledby="btn-matrix">
        <h2 id="btn-matrix">Botões</h2>
        <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
          <button type="button" className="btn">
            Default
          </button>
          <button type="button" className="btn btn-primary">
            Primary
          </button>
          <button type="button" className="btn btn-danger">
            Danger
          </button>
          <button type="button" className="btn" disabled title="Desabilitado para demonstração">
            Disabled
          </button>
          <button
            type="button"
            className="btn btn-primary"
            aria-busy={loading}
            onClick={() => {
              setLoading(true);
              window.setTimeout(() => setLoading(false), 800);
            }}
          >
            {loading ? "Loading…" : "Loading demo"}
          </button>
        </div>
      </section>

      <section className="panel" aria-labelledby="form-matrix">
        <h2 id="form-matrix">Inputs</h2>
        <div className="stack" style={{ maxWidth: 420, gap: 8 }}>
          <label>
            Texto
            <input type="text" defaultValue="Valor de exemplo" />
          </label>
          <label>
            Select
            <select defaultValue="a">
              <option value="a">Opção A</option>
              <option value="b">Opção B</option>
            </select>
          </label>
          <label>
            Textarea
            <textarea defaultValue="Notas operacionais de exemplo." rows={3} />
          </label>
        </div>
      </section>

      <section className="panel" aria-labelledby="state-matrix">
        <h2 id="state-matrix">Estados empty / loading / error / success</h2>
        <EmptyState title="Nenhum item">Não há dados neste recorte.</EmptyState>
        <SkeletonState lines={3} />
        <ErrorState title="Falha de exemplo" error="Mensagem humana de erro." onRetry={() => undefined} />
        <div className="panel" style={{ marginTop: 8 }}>
          <StatusBadge attention="proven" label="Success" />
          <p>Operação concluída com evidências.</p>
        </div>
      </section>

      <section className="panel" aria-labelledby="table-matrix">
        <h2 id="table-matrix">Tabela e card</h2>
        <div className="action-card" style={{ marginBottom: 12 }}>
          <strong>Card de exemplo</strong>
          <span className="muted">Superfície clicável de demonstração</span>
        </div>
        <table className="data">
          <thead>
            <tr>
              <th>Item</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Fixture A</td>
              <td>
                <StatusBadge attention="running" />
              </td>
            </tr>
            <tr>
              <td>Bloqueio humano</td>
              <td>
                <StatusBadge attention="awaiting_human" />
              </td>
            </tr>
          </tbody>
        </table>
      </section>

      <section className="panel" aria-labelledby="dialog-matrix">
        <h2 id="dialog-matrix">Dialog</h2>
        <button type="button" className="btn btn-primary" onClick={() => setDialogOpen(true)}>
          Abrir dialog
        </button>
        {dialogOpen ? (
          <div className="palette-backdrop" role="presentation">
            <div className="palette" role="dialog" aria-modal="true" aria-label="Dialog de exemplo">
              <h3 style={{ marginTop: 0 }}>Confirmação de exemplo</h3>
              <p className="muted">Dialog estático para axe e screenshot.</p>
              <button type="button" className="btn" onClick={() => setDialogOpen(false)}>
                Fechar
              </button>
            </div>
          </div>
        ) : null}
      </section>

      <section className="panel" aria-labelledby="mode-matrix">
        <h2 id="mode-matrix">FIXTURE / REAL bloqueado / preflight</h2>
        <div data-testid="demo-mode-banner" className="status-badge status-attention">
          MODO DEMONSTRAÇÃO (FIXTURE)
        </div>
        <p className="muted">Artefatos gerados com dados de demonstração — não são evidência comercial.</p>
        <StatusBadge attention="blocked_technical" label="REAL bloqueado" />
        <p className="muted">Preflight REAL: BLOCKED_TECHNICAL — configure DSN local read-only.</p>
      </section>
    </div>
  );
}
