"""Transferable Knowledge Unit (TKU) extraction.

Compresses each paper into a structured, domain-separable unit:
problem signature + domain-agnostic method core + assumptions + lessons +
domain bindings. The point is transfer: a method or lesson extracted from a
battery SDL paper should be re-usable when designing experiments for an
unrelated SDL, with the domain-specific nouns stripped out into
`domain_bindings`.

LLM provider resolution mirrors nl_to_sql_service: Kimi first (OpenAI-compatible),
Anthropic fallback. The LLM is asked for strict JSON; we strip markdown fences,
parse, retry once on failure, and validate enums before persisting.

Idempotent: papers that already have a TKU are skipped unless force=True.
Commit-per-paper makes a run crash-safe and resumable.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Paper, PaperEntity, TransferKnowledgeUnit

# ── Enum vocabularies (the LLM may only use these; invalid → coerced/null) ──
_TASK_TYPES = {"optimization", "prediction", "generation", "characterization", "automation"}
_EVAL_COST = {"high", "medium", "low"}
_SEARCH_SPACE = {"continuous", "discrete", "mixed"}
_OBJECTIVES = {"single", "multi"}
_POLARITY = {"positive", "negative", "neutral"}

_SYSTEM_PROMPT = """You compress a scientific paper into a Transferable Knowledge Unit (TKU): \
a structured, domain-separable representation so the METHOD and LESSONS can be \
transferred into a different scientific domain later. Return ONLY a single JSON \
object, no prose, no markdown fences.

JSON schema (use exactly these keys; use null when the title/abstract does not \
support a value; never invent):

{
  "source_domain": str,            // ONE lowercase word for the application domain, e.g. "battery", "polymer", "catalysis", "robotics"
  "problem_signature": {
    "task_type": "optimization"|"prediction"|"generation"|"characterization"|"automation",
    "evaluation_cost": "high"|"medium"|"low",
    "search_space": "continuous"|"discrete"|"mixed",
    "objectives": "single"|"multi",
    "budget_evaluations": int|null,
    "batch_size": int|null,
    "noise": str|null
  },
  "method_core": {
    "workflow": str,               // ONE-LINE phrase, domain-agnostic
    "surrogate_model": str|null,
    "acquisition": str|null,
    "loop": str|null,
    "key_components": [str]
  },
  "assumptions": [str],            // conditions the method relies on
  "lessons": [{"text": str, "polarity": "positive"|"negative"|"neutral"}],
  "domain_bindings": [str]         // domain-specific nouns that do NOT transfer
}

