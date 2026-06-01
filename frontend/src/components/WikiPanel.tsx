import { useEffect, useState } from "react";
import { compileWikiPage, getWikiPage } from "@/lib/api";
import type { WikiPage, WikiSection } from "@/types";
import css from "./WikiPanel.module.css";

// ── Section icons ──────────────────────────────────────────────────────────
const SECTION_ICONS: Record<string, string> = {
  identity:      "#",
  abstract_summary: "≡",
  retrieval_provenance: "↵",
  sdl_evidence:  "◎",
  ac_evidence:   "⬡",
  classification:"✓",
  links:         "↗",
  overview:      "◈",
  ac_connection: "⬡",
  contribution:  "◆",
  evidence:      "▣",
  topics:        "◉",
  related:       "↗",
  open_questions:"?",
  review_notes:  "✎",
};

function SectionBlock({ section }: { section: WikiSection }) {
  const icon = SECTION_ICONS[section.key] ?? "·";
  return (
    <div className={css.section}>
      <h4 className={css.sectionHeading}>
        <span style={{ color: "var(--color-steel)", fontWeight: 400 }}>{icon}</span>
        {section.heading}
      </h4>
      <p className={css.sectionBody}>{section.body}</p>
      {section.chips && section.chips.length > 0 && (
        <div className={css.chips}>
          {section.chips.map((chip, i) => (
            <span key={i} className={`${css.chip} ${css[chip.kind] ?? ""}`}>
              {chip.label}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function Skeleton() {
  return (
    <div>
      <div className={`${css.skeleton} ${css.skLine} ${css.wide}`}  style={{ marginBottom: 16 }} />
      <div className={`${css.skeleton} ${css.skLine} ${css.wide}`} />
      <div className={`${css.skeleton} ${css.skLine} ${css.mid}`} />
      <div className={`${css.skeleton} ${css.skLine} ${css.short}`} style={{ marginBottom: 20 }} />
      <div className={`${css.skeleton} ${css.skLine} ${css.wide}`} />
      <div className={`${css.skeleton} ${css.skLine} ${css.mid}`} />
    </div>
  );
}

interface Props {
  paperId: string;
}

export function WikiPanel({ paperId }: Props) {
  const [wiki, setWiki]       = useState<WikiPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [compiling, setCompiling] = useState(false);
  const [error, setError]     = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setWiki(null);
    getWikiPage(paperId)
      .then(w => { if (!cancelled) { setWiki(w); setLoading(false); } })
      .catch(e => { if (!cancelled) { setError(String(e)); setLoading(false); } });
    return () => { cancelled = true; };
  }, [paperId]);

  const handleCompile = async () => {
    setCompiling(true);
    setError(null);
    try {
      const w = await compileWikiPage(paperId);
      setWiki(w);
    } catch (e) {
      setError(String(e));
    } finally {
      setCompiling(false);
    }
  };

  const ts = wiki?.generated_at
    ? new Date(wiki.generated_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })
    : null;

  return (
    <div className={css.root}>
      {/* Meta bar */}
      <div className={css.meta}>
        <span className={css.metaLabel}>Knowledge Digest</span>
        {wiki && (
          <>
            <span className={css.metaValue}>model: {wiki.model_version}</span>
            <span className={css.metaValue}>·</span>
            <span className={css.metaValue}>{ts}</span>
            {wiki.is_stale && (
              <span className={css.stale}>⚠ stale</span>
            )}
          </>
        )}
        <button
          className={css.compileBtn}
          onClick={handleCompile}
          disabled={compiling || loading}
        >
          {compiling ? "Compiling…" : wiki?.is_stale ? "↻ Recompile" : "↻ Compile"}
        </button>
      </div>

      {/* Body */}
      {loading && <Skeleton />}

      {!loading && error && (
        <div className={css.empty}>{error}</div>
      )}

      {!loading && !error && wiki && (
        wiki.sections.length === 0 ? (
          <div className={css.empty}>
            No content yet — click Compile to generate the knowledge digest.
          </div>
        ) : (
          wiki.sections.map(s => <SectionBlock key={s.key} section={s} />)
        )
      )}
    </div>
  );
}
