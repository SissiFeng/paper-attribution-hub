"""LLM-as-judge for the UNCERTAIN bucket (v0.7).

The rules engine + cross-encoder push most papers to a definitive label. What's
left are honest-to-god borderline cases: maybe an AC-adjacent author whose
ORCID is missing, maybe a paper using AC-vocabulary in passing without doing
SDL work, maybe a citation to an AC paper buried in a Section 4 paragraph.

For those, we ask an LLM. The LLM's job is *not* to invent. It must:

  1. Reference the abstract / matched topic snippets given to it.
  2. Return one of {CORE_RELEVANT, RELATED_RELEVANT, ADJACENT, EXCLUDE}.
  3. List **disqualifying_evidence** — verbatim phrases that argue *against*
     relevance. These are persisted as negative-evidence rows so they show up
     in the next classification pass.

By default `get_judge()` returns a `StubJudge` (deterministic, no network)
so tests and `pip install -r requirements.txt` users don't need an API key.
Set PAS_LLM_JUDGE_BACKEND=anthropic + ANTHROPIC_API_KEY=… to enable the real
model.
"""
from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass


VALID_LABELS = {
    "CORE_RELEVANT",
    "RELATED_RELEVANT",
    "ADJACENT",
    "UNCERTAIN",
    "EXCLUDE",
}


@dataclass
class JudgeVerdict:
    label: str
    confidence: float
    reasons: list[str]
    disqualifying_evidence: list[str]
    raw: str | None = None


class LLMJudge(ABC):
    name: str

    @abstractmethod
    def adjudicate(
        self,
        *,
        title: str,
        abstract: str,
        matched_topics: list[dict],
        evidence: list[dict],
        current_label: str,
        current_confidence: float,
    ) -> JudgeVerdict | None: ...


# ---------------------------------------------------------------------------
# Stub (default — used in tests and when API key missing)
# ---------------------------------------------------------------------------


class StubJudge(LLMJudge):
    """Heuristic stand-in.

    The stub re-applies a few clean rules that the main rules engine
    deliberately doesn't (because they're too aggressive for the bulk path
    but fine on UNCERTAIN-only). Specifically:

      * If the abstract contains negation around every core hit → EXCLUDE.
      * If there's at least one funding-acknowledgement evidence row → RELATED.
      * If the abstract explicitly says "no autonomous platform is
        described" or "is not closed-loop" → EXCLUDE.
      * Otherwise leave label unchanged but trim confidence by 0.1.

    The stub returns a verdict shaped like the real judge so callers don't
    need to special-case.
    """

    name = "stub"

    _DISQUALIFYING_PATTERNS = [
        re.compile(r"no\s+autonomous\s+platform\s+is\s+described", re.I),
        re.compile(r"not\s+(a\s+)?self-driving\s+lab", re.I),
        re.compile(r"is\s+not\s+closed[\s-]loop", re.I),
        re.compile(r"this\s+is\s+not\s+an\s+sdl", re.I),
    ]

    def adjudicate(
        self,
        *,
        title: str,
        abstract: str,
        matched_topics: list[dict],
        evidence: list[dict],
        current_label: str,
        current_confidence: float,
    ) -> JudgeVerdict | None:
        full = f"{title}\n{abstract}"
        disqualifying: list[str] = []
        for pat in self._DISQUALIFYING_PATTERNS:
            m = pat.search(full)
            if m:
                # Capture a small surrounding window so the persisted snippet
                # is human-readable.
                start = max(0, m.start() - 40)
                end = min(len(full), m.end() + 40)
                disqualifying.append(full[start:end].strip())

        if disqualifying:
            return JudgeVerdict(
                label="EXCLUDE",
                confidence=min(current_confidence + 0.1, 0.9),
                reasons=[
                    "Abstract explicitly disclaims SDL methodology.",
                ],
                disqualifying_evidence=disqualifying,
            )

        has_funding = any(
            e.get("type") == "funding_acknowledgement" for e in evidence
        )
        if has_funding:
            return JudgeVerdict(
                label="RELATED_RELEVANT",
                confidence=max(current_confidence, 0.7),
                reasons=[
                    "Acknowledgements mention AC funding; promoted from "
                    "UNCERTAIN to RELATED.",
                ],
                disqualifying_evidence=[],
            )

        # No strong evidence either way — just downgrade to ADJACENT with
        # reduced confidence; the rules already flagged this as UNCERTAIN.
        return JudgeVerdict(
            label="ADJACENT",
            confidence=max(0.3, current_confidence - 0.1),
            reasons=[
                "Stub judge: no disqualifying or funding evidence found; "
                "demoting UNCERTAIN to ADJACENT for clarity.",
            ],
            disqualifying_evidence=[],
        )


