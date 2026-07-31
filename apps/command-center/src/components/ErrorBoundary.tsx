import { Component, type ErrorInfo, type ReactNode } from "react";

type Props = {
  children: ReactNode;
  area?: string;
};

type State = {
  error: Error | null;
  detailOpen: boolean;
};

const SECRET_RE =
  /(password|secret|token|api[_-]?key|authorization|bearer\s+\S+|postgres(?:ql)?:\/\/\S+|dsn=)/i;

function sanitizeErrorText(raw: string): string {
  return raw
    .split("\n")
    .map((line) => (SECRET_RE.test(line) ? "[redacted]" : line))
    .join("\n")
    .slice(0, 4000);
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null, detailOpen: false };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    try {
      const payload = {
        ts: new Date().toISOString(),
        area: this.props.area || "global",
        message: sanitizeErrorText(error.message || String(error)),
        stack: sanitizeErrorText(error.stack || ""),
        componentStack: sanitizeErrorText(info.componentStack || ""),
      };
      const key = "cc-error-log";
      const prev = JSON.parse(sessionStorage.getItem(key) || "[]") as unknown[];
      const next = [...prev.slice(-19), payload];
      sessionStorage.setItem(key, JSON.stringify(next));
    } catch {
      /* storage may be unavailable */
    }
  }

  render() {
    if (!this.state.error) return this.props.children;
    const safeMsg = sanitizeErrorText(this.state.error.message || "Erro inesperado");
    const safeStack = sanitizeErrorText(this.state.error.stack || "");

    return (
      <div className="panel error-boundary" role="alert" data-testid="error-boundary">
        <h2 style={{ marginTop: 0 }}>Algo deu errado nesta área</h2>
        <p>
          A interface local encontrou um erro e parou de renderizar este bloco. Seus dados no disco não
          foram alterados por este erro de tela.
        </p>
        <div className="row" style={{ gap: 8, marginBottom: 12 }}>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => this.setState({ error: null, detailOpen: false })}
          >
            Tentar novamente
          </button>
          <button
            type="button"
            className="btn"
            onClick={() => this.setState((s) => ({ detailOpen: !s.detailOpen }))}
          >
            {this.state.detailOpen ? "Ocultar detalhe técnico" : "Detalhe técnico"}
          </button>
        </div>
        {this.state.detailOpen ? (
          <pre className="mono technical-detail" style={{ whiteSpace: "pre-wrap", fontSize: "0.8rem" }}>
            {safeMsg}
            {"\n"}
            {safeStack}
          </pre>
        ) : null}
      </div>
    );
  }
}
