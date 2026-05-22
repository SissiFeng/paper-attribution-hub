from app.services.external.source_reliability import (
    SOURCE_TRUST,
    merge_paper_records,
    pick_best,
    trust,
)


def test_trust_order():
    assert trust("internal") > trust("crossref")
    assert trust("crossref") > trust("openalex")
    assert trust("openalex") > trust("semantic_scholar")
    assert trust("semantic_scholar") > trust("pdf")
    assert trust("pdf") > trust("llm")


def test_pick_best_prefers_higher_trust():
    assert pick_best(("openalex", "openalex value"), ("crossref", "crossref value")) == "crossref value"
    # When the higher-trust source has empty value, fall through.
    assert pick_best(("crossref", None), ("openalex", "openalex value")) == "openalex value"
    assert pick_best(("crossref", ""), ("openalex", "x")) == "x"


def test_merge_paper_records():
    from app.adapters.base import PaperRecord

    openalex_rec = PaperRecord(
        paper_id="P1",
        title="OA title",
        authors=["A", "B"],
        year=2024,
        source="openalex",
    )
    crossref_rec = PaperRecord(
        paper_id="P1",
        title="Crossref title",
        authors=["Crossref Author"],
        year=2023,
        source="crossref",
    )
    merged = merge_paper_records(openalex_rec, crossref_rec)
    # Crossref outranks OpenAlex.
    assert merged["title"] == "Crossref title"
    assert merged["year"] == 2023
    assert merged["sources"] == ["openalex", "crossref"]
