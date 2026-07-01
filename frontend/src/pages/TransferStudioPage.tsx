import { useEffect, useState } from "react";

import {
  generateTransferDesign,
  getTransferTargets,
  getTransferTkus,
} from "@/lib/api";
import type { TransferDesign, TransferTarget, TransferTku } from "@/types";

// ── minimal markdown renderer ────────────────────────────────────────────────
// The codebase ships no markdown library (WikiPanel renders plain text). The
// proposal uses a small, known subset — headings, bullet lists, bold, tables,
// and [src:id] citation tags — so a focused renderer keeps the dependency
// surface flat and matches existing inline-style conventions.

function renderInline(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(
      /\[src:([^\]]+)\]/g,
      '<span style="color:var(--related);font-size:0.78em;background:var(--related-dim);border-radius:4px;padding:0 4px;margin:0 1px;">$1</span>'
    );
}

function MarkdownView({ md }: { md: string }) {
  const lines = md.split("\n");
  const blocks: JSX.Element[] = [];
  let i = 0;
  let key = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (line.startsWith("# ")) {
      blocks.push(<h2 key={key++}>{line.slice(2)}</h2>);
      i++;
    } else if (line.startsWith("## ")) {
      blocks.push(
        <h3 key={key++} style={{ marginTop: "1.1rem" }}>
          {line.slice(3)}
        </h3>
      );
      i++;
    } else if (line.startsWith("|")) {
      // table block
      const rows: string[] = [];
      while (i < lines.length && lines[i].startsWith("|")) {
        rows.push(lines[i]);
        i++;
      }
      const parse = (r: string) =>
        r
          .split("|")
          .slice(1, -1)
          .map((c) => c.trim());
      const header = parse(rows[0]);
      const body = rows.slice(2).map(parse);
      blocks.push(
        <table className="eval-table" key={key++} style={{ marginTop: "0.4rem" }}>
          <thead>
            <tr>
              {header.map((h, j) => (
                <th key={j}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {body.map((row, ri) => (
              <tr key={ri}>
                {row.map((c, ci) => (
                  <td
                    key={ci}
                    dangerouslySetInnerHTML={{ __html: renderInline(c) }}
                  />
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      );
    } else if (line.match(/^\s*-\s/)) {
      const items: { indent: number; text: string }[] = [];
      while (i < lines.length && lines[i].match(/^\s*-\s/)) {
        const indent = lines[i].search(/\S/);
        items.push({ indent, text: lines[i].replace(/^\s*-\s/, "") });
        i++;
      }
      blocks.push(
        <ul key={key++} style={{ margin: "0.3rem 0", paddingLeft: "1.1rem" }}>
          {items.map((it, j) => (
            <li
              key={j}
              style={{ marginLeft: it.indent > 2 ? "1rem" : 0 }}
              dangerouslySetInnerHTML={{ __html: renderInline(it.text) }}
            />
          ))}
        </ul>
      );
    } else if (line.trim() === "") {
      i++;
    } else {
      blocks.push(
        <p
          key={key++}
          style={{ margin: "0.3rem 0" }}
          dangerouslySetInnerHTML={{ __html: renderInline(line) }}
        />
      );
    }
  }
  return <div>{blocks}</div>;
}

// ── page ──────────────────────────────────────────────────────────────────────

export default function TransferStudioPage() {
  const [targets, setTargets] = useState<TransferTarget[] | null>(null);
  const [tkus, setTkus] = useState<TransferTku[]>([]);
  const [targetId, setTargetId] = useState<string>("");
  const [sourceDomain, setSourceDomain] = useState<string>("");
  const [useLlm, setUseLlm] = useState(false);
  const [design, setDesign] = useState<TransferDesign | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([getTransferTargets(), getTransferTkus()])
      .then(([t, k]) => {
        if (cancelled) return;
        setTargets(t);
        setTkus(k);
        if (t.length > 0) setTargetId(t[0].id);
      })
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      cancelled = true;
    };
  }, []);

  const selected = targets?.find((t) => t.id === targetId) ?? null;
  const domains = Array.from(new Set(tkus.map((k) => k.source_domain))).sort();

  const handleGenerate = () => {
    if (!targetId) return;
    setLoading(true);
    setError(null);
    setDesign(null);
    generateTransferDesign({
      target_id: targetId,
      source_domain: sourceDomain || undefined,
      use_llm: useLlm,
    })
      .then(setDesign)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  };

  if (error && !targets) {
    return (
      <div>
        <h2>Transfer Studio</h2>
        <div style={{ color: "var(--uncertain)" }}>Backend error: {error}</div>
      </div>
    );
  }
  if (!targets) {
    return (
      <div>
        <h2>Transfer Studio</h2>
        <div className="empty">Loading…</div>
      </div>
    );
  }

  return (
    <div>
      <h2>Transfer Studio</h2>
      <p style={{ color: "var(--muted)", marginTop: "0.2rem" }}>
        Match transferable knowledge units from source domains against a target
        SDL, then draft an experiment-design proposal. Every transferred claim is
        cited back to its source paper.
      </p>

      <div style={{ display: "flex", gap: "1.4rem", alignItems: "flex-start", marginTop: "0.8rem" }}>
        {/* Left column — controls */}
        <div style={{ width: 320, flexShrink: 0 }}>
          <div className="v7-card">
            <label style={{ display: "block", marginBottom: "0.6rem" }}>
              <div style={{ fontWeight: 600, marginBottom: "0.2rem" }}>Target SDL</div>
              <select
                value={targetId}
                onChange={(e) => setTargetId(e.target.value)}
                style={{ width: "100%" }}
              >
                {targets.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
            </label>
            {selected && (
              <p style={{ color: "var(--muted)", fontSize: "0.85em", margin: "0.3rem 0 0.7rem" }}>
                {selected.description}
              </p>
            )}

            <label style={{ display: "block", marginBottom: "0.6rem" }}>
              <div style={{ fontWeight: 600, marginBottom: "0.2rem" }}>
                Source domain (optional)
              </div>
              <select
                value={sourceDomain}
                onChange={(e) => setSourceDomain(e.target.value)}
                style={{ width: "100%" }}
              >
                <option value="">All domains</option>
                {domains.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            </label>

            <label
              style={{ display: "flex", alignItems: "center", gap: "0.4rem", marginBottom: "0.7rem" }}
              title="需要后端配置 PAS_KIMI_API_KEY"
            >
              <input
                type="checkbox"
                checked={useLlm}
                onChange={(e) => setUseLlm(e.target.checked)}
              />
              LLM 重写
              <span style={{ color: "var(--muted)", fontSize: "0.8em" }}>
                (需要 PAS_KIMI_API_KEY)
              </span>
            </label>

            <button onClick={handleGenerate} disabled={loading || !targetId}>
              {loading ? "Generating…" : "Generate proposal"}
            </button>
          </div>
        </div>

        {/* Right column — proposal + matches */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {error && (
            <div style={{ color: "var(--uncertain)", marginBottom: "0.6rem" }}>
              Backend error: {error}
            </div>
          )}
          {!design && !loading && (
            <div className="empty">
              Pick a target SDL and click Generate to draft a transfer proposal.
            </div>
          )}
          {loading && <div className="empty">Generating proposal…</div>}

          {design && (
            <>
              <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", marginBottom: "0.4rem" }}>
                <span
                  className="badge"
                  style={{
                    background: design.mode === "llm" ? "var(--core-dim)" : "var(--panel-2)",
                    color: design.mode === "llm" ? "var(--core)" : "var(--muted)",
                  }}
                >
                  {design.mode === "llm" ? "LLM rewrite" : "template"}
                </span>
                <span style={{ color: "var(--muted)", fontSize: "0.85em" }}>
                  {design.matches.length} matched source(s)
                </span>
              </div>

              {design.matches.length > 0 && (
                <table className="eval-table" style={{ marginBottom: "1rem" }}>
                  <thead>
                    <tr>
                      <th>Paper</th>
                      <th>Domain</th>
                      <th>Score</th>
                      <th>Key lesson</th>
                    </tr>
                  </thead>
                  <tbody>
                    {design.matches.map((m) => (
                      <tr key={m.paper_id}>
                        <td>
                          {m.title}{" "}
                          <span style={{ color: "var(--muted)" }}>
                            ({m.year ?? "n.d."})
                          </span>
                        </td>
                        <td>{m.source_domain}</td>
                        <td>{m.score}</td>
                        <td style={{ color: "var(--muted)" }}>{m.key_lesson ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}

              <div className="v7-card">
                <MarkdownView md={design.markdown} />
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
