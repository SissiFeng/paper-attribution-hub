import { Fragment, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { getKbEntities, getKbEntityPage, getKbSummary } from "@/lib/api";
import type { KbEntityIndexItem, KbEntityPage, KbSummary } from "@/types";
import styles from "./KnowledgeHierarchy.module.css";

const ENTITY_TYPES = ["all", "method", "material", "instrument", "software"];

function yearSpan(first: number | null, last: number | null): string {
  if (first == null && last == null) return "—";
  if (first === last) return String(first);
  return `${first ?? "?"}–${last ?? "?"}`;
}

function EntityDetail({ detail }: { detail: KbEntityPage }) {
  return (
    <div style={{ padding: "0.6rem 0.4rem" }}>
      {detail.concept_id && (
        <section className={styles.hierarchyBand} aria-label="Ontology hierarchy">
          <div>
            <div className={styles.lineage}>
              {[...detail.ancestors].reverse().map((ancestor) => (
                <Fragment key={ancestor.concept_id}>
                  <span className={styles.branch}>{ancestor.name}</span>
                  <span aria-hidden="true">→</span>
                </Fragment>
              ))}
              <strong>{detail.entity}</strong>
            </div>
            <div className={styles.conceptId}>{detail.concept_id}</div>
            {detail.children.length > 0 && (
              <div className={styles.lineage} style={{ marginTop: 8 }}>
                <span>Branches</span>
                {detail.children.map((child) => (
                  <span className={styles.branch} key={child.concept_id}>
                    {child.name}
                  </span>
                ))}
              </div>
            )}
          </div>
          <div className={styles.metricPair} aria-label="Direct and rolled-up coverage">
            <div>
              <strong>{detail.direct_paper_count}</strong>
              <span>direct papers</span>
            </div>
            <div>
              <strong>{detail.rolled_up_paper_count}</strong>
              <span>with branches</span>
            </div>
          </div>
        </section>
      )}

      {(detail.reactions.length > 0 || detail.compositions.length > 0) && (
        <div className={styles.facetGrid}>
          <section className={styles.facetColumn}>
            <h4>Catalyzed reactions</h4>
            {detail.reactions.length === 0 ? (
              <div className="empty">No reaction relation extracted.</div>
            ) : (
              <ul className={styles.facetList}>
                {detail.reactions.map((facet) => (
                  <li className={styles.facetRow} key={facet.concept_id ?? facet.name}>
                    <span>
                      {facet.name} · {facet.paper_count} paper(s)
                    </span>
                    <span className={styles.stateBadge}>{facet.knowledge_state}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
          <section className={styles.facetColumn}>
            <h4>Explicit compositions</h4>
            {detail.compositions.length === 0 ? (
              <div className="empty">No explicit composition extracted.</div>
            ) : (
              <ul className={styles.facetList}>
                {detail.compositions.map((facet) => (
                  <li className={styles.facetRow} key={facet.name}>
                    <span>
                      {facet.name} · {facet.paper_count} paper(s)
                    </span>
                    <span className={styles.stateBadge}>{facet.knowledge_state}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      )}

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
                <span className={styles.evidenceMeta}>
                  <span style={{ color: "var(--muted)" }}>{ev.paper_title}</span>
                  {ev.matched_entity && (
                    <span className={styles.branch}>{ev.matched_entity}</span>
                  )}
                  {ev.knowledge_state && (
                    <span className={styles.stateBadge}>{ev.knowledge_state}</span>
                  )}
                </span>
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
          No SDL labs or paper↔lab links yet. Run{" "}
          <code>python -m app.scripts.seed_sdl_labs</code> and{" "}
          <code>python -m app.scripts.run_entity_extraction</code> in the backend
          first, then reload.
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
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        toggleRow(item);
                      }
                    }}
                    className={styles.interactiveRow}
                    tabIndex={0}
                    role="button"
                    aria-expanded={expanded === key}
                    style={{ cursor: "pointer" }}
                  >
                    <td>
                      <span className={styles.entityName}>
                        <span aria-hidden="true">
                          {expanded === key ? "▾" : "▸"}
                        </span>
                        {item.parent_concept_ids.length > 0 && (
                          <span className={styles.depthMark} aria-label="ontology branch">
                            └
                          </span>
                        )}
                        {item.name}
                      </span>
                    </td>
                    <td>{item.entity_type}</td>
                    <td className={styles.countCell}>
                      {item.direct_paper_count ?? item.paper_count}
                      {item.rolled_up_paper_count != null &&
                        item.rolled_up_paper_count !== item.direct_paper_count && (
                          <span className={styles.rollupCount}>
                            {item.rolled_up_paper_count} incl. branches
                          </span>
                        )}
                    </td>
                    <td className={styles.countCell}>
                      {item.direct_lab_count ?? item.lab_count}
                      {item.rolled_up_lab_count != null &&
                        item.rolled_up_lab_count !== item.direct_lab_count && (
                          <span className={styles.rollupCount}>
                            {item.rolled_up_lab_count} incl. branches
                          </span>
                        )}
                    </td>
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
