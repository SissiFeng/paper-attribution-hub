"""Name + DOI + institution normalization.

Rules:
- Strip diacritics, collapse whitespace, lowercase.
- Drop punctuation but keep hyphens that join name particles (Aspuru-Guzik).
- Handle "Last, First" → "First Last".
- Initials expand to first-letter tokens so "A. Aspuru-Guzik" normalizes to
  "a aspuru-guzik" (matches against canonical "alan aspuru-guzik" via fuzzy
  threshold in the matcher).
"""
from __future__ import annotations

import re
import unicodedata

_PUNCT_KEEP_HYPHEN_RE = re.compile(r"[^\w\s\-]", flags=re.UNICODE)
_MULTI_SPACE_RE = re.compile(r"\s+")
_DOI_PREFIX_RE = re.compile(r"^(https?://)?(dx\.)?doi\.org/", flags=re.IGNORECASE)


def strip_diacritics(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize_name(name: str | None) -> str:
    if not name:
        return ""
    text = strip_diacritics(name)
    if "," in text:
        # "Last, First M." → "First M. Last"
        parts = [p.strip() for p in text.split(",", 1)]
        if len(parts) == 2 and parts[0] and parts[1]:
            text = f"{parts[1]} {parts[0]}"
    text = text.lower()
    text = _PUNCT_KEEP_HYPHEN_RE.sub(" ", text)
    text = _MULTI_SPACE_RE.sub(" ", text).strip()
    return text


def name_initials(name: str) -> str:
    """Return space-separated initials, e.g. 'Alan Aspuru-Guzik' → 'a a'."""
    tokens = normalize_name(name).split()
    return " ".join(tok[0] for tok in tokens if tok)


def normalize_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    cleaned = _DOI_PREFIX_RE.sub("", doi.strip())
    cleaned = cleaned.strip().lower()
    return cleaned or None


def normalize_institution(text: str | None) -> str:
    if not text:
        return ""
    cleaned = strip_diacritics(text)
    cleaned = cleaned.lower()
    cleaned = re.sub(r"[^\w\s\-&]", " ", cleaned)
    cleaned = _MULTI_SPACE_RE.sub(" ", cleaned).strip()
    # Common abbreviation expansions.
    replacements = {
        "univ.": "university",
        "univ ": "university ",
        "u ": "university ",
        "uoft": "university of toronto",
        "ubc": "university of british columbia",
        "mit": "massachusetts institute of technology",
        "ethz": "eth zurich",
    }
    for needle, replacement in replacements.items():
        if cleaned == needle.strip():
            cleaned = replacement
        cleaned = re.sub(rf"\b{re.escape(needle)}\b", replacement, cleaned)
    cleaned = _MULTI_SPACE_RE.sub(" ", cleaned).strip()
    return cleaned
