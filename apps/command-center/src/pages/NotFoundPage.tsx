import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <div className="panel" role="alert" data-testid="not-found">
      <header className="page-header">
        <h1>Página não encontrada</h1>
        <p className="muted">
          O endereço solicitado não existe neste Centro de Comando local. Verifique o link ou volte ao
          início.
        </p>
      </header>
      <div className="row" style={{ gap: 12 }}>
        <Link className="btn btn-primary" to="/">
          Ir para o início
        </Link>
        <Link className="btn" to="/work/start">
          Iniciar trabalho
        </Link>
      </div>
    </div>
  );
}
