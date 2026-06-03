import { useCallback, useEffect, useMemo, useState } from "react";

import { getPeopleGrid } from "@/lib/api";
import type { PeopleElement, PeopleGrid } from "@/types";

// SDL-specific colors — each SDL track gets a distinct color
const SDL_COLORS: Record<string, string> = {
  sdl_ai:           "#60a5fa",  // SDL 0 - AI & Automation  → blue
  sdl_robotics:     "#818cf8",  // SDL 1 - Robotics         → indigo
  sdl_organic:      "#34d399",  // SDL 2 - Organic          → emerald
  sdl_inorganic:    "#2dd4bf",  // SDL 3 - Inorganic        → teal
  sdl_biology:      "#f472b6",  // SDL 4 - Biology          → pink
  sdl_formulations: "#fbbf24",  // SDL 5 - Formulations     → amber
  sdl_energy:       "#fb923c",  // SDL 6 - Energy           → orange
  sdl_scale:        "#a78bfa",  // SDL 7 - Scale up         → violet
  sdl_other:        "#94a3b8",  // other SDL                → slate
  uncategorized:    "#64748b",  // no SDL data              → gray
};

// Fallback palette for unknown categories
const PALETTE = ["#E84A85","#F0712C","#F5C518","#5E4E96","#1B3590",
                  "#6377B5","#C73C73","#7E94CE","#F0A03A","#E891AC"];

function colorForCategory(category: string, allCategories: string[]): string {
  if (category in SDL_COLORS) return SDL_COLORS[category];
  const idx = allCategories.indexOf(category);
  return PALETTE[idx >= 0 ? idx % PALETTE.length : 0];
}

// ── Human review types ────────────────────────────────────────────────────────
interface DedupPair {
  author_a: { id: string; name: string; orcid?: string };
  author_b: { id: string; name: string; orcid?: string };
  score: number;
  reasons: string[];
}

// Persist dismissed pairs in localStorage so they don't reappear
const DISMISSED_KEY = "people_grid_dedup_dismissed";
function loadDismissed(): Set<string> {
  try {
    const raw = localStorage.getItem(DISMISSED_KEY);
    return new Set(raw ? JSON.parse(raw) : []);
  } catch { return new Set(); }
}
function saveDismissed(s: Set<string>) {
  try { localStorage.setItem(DISMISSED_KEY, JSON.stringify([...s])); } catch {}
}
function pairKey(a: string, b: string) {
  return [a, b].sort().join("__");
}

const API_BASE = (import.meta.env.VITE_API_BASE ?? "http://localhost:8000").replace(/\/$/, "");

export default function PeopleGridPage() {
  const [data, setData] = useState<PeopleGrid | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<PeopleElement | null>(null);
  const [dedupPairs, setDedupPairs] = useState<DedupPair[]>([]);
  const [dismissed, setDismissed] = useState<Set<string>>(loadDismissed);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const out = await getPeopleGrid();
      setData(out);
      // Also fetch dedup candidates
      const dd = await fetch(`${API_BASE}/admin/dedup-candidates`).then(r => r.json());
      setDedupPairs([...(dd.auto_merge ?? []), ...(dd.human_review ?? [])]);
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

      {/* ── Human review panel for uncertain duplicate pairs ─────────────── */}
      {(() => {
        const pending = dedupPairs.filter(
          p => !dismissed.has(pairKey(p.author_a.id, p.author_b.id))
        );
        if (pending.length === 0) return null;
        return (
          <div style={{
            marginTop: "2rem",
            border: "1px solid rgba(251,191,36,0.4)",
            borderRadius: 10,
            background: "rgba(251,191,36,0.06)",
            padding: "16px 20px",
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
              <span style={{ fontSize: 18 }}>⚠</span>
              <strong style={{ color: "#f59e0b" }}>
                {pending.length} possible duplicate{pending.length > 1 ? "s" : ""} — please review
              </strong>
              <span style={{ color: "var(--muted)", fontSize: "0.8rem" }}>
                Confirmed decisions won't appear again.
              </span>
            </div>

            {pending.map(pair => {
              const key = pairKey(pair.author_a.id, pair.author_b.id);
              const dismiss = () => {
                const next = new Set(dismissed);
                next.add(key);
                setDismissed(next);
                saveDismissed(next);
              };
              const handleMerge = async () => {
                // Keep the one with shorter ID (CSV anchor) or first one
                const keepId = pair.author_a.id < pair.author_b.id ? pair.author_a.id : pair.author_b.id;
                const removeId = keepId === pair.author_a.id ? pair.author_b.id : pair.author_a.id;
                await fetch(
                  `${API_BASE}/admin/dedup-merge?keep_id=${encodeURIComponent(keepId)}&remove_id=${encodeURIComponent(removeId)}&decided_by=human`,
                  { method: "POST" }
                );
                dismiss();
                void load();
              };
              const handleSeparate = async () => {
                await fetch(
                  `${API_BASE}/admin/dedup-separate?author_id_a=${encodeURIComponent(pair.author_a.id)}&author_id_b=${encodeURIComponent(pair.author_b.id)}&decided_by=human`,
                  { method: "POST" }
                );
                dismiss();
              };

              return (
                <div key={key} style={{
                  display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap",
                  padding: "10px 0", borderBottom: "1px solid rgba(251,191,36,0.15)",
                  fontSize: "0.85rem",
                }}>
                  <div style={{ flex: 1, minWidth: 200 }}>
                    <div style={{ display: "flex", gap: 8, alignItems: "baseline" }}>
                      <strong>{pair.author_a.name}</strong>
                      <span style={{ color: "var(--muted)", fontSize: "0.75rem" }}>{pair.author_a.id}</span>
                      <span style={{ color: "#f59e0b", fontFamily: "monospace" }}>↔</span>
                      <strong>{pair.author_b.name}</strong>
                      <span style={{ color: "var(--muted)", fontSize: "0.75rem" }}>{pair.author_b.id}</span>
                    </div>
                    <div style={{ color: "var(--muted)", fontSize: "0.78rem", marginTop: 2 }}>
                      Score {(pair.score * 100).toFixed(0)}% · {pair.reasons.join(" · ")}
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button
                      onClick={handleMerge}
                      style={{
                        padding: "4px 14px", borderRadius: 6, cursor: "pointer",
                        background: "#34d399", border: "none", color: "#0f1115",
                        fontWeight: 600, fontSize: "0.8rem",
                      }}
                    >
                      ✓ Same person
                    </button>
                    <button
                      onClick={handleSeparate}
                      style={{
                        padding: "4px 14px", borderRadius: 6, cursor: "pointer",
                        background: "transparent",
                        border: "1px solid rgba(249,115,22,0.5)",
                        color: "#fb923c", fontSize: "0.8rem",
                      }}
                    >
                      ✕ Different
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        );
      })()}
    </div>
  );
}
