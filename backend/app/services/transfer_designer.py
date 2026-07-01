"""Cross-SDL transfer engine.

Matches Transferable Knowledge Units (TKUs) extracted from source-domain papers
against a target SDL profile, then drafts an experiment-design proposal.

Two output modes, mirroring reporting_service's no-invention contract:

  * template — a deterministic markdown skeleton assembled straight from the
    matched TKUs. Every transferred claim carries a `[src:<paper_id>]` tag back
    to the paper it came from. This always runs and is always useful on its own.
  * llm      — an optional rewrite. The skeleton + the TKU JSONs are sent to the
    configured provider (Kimi → Anthropic, resolved like nl_to_sql_service) with
    a strict prompt: rewrite for coherence, invent no numbers or methods, keep
    every [src:] tag. A validation pass rejects any [src:id] not in the input
    set and falls back to the template — the same guarantee reporting_service
    enforces for numbers.

Target profiles live in data/sdl_targets.yaml (a curator file).
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import DATA_DIR, REPO_ROOT
from app.models import Paper, PaperLabLink, TransferKnowledgeUnit

SDL_TARGETS_YAML = DATA_DIR / "sdl_targets.yaml"
TRANSFERS_DIR = REPO_ROOT / "llm-wiki" / "transfers"

_SRC_TAG_RE = re.compile(r"\[src:([^\]]+)\]")


# ── target loading ───────────────────────────────────────────────────────────


def load_targets(path: Path | None = None) -> list[dict]:
    p = Path(path or SDL_TARGETS_YAML)
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return list(raw.get("targets") or [])


def load_target(target_id: str, path: Path | None = None) -> dict | None:
    for target in load_targets(path):
        if target.get("id") == target_id:
            return target
    return None


# ── matching / scoring ───────────────────────────────────────────────────────


def _keywords_of_method(method_core: dict) -> list[str]:
    """Lowercased terms drawn from a TKU's method_core for keyword overlap."""
    terms: list[str] = []
    workflow = method_core.get("workflow")
    if isinstance(workflow, str):
        terms.append(workflow.lower())
    for comp in method_core.get("key_components") or []:
        if isinstance(comp, str):
            terms.append(comp.lower())
    return terms


def _keyword_overlap(target_keywords: list[str], method_terms: list[str]) -> list[str]:
    """Target keywords that appear (as a substring, either direction) in any
    method term. De-duplicated, order preserved by target keyword order."""
    hits: list[str] = []
    for kw in target_keywords:
        kwl = kw.lower()
        if any(kwl in term or term in kwl for term in method_terms if term):
            if kw not in hits:
                hits.append(kw)
    return hits


def _paper_labs(session: Session, paper_id: str) -> list[str]:
    return [
        lab_id
        for lab_id in session.execute(
            select(PaperLabLink.lab_id).where(PaperLabLink.paper_id == paper_id)
        ).scalars()
    ]


def _score_tku(tku: TransferKnowledgeUnit, target: dict) -> tuple[int, dict]:
    sig = tku.problem_signature or {}
    tsig = target.get("typical_signature") or {}
    breakdown: dict[str, object] = {}
    score = 0

    if sig.get("task_type") and sig.get("task_type") == tsig.get("task_type"):
        score += 3
        breakdown["task_type"] = 3
    if sig.get("search_space") and sig.get("search_space") == tsig.get("search_space"):
        score += 2
        breakdown["search_space"] = 2
    if sig.get("objectives") and sig.get("objectives") == tsig.get("objectives"):
        score += 2
        breakdown["objectives"] = 2
    if sig.get("evaluation_cost") and sig.get("evaluation_cost") == tsig.get(
        "evaluation_cost"
    ):
        score += 1
        breakdown["evaluation_cost"] = 1

    overlap = _keyword_overlap(
        target.get("keywords") or [], _keywords_of_method(tku.method_core or {})
    )
    if overlap:
        kw_points = min(len(overlap), 3)
        score += kw_points
        breakdown["keyword_overlap"] = {"points": kw_points, "terms": overlap}

    # Cross-domain is the point: reward a different source domain than the
    # target. Same-domain is allowed but not boosted.
    if tku.source_domain and tku.source_domain != target.get("id"):
        score += 1
        breakdown["cross_domain"] = 1

    return score, breakdown


