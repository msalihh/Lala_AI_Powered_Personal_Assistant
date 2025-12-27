"""
Answer validation and hallucination detection for RAG responses.
"""
import re
import logging
from typing import Dict, Optional, Tuple, List

logger = logging.getLogger(__name__)


def validate_answer_against_context(
    answer: str,
    rag_context: str,
    sources: List[Dict]
) -> Dict[str, any]:
    """
    Validate answer against RAG context to detect potential hallucinations.
    
    Args:
        answer: Generated answer text
        rag_context: RAG context that was used
        sources: List of source chunks
        
    Returns:
        Dict with:
        - is_valid: Whether answer appears valid
        - confidence: Confidence score (0.0-1.0)
        - issues: List of detected issues
        - suggestions: Suggestions for improvement
    """
    if not rag_context or not sources:
        # No RAG context - can't validate
        return {
            "is_valid": True,  # Assume valid if no context
            "confidence": 0.5,
            "issues": [],
            "suggestions": []
        }
    
    issues = []
    suggestions = []
    
    # Check 1: Answer mentions specific facts not in context
    # Extract key facts from answer (numbers, dates, names, etc.)
    answer_facts = _extract_facts(answer)
    context_facts = _extract_facts(rag_context)
    
    # Find facts in answer that are not in context
    missing_facts = []
    for fact in answer_facts:
        if fact not in context_facts:
            # Check if similar fact exists (fuzzy match)
            if not _find_similar_fact(fact, context_facts):
                missing_facts.append(fact)
    
    if missing_facts:
        issues.append(f"Answer contains {len(missing_facts)} facts not found in context")
        suggestions.append("Review answer for potential hallucinations")
    
    # Check 2: Answer makes strong claims without source references
    strong_claim_patterns = [
        r'\b(kesinlikle|mutlaka|her zaman|asla|hiçbir zaman)\b',
        r'\b(definitely|always|never|absolutely|certainly)\b'
    ]
    
    strong_claims = []
    for pattern in strong_claim_patterns:
        matches = re.finditer(pattern, answer, re.IGNORECASE)
        for match in matches:
            # Check if nearby text has source reference
            start = max(0, match.start() - 50)
            end = min(len(answer), match.end() + 50)
            nearby_text = answer[start:end]
            if not re.search(r'\[Kaynak|doküman|belge', nearby_text, re.IGNORECASE):
                strong_claims.append(match.group())
    
    if strong_claims:
        issues.append(f"Answer contains {len(strong_claims)} strong claims without source references")
        suggestions.append("Add source references for strong claims")
    
    # Check 3: Mathematical expressions format
    math_issues = _validate_math_format(answer)
    if math_issues:
        issues.extend(math_issues)
        suggestions.append("Review mathematical expressions for LaTeX format")
    
    # Calculate confidence
    confidence = 1.0 - (len(issues) * 0.2)
    confidence = max(0.0, min(1.0, confidence))
    
    is_valid = len(issues) == 0 or confidence >= 0.6
    
    return {
        "is_valid": is_valid,
        "confidence": confidence,
        "issues": issues,
        "suggestions": suggestions,
        "missing_facts_count": len(missing_facts)
    }


def _extract_facts(text: str) -> List[str]:
    """Extract key facts from text (numbers, dates, names, etc.)."""
    facts = []
    
    # Extract numbers
    numbers = re.findall(r'\b\d+[.,]?\d*\b', text)
    facts.extend(numbers)
    
    # Extract dates
    dates = re.findall(r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b', text)
    facts.extend(dates)
    
    # Extract capitalized words (potential names/entities)
    capitalized = re.findall(r'\b[A-Z][a-z]+\b', text)
    facts.extend(capitalized[:10])  # Limit to avoid too many
    
    return facts


def _find_similar_fact(fact: str, context_facts: List[str]) -> bool:
    """Check if similar fact exists in context (fuzzy match)."""
    # Simple similarity check - could be improved with fuzzy matching
    fact_lower = fact.lower()
    for ctx_fact in context_facts:
        if fact_lower in ctx_fact.lower() or ctx_fact.lower() in fact_lower:
            return True
    return False


def _validate_math_format(text: str) -> List[str]:
    """Validate mathematical expression format."""
    issues = []
    
    # Check for unicode math characters (should be in LaTeX)
    unicode_math = re.search(r'[√×÷±²³¹⁰⁴⁵⁶⁷⁸⁹₀₁₂₃₄₅₆₇₈₉]', text)
    if unicode_math:
        issues.append("Unicode math characters found - should use LaTeX")
    
    # Check for unmatched $ delimiters
    dollar_count = text.count('$') - text.count('$$') * 2
    if dollar_count % 2 != 0:
        issues.append("Unmatched $ delimiters in LaTeX")
    
    return issues


def generate_self_repair_prompt(
    original_answer: str,
    validation_result: Dict,
    rag_context: str
) -> Optional[str]:
    """
    Generate a self-repair prompt if validation found issues.
    
    Args:
        original_answer: Original answer text
        validation_result: Validation result from validate_answer_against_context
        rag_context: RAG context
        
    Returns:
        Self-repair prompt or None if no repair needed
    """
    if validation_result["is_valid"] or validation_result["confidence"] >= 0.7:
        return None
    
    issues = validation_result.get("issues", [])
    if not issues:
        return None
    
    prompt = f"""Aşağıdaki cevabı gözden geçir ve düzelt. Anlamı değiştirme, sadece formatı ve kaynak referanslarını düzelt.

Tespit edilen sorunlar:
{chr(10).join(f"- {issue}" for issue in issues)}

Orijinal cevap:
{original_answer}

RAG bağlamı (referans):
{rag_context[:1000]}...

Lütfen cevabı şu şekilde düzelt:
1. Kaynak referansları ekle: [Kaynak: Doküman adı, Bölüm X]
2. Matematik ifadelerini LaTeX formatına çevir ($...$ veya $$...$$)
3. Dokümanda olmayan iddiaları kaldır veya "dokümanlarda belirtilmemiş" olarak işaretle
4. Anlamı değiştirme, sadece format ve kaynakları düzelt

Düzeltilmiş cevap:"""
    
    return prompt

