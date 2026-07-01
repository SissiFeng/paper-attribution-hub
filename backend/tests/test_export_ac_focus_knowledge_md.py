from __future__ import annotations

import csv
import gzip
import json


def _write_focus_csv(path, rows):
    fieldnames = [
        "Key",
        "Peer Reviewed",
        "Catagory",
        "Acknowledges AC",
        "Highly Relevant",
        "High Impact",
        "Publication Year",
        "Title",
        "AC Members",
        "Author",
        "Publication Title",
        "DOI",
        "Url",
        "One sentence summary",
        "Abstract Note",
        "AC Funded Programs",
        "Membership status (from AC Members)",
        "SDL",
        "Research Tags",
        "Applied Tags",
    ]
    with gzip.open(path, "wt", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_load_ac_focus_csv_reads_gzip(tmp_path):
    from app.scripts.export_ac_focus_knowledge_md import load_ac_focus_csv

    csv_path = tmp_path / "focus.csv.gz"
    _write_focus_csv(csv_path, [{
        "Key": "k1",
        "Title": "Robotic discovery platform",
        "DOI": "https://doi.org/10.1000/ABC",
        "Publication Year": "2024",
        "Author": "Alice; Bob",
    }])

    papers = load_ac_focus_csv(csv_path)

    assert len(papers) == 1
    assert papers[0].doi == "10.1000/abc"
    assert papers[0].title == "Robotic discovery platform"


def test_export_markdown_enriches_from_cross_sdl_reasoning(tmp_path):
    from app.scripts.export_ac_focus_knowledge_md import export_markdown

    csv_path = tmp_path / "focus.csv.gz"
    _write_focus_csv(csv_path, [{
        "Key": "k1",
        "Peer Reviewed": "Peer Reviewed",
        "Catagory": "Journal article",
        "Publication Year": "2024",
        "Title": "Automated membrane platform",
        "Author": "Alice; Bob",
        "Publication Title": "Digital Discovery",
        "DOI": "10.1234/membrane",
        "Url": "https://example.test/paper",
        "One sentence summary": "A robotic platform automates membrane fabrication.",
        "Abstract Note": "The automated platform integrates a robot, blade casting, and compression testing.",
        "SDL": "SDL 1 - Robotics",
        "Research Tags": "Automation and Robotics,Materials Science",
    }])

    cross_root = tmp_path / "cross"
    reasoning_dir = cross_root / "data" / "reasoning"
    reasoning_dir.mkdir(parents=True)
    manifest = [{
        "paper_id": "acgold_test",
        "title": "Automated membrane platform",
        "doi": "10.1234/membrane",
        "year": 2024,
        "abstract": "manifest abstract",
        "sdl_tags": ["SDL 1 - Robotics"],
        "text_chars": 1234,
        "source": "pdf",
    }]
    (reasoning_dir / "corpus_manifest.json").write_text(json.dumps(manifest))
    (reasoning_dir / "acgold_test.json").write_text(json.dumps({
        "paper_id": "acgold_test",
        "phase0": manifest[0],
        "phase1": {
            "problem": "Manual membrane development is slow.",
            "hypothesis": "Automation improves reproducibility.",
            "method": "A robotic membrane fabrication platform combines solution preparation, blade casting, immersion, and compression testing.",
            "evidence": "Automated stress-strain analysis reproduced expected trends.",
            "conclusion": "The platform accelerates membrane screening.",
        },
        "phase2": {
            "entities": ["porous membrane", "robotic platform"],
            "mechanisms": ["automated parameter control"],
            "outcomes": ["reproducible membrane fabrication"],
        },
        "phase3": {
            "layer3_motifs": ["Automation -> Reproducibility"],
            "layer4_principles": ["Control Through Constraints"],
        },
        "phase4": {"attempts": []},
        "extraction_quality": 0.82,
        "extraction_notes": "test extraction",
    }))

    out_dir = tmp_path / "md"
    total, matched = export_markdown(csv_path, out_dir, cross_root, force=True)

    assert (total, matched) == (1, 1)
    md_files = [p for p in out_dir.glob("*.md") if p.name != "index.md"]
    assert len(md_files) == 1
    content = md_files[0].read_text()
    assert "Cross-SDL ID: `acgold_test`" in content
    assert "A robotic membrane fabrication platform" in content
    assert "automated parameter control" in content
    assert "Control Through Constraints" in content
    assert "robot" in content.lower()
    assert "## Validation" in content

    json_files = list((out_dir / "knowledge_json").glob("*.json"))
    assert len(json_files) == 1
    data = json.loads(json_files[0].read_text())
    assert data["paper_id"].startswith("acfocus_")
    assert data["provenance"]["cross_sdl_id"] == "acgold_test"
    assert data["hardware"][0]["source"] == "heuristic_text_scan"
    assert data["methods"][0]["source"] == "cross_sdl_phase1"
    assert data["materials"]
    assert data["measurements"]
    assert data["validation"]["coverage"]["hardware"] is True
    assert data["validation"]["coverage"]["cross_sdl_match"] is True

    index = (out_dir / "index.md").read_text()
    assert "validation:" in index
    assert "knowledge_json/" in index


def test_render_markdown_falls_back_to_csv_fields():
    from app.scripts.export_ac_focus_knowledge_md import AcFocusPaper, render_markdown

    paper = AcFocusPaper(
        key="k1",
        title="Sparse random Fourier features based interatomic potentials",
        doi="10.48550/arxiv.2302.06844",
        url="",
        year="2023",
        authors="Alice; Bob",
        ac_members="Alice",
        venue="arXiv",
        category="Preprint",
        peer_reviewed="Non Peer Reviewed",
        summary="This work introduces a computationally efficient random features-based interatomic potential.",
        abstract="The method models high entropy alloys and predicted atomic forces close to DFT accuracy.",
        ac_programs="",
        membership_status="AC Full Member",
        sdl="",
        research_tags="Artificial Intelligence & Data Science,Materials Science",
        applied_tags="",
        high_impact="",
        highly_relevant="",
        acknowledges_ac="",
    )

    content = render_markdown(paper)

    assert "## Scientific Elements" in content
    assert "### Materials / Systems" in content
    assert "### Properties" in content
    assert "### Measurements" in content
    assert "### Conditions" in content
    assert "computationally efficient random features-based interatomic potential" in content
    assert "Artificial Intelligence & Data Science" in content
    assert "Not specified by cross-SDL extraction" in content
    assert "cross_sdl_match" in content


def test_build_knowledge_reports_missing_fields_without_cross_sdl():
    from app.scripts.export_ac_focus_knowledge_md import AcFocusPaper, build_knowledge, knowledge_to_dict

    paper = AcFocusPaper(
        key="k1",
        title="Minimal CSV paper",
        doi="",
        url="",
        year="",
        authors="",
        ac_members="",
        venue="",
        category="",
        peer_reviewed="",
        summary="",
        abstract="",
        ac_programs="",
        membership_status="",
        sdl="",
        research_tags="",
        applied_tags="",
        high_impact="",
        highly_relevant="",
        acknowledges_ac="",
    )

    knowledge = build_knowledge(paper)
    data = knowledge_to_dict(knowledge)

    assert knowledge.validation.score == 0
    assert "hardware" in knowledge.validation.missing
    assert "method" in knowledge.validation.missing
    assert "materials" in knowledge.validation.missing
    assert "properties" in knowledge.validation.missing
    assert "measurements" in knowledge.validation.missing
    assert "conditions" in knowledge.validation.missing
    assert "cross_sdl_match" in knowledge.validation.missing
    assert data["validation"]["coverage"]["abstract"] is False


def test_material_inference_uses_word_boundaries():
    from app.scripts.export_ac_focus_knowledge_md import AcFocusPaper, build_knowledge

    paper = AcFocusPaper(
        key="k1",
        title="Robot task planning",
        doi="",
        url="",
        year="",
        authors="",
        ac_members="",
        venue="",
        category="",
        peer_reviewed="",
        summary="Generated plans can be executed by a task and motion planner.",
        abstract="",
        ac_programs="",
        membership_status="",
        sdl="",
        research_tags="",
        applied_tags="",
        high_impact="",
        highly_relevant="",
        acknowledges_ac="",
    )
    reasoning = {
        "phase2": {
            "entities": ["Task and Motion Planner"],
            "mechanisms": [],
            "outcomes": [],
        }
    }

    knowledge = build_knowledge(paper, reasoning=reasoning)

    assert knowledge.materials == []
