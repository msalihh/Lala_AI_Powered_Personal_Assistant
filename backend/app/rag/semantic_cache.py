"""
Semantic caching for RAG queries.
Caches frequently asked questions and their results to improve performance.
Inspired by professional AI tools (Perplexity, ChatGPT).
"""
import hashlib
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from app.rag.embedder import embed_text
from app.utils import estimate_tokens

logger = logging.getLogger(__name__)

# In-memory cache (production'da Redis kullanılabilir)
_semantic_cache: Dict[str, Dict] = {}
_cache_ttl_seconds = 3600  # 1 hour TTL


def _compute_semantic_hash(query_embedding: List[float]) -> str:
    """Compute hash from query embedding for semantic similarity."""
    # Use first 10 dimensions for hash (faster, still unique enough)
    hash_input = ",".join([f"{v:.4f}" for v in query_embedding[:10]])
    return hashlib.sha256(hash_input.encode()).hexdigest()


async def get_cached_results(
    query: str,
    query_embedding: Optional[List[float]] = None,
    similarity_threshold: float = 0.95
) -> Optional[Tuple[List[dict], float]]:
    """
    Get cached results if similar query was asked recently.
    
    Args:
        query: User query text
        query_embedding: Optional pre-computed embedding (for performance)
        similarity_threshold: Minimum similarity to consider cache hit (0.95 = very similar)
        
    Returns:
        Tuple of (cached_chunks, similarity_score) or None if no cache hit
    """
    if not query_embedding:
        query_embedding = await embed_text(query)
        if not query_embedding:
            return None
    
    cache_hash = _compute_semantic_hash(query_embedding)
    
    # Check cache
    if cache_hash in _semantic_cache:
        cached_entry = _semantic_cache[cache_hash]
        cache_age = (datetime.utcnow() - cached_entry["cached_at"]).total_seconds()
        
        if cache_age < _cache_ttl_seconds:
            # Check similarity (cosine similarity with cached embedding)
            cached_embedding = cached_entry["query_embedding"]
            similarity = _cosine_similarity(query_embedding, cached_embedding)
            
            if similarity >= similarity_threshold:
                logger.info(
                    f"Semantic cache HIT: similarity={similarity:.3f}, "
                    f"age={cache_age:.1f}s, chunks={len(cached_entry['chunks'])}"
                )
                return (cached_entry["chunks"], similarity)
            else:
                logger.debug(
                    f"Semantic cache MISS: similarity={similarity:.3f} < {similarity_threshold}"
                )
    
    return None


def cache_results(
    query: str,
    query_embedding: List[float],
    chunks: List[dict]
):
    """
    Cache query results for future similar queries.
    
    Args:
        query: User query text
        query_embedding: Query embedding vector
        chunks: Retrieved chunks to cache
    """
    cache_hash = _compute_semantic_hash(query_embedding)
    
    _semantic_cache[cache_hash] = {
        "query": query,
        "query_embedding": query_embedding,
        "chunks": chunks,
        "cached_at": datetime.utcnow()
    }
    
    # Cleanup old entries (keep last 1000)
    if len(_semantic_cache) > 1000:
        # Remove oldest entries
        sorted_entries = sorted(
            _semantic_cache.items(),
            key=lambda x: x[1]["cached_at"]
        )
        for old_hash, _ in sorted_entries[:len(_semantic_cache) - 1000]:
            del _semantic_cache[old_hash]
    
    logger.debug(f"Semantic cache stored: hash={cache_hash[:8]}..., chunks={len(chunks)}")


def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if len(vec1) != len(vec2):
        return 0.0
    
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    magnitude1 = sum(a * a for a in vec1) ** 0.5
    magnitude2 = sum(b * b for b in vec2) ** 0.5
    
    if magnitude1 == 0 or magnitude2 == 0:
        return 0.0
    
    return dot_product / (magnitude1 * magnitude2)