Rules:
- Extract ONLY what the title/abstract supports. Use null when unknown.
- Lessons must be FAITHFUL to the paper. Negative results are especially valuable; \
mark them polarity "negative".
- domain_bindings are the specific materials/devices/targets unique to this domain \
(e.g. "lithium electrolyte", "PLGA nanoparticle") that would NOT carry over to \
another domain; the method_core must read without them.
- source_domain is one lowercase word naming the application domain."""


def _resolve_client():
    """Return (client, provider, model) following the nl_to_sql pattern.

    Kimi first, Anthropic fallback; raise a clear RuntimeError if neither key
    is configured. `client` is a lightweight callable wrapper: it takes a
    messages list and returns the raw text content, hiding the SDK differences.
    """
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
                model=model,
                messages=messages,
                max_tokens=1500,
                temperature=0.0,
            )
            return resp.choices[0].message.content or ""

        return call, "kimi", model

    if provider == "anthropic" and settings.anthropic_api_key:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        model = "claude-sonnet-4-6"

        def call(messages: list[dict]) -> str:
            system = "\n\n".join(
                m["content"] for m in messages if m["role"] == "system"
            )
            chat = [m for m in messages if m["role"] != "system"]
            resp = client.messages.create(
                model=model,
                max_tokens=1500,
                temperature=0.0,
                system=system,
                messages=chat,
            )
            return resp.content[0].text

        return call, "anthropic", model

    raise RuntimeError(
        "No LLM provider configured for TKU extraction. Set PAS_KIMI_API_KEY "
        "in backend/.env (Kimi/MoonShot, OpenAI-compatible) or PAS_ANTHROPIC_API_KEY."
    )


def _build_user_message(session: Session, paper: Paper) -> str:
    """Title + abstract + deterministic hints that ground the LLM."""
    entities = list(
        session.execute(
            select(PaperEntity).where(
                PaperEntity.paper_id == paper.id,
                PaperEntity.entity_type == "method",
            )
        ).scalars()
    )
    hint_lines: list[str] = []
    for ent in entities:
        bits = [ent.normalized_name]
        if ent.stage:
            bits.append(f"stage={ent.stage}")
        if ent.usage_snippet:
            bits.append(f'used in: "{ent.usage_snippet.strip()}"')
        hint_lines.append("  - " + "; ".join(bits))

    parts = [
        f"Title: {paper.title}",
        f"Abstract: {paper.abstract or '(none)'}",
    ]
    if hint_lines:
        parts.append("Extracted method entities (hints, not authoritative):")
        parts.extend(hint_lines)
    if paper.sdl_tags:
        parts.append(f"SDL tags: {', '.join(paper.sdl_tags)}")
    if paper.research_tags:
        parts.append(f"Research tags: {', '.join(paper.research_tags)}")
    parts.append("\nReturn the TKU as a single JSON object.")
    return "\n".join(parts)


def _strip_fences(text: str) -> str:
    """Remove ```json ... ``` markdown fences if present."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.endswith("```"):
            t = t[: t.rfind("```")]
        # drop a leading "json" language tag left over from the first line
        t = t.strip()
    return t.strip()


def _coerce_enum(value, allowed: set[str]):
    if isinstance(value, str) and value in allowed:
        return value
    return None


def _validate(data: dict) -> dict:
    """Coerce/drop invalid enum fields and normalise structure."""
    sig = data.get("problem_signature") or {}
    if not isinstance(sig, dict):
        sig = {}
    problem_signature = {
        "task_type": _coerce_enum(sig.get("task_type"), _TASK_TYPES),
        "evaluation_cost": _coerce_enum(sig.get("evaluation_cost"), _EVAL_COST),
        "search_space": _coerce_enum(sig.get("search_space"), _SEARCH_SPACE),
        "objectives": _coerce_enum(sig.get("objectives"), _OBJECTIVES),
        "budget_evaluations": sig.get("budget_evaluations")
        if isinstance(sig.get("budget_evaluations"), int)
        else None,
        "batch_size": sig.get("batch_size")
        if isinstance(sig.get("batch_size"), int)
        else None,
        "noise": sig.get("noise") if isinstance(sig.get("noise"), str) else None,
    }

    core = data.get("method_core") or {}
    if not isinstance(core, dict):
        core = {}
    method_core = {
        "workflow": core.get("workflow") if isinstance(core.get("workflow"), str) else "",
        "surrogate_model": core.get("surrogate_model")
        if isinstance(core.get("surrogate_model"), str)
        else None,
        "acquisition": core.get("acquisition")
        if isinstance(core.get("acquisition"), str)
        else None,
        "loop": core.get("loop") if isinstance(core.get("loop"), str) else None,
        "key_components": [
            str(c) for c in (core.get("key_components") or []) if isinstance(c, str)
        ],
    }

    assumptions = [str(a) for a in (data.get("assumptions") or []) if isinstance(a, str)]

    lessons = []
    for lesson in data.get("lessons") or []:
        if not isinstance(lesson, dict) or not isinstance(lesson.get("text"), str):
            continue
        polarity = _coerce_enum(lesson.get("polarity"), _POLARITY) or "neutral"
        lessons.append({"text": lesson["text"], "polarity": polarity})

    domain_bindings = [
        str(b) for b in (data.get("domain_bindings") or []) if isinstance(b, str)
    ]

    source_domain = data.get("source_domain")
    source_domain = (
        source_domain.strip().lower().split()[0]
        if isinstance(source_domain, str) and source_domain.strip()
        else "unknown"
    )

    return {
        "source_domain": source_domain,
        "problem_signature": problem_signature,
        "method_core": method_core,
        "assumptions": assumptions,
        "lessons": lessons,
        "domain_bindings": domain_bindings,
    }


