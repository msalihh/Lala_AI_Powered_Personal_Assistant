"""
Intent classification for RAG decision making.
Includes doc-grounded detection to prevent "doküman yok" spam.
"""
import re
import logging
from typing import Dict, Literal, Optional, List

from app.rag.config import intent_config

logger = logging.getLogger(__name__)

IntentType = Literal["qa", "summarize", "extract", "general_chat", "general_assistant"]


def classify_intent(
    query: str, 
    mode: str = "qa",
    document_ids: Optional[List[str]] = None
) -> Dict[str, any]:
    """
    Classify query intent to determine RAG priority.
    Also detects if query is doc-grounded (explicitly about documents).
    
    Args:
        query: User query text
        mode: Explicit mode from request ("qa", "summarize", "extract")
        document_ids: Optional list of document IDs (if provided, query is more likely doc-grounded)
        
    Returns:
        Dict with:
        - intent: Intent type
        - rag_priority: RAG priority (0.0-1.0)
        - rag_required: Whether RAG is required
        - confidence: Classification confidence
        - doc_grounded: True if query explicitly references documents or needs docIds content
        - doc_grounded_reason: Reason for doc_grounded classification
    """
    # Detect doc-grounded query
    doc_grounded_result = _detect_doc_grounded(query, document_ids)
    doc_grounded = doc_grounded_result["doc_grounded"]
    doc_grounded_reason = doc_grounded_result["reason"]
    
    if not intent_config.enable_intent_aware:
        # Default behavior: use mode
        return {
            "intent": mode,
            "rag_priority": 0.7,
            "rag_required": False,
            "confidence": 0.5,
            "doc_grounded": doc_grounded,
            "doc_grounded_reason": doc_grounded_reason
        }
    
    query_lower = query.lower().strip()
    
    # Explicit mode takes precedence
    if mode in ["summarize", "extract"]:
        return {
            "intent": mode,
            "rag_priority": 1.0,
            "rag_required": True,
            "confidence": 1.0
        }
    
    # Pattern-based classification
    # Summarize patterns
    summarize_patterns = [
        r'\b(özet|özetle|özetini|özeti|hakkında|ne diyor|ne anlatıyor)\b',
        r'\b(summarize|summary|overview|what does it say)\b'
    ]
    
    # Extract patterns
    extract_patterns = [
        r'\b(çıkar|çıkarım|bul|göster|listele|hangi|nerede|kim|ne zaman)\b',
        r'\b(extract|find|show|list|which|where|who|when)\b'
    ]
    
    # Analysis/Review patterns (should be treated as doc-grounded)
    analysis_patterns = [
        r'\b(incele|analiz|değerlendir|karşılaştır|inceleme|analiz et|değerlendirme)\b',
        r'\b(analyze|review|examine|evaluate|compare|analysis)\b'
    ]
    
    # QA patterns
    qa_patterns = [
        r'\b(nedir|ne|nasıl|neden|niçin|açıkla|anlat)\b',
        r'\b(what|how|why|explain|tell me)\b',
        r'\?',  # Question mark
    ]
    
    # General chat patterns
    general_patterns = [
        r'\b(merhaba|selam|teşekkür|sağol|görüşürüz)\b',
        r'\b(hello|hi|thanks|thank you|bye)\b'
    ]
    
    # Check patterns
    summarize_score = sum(1 for pattern in summarize_patterns if re.search(pattern, query_lower))
    extract_score = sum(1 for pattern in extract_patterns if re.search(pattern, query_lower))
    analysis_score = sum(1 for pattern in analysis_patterns if re.search(pattern, query_lower))
    qa_score = sum(1 for pattern in qa_patterns if re.search(pattern, query_lower))
    general_score = sum(1 for pattern in general_patterns if re.search(pattern, query_lower))
    
    # Determine intent
    # Analysis patterns should be treated as extract/qa with high priority
    scores = {
        "summarize": summarize_score,
        "extract": extract_score + analysis_score,  # Analysis counts as extract
        "qa": qa_score + (analysis_score * 0.5),  # Analysis also counts as QA
        "general_chat": general_score,
        "general_assistant": 0.1  # Base score for general assistant
    }
    
    max_score = max(scores.values())
    if max_score <= 0.1:
        # Default to general_assistant if no patterns match strongly
        intent = "general_assistant"
        confidence = 0.3
    else:
        intent = max(scores, key=scores.get)
        confidence = min(1.0, max_score / 2.0)  # Normalize confidence
    
    # Determine RAG priority and requirement
    if intent == "summarize":
        rag_priority = 1.0
        rag_required = intent_config.summarize_rag_required
    elif intent == "extract":
        rag_priority = 1.0
        rag_required = intent_config.extract_rag_required
    elif intent == "qa":
        rag_priority = intent_config.qa_rag_priority
        rag_required = False
    elif intent == "general_assistant":
        rag_priority = 0.6  # Decent priority but not blocking
        rag_required = False
    else:  # general_chat
        rag_priority = intent_config.general_chat_rag_threshold
        rag_required = False
    
    logger.debug(
        f"Intent classified: query='{query[:50]}...', "
        f"intent={intent}, priority={rag_priority}, required={rag_required}, confidence={confidence:.2f}, "
        f"doc_grounded={doc_grounded}, reason={doc_grounded_reason}"
    )
    
    return {
        "intent": intent,
        "rag_priority": rag_priority,
        "rag_required": rag_required,
        "confidence": confidence,
        "doc_grounded": doc_grounded,
        "doc_grounded_reason": doc_grounded_reason
    }


