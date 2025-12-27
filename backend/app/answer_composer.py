"""
AnswerComposer: Transform raw LLM output into ChatGPT-quality structured answers.

This module ensures all answers are:
- Well-structured with headings and sections
- Properly formatted (no vertical math artifacts)
- Of sufficient length and quality
- Professional and satisfying to read
"""
import re
import logging
from typing import Dict, Optional, List, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class QuestionIntent(Enum):
    """Question intent classification."""
    MATH = "math"
    EXPLANATION = "explanation"  # "nedir", "nereden geliyor", "nasıl çalışır"
    HISTORY = "history"
    EXAMPLE = "example"  # "örnek ver", "1 tane daha"
    COMPARISON = "comparison"  # "fark nedir", "karşılaştır"
    GENERAL = "general"  # General knowledge questions


def analyze_intent(question: str, previous_topic: Optional[str] = None) -> QuestionIntent:
    """
    Analyze question intent to determine answer structure.
    
    Args:
        question: User question text
        previous_topic: Previous topic from conversation state
        
    Returns:
        QuestionIntent enum
    """
    question_lower = question.lower().strip()
    
    # Math patterns
    math_patterns = [
        r'\b(karekök|radikal|üslü|logaritma|türev|integral|denklem|fonksiyon|matematik|math)\b',
        r'\b(çöz|hesapla|sadeleştir|topla|çıkar|çarp|böl)\b',
        r'\$\$|\$|\\sqrt|\\frac|\^\{|_\{',
    ]
    
    # Explanation patterns
    explanation_patterns = [
        r'\b(nedir|ne\s+demek|nasıl\s+çalışır|nereden\s+geliyor|açıkla|anlat)\b',
        r'\b(what\s+is|how\s+does|explain|tell\s+me)\b',
    ]
    
    # History patterns
    history_patterns = [
        r'\b(tarih|geçmiş|ne\s+zaman|kim\s+buldu|kim\s+icat)\b',
        r'\b(history|when|who\s+invented|who\s+discovered)\b',
    ]
    
    # Example patterns
    example_patterns = [
        r'\b(örnek|example|1\s+tane|bir\s+tane|daha)\b',
        r'\b(uzun\s+çöz|uzun\s+soru|devam)\b',
    ]
    
    # Comparison patterns
    comparison_patterns = [
        r'\b(fark\s+nedir|karşılaştır|benzerlik|difference|compare)\b',
    ]
    
    # Check patterns
    if any(re.search(p, question_lower, re.IGNORECASE) for p in math_patterns):
        return QuestionIntent.MATH
    elif any(re.search(p, question_lower, re.IGNORECASE) for p in explanation_patterns):
        return QuestionIntent.EXPLANATION
    elif any(re.search(p, question_lower, re.IGNORECASE) for p in history_patterns):
        return QuestionIntent.HISTORY
    elif any(re.search(p, question_lower, re.IGNORECASE) for p in example_patterns):
        return QuestionIntent.EXAMPLE
    elif any(re.search(p, question_lower, re.IGNORECASE) for p in comparison_patterns):
        return QuestionIntent.COMPARISON
    else:
        return QuestionIntent.GENERAL


def compose_answer(
    raw_llm_output: str,
    question: str,
    intent: QuestionIntent,
    is_doc_grounded: bool = False,
    rag_context: Optional[str] = None
) -> str:
    """
    Compose a structured, high-quality answer from raw LLM output.
    
    Args:
        raw_llm_output: Raw response from LLM
        question: Original user question
        intent: Question intent
        is_doc_grounded: Whether answer is based on documents
        rag_context: RAG context if available
        
    Returns:
        Composed, structured answer
    """
    if not raw_llm_output or not raw_llm_output.strip():
        return "Üzgünüm, bir cevap üretemedim. Lütfen tekrar deneyin."
    
    # Step 1: Clean and normalize
    answer = _clean_raw_output(raw_llm_output)
    
    # Step 2: Structure based on intent
    if intent == QuestionIntent.MATH:
        answer = _structure_math_answer(answer)
    elif intent == QuestionIntent.EXPLANATION:
        answer = _structure_explanation_answer(answer, question)
    elif intent == QuestionIntent.HISTORY:
        answer = _structure_history_answer(answer)
    elif intent == QuestionIntent.COMPARISON:
        answer = _structure_comparison_answer(answer)
    elif intent == QuestionIntent.EXAMPLE:
        answer = _structure_example_answer(answer)
    else:  # GENERAL
        answer = _structure_general_answer(answer, question)
    
    # Step 3: Ensure minimum quality
    answer = _ensure_minimum_quality(answer, question, intent)
    
    # Step 4: Final formatting
    answer = _final_formatting(answer)
    
    return answer


