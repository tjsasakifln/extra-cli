import { useEffect, useRef, useState } from "react";

export function LogStream({
  lines,
  title = "Logs",
}: {
  lines: Array<{ stream?: string; message: string }>;
  title?: string;
}) {
  const [autoScroll, setAutoScroll] = useState(true);
  const [paused, setPaused] = useState(false);
  const [filter, setFilter] = useState("");
  const ref = useRef<HTMLPreElement>(null);
  const visible = paused
    ? lines
    : lines.filter((l) => !filter || l.message.toLowerCase().includes(filter.toLowerCase()));

  useEffect(() => {
    if (autoScroll && ref.current && !paused) {
      ref.current.scrollTop = ref.current.scrollHeight;
    }
  }, [visible, autoScroll, paused]);

  return (
    <div className="panel">
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
        <h3 style={{ margin: 0 }}>{title}</h3>
        <div className="row">
          <label className="row" style={{ fontSize: "0.85rem" }}>
            <input type="checkbox" checked={autoScroll} onChange={(e) => setAutoScroll(e.target.checked)} />
            Auto-scroll
          </label>
          <button type="button" className="btn" onClick={() => setPaused((p) => !p)}>
            {paused ? "Retomar" : "Pausar"}
          </button>
        </div>
      </div>
      <div className="field">
        <label htmlFor="log-filter">Buscar nos logs</label>
        <input id="log-filter" value={filter} onChange={(e) => setFilter(e.target.value)} />
      </div>
      <pre className="log-stream" ref={ref} tabIndex={0} aria-live="polite">
        {visible.length === 0
          ? "Sem logs ainda."
          : visible.map((l) => `${l.stream ? `[${l.stream}] ` : ""}${l.message}`).join("\n")}
      </pre>
    </div>
  );
}
