"""llm-wiki vault export: structure, index↔page parity, wikilink resolution,
front-matter, append-only log, graph data, and the defensive contract for
fine-grained method fields (stage / usage_snippet / categories) that land
with a concurrent extraction change."""
from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import yaml

from app.models import (
    Paper,
    PaperClassification,
    PaperEntity,
    PaperLabLink,
    PaperReference,
    SdlLab,
)

_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)")


def _lab(lab_id: str) -> SdlLab:
    return SdlLab(
        id=lab_id,
        name=f"Lab {lab_id[-1].upper()}",
        institution="Test U",
        domain_focus="testing",
    )


def _entity(paper_id: str, entity_type: str, name: str) -> PaperEntity:
    return PaperEntity(
        id=f"ent_{paper_id}_{name.replace(' ', '_')}",
        paper_id=paper_id,
        entity_type=entity_type,
        name=name,
        normalized_name=name,
    )


def _seed(session) -> None:
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
    session.add(PaperLabLink(paper_id="PB1", lab_id="lab-a"))  # shared paper
    session.add_all(
        [
            _entity("PA1", "method", "bayesian optimization"),
            _entity("PA2", "method", "bayesian optimization"),
            _entity("PB1", "method", "bayesian optimization"),
            _entity("PC1", "method", "active learning"),
            _entity("PA1", "material", "perovskite"),
            _entity("PB1", "instrument", "liquid handler"),
            _entity("PA1", "software", "python"),
        ]
    )
    session.add(
        PaperClassification(
            id="C1", paper_id="PA1", label="CORE_RELEVANT", confidence=0.9
        )
    )
    session.add(
        PaperReference(
            id="R1", citing_paper_id="PB1", cited_paper_id="PA1", raw_text="r"
        )
    )
    session.commit()


def _export(tmp_path: Path) -> Path:
    from app.scripts.export_llm_wiki import export_llm_wiki

    out = tmp_path / "llm-wiki"
    export_llm_wiki(out)
    return out


def _wikilinks(text: str) -> set[str]:
    return {t.strip() for t in _WIKILINK_RE.findall(text)}


def test_vault_structure_and_index_parity(session, tmp_path):
    _seed(session)
    out = _export(tmp_path)

    for name in ("CLAUDE.md", "index.md", "log.md", "graph.html", "graph.json"):
        assert (out / name).is_file(), f"missing {name}"
    assert (out / "wiki" / "overview.md").is_file()
    assert (out / "wiki" / "labs" / "lab-a.md").is_file()
    assert (out / "wiki" / "methods" / "bayesian-optimization.md").is_file()
    assert (out / "wiki" / "materials" / "perovskite.md").is_file()
    assert (out / "wiki" / "instruments" / "liquid-handler.md").is_file()
    assert (out / "wiki" / "software" / "python.md").is_file()

    # index links exactly the wiki pages that exist (no orphans either way)
    page_paths = {
        str(p.relative_to(out))[: -len(".md")] for p in (out / "wiki").rglob("*.md")
    }
    index_links = _wikilinks((out / "index.md").read_text(encoding="utf-8"))
    assert index_links == page_paths


def test_wikilinks_resolve_and_frontmatter_parses(session, tmp_path):
    _seed(session)
    out = _export(tmp_path)

    md_files = [out / "index.md", *sorted((out / "wiki").rglob("*.md"))]
    for md in md_files:
        text = md.read_text(encoding="utf-8")
        for target in _wikilinks(text):
            assert (out / f"{target}.md").is_file(), f"{md.name}: broken [[{target}]]"
        parts = text.split("---\n")
        assert text.startswith("---\n"), f"{md.name}: no front-matter"
        fm = yaml.safe_load(parts[1])
        assert isinstance(fm, dict) and fm.get("type") and fm.get("name"), md.name

    lab_a = (out / "wiki" / "labs" / "lab-a.md").read_text(encoding="utf-8")
    fm = yaml.safe_load(lab_a.split("---\n")[1])
    assert "bayesian optimization" in fm["uses_methods"]
    assert fm["collaborates_with"] == ["lab-b"]
    assert "[[wiki/methods/bayesian-optimization|bayesian optimization]]" in lab_a
    assert "## Classification profile" in lab_a
    assert "## Citation flows" in lab_a

    method = (out / "wiki" / "methods" / "bayesian-optimization.md").read_text(
        encoding="utf-8"
    )
    assert "[[wiki/labs/lab-a|Lab A]]" in method
    assert "`CORE_RELEVANT`" in method
    assert "## Adoption" in method


def test_log_appends_across_runs(session, tmp_path):
    _seed(session)
    out = _export(tmp_path)
    _export(tmp_path)

    log = (out / "log.md").read_text(encoding="utf-8")
    entries = re.findall(r"^## \[\d{4}-\d{2}-\d{2}\] ingest \| ", log, re.M)
    assert len(entries) == 2
    assert "Rebuilt from" in log and "3 labs" in log


