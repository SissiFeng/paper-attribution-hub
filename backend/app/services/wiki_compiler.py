"""Wiki / Knowledge Digest compiler (v0.1).

Compiles a structured wiki page for a corpus entity from its DB data.
Two modes:
  - template (default): deterministic, no LLM required — builds sections
    from matched_people, topics, evidence, classification, graph signals.
  - llm (when PAS_WIKI_LLM=1): passes a rich prompt to the configured
    LLM and parses the JSON response into sections.

The template mode is sufficient for the frontend entry point and walk-through.
LLM mode can be wired in later.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Paper, WikiPage


# ── Section builders ──────────────────────────────────────────────────────────

def _chip(label: str, kind: str) -> dict:
    return {"label": label, "kind": kind}


def _build_paper_sections(paper: Paper) -> list[dict]:
    c = paper.classification
    sections: list[dict] = []

    # 1. Identity
    body_parts: list[str] = []
    body_parts.append(f"Title: {paper.title}")
    if paper.doi:
        body_parts.append(f"DOI: {paper.doi}")
    if paper.year:
        body_parts.append(f"Year: {paper.year}")
    if paper.venue:
        body_parts.append(f"Source venue: {paper.venue}")
    authors = ", ".join(pa.author.canonical_name for pa in paper.authors[:8] if pa.author)
    if authors:
        body_parts.append(f"Authors: {authors}")

    identity_chips = []
    if paper.year:
        identity_chips.append(_chip(str(paper.year), "year"))
    if paper.venue:
        identity_chips.append(_chip(paper.venue, "institution"))
    if paper.doi:
        identity_chips.append(_chip(f"DOI: {paper.doi}", "paper"))

    sections.append({
        "key": "identity",
        "heading": "Identity",
        "body": "\n".join(body_parts),
        "chips": identity_chips,
    })

    # 2. Abstract summary
    sections.append({
        "key": "abstract_summary",
        "heading": "Abstract Summary",
        "body": paper.abstract[:900] + ("..." if paper.abstract and len(paper.abstract) > 900 else "")
        if paper.abstract else "No abstract available.",
        "chips": [],
    })

    # 3. Retrieval provenance
    provenance = [
        f"Source: {paper.provenance or paper.source or 'unknown'}",
        f"Retrieval tier: {paper.retrieval_tier or 'not recorded'}",
    ]
    if paper.merge_tier_membership:
        provenance.append(f"Tier membership: {paper.merge_tier_membership}")
    if paper.query_string:
        provenance.append(f"Query matched: {paper.query_string[:300]}")
    if paper.eid:
        provenance.append(f"Scopus EID: {paper.eid}")
    sections.append({
        "key": "retrieval_provenance",
        "heading": "Retrieval Provenance",
        "body": "\n".join(provenance),
        "chips": [_chip(paper.retrieval_tier, "paper")] if paper.retrieval_tier else [],
    })

    # 4. SDL evidence
    ai = paper.ai_decision_score or 0.0
    auto = paper.automation_score or 0.0
    loop = paper.closed_loop_score or 0.0
    arch = c.architecture_signal if c else max(ai, auto, loop)
    sdl_lines = [
        f"AI decision-making: {'yes' if ai > 0 else 'no'}",
        f"Automation/high-throughput: {'yes' if auto > 0 else 'no'}",
        f"Closed-loop optimization: {'yes' if loop > 0 else 'no'}",
        f"Architecture score: {arch:.2f}",
        f"Semantic SDL label: {c.sdl_relevance_label if c and c.sdl_relevance_label else 'not recorded'}",
    ]
    if paper.sdl_tags:
        sdl_lines.append("SDL tags: " + ", ".join(paper.sdl_tags))
    sections.append({
        "key": "sdl_evidence",
        "heading": "SDL Evidence",
        "body": "\n".join(sdl_lines),
        "chips": [_chip(t, "topic") for t in (paper.sdl_tags or [])[:5]],
    })

    # 5. AC evidence
    if c:
        conn_lines: list[str] = []
        ac_chips: list[dict] = []

        people = c.matched_people or []
        ac_people = [p for p in people if p.get("person_id")]
        if ac_people:
            names = ", ".join(p["name"] for p in ac_people[:3])
            conn_lines.append(f"AC members: {names}.")
            for p in ac_people[:4]:
                ac_chips.append(_chip(f"{p['name']} ({p['match_type']})", "author"))

        insts = c.matched_institutions or []
        partners = [i for i in insts if i.get("is_partner")]
        if partners:
            inst_names = ", ".join(i["canonical_name"] for i in partners[:3])
            conn_lines.append(f"Partner institutions: {inst_names}.")
            for i in partners[:3]:
                ac_chips.append(_chip(i["canonical_name"], "institution"))

        conn_lines.append(f"AC publication match: {'yes' if paper.ac_known_publication else 'no'}")
        conn_lines.append(f"AC author match: {'yes' if (paper.ac_members_matched or c.matched_people) else 'no'}")
        has_funding = (c.funding_signal or 0.0) > 0 or (c.acknowledgement_signal or 0.0) > 0
        conn_lines.append(f"AC funding/acknowledgement: {'yes' if (paper.ac_acknowledged or paper.ac_programs or has_funding) else 'no'}")
        conn_lines.append(f"AC attribution label: {c.ac_attribution_label or 'not recorded'}")
        if paper.ac_programs:
            conn_lines.append(f"AC program: {paper.ac_programs}")

        if not conn_lines:
            conn_lines.append("No direct AC connection signals detected.")

        sections.append({
            "key": "ac_evidence",
            "heading": "AC Evidence",
            "body": "\n".join(conn_lines),
            "chips": ac_chips,
        })

    # 6. Topics
    if c and c.matched_topics:
        core   = [t for t in c.matched_topics if t.get("is_core") and t.get("score", 0) > 0]
        adj    = [t for t in c.matched_topics if not t.get("is_core") and t.get("score", 0) > 0]
        t_body: list[str] = []
        t_chips: list[dict] = []
        if core:
            names = ", ".join(t["name"] for t in core[:4])
            t_body.append(f"Core topics: {names}.")
            for t in core[:4]:
                t_chips.append(_chip(t["name"], "topic"))
                if t.get("hits"):
                    t_body.append(f"  · {t['name']} keywords: {', '.join(t['hits'][:4])}.")
        if adj:
            names = ", ".join(t["name"] for t in adj[:3])
            t_body.append(f"Adjacent topics: {names}.")
        if not t_body:
            t_body.append("No topic matches recorded.")
        sections.append({
            "key": "topics",
            "heading": "Topics",
            "body": "\n".join(t_body),
            "chips": t_chips,
        })

    # 7. Classification
    if c:
        conf_str = f"{c.confidence:.0%}" if c.confidence else "n/a"
        review_status = "human-confirmed" if c.human_confirmed else ("needs review" if c.needs_review else "machine-classified")
        sections.append({
            "key": "classification",
            "heading": "Classification",
            "body": "\n".join([
                f"Display label: {c.label or 'UNCLASSIFIED'}",
                f"SDL relevance label: {c.sdl_relevance_label or 'not recorded'}",
                f"AC attribution label: {c.ac_attribution_label or 'not recorded'}",
                f"Confidence: {conf_str}",
                f"Review status: {review_status}",
                f"Agreement status: {c.model_agreement_status or 'not recorded'}",
            ]),
            "chips": [_chip(c.label or "UNCLASSIFIED", "label")],
        })

    # 8. Evidence trace
    if c:
        ev_lines: list[str] = []
        ev_chips: list[dict] = []
        reasons = c.reasons or []
        for r in reasons[:6]:
            ev_lines.append(f"· {r}")
        graph_sig = c.graph_signals or {}
        if graph_sig.get("bridge_score") is not None:
            ev_lines.append(f"· Bridge score: {graph_sig.get('bridge_score')}.")
        paths = graph_sig.get("second_degree_paths", [])
        if paths:
            via = paths[0].get("via_author_name", "?")
            ac  = paths[0].get("ac_author_name", "?")
            ev_lines.append(f"· Second-degree collaboration: {via} ↔ {ac}.")
        cites = graph_sig.get("citation_signals", [])
        if cites:
            cited_title = cites[0].get("cited_ac_core_title", "AC core paper")
            ev_lines.append(f'· Cites AC core: "{cited_title}".')
        if not ev_lines:
            ev_lines.append("No evidence signals beyond metadata.")
        sections.append({
            "key": "evidence",
            "heading": "Evidence",
            "body": "\n".join(ev_lines),
            "chips": ev_chips,
        })

    # 9. Links
    link_lines = []
    if paper.authors:
        link_lines.append("Authors: " + ", ".join(pa.author.canonical_name for pa in paper.authors[:8] if pa.author))
    if paper.sdl_tags:
        link_lines.append("SDLs/topics: " + ", ".join(paper.sdl_tags))
    if c and c.matched_topics:
        link_lines.append("Matched topics: " + ", ".join(t.get("name", "") for t in c.matched_topics[:6] if t.get("name")))
    sections.append({
        "key": "links",
        "heading": "Links",
        "body": "\n".join(link_lines) if link_lines else "No linked entities recorded.",
        "chips": [],
    })

    # 10. Review notes
    review = getattr(paper, "review", None)
    if review and (review.notes or review.human_label):
        r_lines = []
        if review.human_label:
            r_lines.append(f"Human decision: {review.human_label}")
            if review.reviewer:
                r_lines.append(f"Reviewer: {review.reviewer}")
        if review.notes:
            r_lines.append(f"\n{review.notes}")
        sections.append({
            "key": "review_notes",
            "heading": "Review Notes",
            "body": "\n".join(r_lines),
            "chips": [],
        })

    # 6. Open questions
    open_q: list[str] = []
    if c:
        if not (c.matched_people or []):
            open_q.append("No AC author matched — is this a false positive from topic/funding signals only?")
        fulltext_ev = getattr(c, "fulltext_evidence", None) or []
        if not fulltext_ev and not paper.full_text_available:
            open_q.append("Full text not indexed — funding acknowledgements and SDL methodology signals unavailable.")
        if c.label in ("UNCERTAIN", "ADJACENT"):
            open_q.append("Label is uncertain — human review recommended.")
    if open_q:
        sections.append({
            "key": "open_questions",
            "heading": "Open Questions",
            "body": "\n".join(f"· {q}" for q in open_q),
            "chips": [],
        })

    return sections


# ── Public API ────────────────────────────────────────────────────────────────

def get_or_compile_wiki(session: Session, paper_id: str) -> WikiPage:
    """Return existing wiki page, or compile a new one if none exists."""
    existing = session.execute(
        select(WikiPage).where(
            WikiPage.entity_type == "paper",
            WikiPage.entity_id == paper_id,
        )
    ).scalar_one_or_none()

    if existing is not None:
        return existing

    return compile_wiki(session, paper_id)


def compile_wiki(session: Session, paper_id: str) -> WikiPage:
    """(Re)compile and persist a wiki page for a paper."""
    paper = session.get(Paper, paper_id)
    if paper is None:
        raise ValueError(f"Paper {paper_id!r} not found")

    sections = _build_paper_sections(paper)
    title = paper.title or f"Paper {paper_id}"

    existing = session.execute(
        select(WikiPage).where(
            WikiPage.entity_type == "paper",
            WikiPage.entity_id == paper_id,
        )
    ).scalar_one_or_none()

    if existing is not None:
        existing.title       = title
        existing.sections    = sections
        existing.generated_at = datetime.now(UTC)
        existing.is_stale    = False
        existing.model_version = "template-v0.1"
        session.flush()
        return existing

    page = WikiPage(
        id=f"wiki_{uuid.uuid4().hex[:12]}",
        entity_type="paper",
        entity_id=paper_id,
        title=title,
        sections=sections,
        generated_at=datetime.now(UTC),
        model_version="template-v0.1",
        prompt_version="v0.1",
        is_stale=False,
    )
    session.add(page)
    session.flush()
    return page


def mark_stale(session: Session, paper_id: str) -> None:
    """Called when a paper's classification or review changes."""
    page = session.execute(
        select(WikiPage).where(
            WikiPage.entity_type == "paper",
            WikiPage.entity_id == paper_id,
        )
    ).scalar_one_or_none()
    if page is not None:
        page.is_stale = True
        session.flush()
