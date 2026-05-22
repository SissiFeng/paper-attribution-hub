"""GROBID adapter for high-fidelity scholarly PDF parsing.

Why GROBID (per parse.md §1): a two-column PDF run through a generic text
extractor returns "学术沙拉". GROBID is purpose-built — it returns TEI XML
with clean title / authors / affiliations / sections / references /
biblStruct elements. We use it via its HTTP API (default port 8070) and
fall back to PyMuPDF when the service is unreachable.

Local development:
    docker run -t --rm --init -p 8070:8070 lfoppiano/grobid:0.8.0
    export PAS_GROBID_URL=http://localhost:8070

Without that env var the system silently uses PyMuPDF — GROBID is a
quality upgrade, never a blocker for getting started.

Tests cover the TEI parsing path with a real fixture so we don't need
Docker running in CI.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable

from app.services.normalization_service import normalize_doi
from app.services.pdf_parser import (
    ParsedAuthor,
    ParsedDocument,
    ParsedReferenceRecord,
    ParsedSection,
)

TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0"}

# Map GROBID `head[@n]` numbering / `type` attributes onto our canonical
# section-type vocabulary. The keys are lowercase keyword hits.
HEAD_TO_SECTION_TYPE: dict[str, str] = {
    "abstract": "abstract",
    "summary": "abstract",
    "introduction": "introduction",
    "background": "introduction",
    "method": "methods",
    "methods": "methods",
    "materials": "methods",
    "experimental": "methods",
    "result": "results",
    "results": "results",
    "discussion": "discussion",
    "conclusion": "discussion",
    "acknowledg": "acknowledgements",
    "funding": "acknowledgements",
    "reference": "references",
    "bibliograph": "references",
    "supplementary": "supplementary",
    "supporting": "supplementary",
}


class GrobidUnavailable(RuntimeError):
    """Raised when GROBID isn't reachable. parse_any catches this and falls back."""


def is_grobid_available(url: str, timeout: float = 5.0) -> bool:
    """Cheap health probe — `GET /api/isalive` returns "true" when up."""
    if not url:
        return False
    try:
        import httpx

        r = httpx.get(f"{url.rstrip('/')}/api/isalive", timeout=timeout)
        return r.status_code == 200 and r.text.strip().lower() == "true"
    except Exception:
        return False


def parse_pdf_via_grobid(
    path: Path, *, url: str | None = None, timeout: float | None = None
) -> ParsedDocument:
    """Submit the PDF to GROBID and return a ParsedDocument from the TEI."""
    from app.config import settings

    server = (url or settings.grobid_url or "").rstrip("/")
    if not server:
        raise GrobidUnavailable("PAS_GROBID_URL is not set")

    import httpx

    timeout_s = timeout or settings.grobid_timeout_s
    try:
        with open(path, "rb") as fh:
            files = {"input": (Path(path).name, fh, "application/pdf")}
            r = httpx.post(
                f"{server}/api/processFulltextDocument",
                files=files,
                data={"consolidateHeader": "1", "consolidateCitations": "1"},
                timeout=timeout_s,
            )
    except httpx.HTTPError as e:
        raise GrobidUnavailable(f"GROBID call failed: {e}") from e
    if r.status_code != 200:
        raise GrobidUnavailable(
            f"GROBID returned {r.status_code}: {r.text[:200]}"
        )
    return parse_tei_xml(r.text)


# ---------------------------------------------------------------------------
# TEI XML → ParsedDocument
# ---------------------------------------------------------------------------


def parse_tei_xml(xml_text: str) -> ParsedDocument:
    """Convert a TEI XML string (GROBID output) into a ParsedDocument."""
    root = ET.fromstring(xml_text)

    title = _grobid_title(root)
    abstract = _grobid_abstract(root)
    authors = _grobid_authors(root)
    affiliations = sorted(
        {aff for a in authors for aff in a.affiliations if aff}
    )
    body_sections = list(_grobid_body_sections(root))
    sections: list[ParsedSection] = []
    if abstract:
        sections.append(
            ParsedSection(section_type="abstract", title="Abstract", text=abstract)
        )
    sections.extend(body_sections)
    ack = _grobid_back_section(root, ("ack", "funding", "acknowledg"), "acknowledgements")
    if ack:
        sections.append(ack)
    annex = _grobid_back_section(root, ("annex", "supplementary"), "supplementary")
    if annex:
        sections.append(annex)

    references = list(_grobid_references(root))

    return ParsedDocument(
        title=title,
        abstract=abstract,
        authors=authors,
        affiliations=affiliations,
        sections=sections,
        references=references,
        source="grobid",
    )


def _t(text: str | None) -> str:
    return (text or "").strip()


def _itertext(el: ET.Element | None) -> str:
    if el is None:
        return ""
    parts: list[str] = []
    for chunk in el.itertext():
        parts.append(chunk)
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def _grobid_title(root: ET.Element) -> str | None:
    title = root.find(
        ".//tei:teiHeader/tei:fileDesc/tei:titleStmt/tei:title",
        TEI_NS,
    )
    return _itertext(title) or None


def _grobid_abstract(root: ET.Element) -> str | None:
    abstract = root.find(".//tei:profileDesc/tei:abstract", TEI_NS)
    if abstract is None:
        return None
    paragraphs = [
        _itertext(p) for p in abstract.findall(".//tei:p", TEI_NS)
    ]
    paragraphs = [p for p in paragraphs if p]
    if not paragraphs:
        text = _itertext(abstract)
        return text or None
    return "\n\n".join(paragraphs)


