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
    # The default methods policy is 600 tokens with 100 overlap → step 500.
    assert all(c.token_count <= 600 for c in out)


def test_chunk_sections_assigns_increasing_order():
    sections = [
        ParsedSection(section_type="abstract", title="Abstract", text="abc"),
        ParsedSection(section_type="methods", title="Methods", text=" ".join(["m"] * 1200)),
    ]
    out = chunk_sections(sections)
    orders = [c.order_index for c in out]
    assert orders == sorted(orders)
    assert orders[-1] >= 1