# ---------------------------------------------------------------------------
# Anthropic (real)
# ---------------------------------------------------------------------------


_ANTHROPIC_PROMPT_TEMPLATE = """You are reviewing a research paper to decide whether it should be attributed to the Acceleration Consortium (AC), which is the University of Toronto / UBC initiative on self-driving labs (SDL), autonomous chemistry, closed-loop Bayesian optimization, and AI for science.

Rules for your label:
- CORE_RELEVANT: the paper is *about* SDL/AC mission research, with AC-affiliated authors or AC funding.
- RELATED_RELEVANT: the paper materially advances AC's mission OR explicitly acknowledges AC funding/AC core people, but is not itself an SDL paper.
- ADJACENT: the paper touches AC themes but isn't an SDL paper and has no AC funding/people.
- EXCLUDE: not AC.

You MUST quote verbatim phrases from the abstract or evidence when justifying. You MUST list any phrase in the paper that argues *against* AC relevance (e.g. "no autonomous platform is described", "we focus on autonomous vehicles").

Reply with strict JSON only:
{{
  "label": "CORE_RELEVANT|RELATED_RELEVANT|ADJACENT|EXCLUDE",
  "confidence": 0.0-1.0,
  "reasons": ["...verbatim quote..."],
  "disqualifying_evidence": ["...verbatim phrase that argues against..."]
}}

Paper title: {title}

Abstract:
{abstract}

Matched topics so far: {matched_topics}

Evidence snippets so far: {evidence}

Rules-based current label: {current_label} (confidence {current_confidence:.2f})
"""


class AnthropicJudge(LLMJudge):
    """Calls Anthropic's Messages API. Requires `ANTHROPIC_API_KEY`."""

    name = "anthropic"

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.model = model or os.environ.get(
            "PAS_LLM_JUDGE_MODEL", "claude-haiku-4-5-20251001"
        )
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. "
                "Either set the env var or switch to PAS_LLM_JUDGE_BACKEND=stub."
            )

    def adjudicate(
        self,
        *,
        title: str,
        abstract: str,
        matched_topics: list[dict],
        evidence: list[dict],
        current_label: str,
        current_confidence: float,
    ) -> JudgeVerdict | None:
        prompt = _ANTHROPIC_PROMPT_TEMPLATE.format(
            title=title or "(no title)",
            abstract=abstract or "(no abstract)",
            matched_topics=json.dumps(matched_topics, ensure_ascii=False),
            evidence=json.dumps(
                [
                    {"type": e.get("type"), "snippet": e.get("snippet", "")[:600]}
                    for e in evidence
                ],
                ensure_ascii=False,
            ),
            current_label=current_label,
            current_confidence=current_confidence,
        )

        try:
            import httpx
        except ImportError as e:
            raise RuntimeError("httpx is required for AnthropicJudge") from e

        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": self.model,
                "max_tokens": 700,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30.0,
        )
        if resp.status_code >= 400:
            return None
        body = resp.json()
        text = ""
        for chunk in body.get("content") or []:
            if chunk.get("type") == "text":
                text += chunk.get("text", "")
        return parse_judge_response(text)


def parse_judge_response(text: str) -> JudgeVerdict | None:
    """Extract the JSON object from a model response, robust to surrounding
    prose."""
    if not text:
        return None
    # Try fenced JSON first.
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    raw_json = fence.group(1) if fence else None
    if raw_json is None:
        brace = re.search(r"\{.*\}", text, re.S)
        raw_json = brace.group(0) if brace else None
    if raw_json is None:
        return None
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        return None
    label = str(data.get("label", "")).upper()
    if label not in VALID_LABELS:
        return None
    try:
        conf = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        conf = 0.0
    reasons = [str(r) for r in (data.get("reasons") or [])]
    disq = [str(r) for r in (data.get("disqualifying_evidence") or [])]
    return JudgeVerdict(
        label=label,
        confidence=max(0.0, min(1.0, conf)),
        reasons=reasons,
        disqualifying_evidence=disq,
        raw=text,
    )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_judge() -> LLMJudge:
    backend = os.environ.get("PAS_LLM_JUDGE_BACKEND", "stub").lower()
    if backend == "anthropic":
        try:
            return AnthropicJudge()
        except RuntimeError:
            # Fall through to stub if API key missing.
            return StubJudge()
    return StubJudge()
