"""
Data audit for the new Scopus batch + AC Publications gold set.

Run from project root:
    python -m app.scripts.audit_new_data

Outputs a plain-text report to stdout and writes
  data/audit_report.txt
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

TIER_CSV = ROOT / "tier1_tier2_merged_classification_ready.csv"
AC_CSV = ROOT / "AC Publications (Focused)-Grid view.csv"

FUZZY_TITLE_THRESH = 0.85  # Jaccard token overlap threshold


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _norm_doi(doi: str | float) -> str | None:
    if pd.isna(doi):
        return None
    d = str(doi).strip().lower()
    d = re.sub(r"^https?://(dx\.)?doi\.org/", "", d)
    return d or None


def _norm_title(title: str | float) -> str:
    if pd.isna(title):
        return ""
    t = str(title).lower()
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _title_tokens(title: str) -> set[str]:
    return set(_norm_title(title).split())


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _year_norm(val) -> int | None:
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# load
# ---------------------------------------------------------------------------

def load_tier(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, low_memory=False)
    df.columns = df.columns.str.strip().str.lstrip("﻿").str.strip('"')
    df["_doi_norm"] = df["DOI"].apply(_norm_doi)
    df["_title_norm"] = df["Title"].apply(_norm_title)
    df["_year"] = df["Publication_Year"].apply(_year_norm)
    df["_first_author"] = df["first_author_name"].fillna("").str.strip().str.lower()
    return df


def load_ac(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, low_memory=False)
    df.columns = df.columns.str.strip().str.lstrip("﻿").str.strip('"')
    df["_doi_norm"] = df["DOI"].apply(_norm_doi)
    df["_title_norm"] = df["Title"].apply(_norm_title)
    df["_year"] = df["Publication Year"].apply(_year_norm)
    return df


# ---------------------------------------------------------------------------
# dedup analysis
# ---------------------------------------------------------------------------

def dedup_analysis(df: pd.DataFrame, label: str) -> dict:
    total = len(df)
    doi_missing = df["_doi_norm"].isna().sum()

    doi_counts = df["_doi_norm"].dropna().value_counts()
    dup_doi_groups = (doi_counts > 1).sum()
    dup_doi_rows = int((doi_counts[doi_counts > 1] - 1).sum())

    title_counts = df["_title_norm"].value_counts()
    dup_title_groups = int((title_counts > 1).sum())
    dup_title_rows = int((title_counts[title_counts > 1] - 1).sum())

    return {
        "label": label,
        "total": total,
        "doi_missing": int(doi_missing),
        "doi_missing_pct": round(doi_missing / total * 100, 1),
        "dup_doi_groups": int(dup_doi_groups),
        "dup_doi_extra_rows": dup_doi_rows,
        "dup_title_groups": dup_title_groups,
        "dup_title_extra_rows": dup_title_rows,
    }


# ---------------------------------------------------------------------------
# tier breakdown
# ---------------------------------------------------------------------------

def tier_breakdown(df: pd.DataFrame) -> dict:
    col = "RETRIEVAL_TIER"
    if col not in df.columns:
        return {}
    vc = df[col].value_counts()
    return {str(k): int(v) for k, v in vc.items()}


def year_range(df: pd.DataFrame, year_col: str = "_year") -> tuple[int | None, int | None]:
    valid = df[year_col].dropna()
    if valid.empty:
        return None, None
    return int(valid.min()), int(valid.max())


# ---------------------------------------------------------------------------
# AC gold match
# ---------------------------------------------------------------------------

def match_ac_to_tier(tier: pd.DataFrame, ac: pd.DataFrame) -> dict:
    # build lookup indices for tier
    tier_by_doi: dict[str, int] = {}
    for idx, row in tier.iterrows():
        if row["_doi_norm"]:
            tier_by_doi.setdefault(row["_doi_norm"], idx)

    tier_titles = [(i, row["_title_norm"], row["_year"]) for i, row in tier.iterrows()]

    matched_doi: list[int] = []       # ac row indices matched by DOI
    matched_title: list[int] = []     # ac row indices matched by fuzzy title
    unmatched: list[int] = []

    tier_matched_idx: set = set()     # tier row indices that matched any AC paper

    for ac_idx, ac_row in ac.iterrows():
        doi = ac_row["_doi_norm"]
        ac_title_tok = _title_tokens(ac_row["_title_norm"])
        ac_year = ac_row["_year"]

        # 1. DOI exact
        if doi and doi in tier_by_doi:
            matched_doi.append(ac_idx)
            tier_matched_idx.add(tier_by_doi[doi])
            continue

        # 2. fuzzy title + year
        best_score = 0.0
        best_tier_idx = None
        for t_idx, t_title, t_year in tier_titles:
            if ac_year and t_year and abs(ac_year - t_year) > 1:
                continue
            score = _jaccard(ac_title_tok, _title_tokens(t_title))
            if score > best_score:
                best_score = score
                best_tier_idx = t_idx

        if best_score >= FUZZY_TITLE_THRESH and best_tier_idx is not None:
            matched_title.append(ac_idx)
            tier_matched_idx.add(best_tier_idx)
        else:
            unmatched.append(ac_idx)

    return {
        "ac_total": len(ac),
        "matched_by_doi": len(matched_doi),
        "matched_by_title": len(matched_title),
        "matched_total": len(matched_doi) + len(matched_title),
        "unmatched_ac": len(unmatched),
        "recall_pct": round((len(matched_doi) + len(matched_title)) / len(ac) * 100, 1),
        "tier_rows_matching_ac": len(tier_matched_idx),
        "unmatched_ac_indices": unmatched,
        "matched_doi_indices": matched_doi,
        "matched_title_indices": matched_title,
    }


# ---------------------------------------------------------------------------
# retrieval tier of matched AC papers
# ---------------------------------------------------------------------------

def matched_tier_distribution(tier: pd.DataFrame, match_result: dict) -> dict:
    # rebuild from match result — re-run lightweight match to get tier idx
    # (we already have indices but only tier_matched_idx set — recompute)
    # Simpler: just filter tier rows whose DOI is in AC DOIs
    return {}  # placeholder; real impl below


def tier_dist_for_matched(tier: pd.DataFrame, ac: pd.DataFrame, match_res: dict) -> dict:
    """Return RETRIEVAL_TIER distribution for tier rows matched to AC gold."""
    ac_doi_set = set(ac["_doi_norm"].dropna())

    matched_rows = tier[tier["_doi_norm"].isin(ac_doi_set)]
    if "RETRIEVAL_TIER" not in tier.columns or matched_rows.empty:
        return {}
    vc = matched_rows["RETRIEVAL_TIER"].value_counts()
    return {str(k): int(v) for k, v in vc.items()}


# ---------------------------------------------------------------------------
# unmatched AC paper characteristics
# ---------------------------------------------------------------------------

def unmatched_ac_profile(ac: pd.DataFrame, unmatched_idx: list[int]) -> dict:
    if not unmatched_idx:
        return {"count": 0}
    sub = ac.loc[unmatched_idx]
    result: dict = {"count": len(sub)}

    for col in ["SDL", "Acknowledges AC", "Highly Relevant", "AC Funded Programs"]:
        if col in sub.columns:
            non_null = sub[col].dropna()
            # treat empty string as null
            non_null = non_null[non_null.str.strip() != ""]
            result[f"{col}_non_null"] = int(len(non_null))

    if "_year" in sub.columns:
        yr = sub["_year"].dropna()
        if not yr.empty:
            result["year_min"] = int(yr.min())
            result["year_max"] = int(yr.max())

    return result


# ---------------------------------------------------------------------------
# Tier 2 noise heuristic: docs with only 1 architecture component
# ---------------------------------------------------------------------------

def tier2_noise_estimate(tier: pd.DataFrame) -> dict:
    tier2 = tier[tier["RETRIEVAL_TIER"].astype(str) == "2"].copy()
    if tier2.empty:
        return {"tier2_total": 0}

    def _has_token(text: str | float, tokens: list[str]) -> bool:
        if pd.isna(text):
            return False
        t = str(text).lower()
        return any(tok in t for tok in tokens)

    ai_kw = ["machine learning", "deep learning", "neural network", "reinforcement learning",
             "bayesian optimization", "gaussian process", "active learning", "ai-driven",
             "ai driven", "artificial intelligence"]
    auto_kw = ["automated", "high-throughput", "high throughput", "robotic", "autonomous experimentation",
               "liquid handling", "automated synthesis", "flow chemistry"]
    loop_kw = ["closed-loop", "closed loop", "iterative optimization", "self-driving",
               "autonomous discovery", "feedback loop", "sequential optimization"]

    combined = (tier2["Title"].fillna("") + " " + tier2["Abstract"].fillna(""))
    tier2["_ai"] = combined.apply(lambda x: _has_token(x, ai_kw))
    tier2["_auto"] = combined.apply(lambda x: _has_token(x, auto_kw))
    tier2["_loop"] = combined.apply(lambda x: _has_token(x, loop_kw))

    tier2["_component_count"] = tier2[["_ai", "_auto", "_loop"]].sum(axis=1)

    dist = tier2["_component_count"].value_counts().sort_index()
    return {
        "tier2_total": len(tier2),
        "components_0": int(dist.get(0, 0)),
        "components_1": int(dist.get(1, 0)),
        "components_2": int(dist.get(2, 0)),
        "components_3": int(dist.get(3, 0)),
        "all_3_components": int((tier2["_component_count"] == 3).sum()),
        "only_1_component_pct": round(int(dist.get(1, 0)) / len(tier2) * 100, 1),
        "strong_sdl_pct": round(int(dist.get(3, 0)) / len(tier2) * 100, 1),
    }


# ---------------------------------------------------------------------------
# AC publications field coverage
# ---------------------------------------------------------------------------

def ac_field_coverage(ac: pd.DataFrame) -> dict:
    result = {}
    for col in ["Acknowledges AC", "Highly Relevant", "High Impact",
                "AC Funded Programs", "AC Members", "SDL",
                "Research Tags", "Applied Tags"]:
        if col not in ac.columns:
            result[col] = "N/A"
            continue
        non_null = ac[col].dropna()
        non_null = non_null[non_null.str.strip() != ""]
        result[col] = f"{len(non_null)} / {len(ac)} ({round(len(non_null)/len(ac)*100,1)}%)"
    return result


def ac_year_dist(ac: pd.DataFrame) -> dict:
    vc = ac["_year"].value_counts().sort_index()
    return {str(int(k)): int(v) for k, v in vc.items() if not pd.isna(k)}


def tier_year_dist(df: pd.DataFrame) -> dict:
    vc = df["_year"].value_counts().sort_index()
    return {str(int(k)): int(v) for k, v in vc.items() if not pd.isna(k)}


# ---------------------------------------------------------------------------
# report formatter
# ---------------------------------------------------------------------------

def fmt_section(title: str) -> str:
    bar = "=" * 60
    return f"\n{bar}\n  {title}\n{bar}"


def fmt_dict(d: dict, indent: int = 2) -> str:
    pad = " " * indent
    lines = []
    for k, v in d.items():
        if isinstance(v, dict):
            lines.append(f"{pad}{k}:")
            lines.append(fmt_dict(v, indent + 4))
        else:
            lines.append(f"{pad}{k}: {v}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def run_audit() -> str:
    lines: list[str] = []
    lines.append("PAPER ATTRIBUTION SYSTEM — DATA AUDIT REPORT")
    lines.append("Files audited:")
    lines.append(f"  tier1_tier2: {TIER_CSV.name}")
    lines.append(f"  ac_gold:     {AC_CSV.name}")
    lines.append("")

    print("Loading CSVs...", file=sys.stderr)
    tier = load_tier(TIER_CSV)
    ac = load_ac(AC_CSV)
    print(f"  tier: {len(tier)} rows, ac: {len(ac)} rows", file=sys.stderr)

    # ── 1. Basic dedup stats ──────────────────────────────────────────────
    lines.append(fmt_section("1. DEDUPLICATION ANALYSIS"))

    t_dedup = dedup_analysis(tier, "tier1_tier2")
    lines.append("\ntier1_tier2_merged:")
    lines.append(fmt_dict({k: v for k, v in t_dedup.items() if k != "label"}))

    ac_dedup = dedup_analysis(ac, "ac_publications")
    lines.append("\nAC Publications:")
    lines.append(fmt_dict({k: v for k, v in ac_dedup.items() if k != "label"}))

    # ── 2. Tier breakdown ─────────────────────────────────────────────────
    lines.append(fmt_section("2. RETRIEVAL TIER BREAKDOWN"))
    tb = tier_breakdown(tier)
    for k, v in sorted(tb.items()):
        pct = round(v / len(tier) * 100, 1)
        lines.append(f"  Tier {k}: {v:>6} rows  ({pct}%)")

    yr_min, yr_max = year_range(tier)
    lines.append(f"\n  Year range: {yr_min} – {yr_max}")
    lines.append("\n  Year distribution (tier1_tier2):")
    for yr, cnt in tier_year_dist(tier).items():
        lines.append(f"    {yr}: {cnt}")

    # ── 3. AC Publications field coverage ────────────────────────────────
    lines.append(fmt_section("3. AC PUBLICATIONS — FIELD COVERAGE"))
    fc = ac_field_coverage(ac)
    lines.append(fmt_dict(fc))
    lines.append("\n  Year distribution (AC Publications):")
    for yr, cnt in ac_year_dist(ac).items():
        lines.append(f"    {yr}: {cnt}")

    # ── 4. AC ↔ tier matching ─────────────────────────────────────────────
    lines.append(fmt_section("4. AC GOLD ↔ CANDIDATE POOL MATCHING"))
    print("Running AC ↔ tier match (fuzzy title scan)...", file=sys.stderr)
    match_res = match_ac_to_tier(tier, ac)

    lines.append(f"""
  AC papers total:              {match_res['ac_total']}
  Matched by DOI exact:         {match_res['matched_by_doi']}
  Matched by fuzzy title:       {match_res['matched_by_title']}
  Total matched:                {match_res['matched_total']}
  NOT found in candidate pool:  {match_res['unmatched_ac']}
  Retrieval RECALL on AC gold:  {match_res['recall_pct']}%

  Tier rows that are AC papers: {match_res['tier_rows_matching_ac']}
    (= {round(match_res['tier_rows_matching_ac']/len(tier)*100,2)}% of 10890 candidates)""")

    # Tier distribution of matched AC papers
    lines.append("\n  RETRIEVAL_TIER of matched AC papers:")
    td = tier_dist_for_matched(tier, ac, match_res)
    if td:
        for k, v in sorted(td.items()):
            lines.append(f"    Tier {k}: {v}")
    else:
        lines.append("    (unable to compute)")

    # ── 5. Unmatched AC profile ───────────────────────────────────────────
    lines.append(fmt_section("5. UNMATCHED AC PAPERS — PROFILE"))
    unmatched_profile = unmatched_ac_profile(ac, match_res["unmatched_ac_indices"])
    lines.append(fmt_dict(unmatched_profile))

    # Sample titles of unmatched AC papers
    if match_res["unmatched_ac_indices"]:
        lines.append("\n  Sample unmatched AC paper titles (up to 15):")
        sample_idx = match_res["unmatched_ac_indices"][:15]
        for i in sample_idx:
            row = ac.loc[i]
            yr = row.get("Publication Year", "?")
            title = str(row.get("Title", ""))[:80]
            lines.append(f"    [{yr}] {title}")

    # ── 6. Tier 2 noise heuristic ─────────────────────────────────────────
    lines.append(fmt_section("6. TIER 2 NOISE HEURISTIC (architecture components)"))
    noise = tier2_noise_estimate(tier)
    lines.append(fmt_dict(noise))
    lines.append("""
  Interpretation:
    components_3 = strong SDL (AI + automation + closed-loop)
    components_2 = partial SDL (meets two-of-three rule)
    components_1 = weak match (likely noise in Tier 2)
    components_0 = no keyword match (retrieval on other terms)""")

    # ── 7. Summary & recommendations ─────────────────────────────────────
    lines.append(fmt_section("7. SUMMARY & RECOMMENDATIONS"))

    recall = match_res["recall_pct"]
    if recall < 70:
        recall_note = "⚠  LOW — retrieval protocol may be too narrow"
    elif recall < 85:
        recall_note = "⚡  MODERATE — review unmatched AC papers for missing query terms"
    else:
        recall_note = "✓  GOOD"

    noise_pct = noise.get("only_1_component_pct", "?")

    lines.append(f"""
  Retrieval recall on AC gold:  {recall}%  {recall_note}
  Tier 2 single-component rows: {noise_pct}%  (potential false positives)

  Recommended next steps:
  1. Deduplicate tier1_tier2 before any LLM classification
     → {t_dedup['dup_doi_extra_rows']} extra rows from duplicate DOIs to collapse
  2. Clean AC Publications gold set
     → {ac_dedup['dup_doi_extra_rows']} extra rows from duplicate DOIs
  3. Investigate {match_res['unmatched_ac']} AC papers not found by retrieval
     → are they missing SDL keywords? check titles above
  4. Use Tier 2 architecture score decomposition to reduce noise
     → {noise.get('components_1', '?')} single-component Tier 2 rows are candidate exclusions
  5. Run rule-based classifier before any LLM pass""")

    report = "\n".join(lines)
    return report


if __name__ == "__main__":
    report = run_audit()
    print(report)

    out = DATA_DIR / "audit_report.txt"
    out.write_text(report, encoding="utf-8")
    print(f"\n[audit] Report saved to {out}", file=sys.stderr)
