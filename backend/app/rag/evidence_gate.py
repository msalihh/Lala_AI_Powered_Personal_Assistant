"""
Evidence-based source gating system.
Prevents irrelevant sources from being shown by using evidence scoring and query classification.
"""
import re
import logging
from typing import List, Dict, Optional, Literal
from dataclasses import dataclass

from app.rag.config import rag_config

logger = logging.getLogger(__name__)


@dataclass
class EvidenceMetrics:
    """Evidence scoring metrics for a hit."""
    vector_score: float  # Original vector similarity score (0-1)
    evidence_score: float  # Combined evidence score (0-1)
    term_overlap: int  # Number of query keywords found in hit
    has_number_match: bool  # Whether numbers/dates/codes match
    has_entity_match: bool  # Whether important entities match (filename/title)
    query_type: str  # Query classification: "chitchat", "definition", "general_math", "general_knowledge", "doc_intent", "qa"
    doc_intent: bool  # Whether query has document intent


@dataclass
class EvidenceDecision:
    """Final decision from evidence gate."""
    use_documents: bool  # Whether to use documents (show sources)
    sources: List[Dict]  # Filtered sources (only if use_documents=True)
    reason: str  # Decision reason for debugging
    evidence_metrics: Optional[EvidenceMetrics] = None  # Top hit metrics
    query_type: str = "qa"  # Query classification
    doc_intent: bool = False  # Document intent flag


