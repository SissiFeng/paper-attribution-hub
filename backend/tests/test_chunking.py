from app.services.chunking_service import chunk_section, chunk_sections
from app.services.pdf_parser import ParsedSection


def test_abstract_not_split():
    sec = ParsedSection(section_type="abstract", title="Abstract", text=" ".join(["w"] * 2000))
    out = chunk_section(sec)
    assert len(out) == 1
    assert out[0].section_type == "abstract"


def test_acknowledgements_not_split():
    sec = ParsedSection(
        section_type="acknowledgements",
        title="Acknowledgements",
        text=" ".join(["w"] * 5000),
    )
    out = chunk_section(sec)
    assert len(out) == 1


def test_methods_chunked_with_overlap():
    sec = ParsedSection(
        section_type="methods",
        title="Methods",
        text=" ".join([f"word{i}" for i in range(2000)]),
    )
    out = chunk_section(sec)
    assert len(out) > 1
    # Methods chunks are adaptive, but still capped by the section policy.
    assert all(c.token_count <= 600 for c in out)
    assert all(c.parent_id for c in out)
    assert all(c.parent_text for c in out)


def test_chunk_sections_assigns_increasing_order():
    sections = [
        ParsedSection(section_type="abstract", title="Abstract", text="abc"),
        ParsedSection(section_type="methods", title="Methods", text=" ".join(["m"] * 1200)),
    ]
    out = chunk_sections(sections)
    orders = [c.order_index for c in out]
    assert orders == sorted(orders)
    assert orders[-1] >= 1


def test_semantic_break_splits_topic_shift():
    lab = " ".join(["robotic synthesis closed loop optimization catalyst"] * 45)
    biology = " ".join(["clinical cohort imaging diagnosis patient"] * 45)
    sec = ParsedSection(
        section_type="methods",
        title="Methods",
        text=f"{lab}\n\n{biology}",
    )

    out = chunk_section(sec)

    assert len(out) == 2
    assert "robotic synthesis" in out[0].text
    assert "clinical cohort" in out[1].text
    assert out[0].parent_id != out[1].parent_id


def test_adaptive_long_parent_uses_smaller_child_limit():
    sec = ParsedSection(
        section_type="methods",
        title="Methods",
        text=" ".join([f"token{i}" for i in range(900)]),
    )

    out = chunk_section(sec)

    assert len(out) > 1
    assert all(c.token_count <= 450 for c in out)
    assert all(c.split_strategy == "sliding_fallback" for c in out)
