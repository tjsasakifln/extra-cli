import { Link } from "react-router-dom";
import type { Capability } from "../api/client";
import { StatusBadge } from "./StatusBadge";

export function CapabilityCard({ cap }: { cap: Capability }) {
  const available = cap.availability === "available";
  return (
    <article className="panel cap-card" style={{ marginTop: 0 }}>
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 4 }}>
        <h3 style={{ margin: 0 }}>{cap.name}</h3>
        <StatusBadge
          state={available ? "SUCCEEDED" : "UNAVAILABLE"}
          attention={available ? "healthy" : "no_data"}
          label={available ? "Pronta" : "Indisponível"}
        />
      </div>
      <p className="muted" style={{ margin: 0, flex: 1 }}>
        {cap.description}
      </p>
      <div className="row" style={{ fontSize: "0.82rem" }}>
        <span className={`risk-chip ${cap.risk}`}>{riskLabel(cap.risk)}</span>
        {cap.requires_confirmation ? <span className="muted">pede confirmação</span> : null}
      </div>
      {!available && cap.unavailable_reason ? (
        <p style={{ margin: 0, fontSize: "0.9rem" }}>{cap.unavailable_reason}</p>
      ) : null}
      <div className="actions">
        <Link className={`btn ${available ? "btn-primary" : ""}`} to={`/actions/${cap.id}`}>
          {available ? "Abrir e executar" : "Ver detalhes"}
        </Link>
      </div>
    </article>
  );
}

function riskLabel(risk: string): string {
  const map: Record<string, string> = {
    read: "Consulta",
    write_local: "Gera arquivos",
    human_decision: "Decisão humana",
    destructive: "Sensível",
  };
  return map[risk] || risk;
}