def classify_query(query: str, selected_doc_ids: Optional[List[str]] = None) -> Dict[str, any]:
    """
    Classify query type and detect document intent.
    
    Args:
        query: User query text
        selected_doc_ids: Optional list of selected document IDs
        
    Returns:
        Dict with:
        - query_type: "chitchat", "definition", "general_math", "general_knowledge", "doc_intent", "qa"
        - doc_intent: bool (whether query has document intent)
        - keywords: List of important keywords extracted from query
    """
    query_lower = query.lower().strip()
    query_words = query_lower.split()
    
    # Extract keywords (non-stopwords, length > 2)
    stopwords = {
        "nedir", "ne", "nasıl", "neden", "niçin", "hangi", "nerede", "kim", "ne zaman",
        "bu", "şu", "o", "bir", "ve", "ile", "için", "gibi", "kadar", "daha", "en",
        "var", "yok", "olur", "oldu", "olacak", "ise", "ki", "de", "da", "mi", "mı",
        "what", "how", "why", "which", "where", "who", "when", "is", "are", "was", "were",
        "the", "a", "an", "this", "that", "for", "with", "from", "to", "in", "on", "at"
    }
    keywords = [w for w in query_words if len(w) > 2 and w not in stopwords]
    
    # Detect document intent signals
    doc_intent_patterns = [
        r'\b(bu\s+belgede|bu\s+dokümanda|bu\s+dosyada|şu\s+belgede|şu\s+dokümanda|şu\s+dosyada)\b',
        r'\b(belgede|dokümanda|dosyada|pdf|document|file)\s+(ne|hangi|nedir|var|yok)\b',
        r'\b(transkript|dekont|fatura|rapor|belge|doküman|dosya)\w*\b',
        r'\b(yüklediğim|yüklediğin|upload|yükleme)\b',
        r'\b(incele|analiz|değerlendir|karşılaştır|inceleme|analiz et|değerlendirme)\b',
        r'\b(analyze|review|examine|evaluate|compare|analysis)\b',
    ]
    has_doc_intent_signal = any(re.search(pattern, query_lower, re.IGNORECASE) for pattern in doc_intent_patterns)
    
    # Detect email intent signals (CRITICAL: Treat email queries as document intent)
    # BUT: Exclude general knowledge questions like "mail nedir?"
    email_lookup_patterns = [
        r'\b(mailleri|e-postaları|e-postalar|mailler|mail|e-posta)\s+(bul|ara|listele|göster|getir|incele|analiz|özet|özetle)\b',
        r'\b(bul|ara|listele|göster|getir|incele|analiz|özet|özetle)\s+(.*)\s+(mailleri|e-postaları|e-postalar|mailler|mail|e-posta)\b',
        r'\b(.*)\s+(ile|hakkında|konulu|konusunda)\s+(mailleri|e-postaları|e-postalar|mailler|mail|e-posta)\b',
        r'\b(en\s+son|son|güncel|yeni)\s+(mail|e-posta|mesaj)\b',
        r'\b(find|search|list|show|get|analyze|summarize)\s+(.*)\s+(email|emails|mail|mails)\b',
    ]
    
    # Exclude general knowledge questions (e.g., "mail nedir?", "e-posta ne demek?")
    email_general_knowledge_patterns = [
        r'^(mail|e-posta|email)\s+(nedir|ne\s+demek|ne|anlamı|tanımı)\s*\?*$',
        r'^(what|what is|what are)\s+(mail|e-posta|email)\s*\?*$',
        r'\b(mail|e-posta|email)\s+(nedir|ne\s+demek|anlamı|tanımı)\b',
    ]
    
    # Check if query is a general knowledge question about email
    is_email_general_knowledge = any(re.search(pattern, query_lower, re.IGNORECASE) for pattern in email_general_knowledge_patterns)
    
    # Only treat as email intent if it's a lookup query, not a general knowledge question
    has_email_intent_signal = (
        any(re.search(pattern, query_lower, re.IGNORECASE) for pattern in email_lookup_patterns)
        and not is_email_general_knowledge
    )
    
    has_explicit_docs = selected_doc_ids is not None and len(selected_doc_ids) > 0
    
    # CRITICAL: Email queries should be treated as document intent (require RAG)
    doc_intent = has_doc_intent_signal or has_email_intent_signal or has_explicit_docs
    
    # Classify query type
    # Chitchat patterns
    chitchat_patterns = [
        r'\b(merhaba|selam|teşekkür|sağol|görüşürüz|iyi günler|iyi akşamlar)\b',
        r'\b(hello|hi|thanks|thank you|bye|goodbye|good day|good evening)\b',
        r'^(selam|merhaba|hi|hello)$',
    ]
    is_chitchat = any(re.search(pattern, query_lower) for pattern in chitchat_patterns)
    
    # Definition patterns (general knowledge questions)
    definition_patterns = [
        r'^(.*)\s+nedir\s*\?*$',  # "X nedir?"
        r'^(what|what is|what are)\s+(.*)\?*$',  # "What is X?"
        r'\b(nedir|ne demek|anlamı|tanımı)\b',
    ]
    is_definition = any(re.search(pattern, query_lower) for pattern in definition_patterns)
    
    # General math/knowledge patterns (very short, generic)
    is_very_short = len(query_words) <= 2
    is_generic_math = bool(re.search(r'\b(kare|üçgen|daire|sayı|matematik|math)\b', query_lower)) and not doc_intent
    
    # Determine query_type
    if is_chitchat:
        query_type = "chitchat"
    elif is_definition and not doc_intent:
        query_type = "definition"
    elif is_generic_math:
        query_type = "general_math"
    elif is_very_short and not doc_intent:
        query_type = "general_knowledge"
    elif doc_intent:
        query_type = "doc_intent"
    else:
        query_type = "qa"
    
    # Determine if this is specifically an email lookup (not general knowledge)
    email_lookup_patterns = [
        r'\b(mailleri|e-postaları|e-postalar|mailler|mail|e-posta)\s+(bul|ara|listele|göster|getir|incele|analiz|özet|özetle)\b',
        r'\b(bul|ara|listele|göster|getir|incele|analiz|özet|özetle)\s+(.*)\s+(mailleri|e-postaları|e-postalar|mailler|mail|e-posta)\b',
        r'\b(.*)\s+(ile|hakkında|konulu|konusunda)\s+(mailleri|e-postaları|e-postalar|mailler|mail|e-posta)\b',
        r'\b(en\s+son|son|güncel|yeni)\s+(mail|e-posta|mesaj)\b',
    ]
    email_general_knowledge_patterns = [
        r'^(mail|e-posta|email)\s+(nedir|ne\s+demek|ne|anlamı|tanımı)\s*\?*$',
        r'^(what|what is|what are)\s+(mail|e-posta|email)\s*\?*$',
    ]
    is_email_general_knowledge = any(re.search(pattern, query_lower, re.IGNORECASE) for pattern in email_general_knowledge_patterns)
    is_email_lookup = (
        any(re.search(pattern, query_lower, re.IGNORECASE) for pattern in email_lookup_patterns)
        and not is_email_general_knowledge
    )
    
    return {
        "query_type": query_type,
        "doc_intent": doc_intent,
        "keywords": keywords,
        "is_very_short": is_very_short,
        "is_email_lookup": is_email_lookup,
    }