def extract_tku_for_paper(
    session: Session, paper: Paper, client=None
) -> TransferKnowledgeUnit | None:
    """Extract and persist a TKU for one paper. Returns the row, or None on
    repeated parse failure. `client` is the (call, provider, model) tuple; when
    None it is resolved from settings."""
    if client is None:
        call, _provider, model = _resolve_client()
    else:
        call, _provider, model = client

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_message(session, paper)},
    ]

    data = None
    for attempt in range(2):
        raw = call(messages)
        try:
            data = json.loads(_strip_fences(raw))
            break
        except (json.JSONDecodeError, ValueError):
            if attempt == 0:
                messages.append({"role": "assistant", "content": raw})
                messages.append(
                    {
                        "role": "user",
                        "content": "That was not valid JSON. Return only valid JSON "
                        "matching the schema, with no markdown fences or prose.",
                    }
                )
    if data is None or not isinstance(data, dict):
        return None

    validated = _validate(data)
    tku = TransferKnowledgeUnit(
        id=f"tku-{paper.id}",
        paper_id=paper.id,
        extractor="llm",
        model=model,
        **validated,
    )
    session.merge(tku)
    return tku


def run_tku_extraction(
    session: Session,
    paper_ids: list[str] | None = None,
    provenance: str | None = "ac_gold",
    limit: int | None = None,
    client=None,
    force: bool = False,
) -> dict:
    """Extract TKUs for targeted papers. Targets = papers with an abstract,
    filtered by provenance and/or explicit paper_ids, capped at limit.

    Commits per paper so a crashed run is resumable. Returns counts.
    """
    stmt = select(Paper).where(Paper.abstract.isnot(None), Paper.abstract != "")
    if provenance:
        stmt = stmt.where(Paper.provenance == provenance)
    if paper_ids:
        stmt = stmt.where(Paper.id.in_(paper_ids))
    stmt = stmt.order_by(Paper.id)
    if limit is not None:
        stmt = stmt.limit(limit)
    papers = list(session.execute(stmt).scalars())

    if client is None:
        client = _resolve_client()

    existing_ids = set(
        session.execute(select(TransferKnowledgeUnit.paper_id)).scalars()
    )

    extracted = skipped = failures = 0
    for paper in papers:
        if not force and paper.id in existing_ids:
            skipped += 1
            continue
        tku = extract_tku_for_paper(session, paper, client=client)
        if tku is None:
            failures += 1
            session.rollback()
            continue
        session.commit()
        extracted += 1

    return {
        "targeted": len(papers),
        "extracted": extracted,
        "skipped_existing": skipped,
        "failures": failures,
    }


def load_example_tkus(session: Session, path: str | Path | None = None) -> dict:
    """Load hand-written example TKUs (extractor="example") from YAML.

    These attach real, plausible TKUs to real ac_gold papers so the transfer
    demo works without any API key. Idempotent: existing rows are updated.
    """
    from app.config import settings

    p = Path(path) if path else Path(settings.example_tkus_yaml)
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    entries = raw.get("tkus") or []

    loaded = skipped_missing = 0
    for entry in entries:
        paper_id = entry["paper_id"]
        paper = session.get(Paper, paper_id)
        if paper is None:
            skipped_missing += 1
            continue
        validated = _validate(entry)
        tku = TransferKnowledgeUnit(
            id=f"tku-{paper_id}",
            paper_id=paper_id,
            extractor="example",
            model=None,
            **validated,
        )
        session.merge(tku)
        loaded += 1
    session.commit()
    return {"loaded": loaded, "skipped_missing": skipped_missing}
