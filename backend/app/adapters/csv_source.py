from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pandas as pd
import yaml

from app.adapters.base import (
    InstitutionRecord,
    PaperRecord,
    PaperSource,
    PersonRecord,
    TopicKeyword,
    TopicRecord,
)


def _split_multi(value: str | float | None) -> list[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    return [part.strip() for part in str(value).split(";") if part.strip()]


def _opt(value):
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    return value


def _to_bool(value) -> bool:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return False
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "t", "yes", "y", "1"}


class CsvPaperSource(PaperSource):
    def __init__(
        self,
        papers_csv: Path,
        people_csv: Path,
        institutions_csv: Path,
        topics_yaml: Path,
    ) -> None:
        self.papers_csv = Path(papers_csv)
        self.people_csv = Path(people_csv)
        self.institutions_csv = Path(institutions_csv)
        self.topics_yaml = Path(topics_yaml)

    def papers(self) -> Iterable[PaperRecord]:
        df = pd.read_csv(self.papers_csv)
        for _, row in df.iterrows():
            year_val = _opt(row.get("year"))
            yield PaperRecord(
                paper_id=str(row["paper_id"]).strip(),
                title=str(row["title"]).strip(),
                abstract=_opt(row.get("abstract")),
                authors=_split_multi(row.get("authors")),
                affiliations=_split_multi(row.get("affiliations")),
                year=int(year_val) if year_val is not None else None,
                doi=_opt(row.get("doi")),
                venue=_opt(row.get("venue")),
                keywords=_split_multi(row.get("keywords")),
                raw={k: (None if pd.isna(v) else v) for k, v in row.items()},
            )

    def people(self) -> Iterable[PersonRecord]:
        df = pd.read_csv(self.people_csv)
        for _, row in df.iterrows():
            yield PersonRecord(
                person_id=str(row["person_id"]).strip(),
                name=str(row["name"]).strip(),
                aliases=_split_multi(row.get("aliases")),
                institution=_opt(row.get("institution")),
                department=_opt(row.get("department")),
                lab=_opt(row.get("lab")),
                role=_opt(row.get("role")),
                is_ac_member=_to_bool(row.get("is_ac_member")),
                orcid=_opt(row.get("orcid")),
            )

    def institutions(self) -> Iterable[InstitutionRecord]:
        df = pd.read_csv(self.institutions_csv)
        for _, row in df.iterrows():
            yield InstitutionRecord(
                canonical_name=str(row["canonical_name"]).strip(),
                aliases=_split_multi(row.get("aliases")),
                country=_opt(row.get("country")),
                city=_opt(row.get("city")),
                is_partner=_to_bool(row.get("is_partner")),
            )

    def topics(self) -> Iterable[TopicRecord]:
        with self.topics_yaml.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}

        for section, is_core in (("core_topics", True), ("adjacent_topics", False)):
            for topic_id, body in (data.get(section) or {}).items():
                raw_keywords = body.get("keywords", []) or []
                keywords: list[TopicKeyword] = []
                for entry in raw_keywords:
                    if isinstance(entry, dict):
                        keywords.append(
                            TopicKeyword(
                                term=str(entry.get("term", "")).strip(),
                                weight=float(entry.get("weight", 1.0)),
                            )
                        )
                    else:
                        keywords.append(TopicKeyword(term=str(entry).strip(), weight=1.0))
                keywords = [k for k in keywords if k.term]
                neg_kw = [
                    str(t).strip()
                    for t in (body.get("negative_keywords") or [])
                    if str(t).strip()
                ]
                yield TopicRecord(
                    topic_id=topic_id,
                    name=topic_id.replace("_", " ").title(),
                    description=body.get("description"),
                    keywords=keywords,
                    is_core=is_core,
                    negative_keywords=neg_kw,
                )