def _clean_raw_output(text: str) -> str:
    """Clean raw LLM output: remove artifacts, normalize whitespace."""
    if not text:
        return ""
    
    # Remove character-per-line patterns (vertical math artifacts)
    lines = text.split('\n')
    cleaned_lines = []
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # Skip empty lines (will handle spacing later)
        if not stripped:
            continue
        
        # Remove single-character lines that are likely artifacts
        if len(stripped) == 1 and stripped not in ['$', '=', '+', '-', '*', '/', '^', '_', '\\']:
            # Check if next line is also single char (pattern)
            if i + 1 < len(lines) and len(lines[i + 1].strip()) == 1:
                continue
        
        cleaned_lines.append(line)
    
    text = '\n'.join(cleaned_lines)
    
    # Normalize whitespace
    text = re.sub(r'\n{4,}', '\n\n\n', text)  # Max 3 consecutive newlines
    text = re.sub(r'[ \t]+', ' ', text)  # Collapse multiple spaces
    
    return text.strip()


def _structure_math_answer(text: str) -> str:
    """
    Structure math answers: compact, readable, no vertical spam.
    """
    # Remove vertical math artifacts (İfade:, Sadeleştir:, Sonuç: on separate lines)
    text = re.sub(r'^(İfade|Sadeleştir|Birleştir|Sonuç)\s*:\s*$', '', text, flags=re.MULTILINE | re.IGNORECASE)
    
    # Merge broken math expressions
    # Pattern: Multiple $$ blocks that should be one expression
    math_blocks = re.findall(r'\$\$[^\$]*\$\$', text)
    if len(math_blocks) > 1:
        # Try to merge consecutive math blocks
        # Extract content and merge with = signs
        block_contents = [b.replace('$$', '').strip() for b in math_blocks]
        if all('=' in bc for bc in block_contents):
            # These are likely steps of same expression
            merged = ' = '.join(block_contents)
            # Replace all blocks with single merged block
            for block in math_blocks:
                text = text.replace(block, '', 1)
            # Insert merged block at first position
            first_block_pos = text.find('$$')
            if first_block_pos == -1:
                text = f"$$ {merged} $$\n\n{text}"
            else:
                text = text[:first_block_pos] + f"$$ {merged} $$" + text[first_block_pos:]
    
    # Ensure headers (Adım 1, Adım 2, Sonuç) are at line start
    lines = text.split('\n')
    processed_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('**Adım') or stripped.startswith('**Sonuç'):
            processed_lines.append(stripped)  # No leading spaces
        else:
            processed_lines.append(line)
    
    text = '\n'.join(processed_lines)
    
    # Add spacing between steps
    text = re.sub(r'(^\*\*Adım \d+[^*]+\*\*)', r'\1\n', text, flags=re.MULTILINE)
    text = re.sub(r'(^\*\*Sonuç:\*\*)', r'\n\1', text, flags=re.MULTILINE)
    
    return text


def _structure_explanation_answer(text: str, question: str) -> str:
    """
    Structure explanation answers: introduction, multiple perspectives, summary.
    """
    # Check if answer already has structure
    has_headings = bool(re.search(r'^#{1,3}\s+', text, re.MULTILINE))
    has_sections = bool(re.search(r'^\*\*[^*]+\*\*', text, re.MULTILINE))
    
    if has_headings or has_sections:
        # Already structured, just ensure quality
        return text
    
    # Add structure if missing
    lines = text.split('\n')
    
    # Check if answer is too short or flat
    if len(lines) < 3 or len(text) < 200:
        # Add introduction and structure
        structured = f"## {question}\n\n"
        structured += text
        return structured
    
    # Add introduction if missing
    if not text.startswith('#') and not text.startswith('**'):
        # First paragraph as introduction
        first_para = lines[0] if lines else ""
        if len(first_para) < 100:
            # Add a proper introduction
            structured = f"{first_para}\n\n"
            structured += '\n'.join(lines[1:]) if len(lines) > 1 else text
            return structured
    
    return text


def _structure_history_answer(text: str) -> str:
    """Structure history answers: timeline, key events, summary."""
    # Check if already structured
    if re.search(r'^#{1,3}\s+', text, re.MULTILINE):
        return text
    
    # Add timeline structure if missing
    lines = text.split('\n')
    if len(lines) < 5:
        # Short answer, add structure
        structured = "## Tarihçe\n\n"
        structured += text
        return structured
    
    return text


def _structure_comparison_answer(text: str) -> str:
    """Structure comparison answers: side-by-side or sections."""
    # Check if already structured
    if re.search(r'^#{1,3}\s+', text, re.MULTILINE):
        return text
    
    # Add comparison structure
    lines = text.split('\n')
    structured = "## Karşılaştırma\n\n"
    structured += text
    return structured


