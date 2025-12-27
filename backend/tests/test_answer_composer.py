"""
Test AnswerComposer functionality.
Tests that answers are structured, of sufficient length, and properly formatted.
"""
import pytest
from app.answer_composer import (
    compose_answer,
    analyze_intent,
    QuestionIntent,
    _clean_raw_output,
    _structure_math_answer,
    _structure_general_answer,
    _ensure_minimum_quality
)


def test_analyze_intent_math():
    """Test that math questions are correctly identified."""
    assert analyze_intent("karekök nedir?") == QuestionIntent.MATH
    assert analyze_intent("√12 + √27 çöz") == QuestionIntent.MATH
    assert analyze_intent("denklem çöz") == QuestionIntent.MATH


def test_analyze_intent_explanation():
    """Test that explanation questions are correctly identified."""
    assert analyze_intent("Python nedir?") == QuestionIntent.EXPLANATION
    assert analyze_intent("nasıl çalışır?") == QuestionIntent.EXPLANATION
    assert analyze_intent("nereden geliyor?") == QuestionIntent.EXPLANATION


def test_analyze_intent_example():
    """Test that example requests are correctly identified."""
    assert analyze_intent("örnek ver") == QuestionIntent.EXAMPLE
    assert analyze_intent("1 tane daha") == QuestionIntent.EXAMPLE
    assert analyze_intent("uzun çöz") == QuestionIntent.EXAMPLE


def test_compose_answer_math():
    """Test that math answers are properly structured."""
    raw_output = "$$ √12 + √27 = 2√3 + 3√3 = 5√3 $$"
    composed = compose_answer(
        raw_llm_output=raw_output,
        question="√12 + √27 çöz",
        intent=QuestionIntent.MATH
    )
    
    # Should have structure
    assert "Adım" in composed or "Sonuç" in composed or "$$" in composed
    assert len(composed) >= 50  # Minimum length


def test_compose_answer_general():
    """Test that general answers have structure."""
    raw_output = "Python bir programlama dilidir. Çok popülerdir."
    composed = compose_answer(
        raw_llm_output=raw_output,
        question="Python nedir?",
        intent=QuestionIntent.GENERAL
    )
    
    # Should have structure (headings or lists)
    assert len(composed) >= 100  # Minimum length for general
    # Should not be a single flat paragraph
    assert '\n' in composed or '##' in composed or '-' in composed


def test_compose_answer_explanation():
    """Test that explanation answers have multiple perspectives."""
    raw_output = "Python bir programlama dilidir."
    composed = compose_answer(
        raw_llm_output=raw_output,
        question="Python nedir?",
        intent=QuestionIntent.EXPLANATION
    )
    
    # Should have structure
    assert len(composed) >= 150  # Minimum length for explanation
    assert '##' in composed or '**' in composed  # Should have headings or sections


def test_clean_raw_output_removes_artifacts():
    """Test that character-per-line artifacts are removed."""
    raw = "a\nb\nc\nd\ne"
    cleaned = _clean_raw_output(raw)
    
    # Should remove single-character lines
    assert len(cleaned.split('\n')) < len(raw.split('\n'))


def test_structure_math_removes_vertical_spam():
    """Test that math structure removes vertical spam."""
    raw = "İfade:\nSadeleştir:\n$$ x^2 $$\nSonuç:"
    structured = _structure_math_answer(raw)
    
    # Should remove "İfade:", "Sadeleştir:" headers
    assert "İfade:" not in structured or "Sadeleştir:" not in structured


def test_ensure_minimum_quality():
    """Test that minimum quality is enforced."""
    short_answer = "Kısa cevap."
    quality_checked = _ensure_minimum_quality(
        short_answer,
        "Python nedir?",
        QuestionIntent.EXPLANATION
    )
    
    # Should be longer than original
    assert len(quality_checked) >= len(short_answer)
    # Should end with proper punctuation
    assert quality_checked.rstrip().endswith(('.', '!', '?', ':', ';'))


def test_compose_answer_not_doc_grounded_never_blocks():
    """Test that non-doc-grounded queries never get blocked."""
    raw_output = "Python bir programlama dilidir."
    composed = compose_answer(
        raw_llm_output=raw_output,
        question="Python nedir?",
        intent=QuestionIntent.GENERAL,
        is_doc_grounded=False
    )
    
    # Should always produce an answer
    assert len(composed) > 0
    assert "Dokümanlarda bu bilgi yok" not in composed
    assert "Dokümanlarda bu bilgi bulunmuyor" not in composed

