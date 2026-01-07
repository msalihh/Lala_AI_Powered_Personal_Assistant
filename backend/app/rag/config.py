"""
RAG configuration and settings.
"""
import os
from typing import Optional
from dataclasses import dataclass


@dataclass
class EmbeddingConfig:
    """Embedding configuration."""
    model: str = os.getenv("EMBEDDING_MODEL", "openai/text-embedding-3-small")
    batch_size: int = int(os.getenv("EMBEDDING_BATCH_SIZE", "10"))
    max_retries: int = int(os.getenv("EMBEDDING_MAX_RETRIES", "3"))
    retry_backoff: float = float(os.getenv("EMBEDDING_RETRY_BACKOFF", "1.5"))
    timeout: float = float(os.getenv("EMBEDDING_TIMEOUT", "10.0"))
    enable_deduplication: bool = os.getenv("EMBEDDING_DEDUP", "true").lower() == "true"


@dataclass
class ChunkingConfig:
    """Chunking configuration."""
    default_chunk_words: int = int(os.getenv("CHUNK_WORDS", "300"))
    default_overlap_words: int = int(os.getenv("CHUNK_OVERLAP", "50"))
    min_chunk_words: int = int(os.getenv("CHUNK_MIN_WORDS", "50"))
    max_chunk_words: int = int(os.getenv("CHUNK_MAX_WORDS", "500"))
    enable_adaptive: bool = os.getenv("CHUNK_ADAPTIVE", "true").lower() == "true"
    enable_semantic_boundaries: bool = os.getenv("CHUNK_SEMANTIC", "true").lower() == "true"


@dataclass
class RAGConfig:
    """RAG retrieval configuration."""
    top_k: int = int(os.getenv("RAG_TOP_K", "4"))
    score_threshold: float = float(os.getenv("RAG_SCORE_THRESHOLD", "0.25"))
    min_score_threshold: float = float(os.getenv("RAG_MIN_SCORE_THRESHOLD", "0.15"))
    enable_query_cache: bool = os.getenv("RAG_QUERY_CACHE", "true").lower() == "true"
    query_cache_ttl: int = int(os.getenv("RAG_QUERY_CACHE_TTL", "3600"))  # 1 hour
    enable_score_normalization: bool = os.getenv("RAG_NORMALIZE_SCORES", "true").lower() == "true"
    # Priority document search thresholds
    priority_high_threshold: float = float(os.getenv("RAG_PRIORITY_HIGH_THRESHOLD", "0.35"))
    priority_low_threshold: float = float(os.getenv("RAG_PRIORITY_LOW_THRESHOLD", "0.15"))
    priority_min_hits: int = int(os.getenv("RAG_PRIORITY_MIN_HITS", "1"))
    # Relevance gate thresholds
    # BALANCED: Show sources more easily
    relevance_high_threshold: float = float(os.getenv("RAG_RELEVANCE_HIGH_THRESHOLD", "0.45"))
    relevance_low_threshold: float = float(os.getenv("RAG_RELEVANCE_LOW_THRESHOLD", "0.30"))
    relevance_min_hits: int = int(os.getenv("RAG_RELEVANCE_MIN_HITS", "2"))
    relevance_gap_limit: float = float(os.getenv("RAG_RELEVANCE_GAP_LIMIT", "0.15"))
    # Evidence gate thresholds
    # PERMISSIVE: High priority on showing documents
    evidence_high: float = float(os.getenv("RAG_EVIDENCE_HIGH", "0.40"))
    evidence_low: float = float(os.getenv("RAG_EVIDENCE_LOW", "0.25"))
    evidence_min_overlap: int = int(os.getenv("RAG_EVIDENCE_MIN_OVERLAP", "0"))  # Allow even if no term overlap (vector only)
    evidence_min_hits: int = int(os.getenv("RAG_EVIDENCE_MIN_HITS", "1"))
    evidence_generic_query_min_len: int = int(os.getenv("RAG_EVIDENCE_GENERIC_QUERY_MIN_LEN", "3"))
    evidence_allow_sources_for_general_queries: bool = os.getenv("RAG_EVIDENCE_ALLOW_GENERAL", "true").lower() == "true"


@dataclass
class ContextConfig:
    """Context building configuration."""
    max_tokens: int = int(os.getenv("CONTEXT_MAX_TOKENS", "2000"))
    max_chunks: int = int(os.getenv("CONTEXT_MAX_CHUNKS", "10"))
    enable_budget_management: bool = os.getenv("CONTEXT_BUDGET_MGMT", "true").lower() == "true"
    system_prompt_tokens: int = int(os.getenv("SYSTEM_PROMPT_TOKENS", "500"))
    chat_history_tokens: int = int(os.getenv("CHAT_HISTORY_TOKENS", "1000"))


@dataclass
class IntentConfig:
    """Intent classification configuration."""
    enable_intent_aware: bool = os.getenv("RAG_INTENT_AWARE", "true").lower() == "true"
    qa_rag_priority: float = float(os.getenv("INTENT_QA_PRIORITY", "0.8"))
    summarize_rag_required: bool = os.getenv("INTENT_SUMMARIZE_REQUIRED", "true").lower() == "true"
    extract_rag_required: bool = os.getenv("INTENT_EXTRACT_REQUIRED", "true").lower() == "true"
    general_chat_rag_threshold: float = float(os.getenv("INTENT_GENERAL_THRESHOLD", "0.5"))


# Global config instances
embedding_config = EmbeddingConfig()
chunking_config = ChunkingConfig()
rag_config = RAGConfig()
context_config = ContextConfig()
intent_config = IntentConfig()

