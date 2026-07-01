"""KB Markdown export: front-matter, cross-links, classification/citation
sections, paper cap and transfer highlights."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from app.models import (
    Paper,
    PaperClassification,
    PaperEntity,
    PaperLabLink,
    PaperReference,
    SdlLab,
)

_LINK_RE = re.compile(r"\]\(([^)]+)\)")


def _lab(lab_id: str) -> SdlLab:
    return SdlLab(
        id=lab_id,
        name=f"Lab {lab_id[-1].upper()}",
        institution="Test U",
        domain_focus="testing",
    )


def _entity(
    paper_id: str,
    entity_type: str,
    name: str,
    stage: str | None = None,
    usage_snippet: str | None = None,
) -> PaperEntity:
    return PaperEntity(
        id=f"ent_{paper_id}_{name.replace(' ', '_')}",
        paper_id=paper_id,
        entity_type=entity_type,
        name=name,
        normalized_name=name,
        stage=stage,
        usage_snippet=usage_snippet,
    )


def _seed(session, with_classifications: bool, with_references: bool) -> None:
    session.add_all([_lab("lab-a"), _lab("lab-b"), _lab("lab-c")])
    papers = {
        "PA1": (2020, "lab-a"),
        "PA2": (2022, "lab-a"),
        "PB1": (2021, "lab-b"),
        "PC1": (2023, "lab-c"),
    }
    for pid, (year, lab_id) in papers.items():
        session.add(Paper(id=pid, title=f"Paper {pid}", year=year))
        session.add(PaperLabLink(paper_id=pid, lab_id=lab_id))
    session.add_all(
        [
            _entity(
                "PA1",
                "method",
                "bayesian optimization",
                stage="optimization",
                usage_snippet="Bayesian optimization selected the next experiment.",
            ),
            _entity("PB1", "method", "bayesian optimization"),
            _entity("PC1", "method", "bayesian optimization"),
            _entity("PA1", "software", "python"),
        ]
    )
    if with_classifications:
        session.add_all(
            [
                PaperClassification(
                    id="C1", paper_id="PA1", label="CORE_RELEVANT", confidence=0.9
                ),
                PaperClassification(
                    id="C2", paper_id="PA2", label="CORE_RELEVANT", confidence=0.8
                ),
                PaperClassification(
                    id="C3", paper_id="PB1", label="RELATED_RELEVANT", confidence=0.7
                ),
            ]
        )
    if with_references:
        session.add_all(
            [
                PaperReference(
                    id="R1", citing_paper_id="PB1", cited_paper_id="PA1", raw_text="r"
                ),
                PaperReference(
                    id="R2", citing_paper_id="PC1", cited_paper_id="PA1", raw_text="r"
                ),
            ]
        )
    session.flush()


def _export(tmp_path: Path) -> Path:
    from app.scripts.export_kb_md import export_kb

    out = tmp_path / "kb"
    export_kb(out)
    return out


def _assert_links_resolve(out: Path) -> None:
    """Every relative link target in every generated file must exist."""
    md_files = list(out.rglob("*.md"))
    assert md_files
    for md in md_files:
        for target in _LINK_RE.findall(md.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "#")):
                continue
            resolved = (md.parent / target.split("#")[0]).resolve()
            assert resolved.is_file(), f"{md.name}: broken link {target}"


def _front_matter(path: Path) -> dict:
    content = path.read_text(encoding="utf-8")
    assert content.startswith("---\n")
    raw = content.split("---", 2)[1]
    return yaml.safe_load(raw)


def _assert_okf_bundle(out: Path) -> None:
    index_fm = _front_matter(out / "index.md")
    assert index_fm["okf_version"] == "0.1"
    assert index_fm["type"] == "Knowledge Bundle Index"
    assert index_fm["title"] == "Cross-SDL Knowledge Base"
    assert index_fm["resource"] == "/kb/summary"
    assert "timestamp" in index_fm

    concept_files = [
        *list((out / "entities").glob("*.md")),
        *list((out / "labs").glob("*.md")),
    ]
    for concept in concept_files:
        fm = _front_matter(concept)
        assert fm["type"]
        assert fm["title"]
        assert fm["description"]
        assert fm["resource"]
        assert isinstance(fm["tags"], list)
        assert fm["timestamp"]


def test_export_with_classifications_and_references(session, tmp_path):
    _seed(session, with_classifications=True, with_references=True)
    session.commit()
    out = _export(tmp_path)

    index = (out / "index.md").read_text(encoding="utf-8")
    assert index.startswith('---\ntype: "Knowledge Bundle Index"\n')
    assert "generated: " in index.split("---")[1]
    assert 'okf_version: "0.1"' in index
    assert "- References: 2" in index
    assert "- Classified papers: 3" in index
    # index links labs and entities
    assert "[Lab A](labs/lab-a.md)" in index
    assert "[bayesian optimization](entities/method--bayesian-optimization.md)" in index
    # transfer highlights: entity + origin lab linked, adopters and avg lag
    assert "## Transfer highlights" in index
    assert "| [Lab A](labs/lab-a.md) (2020) | 2 | 2.0 |" in index

    entity = (out / "entities" / "method--bayesian-optimization.md").read_text(
        encoding="utf-8"
    )
    assert entity.startswith('---\ntype: "Knowledge Entity"\n')
    assert 'name: "bayesian optimization"' in entity
    assert 'resource: "/kb/entities/method/bayesian%20optimization"' in entity
    assert 'entity_type: "method"' in entity
    # lab names link to ../labs/<slug>.md
    assert "[Lab A](../labs/lab-a.md)" in entity
    # classified papers carry a label badge
    assert "- Paper PA1 (2020) — labs: [Lab A](../labs/lab-a.md) — CORE_RELEVANT" in entity
    assert "RELATED_RELEVANT" in entity
    # unclassified paper has no badge
    assert "- Paper PC1 (2023) — labs: [Lab C](../labs/lab-c.md)\n" in entity
    assert "## SAG-lite Event Trail" in entity
    assert (
        "- **Paper PA1** (2020) — optimization: Bayesian optimization selected "
        "the next experiment. Related: software:python."
    ) in entity

    lab_a = (out / "labs" / "lab-a.md").read_text(encoding="utf-8")
    assert lab_a.startswith('---\ntype: "SDL Lab"\n')
    assert 'lab_id: "lab-a"' in lab_a
    assert 'resource: "/kb/labs/lab-a/profile"' in lab_a
    assert 'institution: "Test U"' in lab_a
    # entity names link to ../entities/<type>--<slug>.md
    assert "[bayesian optimization](../entities/method--bayesian-optimization.md)" in lab_a
    assert "## Classification profile" in lab_a
    assert "- CORE_RELEVANT: 2" in lab_a
    # lab-a is cited by lab-b and lab-c
    assert "## Citation flows" in lab_a
    assert "### Cited by" in lab_a
    assert "- [Lab B](../labs/lab-b.md): 1 reference(s)" in lab_a

    lab_b = (out / "labs" / "lab-b.md").read_text(encoding="utf-8")
    assert "### Cites" in lab_b
    assert "- [Lab A](../labs/lab-a.md): 1 reference(s)" in lab_b

    _assert_links_resolve(out)
    _assert_okf_bundle(out)


def test_export_without_classifications_or_references(session, tmp_path):
    _seed(session, with_classifications=False, with_references=False)
    session.commit()
    out = _export(tmp_path)

    index = (out / "index.md").read_text(encoding="utf-8")
    assert "- References:" not in index
    assert "- Classified papers:" not in index
    # highlights still come from entity adoption data
    assert "## Transfer highlights" in index

    entity = (out / "entities" / "method--bayesian-optimization.md").read_text(
        encoding="utf-8"
    )
    assert "CORE_RELEVANT" not in entity

    for lab_page in (out / "labs").glob("*.md"):
        content = lab_page.read_text(encoding="utf-8")
        assert "## Classification profile" not in content
        assert "## Citation flows" not in content

    _assert_links_resolve(out)
    _assert_okf_bundle(out)


def test_entity_papers_capped_at_30(session, tmp_path):
    session.add(_lab("lab-a"))
    for i in range(35):
        pid = f"P{i:02d}"
        session.add(Paper(id=pid, title=f"Paper {pid}", year=2020))
        session.add(PaperLabLink(paper_id=pid, lab_id="lab-a"))
        session.add(_entity(pid, "method", "bayesian optimization"))
    session.commit()
    out = _export(tmp_path)

    entity = (out / "entities" / "method--bayesian-optimization.md").read_text(
        encoding="utf-8"
    )
    assert len(re.findall(r"^- Paper P\d+", entity, re.M)) == 30
    assert "- ...and 5 more" in entity
    _assert_links_resolve(out)
    _assert_okf_bundle(out)
