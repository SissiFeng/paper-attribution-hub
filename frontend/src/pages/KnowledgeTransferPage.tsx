import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { EChart } from "@/components/EChart";
import { getTransferAdoption, getTransferFlows, getTransferSummary } from "@/lib/api";
import type { AdoptionLag, TransferFlows, TransferSummary } from "@/types";
import styles from "./KnowledgeHierarchy.module.css";

const ENTITY_TYPES = ["all", "method", "material", "instrument", "software"];
type Granularity = "entity" | "parent" | "reaction";

function heatmapOption(flows: TransferFlows) {
  const labels = flows.labs.map((l) => l.name);
  const cells: [number, number, number][] = [];
  let maxVal = 1;
  flows.matrix.forEach((row, citing) =>
    row.forEach((count, cited) => {
      if (count > 0) {
        // x = cited lab, y = citing lab
        cells.push([cited, citing, count]);
        maxVal = Math.max(maxVal, count);
      }
    })
  );
  return {
    tooltip: {
      formatter: (p: any) =>
        `${labels[p.value[1]]} cites ${labels[p.value[0]]}: <b>${p.value[2]}</b>`,
    },
    grid: { left: 140, right: 40, top: 10, bottom: 60 },
    xAxis: {
      type: "category",
      data: labels,
      name: "cited lab",
      nameLocation: "middle",
      nameGap: 40,
      axisLabel: { color: "#9aa3b2" },
      splitArea: { show: true },
    },
    yAxis: {
      type: "category",
      data: labels,
      name: "citing lab",
      axisLabel: { color: "#9aa3b2" },
      splitArea: { show: true },
    },
    visualMap: {
      min: 0,
      max: maxVal,
      calculable: true,
      orient: "horizontal",
      left: "center",
      bottom: 0,
      textStyle: { color: "#9aa3b2" },
      inRange: { color: ["#1f232c", "#34d399"] },
    },
    series: [
      {
        type: "heatmap",
        data: cells,
        label: { show: true, color: "#e7eaf0" },
      },
    ],
  };
}

