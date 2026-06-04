from app.models import Paper
from app.services.relevance_classifier import LABEL_CORE, LABEL_RELATED, LABEL_SDL_FIELD
from app.services.scopus_classifier import classify_paper


def test_ac_known_publication_never_below_related():
    paper = Paper(
        id="ac_gold_minimal",
        title="Sparse random Fourier features based interatomic potentials",
        abstract=None,
        provenance="ac_gold",
        ac_known_publication=True,
        ac_members_matched=["Chandra Veer Singh"],
    )

    result = classify_paper(paper)

    assert result.label == LABEL_RELATED
    assert result.confidence >= 0.72


def test_highly_relevant_ac_publication_promotes_to_core():
    paper = Paper(
        id="ac_gold_highly_relevant",
        title="How to build an effective self-driving laboratory",
        abstract=None,
        provenance="ac_gold",
        ac_known_publication=True,
        ac_highly_relevant=True,
        ac_members_matched=["Curtis Berlinguette"],
    )

    result = classify_paper(paper)

    assert result.label == LABEL_CORE
    assert result.confidence >= 0.85


def test_non_gold_ac_like_metadata_is_review_candidate_not_ac_positive():
    paper = Paper(
        id="scopus_candidate",
        title="A self-driving laboratory designed to accelerate discovery",
        abstract=None,
        provenance="scopus_batch",
        ac_known_publication=False,
        ac_acknowledged=True,
        retrieval_tier="1",
        ai_decision_score=1.0,
        automation_score=1.0,
        closed_loop_score=0.0,
    )

    result = classify_paper(paper)

    assert result.label == LABEL_SDL_FIELD
    assert result.needs_review is True
    assert result.review_priority >= 0.85


def test_scopus_classifier_emits_sdl_dimensions():
    paper = Paper(
        id="sdl_dim",
        title="Self-driving polymer laboratory with Bayesian optimization",
        abstract="We present a robotic platform for closed-loop polymer synthesis.",
        provenance="scopus_batch",
        indexed_keywords=["Bayesian optimization", "polymer"],
        ai_decision_score=1.0,
        automation_score=1.0,
        closed_loop_score=1.0,
    )

    result = classify_paper(paper)

    assert result.classification_dimensions["domain"] == "polymer"
    assert result.classification_dimensions["automation_level"] == "autonomous"
    assert result.classification_dimensions["optimization_method"] == "bayesian"
    assert result.classification_dimensions["autonomy_basis"] == "paper_self_description"
    assert result.classification_dimensions["platform_type"] == "physical_sdl"


def test_sdl_dimensions_include_ac_six_group_domains():
    cases = [
        ("High entropy inorganic alloy discovery", "inorganic"),
        ("Photoredox organic synthesis optimization", "organic"),
        ("Drug compound screening platform", "drug"),
        ("Polymer RAFT optimization", "polymer"),
        ("Formulation discovery for colloidal inks", "formulation"),
        ("Human-chip microphysiological platform", "human_chip"),
    ]
    for title, expected in cases:
        paper = Paper(id=f"p_{expected}", title=title, abstract="", provenance="scopus_batch")
        result = classify_paper(paper)
        assert result.classification_dimensions["domain"] == expected