def _detect_doc_grounded(
    query: str,
    document_ids: Optional[List[str]] = None
) -> Dict[str, any]:
    """
    Detect if query is doc-grounded (explicitly about documents).
    
    Args:
        query: User query text
        document_ids: Optional list of document IDs
        
    Returns:
        Dict with:
        - doc_grounded: True if query is about documents
        - reason: Reason string for debugging
    """
    query_lower = query.lower().strip()
    
    # Strong indicators that query is about documents
    doc_reference_patterns = [
        r'\b(bu\s+belgede|bu\s+dokümanda|bu\s+dosyada|şu\s+belgede|şu\s+dokümanda|şu\s+dosyada)\b',
        r'\b(bu\s+pdf|bu\s+dosya|yüklediğim|yüklediğin|upload|document|file)\b',
        r'\b(belgede|dokümanda|dosyada|pdf|document)\s+(ne|hangi|nedir|var|yok)\b',
        r'\b(incele|analiz|değerlendir|karşılaştır|inceleme|analiz et|değerlendirme)\b',  # Analysis commands are doc-grounded
        r'\b(analyze|review|examine|evaluate|compare|analysis)\b',
    ]
    
    # Check for document references
    has_doc_reference = any(re.search(pattern, query_lower, re.IGNORECASE) for pattern in doc_reference_patterns)
    
    # If document_ids are explicitly provided, query is likely doc-grounded
    has_explicit_docs = document_ids is not None and len(document_ids) > 0
    
    # Determine doc_grounded
    if has_doc_reference:
        return {
            "doc_grounded": True,
            "reason": "query_references_document"
        }
    elif has_explicit_docs:
        # If user explicitly selected documents, query is doc-grounded
        # UNLESS query is clearly general (greeting, etc.)
        general_patterns = [
            r'\b(merhaba|selam|teşekkür|sağol|hello|hi|thanks)\b',
        ]
        is_general = any(re.search(pattern, query_lower) for pattern in general_patterns)
        
        if is_general:
            return {
                "doc_grounded": False,
                "reason": "general_chat_despite_docs"
            }
        else:
            return {
                "doc_grounded": True,
                "reason": "explicit_document_ids"
            }
    else:
        # No document references and no explicit docs
        return {
            "doc_grounded": False,
            "reason": "no_document_reference"
        }

