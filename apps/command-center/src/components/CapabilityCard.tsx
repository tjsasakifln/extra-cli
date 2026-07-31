import { Link } from "react-router-dom";
import type { Capability } from "../api/client";
import { StatusBadge } from "./StatusBadge";

export function CapabilityCard({ cap }: { cap: Capability }) {
  const available = cap.availability === "available";
  return (
    <article className="panel" style={{ marginTop: 0 }}>
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
        <h3 style={{ margin: 0 }}>{cap.name}</h3>
        <StatusBadge
          state={available ? "SUCCEEDED" : "UNAVAILABLE"}
          attention={available ? "healthy" : "no_data"}
          label={available ? "Disponível" : "Indisponível"}
        />
      </div>
      <p className="muted" style={{ marginTop: 0 }}>
        {cap.description}
      </p>
      <div className="row muted" style={{ fontSize: "0.82rem" }}>
        <span className="mono">{cap.id}</span>
        <span>·</span>
        <span>{cap.risk}</span>
        {cap.requires_confirmation ? <span>· exige confirmação</span> : null}
      </div>
      {!available && cap.unavailable_reason ? (
        <p style={{ marginBottom: 0 }}>
          Ainda não disponível nesta versão. {cap.unavailable_reason}
        </p>
      ) : null}
      <div className="row" style={{ marginTop: 12 }}>
        <Link className="btn" to={`/capabilities/${cap.id}`}>
          Abrir
        </Link>
      </div>
    </article>
  );
}
