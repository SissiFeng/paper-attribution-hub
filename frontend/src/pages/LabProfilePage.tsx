import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { getKbLabProfile } from "@/lib/api";
import type { KbLabProfile } from "@/types";

const ENTITY_TYPE_ORDER = ["method", "material", "instrument", "software"];

export default function LabProfilePage() {
  const { labId } = useParams<{ labId: string }>();
  const [profile, setProfile] = useState<KbLabProfile | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!labId) return;
    let cancelled = false;
    setProfile(null);
    setError(null);
    getKbLabProfile(labId)
      .then((p) => !cancelled && setProfile(p))
      .catch(
        (err) => !cancelled && setError(err instanceof Error ? err.message : String(err))
      );
    return () => {
      cancelled = true;
    };
  }, [labId]);

  if (error) {
    return (
      <div>
        <h2>Lab Profile</h2>
        <div style={{ color: "var(--uncertain)" }}>Backend error: {error}</div>
      </div>
    );
  }
  if (!profile) {
    return (
      <div>
        <h2>Lab Profile</h2>
        <div className="empty">Loading…</div>
      </div>
    );
  }

  const maxTagCount = Math.max(1, ...profile.sdl_tag_histogram.map((t) => t.count));

  return (
    <div>
      <h2>{profile.name}</h2>
      <p style={{ color: "var(--muted)", marginTop: "0.2rem" }}>
        {profile.institution}
        {profile.pi_names.length > 0 && <> · PIs: {profile.pi_names.join(", ")}</>}
        {" · "}
        {profile.domain_focus}
      </p>

      <div className="eval-headline" style={{ marginTop: "0.4rem" }}>
        <div className="cell">
          <div className="label">Papers</div>
          <div className="value">{profile.paper_count}</div>
        </div>
        <div className="cell">
          <div className="label">Years</div>
          <div className="value">
            {profile.first_year != null
              ? `${profile.first_year}–${profile.last_year}`
              : "—"}
          </div>
        </div>
        <div className="cell">
          <div className="label">Collaborating labs</div>
          <div className="value">{profile.collaborations.length}</div>
        </div>
        <div className="cell">
          <div className="label">Unique entities</div>
          <div className="value">{profile.entities_unique_to_lab}</div>
        </div>
      </div>

      {profile.paper_count === 0 && (
        <div className="empty" style={{ marginTop: "0.8rem" }}>
          No papers linked to this lab yet. Run{" "}
          <code>python -m app.scripts.seed_sdl_labs</code> and{" "}
          <code>python -m app.scripts.run_entity_extraction</code> in the backend
          first, then reload.
        </div>
      )}

      <h3 style={{ marginTop: "1rem" }}>SDL tags</h3>
      {profile.sdl_tag_histogram.length === 0 ? (
        <div className="empty">No sdl_tags on linked papers.</div>
      ) : (
        <div>
          {profile.sdl_tag_histogram.map((t) => (
            <div
              key={t.tag}
              style={{ display: "flex", alignItems: "center", gap: "0.5rem", margin: "0.25rem 0" }}
            >
              <span style={{ width: 220, color: "var(--muted)", fontSize: "0.85rem" }}>
                {t.tag}
              </span>
              <div
                style={{
                  width: `${(t.count / maxTagCount) * 60}%`,
                  minWidth: 4,
                  height: 12,
                  background: "var(--accent, #34d399)",
                  borderRadius: 3,
                }}
              />
              <span style={{ fontSize: "0.85rem" }}>{t.count}</span>
            </div>
          ))}
        </div>
      )}

      <h3 style={{ marginTop: "1.4rem" }}>Top entities</h3>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
          gap: "1rem",
        }}
      >
        {ENTITY_TYPE_ORDER.map((etype) => {
          const items = profile.top_entities[etype] ?? [];
          return (
            <div key={etype}>
              <h4 style={{ margin: "0 0 0.4rem", textTransform: "capitalize" }}>
                {etype}
              </h4>
              {items.length === 0 ? (
                <div className="empty">None extracted.</div>
              ) : (
                <ul className="impact-list">
                  {items.map((item) => (
                    <li key={item.name}>
                      <span>{item.name}</span>
                      <span style={{ color: "var(--muted)" }}>
                        {item.paper_count}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          );
        })}
      </div>

      <h3 style={{ marginTop: "1.4rem" }}>Collaborations</h3>
      {profile.collaborations.length === 0 ? (
        <div className="empty">No shared papers with other labs.</div>
      ) : (
        <ul className="impact-list">
          {profile.collaborations.map((c) => (
            <li key={c.lab_id}>
              <span>
                <Link to={`/labs/${c.lab_id}`}>{c.name}</Link>
              </span>
              <span style={{ color: "var(--muted)" }}>
                {c.shared_papers} shared paper(s)
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
