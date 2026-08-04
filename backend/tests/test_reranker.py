
from app.services.reranker import NullReranker, get_reranker
from app.services.retrieval_service import RetrievedChunk


def _make_chunk(chunk_id: str, score: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        paper_id="P000",
        section_type="methods",
        section_title=None,
        text="Some text",
        bm25_score=0.5,
        cosine_score=0.5,
        score=score,
    )


def test_null_reranker_preserves_order():
    items = [_make_chunk("a", 0.9), _make_chunk("b", 0.5), _make_chunk("c", 0.2)]
    out = NullReranker().rerank("query", items)
    assert [c.chunk_id for c in out] == ["a", "b", "c"]


def test_get_reranker_default_is_null(monkeypatch):
    monkeypatch.delenv("PAS_RERANKER", raising=False)
    r = get_reranker()
    assert r.name == "none"


def test_cross_encoder_selected_via_env(monkeypatch):
    monkeypatch.setenv("PAS_RERANKER", "cross-encoder")
    r = get_reranker()
    assert r.name == "cross-encoder"
    # Don't actually load the model in CI — just confirm the class is selected.


def test_cross_encoder_raises_without_sentence_transformers(monkeypatch):
    """If sentence-transformers isn't installed, calling rerank() should fail
    loudly so operators know to install it (rather than silently degrading)."""
    from app.services import reranker as reranker_module

    # Force the lazy loader to raise as if the package were missing.
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __import__

    def fake_import(name, *args, **kwargs):
        if name == "sentence_transformers":
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    ce = reranker_module.CrossEncoderReranker()
    items = [_make_chunk("a", 0.9)]
    import pytest

    with pytest.raises(RuntimeError):
        ce.rerank("q", items)
