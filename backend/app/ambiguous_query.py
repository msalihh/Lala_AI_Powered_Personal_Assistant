"""
Ambiguous query detection and clarification question generation.
"""
import re
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def is_ambiguous_query(query: str, has_strong_rag_sources: bool = False, top_rag_score: float = 0.0) -> Tuple[bool, Optional[str]]:
    """
    Detect if query is ambiguous and needs clarification.
    
    Args:
        query: User query text
        has_strong_rag_sources: Whether there are strong RAG sources (high score)
        top_rag_score: Top RAG source score (if available)
        
    Returns:
        Tuple of (is_ambiguous: bool, clarification_question: Optional[str])
        If ambiguous and no strong sources, returns clarification question.
        If ambiguous but has strong sources, returns (False, None) to proceed with answer.
    """
    query_lower = query.lower().strip()
    query_words = query_lower.split()
    
    # Very short queries (1-2 words) are likely ambiguous
    if len(query_words) <= 2:
        # Check if it's a clear question word
        clear_question_words = ["nedir", "ne", "nasıl", "neden", "kim", "nerede", "ne zaman", "kaç"]
        if any(word in query_lower for word in clear_question_words):
            # Clear question word, not ambiguous
            return False, None
        
        # Check for common ambiguous patterns
        ambiguous_patterns = [
            r'^bunlar\s*ne$',
            r'^bu\s*ne$',
            r'^anlamadım$',
            r'^\?\?+$',
            r'^ne\s*\?+$',
            r'^hmm$',
            r'^tamam$',
        ]
        
        if any(re.match(pattern, query_lower) for pattern in ambiguous_patterns):
            # Ambiguous, but if we have strong RAG sources, proceed anyway
            if has_strong_rag_sources and top_rag_score >= 0.4:
                logger.info(f"Ambiguous query but strong RAG sources (score={top_rag_score:.3f}), proceeding")
                return False, None
            
            # Generate clarification question
            clarification = "Hangi konudan bahsediyorsunuz? Daha spesifik bir soru sorabilir misiniz?"
            return True, clarification
    
    # Check for very vague patterns
    vague_patterns = [
        r'^bunlar\s+ne',
        r'^bu\s+ne',
        r'^anlamadım',
        r'^\?\?+',
        r'^ne\s*\?+',
    ]
    
    if any(re.search(pattern, query_lower) for pattern in vague_patterns):
        # Ambiguous, but if we have strong RAG sources, proceed anyway
        if has_strong_rag_sources and top_rag_score >= 0.4:
            logger.info(f"Ambiguous query but strong RAG sources (score={top_rag_score:.3f}), proceeding")
            return False, None
        
        # Generate clarification question
        clarification = "Hangi konudan bahsediyorsunuz? Daha spesifik bir soru sorabilir misiniz?"
        return True, clarification
    
    return False, None

