"""Publisher adapters for TDM full-text retrieval.

Each adapter knows how to turn a DOI into a download URL + auth + content
negotiation for its publisher. Rules follow the U of T Libraries TDM guide and
each publisher's TDM policy.

Design: adapters are pure functions returning a ``Plan`` (url, headers,
accept, file suffix, license note). The fetch layer owns HTTP + rate limiting
+ cache + resume, so adding a publisher is a ~20-line function.

Compliance notes per publisher (from the U of T guide / publisher policies):
- ACS: no AI use; XML delivery; keep data only for project duration.
- Elsevier: API key + institutional token; TDM XML via Article Retrieval API;
  data must stay on a secure Canadian server.
- Springer: full TDM API requires contacting them; basic OA/metadata API is
  keyless (polite pool).
- Wiley: LAN-only; use the Wiley API.
- IEEE: notify IEEE; full-text API key required.
- RSC / SPIE: scraping allowed with polite delays; SPIE expects manual-style
  downloads; RSC wants TDMCrawler UA + 10-20s delay + notification.
- MDPI / PLOS: open access; bulk downloading allowed.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from urllib.parse import quote, urljoin

# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------

@dataclass
class Plan:
    url: str
    headers: dict[str, str] | None = None
    accept: str = "application/pdf"
    suffix: str = ".pdf"
    note: str = ""            # human-readable source / license note
    min_delay: float = 1.0    # seconds to wait before this request
    # When set, the fetch layer will GET this URL, look for a real PDF link
    # in the HTML (or follow a redirect), and download that instead.
    resolve_pdf: bool = False


def _doi_quote(doi: str) -> str:
    return quote(doi, safe="/")


def _env(name: str) -> str | None:
    val = os.environ.get(name, "").strip()
    return val or None


# ---------------------------------------------------------------------------
# DOI → publisher
# ---------------------------------------------------------------------------

_PREFIX_MAP: dict[str, str] = {
    "1002": "wiley",
    "11142": "spie", "11111": "spie", "1117": "spie",
    "1021": "acs", "1029": "acs", "1028": "acs",
    "1039": "rsc",
    "3390": "mdpi",
    "1007": "springer", "1003": "springer", "1126": "springer",
    "1186": "springer", "1200": "springer", "1044": "springer",
    "1080": "springer", "1006": "springer", "1145": "springer",
    "1180": "springer", "1204": "springer",
    "1177": "sage",
    "1371": "plos",
    "1088": "iop",
    "1103": "aps",
    "1063": "ieee", "1109": "ieee",
    "1005": "elsevier",  # Cell Press (Elsevier)
}

_ELSEVIER_BAND = range(1014, 1821)

# DOI prefixes that have no institutional key route; try OA / open access.
_OA_PREFIXES = {
    "12336", "13182", "15199", "19225", "20964", "20965",
    "24820", "3233", "3791", "4018", "5006", "52202",
    "55092", "5829", "3791", "20965", "12336",
}


def publisher_for_doi(doi: str) -> str | None:
    """Return a canonical publisher key for a DOI, or None if unmapped."""
    m = re.match(r"^10\.(\d{2,6})/", doi.strip().lower())
    if not m:
        return None
    prefix = m.group(1)
    if prefix in _PREFIX_MAP:
        return _PREFIX_MAP[prefix]
    if int(prefix) in _ELSEVIER_BAND:
        return "elsevier"
    return None


# ---------------------------------------------------------------------------
# Adapters
# ---------------------------------------------------------------------------

def _plan_elsevier(doi: str) -> Plan | None:
    key = _env("PAS_ELSEVIER_API_KEY")
    if not key:
        return None
    inst = _env("PAS_ELSEVIER_INSTTOKEN")
    headers = {"X-ELS-APIKey": key}
    if inst:
        headers["X-ELS-Insttoken"] = inst
    return Plan(
        url=f"https://api.elsevier.com/content/article/doi/{_doi_quote(doi)}",
        headers=headers,
        accept="text/xml",
        suffix=".xml",
        note="Elsevier Article Retrieval API (TDM XML); keep on Canadian server; non-commercial",
        min_delay=1.0,
    )


def _plan_acs(doi: str) -> Plan | None:
    key = _env("PAS_ACS_API_KEY")
    if not key:
        return None
    return Plan(
        url=f"https://pubs.acs.org/doi/{_doi_quote(doi)}",
        headers={"X-Oc-Apikey": key, "Accept": "application/xml"},
        accept="application/xml",
        suffix=".xml",
        note="ACS XML delivery (TDM addendum); no AI use; project-duration storage only",
        min_delay=1.0,
    )


def _plan_wiley(doi: str) -> Plan | None:
    key = _env("PAS_WILEY_API_KEY")
    if not key:
        return None
    return Plan(
        url=f"https://api.wiley.com/onlinelibrary/tdm/v1/articles/{_doi_quote(doi)}",
        headers={"Wiley-TDM-Client-Token": key, "Accept": "application/pdf"},
        accept="application/pdf",
        suffix=".pdf",
        note="Wiley TDM API; LAN-only; PDF",
        min_delay=1.0,
    )


def _plan_ieee(doi: str) -> Plan | None:
    key = _env("PAS_IEEE_API_KEY")
    if not key:
        return None
    return Plan(
        url=f"https://ieeexploreapi.ieee.org/api/v1/search/document",
        headers={"apikey": key, "Accept": "application/json"},
        accept="application/json",
        suffix=".json",
        note="IEEE full-text API; requires IEEE notification before TDM",
        min_delay=1.0,
    )


def _plan_springer(doi: str) -> Plan | None:
    key = _env("PAS_SPRINGER_API_KEY")
    if not key:
        return None
    return Plan(
        url="https://api.springernature.com/meta/v2/json",
        headers={"Accept": "application/json"},
        accept="application/json",
        suffix=".json",
        note="Springer Nature API (full TDM needs contacting them); metadata JSON",
        min_delay=1.0,
    )


def _plan_rsc(doi: str) -> Plan:
    return Plan(
        url=f"https://pubs.rsc.org/en/content/articlelanding/{_doi_quote(doi)}",
        headers={"User-Agent": "TDMCrawler (research; contact sissi.feng@utoronto.ca)"},
        accept="text/html",
        suffix=".html",
        note="RSC TDM via scraping; notify ejournals@rsc.org; UA TDMCrawler; 10-20s delay",
        min_delay=10.0,
        resolve_pdf=True,
    )


def _plan_spie(doi: str) -> Plan:
    return Plan(
        url=f"https://www.spiedigitallibrary.org/conference-proceedings-of-spie/{_doi_quote(doi)}",
        headers={"User-Agent": "TDMCrawler (research; contact sissi.feng@utoronto.ca)"},
        accept="text/html",
        suffix=".html",
        note="SPIE TDM; manual-download expectations; polite delays",
        min_delay=5.0,
        resolve_pdf=True,
    )


def _plan_mdpi(doi: str) -> Plan:
    return Plan(
        url=f"https://www.mdpi.com/doi/{_doi_quote(doi)}",
        headers={"User-Agent": "TDMCrawler (research; contact sissi.feng@utoronto.ca)"},
        accept="text/html",
        suffix=".html",
        note="MDPI open access; bulk download allowed",
        min_delay=2.0,
        resolve_pdf=True,
    )


def _plan_plos(doi: str) -> Plan:
    return Plan(
        url=f"https://journals.plos.org/plosone/article?id={_doi_quote(doi)}",
        headers={"User-Agent": "TDMCrawler (research; contact sissi.feng@utoronto.ca)"},
        accept="text/html",
        suffix=".html",
        note="PLOS open access",
        min_delay=1.0,
        resolve_pdf=True,
    )


def _plan_oa_fallback(doi: str) -> Plan:
    """OpenAlex OA lookup (needs no key) — resolves a real PDF URL when OA."""
    return Plan(
        url=f"https://api.openalex.org/works/doi:{_doi_quote(doi)}",
        headers={"Accept": "application/json"},
        accept="application/json",
        suffix=".json",
        note="OpenAlex OA lookup (fallback); will resolve to PDF when available",
        min_delay=1.0,
        resolve_pdf=True,
    )


ADAPTERS = {
    "elsevier": (_plan_elsevier, True),
    "acs": (_plan_acs, True),
    "wiley": (_plan_wiley, True),
    "ieee": (_plan_ieee, True),
    "springer": (_plan_springer, True),
    "rsc": (_plan_rsc, False),
    "spie": (_plan_spie, False),
    "mdpi": (_plan_mdpi, False),
    "plos": (_plan_plos, False),
}


def plan_for(doi: str) -> tuple[Plan | None, str | None]:
    """Return (Plan, publisher_key). Plan is None when the publisher needs a
    missing API key — the fetch layer reports that as 'skipped: needs key'."""
    publisher = publisher_for_doi(doi)
    if publisher is None:
        return _plan_oa_fallback(doi), "openalex"
    adapter, requires_key = ADAPTERS.get(publisher, (None, False))
    if adapter is None:
        return _plan_oa_fallback(doi), "openalex"
    plan = adapter(doi)
    if plan is None:
        if requires_key:
            return None, publisher
        return _plan_oa_fallback(doi), publisher
    return plan, publisher
