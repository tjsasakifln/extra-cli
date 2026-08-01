import type { Capability } from "../api/client";

export function ParameterForm({
  capability,
  values,
  onChange,
  showAdvanced,
  onToggleAdvanced,
}: {
  capability: Capability;
  values: Record<string, unknown>;
  onChange: (name: string, value: unknown) => void;
  showAdvanced: boolean;
  onToggleAdvanced: () => void;
}) {
  const basic = capability.params.filter((p) => !p.advanced);
  const advanced = capability.params.filter((p) => p.advanced);
  const renderField = (p: Capability["params"][number]) => {
    const id = `param-${p.name}`;
    const value = values[p.name] ?? p.default ?? "";
    return (
      <div className="field" key={p.name}>
        <label htmlFor={id}>
          {p.label}
          {p.required ? " *" : ""}
        </label>
        {p.type === "bool" ? (
          <label className="row">
            <input
              id={id}
              type="checkbox"
              checked={Boolean(value)}
              onChange={(e) => onChange(p.name, e.target.checked)}
            />
            Ativar
          </label>
        ) : p.type === "select" ? (
          <select id={id} value={String(value ?? "")} onChange={(e) => onChange(p.name, e.target.value)}>
            {(p.choices || []).map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        ) : p.type === "textarea" ? (
          <textarea id={id} value={String(value ?? "")} onChange={(e) => onChange(p.name, e.target.value)} rows={4} />
        ) : (
          <input
            id={id}
            type={p.type === "int" ? "number" : "text"}
            value={value === null || value === undefined ? "" : String(value)}
            onChange={(e) => onChange(p.name, p.type === "int" ? e.target.value : e.target.value)}
            placeholder={p.example || ""}
          />
        )}
        {p.description ? <div className="hint">{p.description}</div> : null}
      </div>
    );
  };

  return (
    <div>
      {basic.map(renderField)}
      {advanced.length > 0 ? (
        <>
          <button type="button" className="btn" onClick={onToggleAdvanced} style={{ marginBottom: 12 }}>
            {showAdvanced ? "Ocultar avançado" : "Mostrar campos avançados"}
          </button>
          {showAdvanced ? advanced.map(renderField) : null}
        </>
      ) : null}
      {capability.params.length === 0 ? (
        <p className="muted">Esta ação não exige parâmetros adicionais.</p>
      ) : null}
    </div>
  );
}
