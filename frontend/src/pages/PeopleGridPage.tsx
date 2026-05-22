import { useCallback, useEffect, useMemo, useState } from "react";

import { getPeopleGrid } from "@/lib/api";
import type { PeopleElement, PeopleGrid } from "@/types";

// Stable palette taken from user screenshot.
const PALETTE = [
  "#E84A85", // hot pink
  "#F0712C", // orange
  "#F5C518", // yellow
  "#5E4E96", // purple
  "#1B3590", // navy
  "#6377B5", // blue mid
  "#C73C73", // magenta
  "#864020", // brown
  "#7E94CE", // light blue
  "#F0A03A", // light orange
  "#5A6FA8", // steel
  "#E891AC", // pink light
];

function colorForCategory(category: string, allCategories: string[]): string {
  const idx = allCategories.indexOf(category);
  if (idx === -1) return PALETTE[0];
  return PALETTE[idx % PALETTE.length];
}

export default function PeopleGridPage() {
  const [data, setData] = useState<PeopleGrid | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<PeopleElement | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const out = await getPeopleGrid();
      setData(out);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const categoryIds = useMemo(
    () => (data ? data.categories.map((c) => c.id) : []),
    [data]
  );

  return (
    <div className="v7-page">
      <div className="v7-hero">
        <div>
          <h1>Periodic Table of People</h1>
          <p>
            Each AC member as an element. <b>Symbol</b> = two letters from the
            surname; <b>atomic number</b> = papers attributed to them;{" "}
            <b>color</b> = top research topic. Click an element to see their
            recent papers and cross-filter the multi-graph.
          </p>
        </div>
        <div className="v7-hero-actions">
          <button className="v7-btn" onClick={() => void load()} disabled={loading}>
            ↻ Refresh
          </button>
        </div>
      </div>

      {/* Stat overview */}
      <div className="v7-stat-grid">
        <div className="v7-stat">
          <div className="label">AC members</div>
          <div className="value">{data?.total_people ?? "—"}</div>
          <div className="delta">in the periodic grid</div>
        </div>
        <div className="v7-stat">
          <div className="label">Heaviest element</div>
          <div className="value" style={{ fontSize: "1.5rem" }}>
            {data?.elements[0]?.name ?? "—"}
          </div>
          <div className="delta">
            {data?.elements[0] ? `${data.elements[0].atomic_number} papers` : ""}
          </div>
        </div>
        <div className="v7-stat">
          <div className="label">Categories</div>
          <div className="value">{data?.categories.length ?? 0}</div>
          <div className="delta">distinct research topics</div>
        </div>
      </div>

      {error && (
        <div
          className="v7-card"
          style={{ borderColor: "rgba(249,115,22,0.4)", color: "var(--uncertain)" }}
        >
          Backend error: {error}
        </div>
      )}

      {/* Legend */}
      {data && data.categories.length > 0 && (
        <div className="v7-legend-row">
          {data.categories.map((cat) => (
            <span
              key={cat.id}
              className="v7-legend-chip"
              style={
                {
                  "--swatch-color": colorForCategory(cat.id, categoryIds),
                } as React.CSSProperties
              }
            >
              <span className="swatch" />
              {cat.label}
              <span style={{ color: "var(--muted)", fontSize: "0.72rem" }}>
                · {cat.paper_count}
              </span>
            </span>
          ))}
        </div>
      )}

      {/* Grid */}
      <div className="v7-card" style={{ padding: "1rem 1.1rem" }}>
        {loading && !data ? (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(100px, 1fr))",
              gap: 8,
            }}
          >
            {Array.from({ length: 8 }).map((_, i) => (
              <div
                key={i}
                className="v7-skel card"
                style={{ height: 110, borderRadius: 10 }}
              />
            ))}
          </div>
        ) : !data || data.elements.length === 0 ? (
          <div className="v7-empty">
            <span className="icon">🧪</span>
            <div>No AC members in the table yet.</div>
            <div style={{ marginTop: 8, fontSize: 13 }}>
              Add rows to <code>ac_members.csv</code> and re-ingest.
            </div>
          </div>
        ) : (
          <div className="v7-people-grid">
            {data.elements.map((el, idx) => {
              const color = colorForCategory(el.category, categoryIds);
              return (
                <button
                  key={el.person_id}
                  type="button"
                  className={`v7-element ${selected?.person_id === el.person_id ? "selected" : ""}`}
                  style={
                    {
                      "--cell-color": color,
                      animationDelay: `${Math.min(idx, 30) * 18}ms`,
                    } as React.CSSProperties
                  }
                  onClick={() =>
                    setSelected(
                      selected?.person_id === el.person_id ? null : el
                    )
                  }
                  title={`${el.name} · ${el.atomic_number} papers · ${el.category_label}`}
                >
                  <div className="atomic-number">{el.atomic_number}</div>
                  <div className="symbol">{el.symbol}</div>
                  <div className="person-name">{el.name}</div>
                  <div className="category-strip" />
                </button>
              );
            })}
          </div>
        )}
      </div>

      {selected && (
        <div
          className="v7-person-panel"
          style={
            {
              "--cell-color": colorForCategory(selected.category, categoryIds),
            } as React.CSSProperties
          }
        >
          <div className="person-head">
            <div className="person-symbol">{selected.symbol}</div>
            <div style={{ flex: 1 }}>
              <h2 style={{ margin: 0, fontSize: "1.2rem" }}>{selected.name}</h2>
              <div className="person-meta">
                <strong>{selected.atomic_number}</strong> papers ·{" "}
                <strong>{selected.core_count}</strong> core ·{" "}
                <strong>{selected.related_count}</strong> related
                <br />
                {selected.institution} · {selected.country ?? "—"}
                {selected.orcid && (
                  <>
                    {" · "}
                    <a
                      href={`https://orcid.org/${selected.orcid}`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {selected.orcid}
                    </a>
                  </>
                )}
              </div>
            </div>
            <a
              className="v7-btn primary"
              href={`/insights?tab=network&center=author:${selected.person_id}`}
            >
              Focus in network →
            </a>
          </div>
          <h3 style={{ fontSize: "0.95rem", margin: "0 0 0.5rem" }}>
            Recent papers
          </h3>
          {selected.papers.length === 0 ? (
            <div style={{ color: "var(--muted)" }}>No papers yet.</div>
          ) : (
            <ul className="paper-list">
              {selected.papers.map((p) => (
                <li key={p.id}>
                  <span style={{ color: "var(--muted)", minWidth: 36 }}>
                    {p.year ?? "—"}
                  </span>
                  {p.label && (
                    <span
                      className={`v7-label ${p.label}`}
                      style={{ fontSize: "0.7rem", padding: "0.1rem 0.45rem" }}
                    >
                      {p.label.split("_")[0]}
                    </span>
                  )}
                  <span style={{ flex: 1 }}>{p.title}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
