from __future__ import annotations


def test_alignment_repairs_whitespace_and_returns_exact_source_span():
    from app.domain_adaptation.alignment import align_evidence_span
    from app.domain_adaptation.audit import RejectionReason

    source = (
        "Electrochemical tests were performed at 10 mV s−1\n"
        "in 1 M KOH for 2 h."
    )
    cited = (
        "Electrochemical tests were performed at 10 mV s−1 "
        "in 1 M KOH for 2 h."
    )

    result = align_evidence_span(source, cited)

    assert result.matched is True
    assert result.exact_source_span == source
    assert source[result.char_start : result.char_end] == source
    assert result.repair_attempted is True
    assert result.repair_succeeded is True
    assert result.reason == RejectionReason.WHITESPACE_MISMATCH


def test_alignment_repairs_line_break_hyphenation_without_changing_evidence():
    from app.domain_adaptation.alignment import align_evidence_span
    from app.domain_adaptation.audit import RejectionReason

    source = "The electro-\nchemical workstation used a three-electrode cell."
    cited = "The electrochemical workstation used a three-electrode cell."

    result = align_evidence_span(source, cited)

    assert result.matched is True
    assert result.reason == RejectionReason.HYPHENATION
    assert result.exact_source_span == source
    assert source[result.char_start : result.char_end] == source


def test_alignment_repairs_unicode_units_and_superscripts():
    from app.domain_adaptation.alignment import align_evidence_span
    from app.domain_adaptation.audit import RejectionReason

    source = "The scan was recorded at 10 mV s⁻¹ and 25 ℃."
    cited = "The scan was recorded at 10 mV s-1 and 25 °C."

    result = align_evidence_span(source, cited)

    assert result.matched is True
    assert result.reason == RejectionReason.NORMALIZATION
    assert result.exact_source_span == source
    assert source[result.char_start : result.char_end] == source


def test_alignment_repairs_unit_spacing():
    from app.domain_adaptation.alignment import align_evidence_span
    from app.domain_adaptation.audit import RejectionReason

    source = "The electrolyte contained 1M KOH and the scan rate was 10mV s−1."
    cited = "The electrolyte contained 1 M KOH and the scan rate was 10 mV s-1."

    result = align_evidence_span(source, cited)

    assert result.matched is True
    assert result.reason == RejectionReason.NORMALIZATION
    assert result.exact_source_span == source


def test_alignment_rejects_paraphrase_and_returns_nearest_source_span():
    from app.domain_adaptation.alignment import align_evidence_span
    from app.domain_adaptation.audit import RejectionReason

    source = (
        "The precursor was washed with water. "
        "The catalyst was annealed at 500 °C for 2 h in air. "
        "Electrochemical testing followed."
    )
    cited = "The sample was heated at 500 °C for two hours."

    result = align_evidence_span(source, cited)

    assert result.matched is False
    assert result.reason == RejectionReason.SPAN_NOT_IN_SOURCE
    assert result.repair_attempted is True
    assert result.repair_succeeded is False
    assert result.nearest_source_span == (
        "The catalyst was annealed at 500 °C for 2 h in air."
    )
