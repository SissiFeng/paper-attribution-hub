"""Protocol extractors for OER domain packages.

The heuristic extractor is a deterministic, high-precision baseline. It is not
presented as teacher-model output. The Bedrock teacher adapter lives in
``teacher.py`` and implements the same public interface.
"""

from __future__ import annotations

import hashlib
import re
from typing import Protocol

from app.domain_adaptation.models import (
    Caveat,
    CharacterizationUse,
    EvidenceSpan,
    InstrumentUse,
    MaterialInput,
    ProtocolStep,
    ProtocolUnit,
    ReportedResult,
    SourceChunk,
    SourcePaper,
    SoftwareUse,
)


class ProtocolExtractor(Protocol):
    name: str
    mode: str
    model: str | None
    prompt_version: str | None

    def extract(self, paper: SourcePaper) -> list[ProtocolUnit]: ...


_ACTION_RE = re.compile(
    r"\b(?:prepare|prepared|mix(?:ed)?|pipett(?:ed|ing)|sonicat(?:ed|ion)|"
    r"synthesi[sz](?:ed|ing)|deposit(?:ed|ion)|drop-coated|dried|ground|"
    r"immersed|dissolv(?:ed|ing)|heated|calcined|annealed|performed|"
    r"conducted|evaluated|measured|assembled|scanned|cycled|loaded)\b",
    re.IGNORECASE,
)
_METHOD_CUE_RE = re.compile(
    r"\b(?:method|experimental|synthesi[sz]|electrode|electrochemical|"
    r"catalyst ink|workstation|characteri[sz]|measurement|tested|protocol)\b",
    re.IGNORECASE,
)
_CONDITION_RE = re.compile(
    r"\b(?:~|>|<|more than |less than |approximately )?"
    r"\d+(?:\.\d+)?(?:\s*(?:to|–|−|-)\s*\d+(?:\.\d+)?)?\s*"
    r"(?:mA\s*cm\s*[−-]?2|mV\s*s[−-]?1|μL|uL|mL|μm|nm|cm|mm|"
    r"mM|wt%|kHz|mV|Hz|°C|L|mg|g|h|min|s|K|M|%|V)"
    r"(?:\s*(?:vs\.?\s*RHE|s[−-]?1|cm\s*[−-]?2))?",
)
_AMOUNT_MATERIAL_RE = re.compile(
    r"(?P<amount>\d+(?:\.\d+)?\s*(?:μL|uL|mL|L|mg|g|mmol|mol))\s+"
    r"of\s+(?P<name>[A-Za-z0-9α-ωΑ-Ω/()\- ]{2,70}?)"
    r"(?=,|\s+and\s+\d|\s+were\b|\s+was\b|\s+is\b|\.|$)",
    re.IGNORECASE,
)
_CONCENTRATION_MATERIAL_RE = re.compile(
    r"(?P<amount>\d+(?:\.\d+)?\s*(?:M|mM|wt%))\s+"
    r"(?P<name>KOH|NaOH|H2SO4|H₂SO₄|HClO4|HClO₄|NaCl|electrolyte)\b",
    re.IGNORECASE,
)
_MODEL_RE = re.compile(
    r"\b(?P<model>(?:Corrtest|CHI|Gamry|Autolab|BioLogic|Bio-Logic)"
    r"(?=[ -]|\d)[ -]*"
    r"(?:[A-Za-z][A-Za-z0-9-]*[ -]+){0,2}"
    r"[A-Za-z0-9-]*\d[A-Za-z0-9-]*)\b",
    re.IGNORECASE,
)
_RESULT_RE = re.compile(
    r"\b(?P<metric>overpotential|Tafel slope|current density|Faradaic "
    r"efficiency|Faraday efficiency|stability|durability)\b[^.]{0,120}?"
    r"(?P<value>\d+(?:\.\d+)?\s*(?:mV|V|mA\s*cm\s*[−-]?2|%|h))",
    re.IGNORECASE,
)
_CAVEAT_RE = re.compile(
    r"\b(?:however|limitation|limited by|insufficient|unstable|instability|"
    r"degradation|failed|failure|challenge|must be|critical to|careful)\b",
    re.IGNORECASE,
)

