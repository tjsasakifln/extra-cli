/** Lightweight semantic Markdown render (no HTML execution). */

import type { ReactElement } from "react";

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function inlineFormat(line: string): string {
  let s = escapeHtml(line);
  s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/\*([^*]+)\*/g, "<em>$1</em>");
  s = s.replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, '<a href="$2" rel="noopener noreferrer">$1</a>');
  return s;
}

export function MarkdownView({ text }: { text: string }) {
  const lines = String(text || "").split(/\r?\n/);
  const blocks: Array<{ type: string; html?: string; items?: string[] }> = [];
  let listBuf: string[] = [];
  let codeBuf: string[] = [];
  let inCode = false;

  const flushList = () => {
    if (listBuf.length) {
      blocks.push({ type: "ul", items: [...listBuf] });
      listBuf = [];
    }
  };
  const flushCode = () => {
    if (codeBuf.length) {
      blocks.push({ type: "pre", html: escapeHtml(codeBuf.join("\n")) });
      codeBuf = [];
    }
  };

  for (const raw of lines) {
    if (raw.trim().startsWith("```")) {
      if (inCode) {
        flushCode();
        inCode = false;
      } else {
        flushList();
        inCode = true;
      }
      continue;
    }
    if (inCode) {
      codeBuf.push(raw);
      continue;
    }
    const h = raw.match(/^(#{1,3})\s+(.+)$/);
    if (h) {
      flushList();
      blocks.push({ type: `h${h[1].length}`, html: inlineFormat(h[2]) });
      continue;
    }
    if (/^\s*[-*]\s+/.test(raw)) {
      listBuf.push(inlineFormat(raw.replace(/^\s*[-*]\s+/, "")));
      continue;
    }
    if (/^\s*\|.+\|\s*$/.test(raw) && !/^\s*\|?\s*[-:| ]+\|?\s*$/.test(raw)) {
      flushList();
      const cells = raw
        .trim()
        .replace(/^\|/, "")
        .replace(/\|$/, "")
        .split("|")
        .map((c) => inlineFormat(c.trim()));
      blocks.push({ type: "tr", items: cells });
      continue;
    }
    if (/^\s*\|?\s*[-:| ]+\|?\s*$/.test(raw)) {
      continue; // table separator
    }
    flushList();
    if (!raw.trim()) {
      blocks.push({ type: "br" });
    } else {
      blocks.push({ type: "p", html: inlineFormat(raw) });
    }
  }
  flushList();
  flushCode();

  // group consecutive tr into table
  const out: ReactElement[] = [];
  let i = 0;
  let key = 0;
  while (i < blocks.length) {
    const b = blocks[i];
    if (b.type === "tr") {
      const rows: string[][] = [];
      while (i < blocks.length && blocks[i].type === "tr") {
        rows.push(blocks[i].items || []);
        i++;
      }
      out.push(
        <div className="table-wrap" key={key++}>
          <table className="data">
            <tbody>
              {rows.map((cells, ri) => (
                <tr key={ri}>
                  {cells.map((c, ci) =>
                    ri === 0 ? (
                      <th key={ci} dangerouslySetInnerHTML={{ __html: c }} />
                    ) : (
                      <td key={ci} dangerouslySetInnerHTML={{ __html: c }} />
                    ),
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }
    if (b.type === "ul") {
      out.push(
        <ul key={key++}>
          {(b.items || []).map((it, j) => (
            <li key={j} dangerouslySetInnerHTML={{ __html: it }} />
          ))}
        </ul>,
      );
    } else if (b.type === "pre") {
      out.push(
        <pre className="log-stream" key={key++}>
          {b.html}
        </pre>,
      );
    } else if (b.type === "br") {
      out.push(<div key={key++} style={{ height: 8 }} />);
    } else if (b.type === "h1" || b.type === "h2" || b.type === "h3") {
      const Tag = b.type as "h1" | "h2" | "h3";
      out.push(<Tag key={key++} dangerouslySetInnerHTML={{ __html: b.html || "" }} />);
    } else {
      out.push(<p key={key++} dangerouslySetInnerHTML={{ __html: b.html || "" }} />);
    }
    i++;
  }

  return <div className="doc-prose md-semantic">{out}</div>;
}