def score_hit_evidence(query: str, hit: Dict, query_keywords: List[str]) -> EvidenceMetrics:
    """
    Score a single hit for evidence quality.
    
    Args:
        query: Original query text
        hit: Hit dictionary with: text, score, original_filename, document_id
        query_keywords: Extracted keywords from query
        
    Returns:
        EvidenceMetrics with evidence_score and components
    """
    vector_score = hit.get("score", 0.0)
    hit_text = hit.get("text", "").lower()
    filename = hit.get("original_filename", "").lower()
    
    # Base evidence score = vector similarity (normalized 0-1)
    evidence_score = vector_score
    
    # Term overlap bonus: Check how many query keywords appear in hit text
    term_overlap = 0
    for keyword in query_keywords:
        if keyword in hit_text:
            term_overlap += 1
        # Also check in filename
        if keyword in filename:
            term_overlap += 0.5  # Partial bonus for filename match
    
    # Term overlap bonus: +0.1 per keyword match (max +0.3)
    term_overlap_bonus = min(0.3, term_overlap * 0.1)
    evidence_score += term_overlap_bonus
    
    # Number/date/code match bonus
    has_number_match = False
    # Extract numbers from query
    query_numbers = re.findall(r'\d+[.,]?\d*', query)
    if query_numbers:
        # Check if any number appears in hit text
        for num in query_numbers:
            # Normalize number (remove commas, handle decimals)
            num_clean = num.replace(',', '').replace('.', '')
            if num_clean in hit_text.replace(',', '').replace('.', ''):
                has_number_match = True
                break
        if has_number_match:
            evidence_score += 0.15  # Strong signal for number match
    
    # Entity match bonus: Check if important keywords appear in filename
    has_entity_match = False
    if query_keywords:
        # Check if any keyword appears in filename (strong signal)
        for keyword in query_keywords[:3]:  # Top 3 keywords
            if keyword in filename:
                has_entity_match = True
                break
        if has_entity_match:
            evidence_score += 0.1  # Bonus for filename match
    
    # Penalties
    # Generic query penalty (already handled in query classification, but apply small penalty here too)
    query_lower = query.lower().strip()
    is_generic = len(query_lower.split()) <= 3 and not any(
        kw in query_lower for kw in ["transkript", "dekont", "fatura", "belge", "doküman", "dosya"]
    )
    if is_generic:
        evidence_score -= 0.1
    
    # Low spread penalty: If top1 and top2 scores are very close, might be random similarity
    # (This is handled at decision level, not here)
    
    # Clamp evidence score to [0, 1]
    evidence_score = max(0.0, min(1.0, evidence_score))
    
    return EvidenceMetrics(
        vector_score=vector_score,
        evidence_score=evidence_score,
        term_overlap=int(term_overlap),
        has_number_match=has_number_match,
        has_entity_match=has_entity_match,
        query_type="",  # Will be set at decision level
        doc_intent=False  # Will be set at decision level
    )