def _structure_example_answer(text: str) -> str:
    """Structure example answers: clear example with explanation."""
    # Math examples should use math structure
    if re.search(r'\$\$|\$|\\sqrt', text):
        return _structure_math_answer(text)
    
    # General examples
    if not text.startswith('##') and not text.startswith('**'):
        structured = "## Örnek\n\n"
        structured += text
        return structured
    
    return text


def _structure_general_answer(text: str, question: str) -> str:
    """
    Structure general knowledge answers: introduction, headings, lists.
    """
    # Check if already has structure
    has_headings = bool(re.search(r'^#{1,3}\s+', text, re.MULTILINE))
    has_lists = bool(re.search(r'^[-*•]\s+', text, re.MULTILINE))
    
    if has_headings and has_lists:
        # Already well-structured
        return text
    
    lines = text.split('\n')
    
    # If answer is a single flat paragraph, add structure
    if len(lines) <= 3 and len(text) < 300:
        # Add introduction
        structured = f"{text}\n\n"
        return structured
    
    # If answer has multiple paragraphs but no headings, add them
    if not has_headings and len(lines) > 5:
        # Try to identify natural sections
        paragraphs = [line.strip() for line in lines if line.strip() and not line.strip().startswith('-')]
        
        if len(paragraphs) >= 3:
            # First paragraph as introduction
            structured = f"{paragraphs[0]}\n\n"
            
            # Add headings to remaining paragraphs
            structured += f"## {question}\n\n"
            structured += "\n\n".join(paragraphs[1:3]) if len(paragraphs) > 1 else ""
            
            if len(paragraphs) > 3:
                structured += f"\n\n### Ek Bilgiler\n\n"
                structured += "\n\n".join(paragraphs[3:])
            
            return structured
    
    # If no structure at all, add basic structure
    if not has_headings:
        # Add introduction and heading
        first_para = lines[0] if lines else text[:150]
        structured = f"{first_para}\n\n## {question}\n\n"
        if len(lines) > 1:
            structured += "\n\n".join(lines[1:])
        else:
            structured += text[len(first_para):].strip()
        return structured
    
    # Convert long paragraphs into lists if appropriate
    if not has_lists:
        # Check if text has enumeration patterns
        if re.search(r'\d+[.)]\s+', text):
            # Convert numbered list format
            text = re.sub(r'(\d+)[.)]\s+', r'- ', text)
    
    return text


def _ensure_minimum_quality(
    text: str,
    question: str,
    intent: QuestionIntent
) -> str:
    """
    Ensure answer meets minimum quality standards.
    """
    # Minimum length check
    min_lengths = {
        QuestionIntent.MATH: 50,
        QuestionIntent.EXPLANATION: 150,
        QuestionIntent.HISTORY: 100,
        QuestionIntent.COMPARISON: 120,
        QuestionIntent.EXAMPLE: 80,
        QuestionIntent.GENERAL: 100,
    }
    
    min_length = min_lengths.get(intent, 100)
    
    if len(text.strip()) < min_length:
        # Answer too short, add context
        if intent == QuestionIntent.EXPLANATION:
            text += f"\n\nBu konu hakkında daha fazla bilgi edinmek isterseniz, sorularınızı detaylandırabilirsiniz."
        elif intent == QuestionIntent.GENERAL:
            text += f"\n\nBu konuyla ilgili başka sorularınız varsa, çekinmeden sorabilirsiniz."
    
    # Ensure answer doesn't end abruptly
    if not text.strip().endswith(('.', '!', '?', ':', ';')):
        # Add proper ending
        text = text.rstrip() + "."
    
    return text


def _final_formatting(text: str) -> str:
    """
    Final formatting: spacing, line breaks, consistency.
    """
    # Ensure proper spacing between sections
    text = re.sub(r'(^#{1,3}\s+[^\n]+)\n([^\n#])', r'\1\n\n\2', text, flags=re.MULTILINE)
    
    # Ensure spacing around math blocks
    text = re.sub(r'([^\n])\n(\$\$)', r'\1\n\n\2', text)
    text = re.sub(r'(\$\$[^\$]+\$\$)\n([^\n$])', r'\1\n\n\2', text)
    
    # Ensure headers are at line start (no leading spaces)
    lines = text.split('\n')
    processed_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('##') or stripped.startswith('###') or stripped.startswith('**Adım') or stripped.startswith('**Sonuç'):
            processed_lines.append(stripped)
        else:
            processed_lines.append(line)
    
    text = '\n'.join(processed_lines)
    
    # Collapse excessive blank lines (max 2 consecutive)
    text = re.sub(r'\n{4,}', '\n\n\n', text)
    
    # Add spacing at beginning (for frontend rendering)
    if not text.startswith('\n\n\n'):
        text = '\n\n\n' + text.lstrip()
    
    # Ensure spacing at end
    if not text.endswith('\n\n'):
        text = text.rstrip() + '\n\n'
    
    return text

