"""Unit tests for text_utils — the primitive layer of the v0.7 filter."""
from app.services.text_utils import (
    find_term_hits,
    split_paragraphs,
    tokens,
)


def test_token_boundary_blocks_substring_in_word():
    # 'transformer' should NOT match inside 'transformerless'.
    hits = find_term_hits("transformerless converters are popular", "transformer")
    assert hits == []


def test_token_boundary_allows_phrase_match():
    hits = find_term_hits(
        "we built a self-driving lab in Toronto.", "self-driving lab"
    )
    assert len(hits) == 1


def test_phrase_accepts_space_instead_of_hyphen():
    hits = find_term_hits("a self driving lab campaign", "self-driving lab")
    assert len(hits) == 1


def test_negation_marks_hit_negated():
    text = "We do not use a self-driving lab in this work."
    hits = find_term_hits(text, "self-driving lab")
    assert len(hits) == 1
    assert hits[0].negated is True


def test_negation_resets_at_sentence_boundary():
    text = "Some prior work does not work. We built a self-driving lab."
    hits = find_term_hits(text, "self-driving lab")
    assert hits[0].negated is False


def test_blacklist_phrase_substring_does_not_fire():
    # 'self-driving car' should not trigger 'self-driving lab'.
    hits = find_term_hits("review of self-driving car safety", "self-driving lab")
    assert hits == []


def test_paragraph_split():
    text = "para one.\n\npara two.\n\npara three."
    paras = split_paragraphs(text)
    assert len(paras) == 3


def test_tokens_skips_punctuation():
    toks = tokens("Hello, World! self-driving lab.")
    assert "hello" in toks
    assert "self-driving" in toks
