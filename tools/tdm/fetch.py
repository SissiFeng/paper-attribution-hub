"""Publisher-agnostic fetch layer for TDM retrieval.

Responsibilities:
- group papers by publisher (stable order)
- apply per-adapter min delay (rate limiting)
- cache responses in a local cache dir (so re-runs are free)
- resolve OA fallbacks via OpenAlex (PDF URL) when a publisher plan is
  unavailable or the direct route fails
- write manifest.csv / skipped.csv / errors.csv

Callers: `python -m tdm_fetch` (see tdm_fetch.py) or the API router.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin

import httpx

from adapters import Plan, plan_for, publisher_for_doi

# Sandbox-safe default: cache inside the output dir so no HOME writes needed.
CACHE_SUBDIR = ".pas_tdm_cache"

_UA = "Mozilla/5.0 (compatible; pas-tdm/1.0; +mailto:sissi.feng@utoronto.ca)"


class Fetcher:
    def __init__(self, out_dir: Path, *, cache_dir: Path | None = None) -> None:
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir = Path(cache_dir) if cache_dir else self.out_dir / CACHE_SUBDIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.results: list[dict] = []
        self.client = httpx.Client(
            headers={"User-Agent": _UA},
            timeout=60.0,
            follow_redirects=True,
        )

    def close(self) -> None:
        self.client.close()

    # ---------------- cache ----------------
    def _cache_key(self, url: str, accept: str) -> str:
        return hashlib.sha1(f"{url}|{accept}".encode()).hexdigest()

    def _cache_get(self, key: str) -> tuple[bytes, str] | None:
        p = self.cache_dir / f"{key}.bin"
        if p.exists():
            return p.read_bytes(), "cache"
        return None

    def _cache_put(self, key: str, content: bytes) -> None:
        (self.cache_dir / f"{key}.bin").write_bytes(content)

    # ---------------- helpers ----------------
    @staticmethod
    def _safe_name(doi: str) -> str:
        return doi.replace("/", "_").replace(":", "_")

    def _write(self, fname: str, content: bytes) -> Path:
        p = self.out_dir / fname
        p.write_bytes(content)
        return p

    @staticmethod
    def _merged_headers(plan: Plan) -> dict[str, str]:
        headers = dict(plan.headers or {})
        headers.setdefault("Accept", plan.accept)
        headers.setdefault("User-Agent", _UA)
        return headers

    # ---------------- OA resolution ----------------
    def _resolve_oa_pdf(self, doi: str, api_payload: dict) -> str | None:
        """Given an OpenAlex work payload, return a direct PDF URL if OA."""
        oa = api_payload.get("open_access") or {}
        url = oa.get("oa_url")
        if url and (url.endswith(".pdf") or "pdf" in url.lower()):
            return url
        # fall back to locations
        for loc in api_payload.get("locations") or []:
            if loc.get("is_oa"):
                pdf = loc.get("pdf_url")
                if pdf:
                    return pdf
        return None

    def _resolve_html_pdf(self, html: bytes, base_url: str) -> str | None:
        """Parse an HTML landing page for a PDF link (RSC/MDPI/SPIE/PLOS)."""
        text = html.decode("utf-8", errors="ignore")
        candidates = []
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(text, "lxml")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if self._looks_like_pdf(href):
                    candidates.append(urljoin(base_url, href))
        except ImportError:
            for m in re.finditer(r'<a[^>]+href=["\']([^"\']+)["\']', text, re.I):
                href = m.group(1)
                if self._looks_like_pdf(href):
                    candidates.append(urljoin(base_url, href))
        for url in candidates:
            if url.startswith("http"):
                return url
        return None

    @staticmethod
    def _looks_like_pdf(href: str) -> bool:
        href_l = href.lower()
        return (
            href_l.endswith(".pdf")
            or "pdf" in href_l
            and ("download" in href_l or "article" in href_l or "content" in href_l)
        )

    # ---------------- fetch ----------------
    def fetch_one(
        self,
        doi: str,
        *,
        dry_run: bool = False,
        force: bool = False,
    ) -> dict:
        plan, publisher = plan_for(doi)
        if plan is None:
            return {
                "doi": doi,
                "publisher": publisher,
                "status": "skipped",
                "reason": "missing API key",
                "source": None,
                "file": None,
            }

        if dry_run:
            return {
                "doi": doi,
                "publisher": publisher,
                "status": "planned",
                "reason": plan.note,
                "source": plan.url,
                "file": None,
            }

        if plan.min_delay:
            time.sleep(plan.min_delay)

        key = self._cache_key(plan.url, plan.accept)
        cached = None if force else self._cache_get(key)
        if cached is not None:
            content, source = cached
            fname = self._safe_name(doi) + plan.suffix
            self._write(fname, content)
            return {
                "doi": doi,
                "publisher": publisher,
                "status": "downloaded",
                "reason": plan.note,
                "source": "cache",
                "file": fname,
            }

        try:
            resp = self.client.get(plan.url, headers=self._merged_headers(plan))
            resp.raise_for_status()
            content = resp.content
            final_url = str(resp.url)
            # PDF resolver: if the plan says the landing page needs PDF extraction
            if plan.resolve_pdf:
                pdf_url = None
                if publisher == "openalex":
                    try:
                        payload = resp.json()
                    except Exception:
                        payload = {}
                    pdf_url = self._resolve_oa_pdf(doi, payload)
                else:
                    pdf_url = self._resolve_html_pdf(content, final_url)
                if pdf_url:
                    # download the actual PDF
                    time.sleep(plan.min_delay)
                    r2 = self.client.get(pdf_url, headers={"Accept": "application/pdf", "User-Agent": _UA})
                    r2.raise_for_status()
                    content = r2.content
                    final_url = pdf_url
        except httpx.HTTPStatusError as e:
            return {
                "doi": doi,
                "publisher": publisher,
                "status": "error",
                "reason": f"HTTP {e.response.status_code}",
                "source": plan.url,
                "file": None,
            }
        except httpx.HTTPError as e:
            return {
                "doi": doi,
                "publisher": publisher,
                "status": "error",
                "reason": str(e),
                "source": plan.url,
                "file": None,
            }

        self._cache_put(key, content)
        fname = self._safe_name(doi) + plan.suffix
        self._write(fname, content)
        return {
            "doi": doi,
            "publisher": publisher,
            "status": "downloaded",
            "reason": plan.note,
            "source": final_url if plan.resolve_pdf else plan.url,
            "file": fname,
        }

    def fetch_many(
        self,
        dois: list[str],
        *,
        dry_run: bool = False,
        force: bool = False,
        keyed_only: bool = False,
    ) -> list[dict]:
        """Fetch a list of DOIs grouped by publisher. `keyed_only` restricts
        to publishers whose adapters require an API key (useful for the
        keyless-first batch)."""
        from collections import OrderedDict

        order: dict[str, list[str]] = OrderedDict()
        for doi in dois:
            p = publisher_for_doi(doi) or "openalex"
            if keyed_only and p not in {"elsevier", "acs", "wiley", "ieee", "springer"}:
                continue
            order.setdefault(p, []).append(doi)

        results = []
        for publisher, group in order.items():
            for doi in group:
                results.append(self.fetch_one(doi, dry_run=dry_run, force=force))
        self.results = results
        return results