_TECHNIQUES = {
    "cyclic voltammetry": "cyclic voltammetry",
    "CV": "CV",
    "LSV": "LSV",
    "EIS": "EIS",
    "chronopotentiometry": "chronopotentiometry",
    "XRD": "XRD",
    "XPS": "XPS",
    "SEM": "SEM",
    "TEM": "TEM",
    "STEM": "STEM",
    "Raman": "Raman",
    "ICP-MS": "ICP-MS",
    "ICP-OES": "ICP-OES",
    "XAS": "XAS",
    "ATR-FTIR": "ATR-FTIR",
    "DEMS": "DEMS",
}
_SOFTWARE = (
    "VASP",
    "Quantum ESPRESSO",
    "COMSOL",
    "MATLAB",
    "Python",
    "Origin",
    "ZView",
    "CasaXPS",
    "BoTorch",
    "pymatgen",
)
_HIGH_INFORMATION_TECHNIQUE_RE = re.compile(
    r"\b(?:XRD|XPS|SEM|TEM|STEM|Raman|ICP-(?:MS|OES)|LSV|CV|EIS|"
    r"chronopotentiometry|voltammetry|spectroscopy|microscopy|DFT|"
    r"density functional theory)\b",
    re.IGNORECASE,
)
_RESULT_CUE_RE = re.compile(
    r"\b(?:overpotential|Tafel slope|current density|Faradaic efficiency|"
    r"activity|stability|durability|yield|selectivity|performance|result)\b",
    re.IGNORECASE,
)
_HIGH_INFORMATION_SECTIONS = {
    "methods",
    "method",
    "experimental",
    "experimental methods",
    "materials and methods",
    "results",
    "results and discussion",
    "computational details",
    "supplementary",
}
_LOW_INFORMATION_SECTIONS = {
    "abstract",
    "introduction",
    "discussion",
    "conclusion",
    "conclusions",
    "references",
    "acknowledgements",
}
_BOILERPLATE_START_RE = re.compile(
    r"(?im)(?:^|\|)[ \t]*(?:#{1,6}[ \t]*)?(?:references|bibliography|"
    r"acknowledg(?:e)?ments|author contributions|competing interests|"
    r"additional information|publisher['’]s note)\b"
)
_INLINE_BOILERPLATE_START_RE = re.compile(
    r"\b(?:acknowledg(?:e)?ments|author contributions|"
    r"competing (?:financial )?interests)\b",
    re.IGNORECASE,
)
_PUBLICATION_METADATA_SENTENCE_RE = re.compile(
    r"\b(?:department of|university of|institute of|universit[aä]t|"
    r"author contributions?|writing[- ](?:original|review)|data curation|"
    r"competing (?:financial )?interests?|financially supported|funding|"
    r"grant (?:number|no\.?))\b",
    re.IGNORECASE,
)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _stable_id(prefix: str, *parts: str) -> str:
    digest = _sha256("\0".join(parts))[:16]
    return f"{prefix}_{digest}"


def _excluded_section(chunk: SourceChunk) -> bool:
    label = f"{chunk.section_type} {chunk.section_title or ''}".casefold()
    return "reference" in label or "acknowledg" in label


def scientific_content(text: str) -> str:
    """Remove reference and publication boilerplate tails inside mixed chunks."""
    markers = [
        marker
        for marker in (
            _BOILERPLATE_START_RE.search(text),
            _INLINE_BOILERPLATE_START_RE.search(text),
        )
        if marker is not None
    ]
    end = min(marker.start() for marker in markers) if markers else len(text)
    return text[:end].rstrip()


def is_high_information_chunk(chunk: SourceChunk) -> bool:
    """Select semantic scientific chunks without relying on broken section tags."""
    text = scientific_content(chunk.text)
    if _excluded_section(chunk) or len(text.strip()) < 100:
        return False
    normalized_section = (chunk.section_type or "unknown").strip().casefold()
    if normalized_section in _LOW_INFORMATION_SECTIONS:
        return False
    if normalized_section in _HIGH_INFORMATION_SECTIONS:
        return True

    condition_count = len(_CONDITION_RE.findall(text))
    signals = sum(
        (
            bool(_ACTION_RE.search(text)),
            bool(_METHOD_CUE_RE.search(text)),
            bool(_HIGH_INFORMATION_TECHNIQUE_RE.search(text)),
            bool(_RESULT_CUE_RE.search(text)),
        )
    )
    return condition_count >= 1 and signals >= 2