export default function KnowledgeTransferPage() {
  const [summary, setSummary] = useState<TransferSummary | null>(null);
  const [flows, setFlows] = useState<TransferFlows | null>(null);
  const [adoption, setAdoption] = useState<AdoptionLag[] | null>(null);
  const [entityType, setEntityType] = useState("all");
  const [granularity, setGranularity] = useState<Granularity>("entity");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([getTransferSummary(), getTransferFlows()])
      .then(([s, f]) => {
        if (!cancelled) {
          setSummary(s);
          setFlows(f);
        }
      })
      .catch(
        (err) => !cancelled && setError(err instanceof Error ? err.message : String(err))
      );
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const params: {
      entity_type?: string;
      granularity: Granularity;
    } = { granularity };
    if (granularity !== "reaction" && entityType !== "all") {
      params.entity_type = entityType;
    }
    getTransferAdoption(params)
      .then((a) => !cancelled && setAdoption(a))
      .catch(
        (err) => !cancelled && setError(err instanceof Error ? err.message : String(err))
      );
    return () => {
      cancelled = true;
    };
  }, [entityType, granularity]);

  if (error) {
    return (
      <div>
        <h2>Knowledge Transfer</h2>
        <div style={{ color: "var(--uncertain)" }}>Backend error: {error}</div>
      </div>
    );
  }
  if (!summary || !flows) {
    return (
      <div>
        <h2>Knowledge Transfer</h2>
        <div className="empty">Loading…</div>
      </div>
    );
  }

  if (summary.labs === 0 || summary.linked_papers === 0) {
    return (
      <div>
        <h2>Knowledge Transfer</h2>
        <div className="empty">
          No SDL labs or paper↔lab links yet. Run{" "}
          <code>python -m app.scripts.seed_sdl_labs</code> and{" "}
          <code>python -m app.scripts.run_entity_extraction</code> in the backend
          first, then reload.
        </div>
      </div>
    );
  }

  return (
    <div>
      <h2>Knowledge Transfer</h2>
      <p style={{ color: "var(--muted)", marginTop: "0.2rem" }}>
        How methods, materials, instruments and software spread between SDL labs —
        citation flows and adoption lags.
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
          <div className="label">Entities tracked</div>
          <div className="value">{summary.entities_tracked}</div>
        </div>
        <div className="cell">
          <div className="label">Cross-lab entities</div>
          <div className="value">{summary.cross_lab_entities}</div>
        </div>
        <div className="cell">
          <div className="label">Median adoption lag</div>
          <div className="value">
            {summary.median_adoption_lag_years != null
              ? `${summary.median_adoption_lag_years}y`
              : "—"}
          </div>
        </div>
      </div>

      <h3 style={{ marginTop: "1rem" }}>
        Lab × lab citation flows ({flows.total_cross_flows} cross-lab)
      </h3>
      {flows.total_cross_flows === 0 ? (
        <div className="empty">
          No cross-lab citation flows yet — flows appear once papers from
          different labs cite each other.
        </div>
      ) : (
        <EChart option={heatmapOption(flows)} style={{ height: 360 }} />
      )}

      <h3 style={{ marginTop: "1.4rem" }}>Entity adoption lags</h3>
      <div className="filters" style={{ marginTop: "0.4rem" }}>
        <label>
          Entity type:&nbsp;
          <select
            value={entityType}
            disabled={granularity === "reaction"}
            onChange={(e) => setEntityType(e.target.value)}
          >
            {ENTITY_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
        <label>
          Granularity:&nbsp;
          <select
            value={granularity}
            onChange={(e) => setGranularity(e.target.value as Granularity)}
          >
            <option value="entity">Specific entity</option>
            <option value="parent">Parent roll-up</option>
            <option value="reaction">Catalyzed reaction</option>
          </select>
        </label>
        <span className={styles.granularityNote}>
          {granularity === "entity" &&
            "Exact subtype mentions; photocatalyst and electrocatalyst stay separate."}
          {granularity === "parent" &&
            "Ontology children roll up to their parent, e.g. catalyst."}
          {granularity === "reaction" &&
            "Evidence-linked catalyst→reaction relations; these remain proposed."}
        </span>
      </div>
      {!adoption || adoption.length === 0 ? (
        <div className="empty">
          No {granularity === "reaction" ? "reactions" : "entities"} seen in 2+ labs
          {granularity !== "reaction" && entityType !== "all"
            ? ` for type "${entityType}"`
            : ""}
          .
        </div>
      ) : (
        <table className="eval-table">
          <thead>
            <tr>
              <th>Entity</th>
              <th>Type</th>
              <th>Origin lab</th>
              <th>Origin year</th>
              <th>Adopters</th>
            </tr>
          </thead>
          <tbody>
            {adoption.map((e) => (
              <tr key={`${granularity}:${e.entity_type}:${e.entity}`}>
                <td>{e.entity}</td>
                <td>
                  {e.entity_type}{" "}
                  {e.knowledge_state !== "observed" && (
                    <span className={styles.stateBadge}>{e.knowledge_state}</span>
                  )}
                </td>
                <td>
                  <Link to={`/labs/${e.origin_lab}`}>{e.origin_lab}</Link>
                </td>
                <td>{e.origin_year}</td>
                <td>
                  {e.adoptions.length === 0 ? (
                    <span style={{ color: "var(--muted)" }}>
                      none (tied origins)
                    </span>
                  ) : (
                    e.adoptions
                      .map((a) => `${a.lab} +${a.lag_years}y`)
                      .join(", ")
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {summary.fastest_spreading.length > 0 && (
        <>
          <h3 style={{ marginTop: "1.4rem" }}>Fastest-spreading entities</h3>
          <ul className="impact-list">
            {summary.fastest_spreading.map((f) => (
              <li key={`${f.entity_type}:${f.entity}`}>
                <span>
                  {f.entity}{" "}
                  <span style={{ color: "var(--muted)" }}>({f.entity_type})</span>
                </span>
                <span style={{ color: "var(--muted)" }}>
                  {f.adopter_count} adopter(s) · avg lag {f.avg_lag_years}y
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