def match_tkus(
    session: Session,
    target: dict,
    source_domain: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Score every TKU against the target and return the top matches.

    TKUs whose paper is already linked to the target SDL are excluded (we want
    knowledge *transferred in*, not the lab's own work). source_domain filters
    to a single source domain when given.
    """
    stmt = select(TransferKnowledgeUnit)
    if source_domain:
        stmt = stmt.where(TransferKnowledgeUnit.source_domain == source_domain)
    tkus = list(session.execute(stmt).scalars())

    results: list[dict] = []
    target_id = target.get("id")
    for tku in tkus:
        paper = session.get(Paper, tku.paper_id)
        if paper is None:
            continue
        labs = _paper_labs(session, tku.paper_id)
        # Exclude TKUs whose source paper belongs to the target SDL itself.
        if target_id in labs:
            continue
        score, breakdown = _score_tku(tku, target)
        results.append(
            {
                "tku": tku,
                "paper": {
                    "id": paper.id,
                    "title": paper.title,
                    "year": paper.year,
                    "labs": labs,
                },
                "score": score,
                "score_breakdown": breakdown,
            }
        )

    results.sort(key=lambda r: (-r["score"], r["paper"]["id"]))
    return results[:limit]


# ── template markdown ─────────────────────────────────────────────────────────


def _src(paper_id: str) -> str:
    return f"[src:{paper_id}]"


def _most_common_component(matches: list[dict], field: str) -> tuple[str, list[str]]:
    """Most common non-null method_core[field] across matches, with the list of
    paper ids that contributed it (for [src:] citation)."""
    by_value: dict[str, list[str]] = {}
    for m in matches:
        value = (m["tku"].method_core or {}).get(field)
        if isinstance(value, str) and value.strip():
            by_value.setdefault(value.strip(), []).append(m["paper"]["id"])
    if not by_value:
        return "", []
    counts = Counter({v: len(ids) for v, ids in by_value.items()})
    top = counts.most_common(1)[0][0]
    return top, by_value[top]


def _template_markdown(target: dict, matches: list[dict]) -> str:
    name = target.get("name", target.get("id", "target"))
    lines: list[str] = [f"# Experiment design proposal: {name}", ""]

    # Objective
    lines += ["## Objective", ""]
    desc = (target.get("description") or "").strip()
    lines.append(desc or "No target description available.")
    lines.append("")

    if not matches:
        lines += [
            "## Candidate loop design",
            "",
            "No transferable knowledge units matched this target. Extract TKUs "
            "from source-domain papers first, then regenerate.",
            "",
        ]
        return "\n".join(lines)

    # Candidate loop design — most common surrogate / acquisition / loop / workflow.
    lines += ["## Candidate loop design", ""]
    for field, label in (
        ("workflow", "Workflow"),
        ("surrogate_model", "Surrogate model"),
        ("acquisition", "Acquisition"),
        ("loop", "Loop"),
    ):
        value, ids = _most_common_component(matches, field)
        if value:
            cites = " ".join(_src(pid) for pid in ids)
            lines.append(f"- **{label}:** {value} {cites}")
    # Key components, with citations.
    comp_ids: dict[str, list[str]] = {}
    for m in matches:
        for comp in (m["tku"].method_core or {}).get("key_components") or []:
            if isinstance(comp, str) and comp.strip():
                comp_ids.setdefault(comp.strip(), []).append(m["paper"]["id"])
    if comp_ids:
        lines.append("- **Key components:**")
        for comp, ids in sorted(comp_ids.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            cites = " ".join(_src(pid) for pid in ids)
            lines.append(f"  - {comp} {cites}")
    lines.append("")

    # Variables & constraints.
    lines += ["## Variables & constraints", ""]
    for constraint in target.get("typical_constraints") or []:
        lines.append(f"- {constraint}")
    bindings: dict[str, list[str]] = {}
    for m in matches:
        for binding in m["tku"].domain_bindings or []:
            if isinstance(binding, str) and binding.strip():
                bindings.setdefault(binding.strip(), []).append(m["paper"]["id"])
    if bindings:
        lines.append("")
        lines.append(
            "Domain bindings from source methods (needs re-binding to target "
            "domain):"
        )
        for binding, ids in sorted(bindings.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            cites = " ".join(_src(pid) for pid in ids)
            lines.append(f"- {binding} — needs re-binding to target domain {cites}")
    lines.append("")

    # Transferred assumptions to verify.
    lines += ["## Transferred assumptions to verify", ""]
    assumption_ids: dict[str, list[str]] = {}
    for m in matches:
        for assumption in m["tku"].assumptions or []:
            if isinstance(assumption, str) and assumption.strip():
                assumption_ids.setdefault(assumption.strip(), []).append(
                    m["paper"]["id"]
                )
    if assumption_ids:
        for assumption, ids in sorted(
            assumption_ids.items(), key=lambda kv: (-len(kv[1]), kv[0])
        ):
            cites = " ".join(_src(pid) for pid in ids)
            lines.append(f"- {assumption} {cites}")
    else:
        lines.append("- No assumptions recorded in the matched sources.")
    lines.append("")

    # Risks & lessons — negatives first, then positives.
    lines += ["## Risks & lessons from source domains", ""]
    negatives: list[tuple[str, str]] = []
    positives: list[tuple[str, str]] = []
    for m in matches:
        pid = m["paper"]["id"]
        for lesson in m["tku"].lessons or []:
            if not isinstance(lesson, dict):
                continue
            text = lesson.get("text")
            if not isinstance(text, str) or not text.strip():
                continue
            if lesson.get("polarity") == "negative":
                negatives.append((text.strip(), pid))
            else:
                positives.append((text.strip(), pid))
    if negatives:
        lines.append("**Risks (negative results):**")
        for text, pid in negatives:
            lines.append(f"- {text} {_src(pid)}")
        lines.append("")
    if positives:
        lines.append("**What worked (positive lessons):**")
        for text, pid in positives:
            lines.append(f"- {text} {_src(pid)}")
        lines.append("")
    if not negatives and not positives:
        lines.append("- No lessons recorded in the matched sources.")
        lines.append("")

    # Matched sources table.
    lines += [
        "## Matched sources",
        "",
        "| Paper | Source domain | Score |",
        "| --- | --- | --- |",
    ]
    for m in matches:
        title = m["paper"]["title"].replace("|", "\\|")
        lines.append(
            f"| {title} ({m['paper']['id']}) | {m['tku'].source_domain} "
            f"| {m['score']} |"
        )
    lines.append("")

    return "\n".join(lines)


# ── LLM rewrite (optional) ─────────────────────────────────────────────────────


def _resolve_llm_client():
    """Return a callable(messages)->str following nl_to_sql / tku_extractor, or
    None if no provider is configured."""
    from app.config import settings

    provider = settings.llm_provider
    if provider == "auto":
        provider = (
            "kimi"
            if settings.kimi_api_key
            else ("anthropic" if settings.anthropic_api_key else "none")
        )
    if provider == "kimi" and settings.kimi_api_key:
        import openai

        client = openai.OpenAI(
            api_key=settings.kimi_api_key, base_url=settings.kimi_base_url
        )
        model = settings.kimi_model

        def call(messages: list[dict]) -> str:
            resp = client.chat.completions.create(
                model=model, messages=messages, max_tokens=2000, temperature=0.0
            )
            return resp.choices[0].message.content or ""

        return call
    if provider == "anthropic" and settings.anthropic_api_key:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

        def call(messages: list[dict]) -> str:
            system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
            chat = [m for m in messages if m["role"] != "system"]
            resp = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=2000,
                temperature=0.0,
                system=system,
                messages=chat,
            )
            return resp.content[0].text

        return call
    return None


_LLM_SYSTEM = """You rewrite cross-domain experiment-design proposals for self-driving \
lab scientists. STRICT RULES:
1. Use only the methods, assumptions, lessons, and constraints present in the \
SKELETON and the TKU JSONs. Never invent a method, number, or result.
2. Keep every [src:<paper_id>] tag exactly where the skeleton placed it. Do not \
add [src:] tags for paper ids that are not already in the skeleton.
3. Preserve all section headings (the ## lines) and the Matched sources table.
4. Improve flow and readability; one coherent proposal, professional tone.
5. If the skeleton already reads cleanly, return it nearly verbatim."""


def _rewrite_with_llm(
    skeleton: str, matches: list[dict], client
) -> str:
    tku_json = json.dumps(
        [
            {
                "paper_id": m["paper"]["id"],
                "source_domain": m["tku"].source_domain,
                "problem_signature": m["tku"].problem_signature,
                "method_core": m["tku"].method_core,
                "assumptions": m["tku"].assumptions,
                "lessons": m["tku"].lessons,
                "domain_bindings": m["tku"].domain_bindings,
            }
            for m in matches
        ],
        ensure_ascii=False,
        indent=1,
    )
    user = (
        f"TKU SOURCES (JSON):\n{tku_json}\n\n"
        f"SKELETON:\n{skeleton}\n\n"
        "Rewrite the skeleton into a coherent proposal following the rules."
    )
    out = client(
        [{"role": "system", "content": _LLM_SYSTEM}, {"role": "user", "content": user}]
    )
    return (out or "").strip()


def _validate_tags(markdown: str, allowed_ids: set[str]) -> bool:
    """Every [src:id] in the markdown must reference a matched paper."""
    return all(tag in allowed_ids for tag in _SRC_TAG_RE.findall(markdown))


# ── public design entry point ──────────────────────────────────────────────────


def generate_design(
    session: Session,
    target_id: str,
    source_domain: str | None = None,
    llm_client=None,
    top_k: int = 6,
) -> dict:
    target = load_target(target_id)
    if target is None:
        raise ValueError(f"Unknown transfer target '{target_id}'")

    matches = match_tkus(session, target, source_domain=source_domain, limit=top_k)
    skeleton = _template_markdown(target, matches)

    mode = "template"
    markdown = skeleton

    client = llm_client or _resolve_llm_client()
    if client is not None and matches:
        allowed_ids = {m["paper"]["id"] for m in matches}
        try:
            rewritten = _rewrite_with_llm(skeleton, matches, client)
            if rewritten and _validate_tags(rewritten, allowed_ids):
                markdown = rewritten
                mode = "llm"
        except Exception:
            # Never fail a design because the LLM call broke.
            markdown = skeleton
            mode = "template"

    return {
        "target": {
            "id": target["id"],
            "name": target.get("name", target["id"]),
            "description": target.get("description", "").strip(),
        },
        "markdown": markdown,
        "mode": mode,
        "matches": [
            {
                "paper_id": m["paper"]["id"],
                "title": m["paper"]["title"],
                "year": m["paper"]["year"],
                "source_domain": m["tku"].source_domain,
                "score": m["score"],
                "score_breakdown": m["score_breakdown"],
                "key_lesson": _key_lesson(m["tku"]),
            }
            for m in matches
        ],
    }


def _key_lesson(tku: TransferKnowledgeUnit) -> str | None:
    """A representative lesson — prefer the first negative one (risks matter)."""
    lessons = tku.lessons or []
    for lesson in lessons:
        if isinstance(lesson, dict) and lesson.get("polarity") == "negative":
            return lesson.get("text")
    for lesson in lessons:
        if isinstance(lesson, dict) and lesson.get("text"):
            return lesson["text"]
    return None


# ── export to the llm-wiki vault ───────────────────────────────────────────────


def _front_matter(fields: dict) -> str:
    fields = {**fields, "generated": datetime.now(UTC).date().isoformat()}
    return "---\n" + yaml.safe_dump(fields, sort_keys=False, allow_unicode=True) + "---\n\n"


def _append_log(path: Path, query: str, title: str) -> None:
    """Append a log.md entry, reusing export_llm_wiki's helper when importable."""
    try:
        from app.scripts.export_llm_wiki import append_log

        append_log(path, query, title)
        return
    except Exception:
        pass
    header = "# Log\n\nAppend-only operations log. Grep `## [` to list entries.\n"
    if not path.exists():
        path.write_text(header, encoding="utf-8")
    date = datetime.now(UTC).date().isoformat()
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"\n## [{date}] {query} | {title}\n")


def export_transfer_md(
    session: Session,
    target_id: str,
    source_domain: str | None = None,
    llm_client=None,
    top_k: int = 6,
    output_dir: Path | None = None,
) -> Path:
    design = generate_design(
        session,
        target_id,
        source_domain=source_domain,
        llm_client=llm_client,
        top_k=top_k,
    )
    transfers_dir = Path(output_dir or TRANSFERS_DIR)
    transfers_dir.mkdir(parents=True, exist_ok=True)

    date = datetime.now(UTC).date().isoformat()
    out_path = transfers_dir / f"{target_id}--{date}.md"
    fm = _front_matter(
        {
            "type": "transfer-design",
            "target": target_id,
            "mode": design["mode"],
            "sources": [m["paper_id"] for m in design["matches"]],
        }
    )
    out_path.write_text(fm + design["markdown"] + "\n", encoding="utf-8")

    _append_log(
        transfers_dir.parent / "log.md",
        "query",
        f"Transfer design: {design['target']['name']}",
    )
    return out_path


# ── TKU wiki cards ─────────────────────────────────────────────────────────────


def _slugify(value: str) -> str:
    try:
        from app.scripts.export_kb_md import slugify

        return slugify(value)
    except Exception:
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
        return re.sub(r"-{2,}", "-", slug)[:80] or "unnamed"


def export_tku_cards(session: Session, output_dir: Path | None = None) -> int:
    """Write one wiki card per TKU under llm-wiki/wiki/tku/, plus a local
    _index.md for the cards (the main index.md is left untouched to avoid
    fragile string surgery). Returns the number of cards written."""
    base = Path(output_dir or (REPO_ROOT / "llm-wiki"))
    tku_dir = base / "wiki" / "tku"
    tku_dir.mkdir(parents=True, exist_ok=True)

    tkus = list(session.execute(select(TransferKnowledgeUnit)).scalars())
    index_lines = ["# TKU cards", "", "Transferable Knowledge Units, one per paper.", ""]

    written = 0
    for tku in sorted(tkus, key=lambda t: t.paper_id):
        paper = session.get(Paper, tku.paper_id)
        if paper is None:
            continue
        labs = _paper_labs(session, tku.paper_id)
        slug = _slugify(paper.title or tku.paper_id)
        sig = tku.problem_signature or {}
        core = tku.method_core or {}

        fm = _front_matter(
            {
                "type": "tku",
                "paper_id": tku.paper_id,
                "source_domain": tku.source_domain,
                "task_type": sig.get("task_type"),
            }
        )
        lines = [
            f"# {paper.title}",
            "",
            f"- Source domain: {tku.source_domain}",
            f"- Paper: {tku.paper_id} ({paper.year or 'n.d.'})",
            "",
            "## Problem signature",
            "",
        ]
        for key in (
            "task_type",
            "evaluation_cost",
            "search_space",
            "objectives",
            "budget_evaluations",
            "batch_size",
            "noise",
        ):
            lines.append(f"- {key}: {sig.get(key)}")
        lines += ["", "## Method core", ""]
        for key in ("workflow", "surrogate_model", "acquisition", "loop"):
            if core.get(key):
                lines.append(f"- {key}: {core.get(key)}")
        for comp in core.get("key_components") or []:
            lines.append(f"  - component: {comp}")

        if tku.assumptions:
            lines += ["", "## Assumptions", ""]
            lines += [f"- {a}" for a in tku.assumptions]
        if tku.lessons:
            lines += ["", "## Lessons", ""]
            for lesson in tku.lessons:
                if isinstance(lesson, dict) and lesson.get("text"):
                    lines.append(f"- ({lesson.get('polarity', 'neutral')}) {lesson['text']}")
        if tku.domain_bindings:
            lines += ["", "## Domain bindings", ""]
            lines += [f"- {b}" for b in tku.domain_bindings]
        if labs:
            lines += ["", "## Source labs", ""]
            for lab_id in labs:
                lines.append(f"- [[wiki/labs/{_slugify(lab_id)}|{lab_id}]]")
        lines.append("")

        (tku_dir / f"{slug}.md").write_text(fm + "\n".join(lines), encoding="utf-8")
        index_lines.append(
            f"- [[wiki/tku/{slug}|{paper.title}]] — {tku.source_domain}"
        )
        written += 1

    index_lines.append("")
    (tku_dir / "_index.md").write_text("\n".join(index_lines), encoding="utf-8")
    return written