def extraction_chunk_score(chunk: SourceChunk) -> int:
    """Rank high-information chunks for bounded teacher-model context."""
    if not is_high_information_chunk(chunk):
        return 0
    text = chunk.text
    score = min(len(_ACTION_RE.findall(text)), 6)
    score += min(len(_CONDITION_RE.findall(text)), 6)
    score += min(len(_METHOD_CUE_RE.findall(text)), 4)
    if re.search(r"\b(?:OER|oxygen evolution|water oxidation)\b", text, re.I):
        score += 2
    return score


def _sentences_with_offsets(text: str) -> list[tuple[str, int, int]]:
    sentences: list[tuple[str, int, int]] = []
    boundary = re.compile(r"(?:\n\s*\n|(?<=[.!?])\s+(?=[A-Z]))")
    start_offset = 0
    for match in list(boundary.finditer(text)) + [None]:
        end_offset = match.start() if match is not None else len(text)
        raw = text[start_offset:end_offset]
        left_trim = len(raw) - len(raw.lstrip())
        sentence = raw.strip()
        if sentence:
            start = start_offset + left_trim
            sentences.append((sentence, start, start + len(sentence)))
        start_offset = match.end() if match is not None else len(text)
    return sentences


class _EvidenceIndex:
    def __init__(self, paper: SourcePaper, chunk: SourceChunk) -> None:
        self.paper = paper
        self.chunk = chunk
        self._items: dict[tuple[int, int], EvidenceSpan] = {}

    def for_span(self, quote: str, start: int, end: int) -> EvidenceSpan:
        key = (start, end)
        if key not in self._items:
            self._items[key] = EvidenceSpan(
                evidence_id=_stable_id(
                    "ev", self.paper.paper_id, self.chunk.chunk_id, str(start), str(end)
                ),
                paper_id=self.paper.paper_id,
                chunk_id=self.chunk.chunk_id,
                quote=quote,
                char_start=start,
                char_end=end,
                source_sha256=_sha256(self.chunk.text),
                document_char_start=(
                    self.chunk.document_char_start + start
                    if self.chunk.document_char_start is not None
                    else None
                ),
                document_char_end=(
                    self.chunk.document_char_start + end
                    if self.chunk.document_char_start is not None
                    else None
                ),
            )
        return self._items[key]

    def values(self) -> list[EvidenceSpan]:
        return sorted(self._items.values(), key=lambda item: item.char_start)


