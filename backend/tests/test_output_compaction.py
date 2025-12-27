"""
Test output compaction.
Tests that answer text does not contain character-per-line patterns.
"""
import pytest
from app.utils import compact_markdown_output


def test_compact_markdown_removes_character_per_line():
    """Test that character-per-line patterns are removed."""
    # Simulate accidental character-per-line output
    bad_output = """a
b
c
d
e
f"""
    
    compacted = compact_markdown_output(bad_output)
    
    # Should be more compact (fewer lines or different structure)
    assert len(compacted.split('\n')) < len(bad_output.split('\n')), \
        "Compacted output should have fewer lines"


def test_compact_markdown_collapses_excessive_newlines():
    """Test that excessive newlines are collapsed."""
    text_with_many_newlines = "Line 1\n\n\n\n\n\nLine 2"
    
    compacted = compact_markdown_output(text_with_many_newlines)
    
    # Should have max 2 consecutive newlines
    assert "\n\n\n" not in compacted, "Should not have more than 2 consecutive newlines"


def test_compact_markdown_preserves_math_blocks():
    """Test that math blocks are preserved."""
    text_with_math = "$$ x^2 + y^2 = z^2 $$\n\nSonuç: $z = \\sqrt{x^2 + y^2}$"
    
    compacted = compact_markdown_output(text_with_math)
    
    # Should still contain math
    assert "$$" in compacted or "$" in compacted, "Math blocks should be preserved"


def test_compact_markdown_handles_empty_text():
    """Test that empty text is handled gracefully."""
    assert compact_markdown_output("") == ""
    assert compact_markdown_output("   ") == ""
    assert compact_markdown_output("\n\n\n") == ""