def _grobid_authors(root: ET.Element) -> list[ParsedAuthor]:
    authors: list[ParsedAuthor] = []
    seen: set[str] = set()
    for author_el in root.findall(
        ".//tei:teiHeader/tei:fileDesc/tei:sourceDesc//tei:author",
        TEI_NS,
    ):
        pers = author_el.find("tei:persName", TEI_NS)
        if pers is None:
            continue
        forenames = " ".join(
            _itertext(f) for f in pers.findall("tei:forename", TEI_NS)
        ).strip()
        surname = _itertext(pers.find("tei:surname", TEI_NS))
        if not surname and not forenames:
            continue
        full = f"{forenames} {surname}".strip()
        if full in seen:
            continue
        seen.add(full)

        affils: list[str] = []
        for aff in author_el.findall("tei:affiliation", TEI_NS):
            name = _affil_name(aff)
            if name:
                affils.append(name)
        id_el = author_el.find("tei:idno[@type='ORCID']", TEI_NS)
        orcid = _itertext(id_el) if id_el is not None else None

        authors.append(
            ParsedAuthor(name=full, orcid=orcid or None, affiliations=affils)
        )
    return authors


def _affil_name(aff: ET.Element) -> str:
    """Try to find a meaningful institution name inside an <affiliation>."""
    # Preferred: orgName with type='institution'
    for org in aff.findall("tei:orgName", TEI_NS):
        if org.get("type") == "institution":
            text = _itertext(org)
            if text:
                return text
    # Fallback: any orgName
    for org in aff.findall("tei:orgName", TEI_NS):
        text = _itertext(org)
        if text:
            return text
    return _itertext(aff)


def _classify_head(head_text: str, default: str = "unknown") -> str:
    needle = head_text.lower()
    for keyword, label in HEAD_TO_SECTION_TYPE.items():
        if keyword in needle:
            return label
    return default


def _grobid_body_sections(root: ET.Element) -> Iterable[ParsedSection]:
    body = root.find(".//tei:text/tei:body", TEI_NS)
    if body is None:
        return
    for div in body.findall("tei:div", TEI_NS):
        head_el = div.find("tei:head", TEI_NS)
        head_text = _itertext(head_el)
        section_type = _classify_head(head_text)
        paragraphs = [
            _itertext(p) for p in div.findall("tei:p", TEI_NS)
        ]
        paragraphs = [p for p in paragraphs if p]
        body_text = "\n\n".join(paragraphs).strip()
        if not body_text and not head_text:
            continue
        yield ParsedSection(
            section_type=section_type,
            title=head_text or None,
            text=body_text or head_text,
        )

    # Figure captions surface separately (each <figDesc>).
    for fig in body.findall(".//tei:figure", TEI_NS):
        desc = _itertext(fig.find("tei:figDesc", TEI_NS))
        if desc:
            yield ParsedSection(
                section_type="figure_caption",
                title=None,
                text=desc,
            )


def _grobid_back_section(
    root: ET.Element, head_keywords: tuple[str, ...], section_type: str
) -> ParsedSection | None:
    back = root.find(".//tei:text/tei:back", TEI_NS)
    if back is None:
        return None
    chunks: list[str] = []
    for div in back.findall("tei:div", TEI_NS):
        head_text = _itertext(div.find("tei:head", TEI_NS)).lower()
        type_attr = (div.get("type") or "").lower()
        if any(kw in head_text or kw in type_attr for kw in head_keywords):
            for p in div.findall(".//tei:p", TEI_NS):
                paragraph = _itertext(p)
                if paragraph:
                    chunks.append(paragraph)
            if not div.findall(".//tei:p", TEI_NS):
                text = _itertext(div)
                if text:
                    chunks.append(text)
    if not chunks:
        return None
    return ParsedSection(
        section_type=section_type,
        title=None,
        text="\n\n".join(chunks),
    )


def _grobid_references(root: ET.Element) -> Iterable[ParsedReferenceRecord]:
    """Walk <biblStruct> elements — GROBID's structured reference output."""
    list_bibl = root.find(".//tei:text/tei:back//tei:listBibl", TEI_NS)
    if list_bibl is None:
        return
    for bibl in list_bibl.findall("tei:biblStruct", TEI_NS):
        title_el = bibl.find(".//tei:title", TEI_NS)
        title = _itertext(title_el) or None

        authors: list[str] = []
        for pers in bibl.findall(".//tei:author/tei:persName", TEI_NS):
            forenames = " ".join(
                _itertext(f) for f in pers.findall("tei:forename", TEI_NS)
            ).strip()
            surname = _itertext(pers.find("tei:surname", TEI_NS))
            joined = f"{forenames} {surname}".strip()
            if joined:
                authors.append(joined)

        year = None
        date_el = bibl.find(".//tei:date[@when]", TEI_NS)
        if date_el is not None:
            when = date_el.get("when") or ""
            m = re.search(r"\d{4}", when)
            if m:
                year = int(m.group(0))

        doi = None
        for idno in bibl.findall(".//tei:idno", TEI_NS):
            if (idno.get("type") or "").lower() == "doi":
                doi = normalize_doi(_itertext(idno))
                break

        raw_text = _itertext(bibl)
        yield ParsedReferenceRecord(
            raw_text=raw_text or (title or ""),
            doi=doi,
            title=title,
            authors=authors,
            year=year,
        )