class HeuristicOerExtractor:
    name = "oer_high_precision_rules_v0.1"
    mode = "heuristic_baseline"
    model = None
    prompt_version = None

    def extract(self, paper: SourcePaper) -> list[ProtocolUnit]:
        protocols: list[ProtocolUnit] = []
        for chunk in sorted(paper.chunks, key=lambda item: item.chunk_id):
            if _excluded_section(chunk) or not self._is_protocol_candidate(chunk.text):
                continue
            protocol = self._extract_chunk(paper, chunk)
            if protocol.steps or protocol.materials or protocol.instruments:
                protocols.append(protocol)
        return protocols

    @staticmethod
    def _is_protocol_candidate(text: str) -> bool:
        text = scientific_content(text)
        action_count = len(_ACTION_RE.findall(text))
        condition_count = len(_CONDITION_RE.findall(text))
        method_count = len(_METHOD_CUE_RE.findall(text))
        return action_count >= 2 and condition_count >= 1 and method_count >= 1

    def _extract_chunk(self, paper: SourcePaper, chunk: SourceChunk) -> ProtocolUnit:
        evidence_index = _EvidenceIndex(paper, chunk)
        materials: list[MaterialInput] = []
        instruments: list[InstrumentUse] = []
        software: list[SoftwareUse] = []
        steps: list[ProtocolStep] = []
        characterization: list[CharacterizationUse] = []
        results: list[ReportedResult] = []
        caveats: list[Caveat] = []
        seen_materials: set[str] = set()
        seen_techniques: set[str] = set()
        seen_software: set[str] = set()

        for sentence, start, end in _sentences_with_offsets(
            scientific_content(chunk.text)
        ):
            if _PUBLICATION_METADATA_SENTENCE_RE.search(sentence):
                continue
            sentence_evidence: EvidenceSpan | None = None

            def evidence() -> EvidenceSpan:
                nonlocal sentence_evidence
                if sentence_evidence is None:
                    sentence_evidence = evidence_index.for_span(
                        sentence, start, end
                    )
                return sentence_evidence

            for pattern in (_AMOUNT_MATERIAL_RE, _CONCENTRATION_MATERIAL_RE):
                for match in pattern.finditer(sentence):
                    name = re.sub(r"\s+", " ", match.group("name")).strip(" ,")
                    key = name.casefold()
                    if key in seen_materials:
                        continue
                    seen_materials.add(key)
                    span = evidence()
                    materials.append(
                        MaterialInput(
                            entity_id=_stable_id(
                                "mat", paper.paper_id, chunk.chunk_id, key
                            ),
                            name=name,
                            role="electrolyte" if key == "koh" else None,
                            amount=match.group("amount"),
                            evidence_ids=[span.evidence_id],
                        )
                    )

            model_match = _MODEL_RE.search(sentence)
            if model_match:
                model = re.sub(r"\s+", " ", model_match.group("model")).strip()
                span = evidence()
                instruments.append(
                    InstrumentUse(
                        entity_id=_stable_id(
                            "inst", paper.paper_id, chunk.chunk_id, model.casefold()
                        ),
                        name="electrochemical workstation"
                        if "workstation" in sentence.casefold()
                        else "instrument",
                        model=model,
                        evidence_ids=[span.evidence_id],
                    )
                )

            for surface, canonical in _TECHNIQUES.items():
                if not re.search(rf"(?<![A-Za-z]){re.escape(surface)}(?![A-Za-z])", sentence, re.I):
                    continue
                if canonical.casefold() in seen_techniques:
                    continue
                seen_techniques.add(canonical.casefold())
                span = evidence()
                settings = {
                    f"condition_{index + 1}": value
                    for index, value in enumerate(_CONDITION_RE.findall(sentence))
                }
                characterization.append(
                    CharacterizationUse(
                        entity_id=_stable_id(
                            "char", paper.paper_id, chunk.chunk_id, canonical.casefold()
                        ),
                        technique=canonical,
                        settings=settings,
                        evidence_ids=[span.evidence_id],
                    )
                )

            for name in _SOFTWARE:
                if not re.search(rf"\b{re.escape(name)}\b", sentence, re.I):
                    continue
                if name.casefold() in seen_software:
                    continue
                seen_software.add(name.casefold())
                span = evidence()
                software.append(
                    SoftwareUse(
                        entity_id=_stable_id(
                            "soft", paper.paper_id, chunk.chunk_id, name.casefold()
                        ),
                        name=name,
                        evidence_ids=[span.evidence_id],
                    )
                )

            if _ACTION_RE.search(sentence):
                conditions = [match.group(0) for match in _CONDITION_RE.finditer(sentence)]
                span = evidence()
                steps.append(
                    ProtocolStep(
                        step_id=_stable_id(
                            "step", paper.paper_id, chunk.chunk_id, str(len(steps) + 1)
                        ),
                        order=len(steps) + 1,
                        action=sentence,
                        conditions=conditions,
                        evidence_ids=[span.evidence_id],
                    )
                )

            for match in _RESULT_RE.finditer(sentence):
                span = evidence()
                results.append(
                    ReportedResult(
                        result_id=_stable_id(
                            "result",
                            paper.paper_id,
                            chunk.chunk_id,
                            match.group(0).casefold(),
                        ),
                        metric=match.group("metric"),
                        raw_value=match.group("value"),
                        context=sentence,
                        evidence_ids=[span.evidence_id],
                    )
                )

            if _CAVEAT_RE.search(sentence):
                span = evidence()
                caveats.append(
                    Caveat(
                        caveat_id=_stable_id(
                            "caveat",
                            paper.paper_id,
                            chunk.chunk_id,
                            str(len(caveats)),
                        ),
                        text=sentence,
                        evidence_ids=[span.evidence_id],
                    )
                )

        protocol_type = (
            "electrode_preparation_and_testing"
            if materials and characterization
            else "experimental_protocol"
        )
        protocol_id = _stable_id("protocol", paper.paper_id, chunk.chunk_id)
        return ProtocolUnit(
            protocol_id=protocol_id,
            paper_id=paper.paper_id,
            protocol_name=f"{paper.title}: {protocol_type.replace('_', ' ')}",
            protocol_type=protocol_type,
            source_paper_tier=paper.selection_tier,
            evidence_scope=(
                "primary_report"
                if paper.selection_tier == "primary_oer"
                else "secondary_report"
            ),
            source_chunk_ids=[chunk.chunk_id],
            materials=materials,
            instruments=instruments,
            software=software,
            steps=steps,
            characterization=characterization,
            results=results,
            caveats=caveats,
            evidence=evidence_index.values(),
        )
