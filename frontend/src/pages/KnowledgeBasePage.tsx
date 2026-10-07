import { Fragment, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { getKbEntities, getKbEntityPage, getKbSummary } from "@/lib/api";
import type { KbEntityIndexItem, KbEntityPage, KbSummary } from "@/types";

const ENTITY_TYPES = ["all", "method", "material", "instrument", "software"];

function yearSpan(first: number | null, last: number | null): string {
  if (first == null && last == null) return "—";
  if (first === last) return String(first);
  return `${first ?? "?"}–${last ?? "?"}`;
}

function EntityDetail({ detail }: { detail: KbEntityPage }) {
  return (
    <div style={{ padding: "0.6rem 0.4rem" }}>
      <h4 style={{ margin: "0 0 0.4rem" }}>Labs</h4>
      {detail.labs.length === 0 ? (
        <div className="empty">No lab-linked papers mention this entity.</div>
      ) : (
        <ul className="impact-list">
          {detail.labs.map((l) => (
            <li key={l.lab_id}>
              <span>
                <Link to={`/labs/${l.lab_id}`}>{l.lab_name}</Link>
              </span>
              <span style={{ color: "var(--muted)" }}>
                first {l.first_year ?? "—"} · {l.paper_count} paper(s)
              </span>
            </li>
          ))}
        </ul>
      )}

      {detail.adoption && detail.adoption.adoptions.length > 0 && (
        <>
          <h4 style={{ margin: "0.8rem 0 0.4rem" }}>Adoption</h4>
          <div style={{ color: "var(--muted)" }}>
            Origin{" "}
            <Link to={`/labs/${detail.adoption.origin_lab}`}>
              {detail.adoption.origin_lab}
            </Link>{" "}
            ({detail.adoption.origin_year});{" "}
            {detail.adoption.adoptions
              .map((a) => `${a.lab} +${a.lag_years}y`)
              .join(", ")}
          </div>
        </>
      )}

      <h4 style={{ margin: "0.8rem 0 0.4rem" }}>Papers</h4>
      <ul className="impact-list">
        {detail.papers.map((p) => (
          <li key={p.id}>
            <span>
              {p.title}{" "}
              <span style={{ color: "var(--muted)" }}>({p.year ?? "n.d."})</span>
            </span>
            <span style={{ color: "var(--muted)" }}>
              {p.labs.length > 0 ? p.labs.join(", ") : "no lab"} · conf{" "}
              {p.confidence.toFixed(2)}
            </span>
          </li>
        ))}
      </ul>

      <h4 style={{ margin: "0.8rem 0 0.4rem" }}>Evidence</h4>
      {detail.evidence.length === 0 ? (
        <div className="empty">No evidence snippets linked.</div>
      ) : (
        <ul className="impact-list">
          {detail.evidence.map((ev, i) => (
            <li key={`${ev.paper_id}-${i}`}>
              <span>
                <span style={{ color: "var(--muted)" }}>{ev.paper_title}: </span>
                “{ev.text}”
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function KnowledgeBasePage() {
  const [summary, setSummary] = useState<KbSummary | null>(null);
  const [entities, setEntities] = useState<KbEntityIndexItem[] | null>(null);
  const [entityType, setEntityType] = useState("all");
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [detail, setDetail] = useState<KbEntityPage | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getKbSummary()
      .then((s) => !cancelled && setSummary(s))
      .catch(
        (err) => !cancelled && setError(err instanceof Error ? err.message : String(err))
      );
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const params: { entity_type?: string; q?: string } = {};
    if (entityType !== "all") params.entity_type = entityType;
    if (query.trim()) params.q = query.trim();
    getKbEntities(params)
      .then((e) => !cancelled && setEntities(e))
      .catch(
        (err) => !cancelled && setError(err instanceof Error ? err.message : String(err))
      );
    return () => {
      cancelled = true;
    };
  }, [entityType, query]);

  function toggleRow(item: KbEntityIndexItem) {
    const key = `${item.entity_type}:${item.name}`;
    if (expanded === key) {
      setExpanded(null);
      setDetail(null);
      return;
    }
    setExpanded(key);
    setDetail(null);
    setDetailLoading(true);
    getKbEntityPage(item.entity_type, item.name)
      .then((d) => {
        setDetail(d);
        setDetailLoading(false);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : String(err));
        setDetailLoading(false);
      });
  }

  if (error) {
    return (
      <div>
        <h2>Knowledge Base</h2>
        <div style={{ color: "var(--uncertain)" }}>Backend error: {error}</div>
      </div>
    );
  }
  if (!summary) {
    return (
      <div>
        <h2>Knowledge Base</h2>
        <div className="empty">Loading…</div>
      </div>
    );
  }

  if (summary.labs === 0 || summary.linked_papers === 0) {
    return (
      <div>
        <h2>Knowledge Base</h2>
        <div className="empty">
          Paper-derived entities are available in the corpus graph. This page
          additionally requires a separately authorized SDL lab roster and verified
          paper↔lab links, which are not loaded yet.
        </div>
      </div>
    );
  }

  const totalEntities = Object.values(summary.entities_by_type).reduce(
    (a, b) => a + b,
    0
  );

  return (
    <div>
      <h2>Knowledge Base</h2>
      <p style={{ color: "var(--muted)", marginTop: "0.2rem" }}>
        Evidence-linked index of methods, materials, instruments and software
        across SDL labs.
      </p>

      <div className="eval-headline" style={{ marginTop: "0.4rem" }}>
        <div className="cell">
          <div className="label">SDL labs</div>
          <div className="value">{summary.labs}</div>
        </div>
        <div className="cell">
          <div className="label">Linked papers</div>
          <div className="value">{summary.linked_papers}</div>
        </div>
        <div className="cell">
          <div className="label">Entities</div>
          <div className="value">{totalEntities}</div>
        </div>
        <div className="cell">
          <div className="label">Cross-lab entities</div>
          <div className="value">{summary.cross_lab_entities}</div>
        </div>
      </div>

      <div className="filters" style={{ marginTop: "0.8rem" }}>
        <label>
          Entity type:&nbsp;
          <select value={entityType} onChange={(e) => setEntityType(e.target.value)}>
            {ENTITY_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
        <input
          type="search"
          placeholder="Search entities…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>

      {!entities ? (
        <div className="empty">Loading…</div>
      ) : entities.length === 0 ? (
        <div className="empty">No entities match the current filters.</div>
      ) : (
        <table className="eval-table">
          <thead>
            <tr>
              <th>Entity</th>
              <th>Type</th>
              <th>Papers</th>
              <th>Labs</th>
              <th>Years</th>
            </tr>
          </thead>
          <tbody>
            {entities.map((item) => {
              const key = `${item.entity_type}:${item.name}`;
              return (
                <Fragment key={key}>
                  <tr
                    onClick={() => toggleRow(item)}
                    style={{ cursor: "pointer" }}
                  >
                    <td>
                      {expanded === key ? "▾ " : "▸ "}
                      {item.name}
                    </td>
                    <td>{item.entity_type}</td>
                    <td>{item.paper_count}</td>
                    <td>{item.lab_count}</td>
                    <td>{yearSpan(item.first_year, item.last_year)}</td>
                  </tr>
                  {expanded === key && (
                    <tr>
                      <td colSpan={5}>
                        {detailLoading || !detail ? (
                          <div className="empty">Loading…</div>
                        ) : (
                          <EntityDetail detail={detail} />
                        )}
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
