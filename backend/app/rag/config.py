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
    score_threshold: float = float(os.getenv("RAG_SCORE_THRESHOLD", "0.35"))
    min_score_threshold: float = float(os.getenv("RAG_MIN_SCORE_THRESHOLD", "0.25"))  # Minimum score for override cases (increased from 0.15 to prevent irrelevant sources)
    enable_query_cache: bool = os.getenv("RAG_QUERY_CACHE", "true").lower() == "true"
    query_cache_ttl: int = int(os.getenv("RAG_QUERY_CACHE_TTL", "3600"))  # 1 hour
    enable_score_normalization: bool = os.getenv("RAG_NORMALIZE_SCORES", "true").lower() == "true"
    # Priority document search thresholds
    priority_high_threshold: float = float(os.getenv("RAG_PRIORITY_HIGH_THRESHOLD", "0.4"))  # Top score >= this → use priority only
    priority_low_threshold: float = float(os.getenv("RAG_PRIORITY_LOW_THRESHOLD", "0.2"))  # Avg score >= this → use priority
    priority_min_hits: int = int(os.getenv("RAG_PRIORITY_MIN_HITS", "2"))  # Min chunks needed for priority to be sufficient
    # Relevance gate thresholds (for preventing irrelevant sources)
    # STRICT: Only show sources when truly relevant
    relevance_high_threshold: float = float(os.getenv("RAG_RELEVANCE_HIGH_THRESHOLD", "0.55"))  # Hard gate: top1_score >= this → RAG ON (increased from 0.45)
    relevance_low_threshold: float = float(os.getenv("RAG_RELEVANCE_LOW_THRESHOLD", "0.40"))  # Soft gate: avg_score >= this (increased from 0.30)
    relevance_min_hits: int = int(os.getenv("RAG_RELEVANCE_MIN_HITS", "3"))  # Soft gate: min chunks needed (increased from 2)
    relevance_gap_limit: float = float(os.getenv("RAG_RELEVANCE_GAP_LIMIT", "0.10"))  # Soft gate: max gap between top1 and top2 scores (decreased from 0.15)
    # Evidence gate thresholds (NEW: Evidence-based source gating)
    # BALANCED: Show sources when document content is actually used
    # Lowered from strict 0.75/0.60 to balanced 0.50/0.35 for better source display
    evidence_high: float = float(os.getenv("RAG_EVIDENCE_HIGH", "0.50"))  # High evidence threshold (was 0.75 - too strict)
    evidence_low: float = float(os.getenv("RAG_EVIDENCE_LOW", "0.35"))  # Low evidence threshold (was 0.60 - too strict)
    evidence_min_overlap: int = int(os.getenv("RAG_EVIDENCE_MIN_OVERLAP", "1"))  # Minimum term overlap for moderate evidence
    evidence_min_hits: int = int(os.getenv("RAG_EVIDENCE_MIN_HITS", "2"))  # Minimum hits for moderate evidence
    evidence_generic_query_min_len: int = int(os.getenv("RAG_EVIDENCE_GENERIC_QUERY_MIN_LEN", "6"))  # Min words for non-generic query
    evidence_allow_sources_for_general_queries: bool = os.getenv("RAG_EVIDENCE_ALLOW_GENERAL", "false").lower() == "true"  # Allow sources for general queries (default: false)


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

