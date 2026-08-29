from __future__ import annotations


def _paper_with_structured_sections():
    from app.domain_adaptation.models import SourceChunk, SourcePaper

    return SourcePaper(
        paper_id="DOI:10.1000_scientific-chunking",
        title="Structure-first scientific chunking",
        year=2026,
        doi="10.1000/scientific-chunking",
        selection_tier="primary_oer",
        selection_reasons=["Chunking regression fixture"],
        source_bucket="test-bucket",
        source_prefix="raw/test/",
        chunks=[
            SourceChunk(
                chunk_id="methods-1",
                section_type="experimental",
                section_title="Catalyst preparation",
                section_path=["Experimental", "Catalyst preparation"],
                text=(
                    "The catalyst powder was dispersed in 20 mL of ethanol "
                    "and sonicated for 30 min."
                ),
                document_char_start=100,
                document_char_end=189,
            ),
            SourceChunk(
                chunk_id="methods-2",
                section_type="experimental",
                section_title="Catalyst preparation",
                section_path=["Experimental", "Catalyst preparation"],
                text=(
                    "The suspension was heated at 80 °C for 2 h and then "
                    "annealed at 400 °C for 3 h."
                ),
                document_char_start=191,
                document_char_end=278,
            ),
            SourceChunk(
                chunk_id="characterization-1",
                section_type="experimental",
                section_title="Characterization",
                section_path=["Experimental", "Characterization"],
                text=(
                    "XPS measurements were performed using a monochromatic "
                    "Al K alpha source, and XRD patterns were collected from "
                    "10 to 80 degrees."
                ),
                document_char_start=300,
                document_char_end=435,
            ),
        ],
    )


def test_scientific_chunking_is_structure_first_and_evidence_preserving():
    from app.domain_adaptation.chunking import (
        build_scientific_chunks,
        validate_scientific_chunk,
    )

    paper = _paper_with_structured_sections()
    chunks = build_scientific_chunks(paper)

    assert len(chunks) == 2
    preparation, characterization = chunks
    assert preparation.source_chunk_ids == ["methods-1", "methods-2"]
    assert preparation.section_path == ["Experimental", "Catalyst preparation"]
    assert "protocol" in preparation.semantic_roles
    assert len(preparation.segments) == 2
    assert characterization.source_chunk_ids == ["characterization-1"]
    assert "characterization" in characterization.semantic_roles
    assert preparation.parent_section_id != characterization.parent_section_id
    assert all(validate_scientific_chunk(chunk, paper) == [] for chunk in chunks)


def test_scientific_chunking_uses_sentence_fallback_only_for_oversized_blocks():
    from app.domain_adaptation.chunking import (
        ScientificChunkingPolicy,
        build_scientific_chunks,
        validate_scientific_chunk,
    )
    from app.domain_adaptation.models import SourceChunk, SourcePaper

    first_sentence = (
        "The precursor was mixed with 10 mL of water and stirred for 30 min."
    )
    second_sentence = (
        "The resulting suspension was heated at 90 °C for 4 h before cooling."
    )
    paper = SourcePaper(
        paper_id="DOI:10.1000_oversized",
        title="Oversized scientific paragraph",
        selection_tier="primary_oer",
        selection_reasons=["Chunking regression fixture"],
        source_bucket="test-bucket",
        source_prefix="raw/test/",
        chunks=[
            SourceChunk(
                chunk_id="methods-long",
                section_type="methods",
                section_title="Synthesis",
                section_path=["Methods", "Synthesis"],
                text=f"{first_sentence} {second_sentence}",
                document_char_start=50,
                document_char_end=50 + len(first_sentence) + 1 + len(second_sentence),
            )
        ],
    )

    chunks = build_scientific_chunks(
        paper,
        policy=ScientificChunkingPolicy(max_chars=90, min_merge_chars=0),
    )

    assert len(chunks) == 2
    assert [chunk.text for chunk in chunks] == [first_sentence, second_sentence]
    assert [chunk.ordinal for chunk in chunks] == [0, 1]
    assert all(validate_scientific_chunk(chunk, paper) == [] for chunk in chunks)


def test_scientific_chunk_ids_are_deterministic():
    from app.domain_adaptation.chunking import build_scientific_chunks

    paper = _paper_with_structured_sections()

    first = build_scientific_chunks(paper)
    second = build_scientific_chunks(paper.model_copy(deep=True))

    assert [item.model_dump() for item in first] == [
        item.model_dump() for item in second
    ]


def test_scientific_chunking_preserves_markdown_table_rows_at_safety_limit():
    from app.domain_adaptation.chunking import (
        ScientificChunkingPolicy,
        build_scientific_chunks,
    )
    from app.domain_adaptation.models import SourceChunk, SourcePaper

    table = (
        "| Sample | Temperature | Time |\n"
        "| --- | --- | --- |\n"
        "| catalyst-a | 300 °C | 2 h |\n"
        "| catalyst-b | 400 °C | 3 h |\n"
        "| catalyst-c | 500 °C | 4 h |"
    )
    paper = SourcePaper(
        paper_id="DOI:10.1000_table",
        title="Scientific table",
        selection_tier="primary_oer",
        selection_reasons=["Chunking regression fixture"],
        source_bucket="test-bucket",
        source_prefix="raw/test/",
        chunks=[
            SourceChunk(
                chunk_id="methods-table",
                section_type="experimental",
                section_title="Synthesis conditions",
                section_path=["Experimental", "Synthesis conditions"],
                text=table,
            )
        ],
    )

    chunks = build_scientific_chunks(
        paper,
        policy=ScientificChunkingPolicy(max_chars=70, min_merge_chars=0),
    )

    assert len(chunks) >= 2
    assert all(
        line.startswith("|") and line.endswith("|")
        for chunk in chunks
        for line in chunk.text.splitlines()
    )