def decide_use_sources(
    query: str,
    hits: List[Dict],
    selected_doc_ids: Optional[List[str]] = None,
    config: Optional[Dict] = None
) -> EvidenceDecision:
    """
    Main evidence gate decision function.
    Determines whether to show sources based on evidence scoring and query classification.
    
    Args:
        query: User query text
        hits: List of retrieved hits (from query_chunks)
        selected_doc_ids: Optional list of selected document IDs
        config: Optional config override dict
        
    Returns:
        EvidenceDecision with use_documents flag and filtered sources
    """
    # Use config defaults or override
    evidence_high = config.get("evidence_high", rag_config.evidence_high) if config else rag_config.evidence_high
    evidence_low = config.get("evidence_low", rag_config.evidence_low) if config else rag_config.evidence_low
    min_overlap = config.get("min_overlap", rag_config.evidence_min_overlap) if config else rag_config.evidence_min_overlap
    min_hits = config.get("min_hits", rag_config.evidence_min_hits) if config else rag_config.evidence_min_hits
    generic_query_min_len = config.get("generic_query_min_len", rag_config.evidence_generic_query_min_len) if config else rag_config.evidence_generic_query_min_len
    allow_sources_for_general_queries = config.get("allow_sources_for_general_queries", rag_config.evidence_allow_sources_for_general_queries) if config else rag_config.evidence_allow_sources_for_general_queries
    
    # Classify query
    query_classification = classify_query(query, selected_doc_ids)
    query_type = query_classification["query_type"]
    doc_intent = query_classification["doc_intent"]
    keywords = query_classification["keywords"]
    is_very_short = query_classification["is_very_short"]
    is_email_lookup = query_classification.get("is_email_lookup", False)
    
    # If no hits, no sources
    if not hits:
        return EvidenceDecision(
            use_documents=False,
            sources=[],
            reason="NO_HITS",
            query_type=query_type,
            doc_intent=doc_intent
        )
    
    # Score all hits
    scored_hits = []
    for hit in hits:
        metrics = score_hit_evidence(query, hit, keywords)
        # Set query_type and doc_intent in metrics
        metrics.query_type = query_type
        metrics.doc_intent = doc_intent
        scored_hits.append({
            "hit": hit,
            "metrics": metrics
        })
    
    # Sort by evidence_score (descending)
    scored_hits.sort(key=lambda x: x["metrics"].evidence_score, reverse=True)
    
    # Get top metrics
    top_metrics = scored_hits[0]["metrics"] if scored_hits else None
    top_evidence = top_metrics.evidence_score if top_metrics else 0.0
    avg_evidence = sum(s["metrics"].evidence_score for s in scored_hits) / len(scored_hits) if scored_hits else 0.0
    hit_count = len(scored_hits)
    top_term_overlap = top_metrics.term_overlap if top_metrics else 0
    
    # RULE 1: General knowledge queries - NO SOURCES (unless explicitly allowed)
    # STRICT: General queries should NEVER show sources unless explicitly document-related
    if query_type in ["chitchat", "definition", "general_math", "general_knowledge"]:
        if not allow_sources_for_general_queries and not doc_intent:
            return EvidenceDecision(
                use_documents=False,
                sources=[],
                reason=f"GENERAL_QUERY_NO_SOURCES(query_type={query_type}, doc_intent={doc_intent})",
                evidence_metrics=top_metrics,
                query_type=query_type,
                doc_intent=doc_intent
            )
    
    # ADDITIONAL RULE: Very short queries without doc_intent should not show sources
    # This prevents irrelevant sources for queries like "nedir", "nasıl", etc.
    if is_very_short and not doc_intent and query_type != "qa":
        return EvidenceDecision(
            use_documents=False,
            sources=[],
            reason=f"VERY_SHORT_QUERY_NO_SOURCES(query_len={len(query.split())}, doc_intent={doc_intent})",
            evidence_metrics=top_metrics,
            query_type=query_type,
            doc_intent=doc_intent
        )
    
    # RULE 2: Document intent queries - require evidence
    # CRITICAL: For email/document lookup queries, empty results should return "not found"
    if doc_intent:
        
        # CRITICAL GUARD: For email/document lookup queries, if no relevant hits found, reject
        # This prevents showing irrelevant sources when user asks for specific data
        if is_email_lookup and top_evidence < evidence_low:
            # Email lookup with no relevant results - reject to force "not found" response
            return EvidenceDecision(
                use_documents=False,
                sources=[],
                reason=f"EMAIL_LOOKUP_NO_RELEVANT_HITS(top_evidence={top_evidence:.3f}<{evidence_low}, user_data_required=True)",
                evidence_metrics=top_metrics,
                query_type=query_type,
                doc_intent=doc_intent
            )
        
        # High evidence threshold
        if top_evidence >= evidence_high:
            # Accept: High evidence
            filtered_hits = []
            for s in scored_hits:
                if s["metrics"].evidence_score >= evidence_low:
                    hit = s["hit"].copy()
                    hit["evidence_score"] = s["metrics"].evidence_score  # Add evidence_score to hit
                    filtered_hits.append(hit)
            return EvidenceDecision(
                use_documents=True,
                sources=filtered_hits,
                reason=f"DOC_INTENT_HIGH_EVIDENCE(top_evidence={top_evidence:.3f}>={evidence_high})",
                evidence_metrics=top_metrics,
                query_type=query_type,
                doc_intent=doc_intent
            )
        # Moderate evidence with multiple hits and term overlap
        elif hit_count >= min_hits and avg_evidence >= evidence_low and top_term_overlap >= min_overlap:
            # Accept: Multiple hits with moderate evidence
            filtered_hits = []
            for s in scored_hits:
                if s["metrics"].evidence_score >= evidence_low:
                    hit = s["hit"].copy()
                    hit["evidence_score"] = s["metrics"].evidence_score  # Add evidence_score to hit
                    filtered_hits.append(hit)
            return EvidenceDecision(
                use_documents=True,
                sources=filtered_hits,
                reason=f"DOC_INTENT_MODERATE_EVIDENCE(hits={hit_count}>={min_hits}, avg={avg_evidence:.3f}>={evidence_low}, overlap={top_term_overlap}>={min_overlap})",
                evidence_metrics=top_metrics,
                query_type=query_type,
                doc_intent=doc_intent
            )
        else:
            # Reject: Low evidence
            # CRITICAL: For email/document lookup, this means "not found"
            return EvidenceDecision(
                use_documents=False,
                sources=[],
                reason=f"DOC_INTENT_LOW_EVIDENCE(top_evidence={top_evidence:.3f}<{evidence_high}, hits={hit_count}<{min_hits} OR avg={avg_evidence:.3f}<{evidence_low} OR overlap={top_term_overlap}<{min_overlap})",
                evidence_metrics=top_metrics,
                query_type=query_type,
                doc_intent=doc_intent
            )
    
    # RULE 3: Regular QA queries - require strong evidence
    # Only show sources if evidence is very strong
    if top_evidence >= evidence_high:
        filtered_hits = []
        for s in scored_hits:
            if s["metrics"].evidence_score >= evidence_low:
                hit = s["hit"].copy()
                hit["evidence_score"] = s["metrics"].evidence_score  # Add evidence_score to hit
                filtered_hits.append(hit)
        return EvidenceDecision(
            use_documents=True,
            sources=filtered_hits,
            reason=f"QA_HIGH_EVIDENCE(top_evidence={top_evidence:.3f}>={evidence_high})",
            evidence_metrics=top_metrics,
            query_type=query_type,
            doc_intent=doc_intent
        )
    else:
        # Reject: Not strong enough evidence
        return EvidenceDecision(
            use_documents=False,
            sources=[],
            reason=f"QA_LOW_EVIDENCE(top_evidence={top_evidence:.3f}<{evidence_high})",
            evidence_metrics=top_metrics,
            query_type=query_type,
            doc_intent=doc_intent
        )

