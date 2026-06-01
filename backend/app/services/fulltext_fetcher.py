"""Open-access full-text fetcher.

Resolution order per paper
--------------------------
1. arXiv DOI  (10.48550/arxiv.*)  → direct https://arxiv.org/pdf/{id}.pdf
2. OpenAlex   open_access.oa_url  → best-effort OA URL (may be PDF or landing page)
3. Unpaywall  (future hook, not yet implemented)

The fetcher is intentionally stateless — callers own rate-limiting and
session handling.  See fetch_and_ingest_fulltexts.py for the batch script.
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

_ARXIV_DOI_RE = re.compile(r"^10\.48550/arxiv\.(.+)$", re.IGNORECASE)
_PDF_CONTENT_TYPES = {
    "application/pdf",
    "application/octet-stream",
    "binary/octet-stream",
}

# Mimic a browser UA to avoid 403s on some publisher sites
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; paper-attribution-bot/1.0; "
        "+mailto:sissi.feng@utoronto.ca)"
    ),
    "Accept": "application/pdf,*/*",
}


# ---------------------------------------------------------------------------
# URL resolution
# ---------------------------------------------------------------------------

def arxiv_pdf_url(doi: str) -> str | None:
    """Return direct arXiv PDF URL for an arXiv DOI, or None."""
    m = _ARXIV_DOI_RE.match(doi.strip().lower())
    if not m:
        return None
    arxiv_id = m.group(1)
    return f"https://arxiv.org/pdf/{arxiv_id}.pdf"


def openalex_oa_url(session: "Session", doi: str) -> str | None:
    """Query OpenAlex for the best open-access URL for a DOI.

    Returns the URL string or None if unavailable / not OA.
    Caches the OpenAlex response via the existing cache layer.
    """
    from app.services.external.openalex_client import OpenAlexClient

    try:
        with OpenAlexClient() as client:
            work = client.work_by_doi(session, doi)
    except Exception:
        return None

    if not work:
        return None

    oa = work.get("open_access") or {}
    url = oa.get("oa_url")
    if not url:
        # Fall back to primary_location best_oa_location
        for loc in (work.get("locations") or []):
            if loc.get("is_oa") and loc.get("pdf_url"):
                url = loc["pdf_url"]
                break
    return url or None


def resolve_oa_url(session: "Session", doi: str) -> str | None:
    """Return the best available OA URL for a DOI.

    Tries arXiv first (zero latency), then OpenAlex.
    """
    url = arxiv_pdf_url(doi)
    if url:
        return url
    return openalex_oa_url(session, doi)


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def _is_pdf(response: httpx.Response) -> bool:
    ct = response.headers.get("content-type", "").lower().split(";")[0].strip()
    # Also check if the body starts with the PDF magic bytes
    if ct in _PDF_CONTENT_TYPES:
        return True
    if response.content[:4] == b"%PDF":
        return True
    return False


def download_pdf(
    url: str,
    dest: Path,
    *,
    timeout: float = 60.0,
    max_size_mb: float = 50.0,
    follow_redirects: int = 5,
) -> bool:
    """Download a URL to `dest`.  Returns True on success.

    Checks:
    - Content is PDF (magic bytes or Content-Type)
    - File size ≤ max_size_mb
    - Follows up to `follow_redirects` redirects

    Does NOT raise — returns False on any failure so batch scripts can
    continue.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with httpx.Client(
            headers=_HEADERS,
            timeout=timeout,
            follow_redirects=True,
            max_redirects=follow_redirects,
        ) as client:
            with client.stream("GET", url) as r:
                if r.status_code != 200:
                    return False
                # Size guard: check Content-Length header first
                cl = r.headers.get("content-length")
                if cl and int(cl) > max_size_mb * 1024 * 1024:
                    return False

                chunks = []
                total = 0
                limit = int(max_size_mb * 1024 * 1024)
                for chunk in r.iter_bytes(chunk_size=65536):
                    total += len(chunk)
                    if total > limit:
                        return False
                    chunks.append(chunk)

                content = b"".join(chunks)

        # Validate it's actually a PDF
        if content[:4] != b"%PDF":
            return False

        dest.write_bytes(content)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# High-level: fetch + ingest one paper
# ---------------------------------------------------------------------------

def _write_fulltext_score(session: "Session", paper_id: str, score: float) -> None:
    """Write fulltext_evidence_score back to PaperClassification."""
    from sqlalchemy import select
    from app.models import PaperClassification

    cls = session.execute(
        select(PaperClassification).where(PaperClassification.paper_id == paper_id)
    ).scalar_one_or_none()
    if cls is not None:
        cls.fulltext_evidence_score = score
        session.flush()


def fetch_and_ingest(
    session: "Session",
    paper_id: str,
    doi: str,
    dest_dir: Path,
    *,
    prefer_grobid: bool | None = None,
    rate_limit_s: float = 1.0,
) -> tuple[bool, str]:
    """Resolve OA URL, download PDF, run fulltext pipeline.

    Writes fulltext_evidence_score back to PaperClassification.
    Returns (success, reason_string).
    """
    from app.services.fulltext_service import ingest_fulltext_file

    dest = dest_dir / f"{paper_id}.pdf"
    if dest.exists():
        try:
            result = ingest_fulltext_file(session, paper_id, dest, prefer_grobid=prefer_grobid)
            _write_fulltext_score(session, paper_id, result.fulltext_score)
            return True, "re-ingested from cache"
        except Exception as e:
            return False, f"re-ingest error: {e}"

    url = resolve_oa_url(session, doi)
    if not url:
        return False, "no OA URL found"

    time.sleep(rate_limit_s)

    ok = download_pdf(url, dest)
    if not ok:
        return False, f"download failed: {url}"

    try:
        result = ingest_fulltext_file(session, paper_id, dest, prefer_grobid=prefer_grobid)
        _write_fulltext_score(session, paper_id, result.fulltext_score)
        return True, f"fetched from {url}"
    except Exception as e:
        return False, f"parse error: {e}"
