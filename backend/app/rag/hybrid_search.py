"""
Hybrid search combining vector similarity and BM25 keyword search.
Inspired by professional AI tools (Perplexity, ChatGPT) that use hybrid retrieval.
"""
import re
import logging
from typing import List, Dict, Optional, Tuple
from collections import Counter
import math

logger = logging.getLogger(__name__)


def bm25_score(
    query_terms: List[str],
    document_terms: List[str],
    k1: float = 1.5,
    b: float = 0.75,
    avg_doc_length: float = 100.0
) -> float:
    """
    Calculate BM25 score for a document given a query.
    
    BM25 is a ranking function used to estimate the relevance of documents
    to a given search query. It's better than TF-IDF for keyword matching.
    
    Args:
        query_terms: List of query terms (keywords)
        document_terms: List of document terms (words in document)
        k1: Term frequency saturation parameter (default 1.5)
        b: Length normalization parameter (default 0.75)
        avg_doc_length: Average document length (for normalization)
        
    Returns:
        BM25 score (higher = more relevant)
    """
    if not query_terms or not document_terms:
        return 0.0
    
    doc_length = len(document_terms)
    doc_term_counts = Counter(document_terms)
    query_term_counts = Counter(query_terms)
    
    score = 0.0
    for term in query_term_counts:
        if term not in doc_term_counts:
            continue
        
        # Term frequency in document
        tf = doc_term_counts[term]
        
        # Inverse document frequency (simplified - assumes all terms are equally common)
        # In production, you'd calculate IDF from corpus statistics
        idf = math.log((1.0 + 1.0) / (1.0 + 1.0)) + 1.0  # Simplified IDF
        
        # BM25 formula
        numerator = idf * tf * (k1 + 1)
        denominator = tf + k1 * (1 - b + b * (doc_length / avg_doc_length))
        score += numerator / denominator
    
    return score


def tokenize_text(text: str, language: str = "tr") -> List[str]:
    """
    Tokenize text into words (simple word splitting).
    For production, use proper NLP tokenizers (spaCy, NLTK, etc.)
    
    Args:
        text: Input text
        language: Language code (for future language-specific tokenization)
        
    Returns:
        List of lowercase tokens (words)
    """
    # Simple tokenization: lowercase, split on whitespace and punctuation
    text_lower = text.lower()
    # Remove punctuation but keep Turkish characters
    text_clean = re.sub(r'[^\w\sçğıöşüÇĞIİÖŞÜ]', ' ', text_lower)
    tokens = text_clean.split()
    # Filter out very short tokens (likely noise)
    tokens = [t for t in tokens if len(t) > 2]
    return tokens


def hybrid_search(
    query: str,
    chunks: List[dict],
    vector_scores: Optional[List[float]] = None,
    hybrid_weight: float = 0.7  # 0.7 vector + 0.3 BM25
) -> List[dict]:
    """
    Combine vector similarity scores with BM25 keyword scores.
    
    Professional AI tools use hybrid search because:
    - Vector search: Good for semantic similarity
    - BM25: Good for exact keyword matching
    
    Args:
        query: User query text
        chunks: List of chunks with 'text' field
        vector_scores: Optional pre-computed vector similarity scores
        hybrid_weight: Weight for vector scores (1-hybrid_weight for BM25)
        
    Returns:
        List of chunks with combined 'hybrid_score' field, sorted by score
    """
    if not chunks:
        return []
    
    # Tokenize query
    query_terms = tokenize_text(query)
    if not query_terms:
        # No keywords - return vector scores only
        if vector_scores:
            for i, chunk in enumerate(chunks):
                chunk["hybrid_score"] = vector_scores[i] if i < len(vector_scores) else chunk.get("score", 0.0)
            return sorted(chunks, key=lambda x: x.get("hybrid_score", 0.0), reverse=True)
        return chunks
    
    # Calculate average document length for BM25 normalization
    doc_lengths = [len(tokenize_text(chunk.get("text", ""))) for chunk in chunks]
    avg_doc_length = sum(doc_lengths) / len(doc_lengths) if doc_lengths else 100.0
    
    # Calculate BM25 scores
    bm25_scores = []
    for chunk in chunks:
        chunk_text = chunk.get("text", "")
        chunk_terms = tokenize_text(chunk_text)
        bm25 = bm25_score(query_terms, chunk_terms, avg_doc_length=avg_doc_length)
        bm25_scores.append(bm25)
    
    # Normalize BM25 scores to 0-1 range (for combination with vector scores)
    max_bm25 = max(bm25_scores) if bm25_scores else 1.0
    if max_bm25 > 0:
        bm25_scores = [s / max_bm25 for s in bm25_scores]
    
    # Get vector scores (from chunks or provided)
    if vector_scores:
        vec_scores = vector_scores
    else:
        vec_scores = [chunk.get("score", 0.0) for chunk in chunks]
    
    # Normalize vector scores to 0-1 range (if not already)
    max_vec = max(vec_scores) if vec_scores else 1.0
    if max_vec > 0:
        vec_scores = [s / max_vec for s in vec_scores]
    
    # Combine scores: hybrid_score = weight * vector + (1-weight) * BM25
    for i, chunk in enumerate(chunks):
        vector_score = vec_scores[i] if i < len(vec_scores) else 0.0
        bm25_score_norm = bm25_scores[i] if i < len(bm25_scores) else 0.0
        
        hybrid_score = (hybrid_weight * vector_score) + ((1 - hybrid_weight) * bm25_score_norm)
        chunk["hybrid_score"] = hybrid_score
        chunk["vector_score"] = vector_score
        chunk["bm25_score"] = bm25_score_norm
    
    # Sort by hybrid score (descending)
    sorted_chunks = sorted(chunks, key=lambda x: x.get("hybrid_score", 0.0), reverse=True)
    
    logger.debug(
        f"Hybrid search: query='{query[:50]}...', chunks={len(chunks)}, "
        f"avg_vector={sum(vec_scores)/len(vec_scores) if vec_scores else 0:.3f}, "
        f"avg_bm25={sum(bm25_scores)/len(bm25_scores) if bm25_scores else 0:.3f}"
    )
    
    return sorted_chunks