def test_graph_json_and_embedded_html(session, tmp_path):
    _seed(session)
    out = _export(tmp_path)

    graph = json.loads((out / "graph.json").read_text(encoding="utf-8"))
    ids = [n["id"] for n in graph["nodes"]]
    assert len(ids) == len(set(ids))
    id_set = set(ids)
    assert graph["edges"], "graph has no edges"
    for edge in graph["edges"]:
        assert edge["source"] in id_set and edge["target"] in id_set
    # every entity node keeps at least one edge (no orphans from the
    # weight>=2 density filter)
    linked = {e["source"] for e in graph["edges"]} | {
        e["target"] for e in graph["edges"]
    }
    for node in graph["nodes"]:
        if node["type"] != "lab":
            assert node["id"] in linked, f"orphan node {node['id']}"
    # node pages are embedded for the side panel
    method_node = next(
        n for n in graph["nodes"] if n["id"] == "wiki/methods/bayesian-optimization"
    )
    assert "# bayesian optimization" in method_node["md"]

    html = (out / "graph.html").read_text(encoding="utf-8")
    assert len(html) > 10_000
    assert "wiki/methods/bayesian-optimization" in html  # data embedded
    assert "/*__GRAPH_DATA__*/ null" not in html


def test_works_without_stage_usage_or_categories(session, tmp_path):
    """Defensive contract: before the fine-grained extraction change lands,
    PaperEntity has no stage/usage_snippet and there is no entity meta —
    method pages must render without Usage/Stages and without concept pages."""
    _seed(session)
    out = _export(tmp_path)

    method = (out / "wiki" / "methods" / "bayesian-optimization.md").read_text(
        encoding="utf-8"
    )
    assert "## Usage" not in method
    assert "## Stages" not in method
    fm = yaml.safe_load(method.split("---\n")[1])
    assert "stages" not in fm
    assert not list((out / "wiki" / "concepts").glob("*.md"))


def test_collect_method_usage_reads_optional_fields():
    from app.scripts.export_llm_wiki import collect_method_usage

    bare = SimpleNamespace(normalized_name="active learning")
    rich = SimpleNamespace(
        normalized_name="bayesian optimization",
        stage="property_prediction",
        usage_snippet="We used BO to select the next batch.",
    )
    usage, stages = collect_method_usage(
        [(bare, 2021, "lab-b"), (rich, 2020, "lab-a")]
    )
    assert "active learning" not in usage
    assert usage["bayesian optimization"] == [
        {
            "lab_id": "lab-a",
            "year": 2020,
            "stage": "property_prediction",
            "snippet": "We used BO to select the next batch.",
        }
    ]
    assert stages == {"bayesian optimization": {"property_prediction": 1}}


def test_categories_usage_and_stages_render(session, tmp_path, monkeypatch):
    """Other side of the contract: once meta/stage/usage data exists, method
    pages gain category + Stages + Usage and concept pages appear."""
    from app.scripts import export_llm_wiki as mod

    _seed(session)
    monkeypatch.setattr(
        mod,
        "_load_entity_meta",
        lambda: {
            "bayesian optimization": {"category": "machine learning"},
            "active learning": {"category": "machine learning"},
        },
    )
    monkeypatch.setattr(
        mod,
        "collect_method_usage",
        lambda rows: (
            {
                "bayesian optimization": [
                    {
                        "lab_id": "lab-a",
                        "year": 2020,
                        "stage": "modeling",
                        "snippet": "We used BO to plan experiments.",
                    }
                ]
            },
            {"bayesian optimization": {"modeling": 1}},
        ),
    )
    out = _export(tmp_path)

    method = (out / "wiki" / "methods" / "bayesian-optimization.md").read_text(
        encoding="utf-8"
    )
    fm = yaml.safe_load(method.split("---\n")[1])
    assert fm["category"] == "machine learning"
    assert fm["stages"] == {"modeling": 1}
    assert "## Stages" in method and "- modeling: 1" in method
    assert (
        '- [[wiki/labs/lab-a|Lab A]] (2020, modeling): "We used BO to plan experiments."'
        in method
    )

    concept = (out / "wiki" / "concepts" / "machine-learning.md").read_text(
        encoding="utf-8"
    )
    cfm = yaml.safe_load(concept.split("---\n")[1])
    assert cfm["type"] == "concept"
    assert set(cfm["methods"]) == {"bayesian optimization", "active learning"}
    assert "[[wiki/methods/bayesian-optimization|bayesian optimization]]" in concept

    index = (out / "index.md").read_text(encoding="utf-8")
    assert "### Machine Learning" in index
    assert "[[wiki/concepts/machine-learning|Machine Learning]]" in index

    graph = json.loads((out / "graph.json").read_text(encoding="utf-8"))
    assert any(n["type"] == "concept" for n in graph["nodes"])
    assert any(e["type"] == "member" for e in graph["edges"])
