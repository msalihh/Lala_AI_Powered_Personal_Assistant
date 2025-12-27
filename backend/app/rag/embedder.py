"""
Text embedding using OpenRouter API (OpenAI-compatible).
Production-grade with deduplication, retry logic, and metadata tracking.
"""
import os
import httpx
import hashlib
import asyncio
from typing import List, Optional, Dict, Tuple
import logging
from datetime import datetime

from app.rag.config import embedding_config

logger = logging.getLogger(__name__)

# OpenRouter API Configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "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")
OPENROUTER_EMBEDDING_URL = "https://openrouter.ai/api/v1/embeddings"

# In-memory cache for deduplication (production'da Redis kullanılabilir)
_embedding_cache: Dict[str, Tuple[List[float], datetime]] = {}


def _compute_text_hash(text: str) -> str:
    """Compute SHA256 hash of normalized text for deduplication."""
    normalized = text.strip().lower()
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


async def embed_text(
    text: str,
    metadata: Optional[Dict] = None,
    use_cache: bool = True
) -> Optional[List[float]]:
    """
    Generate embedding for a single text chunk using OpenRouter.
    Supports deduplication, retry with backoff, and metadata tracking.
    
    Args:
        text: Text to embed
        metadata: Optional metadata dict (document_id, chunk_index, etc.)
        use_cache: Whether to use deduplication cache
        
    Returns:
        Embedding vector (list of floats) or None if failed
    """
    if not text or not text.strip():
        logger.warning("Empty text provided for embedding")
        return None
    
    # Deduplication: Check cache first
    if use_cache and embedding_config.enable_deduplication:
        text_hash = _compute_text_hash(text)
        if text_hash in _embedding_cache:
            cached_embedding, cached_time = _embedding_cache[text_hash]
            logger.debug(f"Embedding cache hit: hash={text_hash[:8]}...")
            return cached_embedding
    
    # Retry logic with exponential backoff
    last_exception = None
    for attempt in range(embedding_config.max_retries):
        try:
            async with httpx.AsyncClient(timeout=embedding_config.timeout) as client:
                response = await client.post(
                    OPENROUTER_EMBEDDING_URL,
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "http://localhost:8000",
                        "X-Title": "RAG Indexing",
                    },
                    json={
                        "model": embedding_config.model,
                        "input": text.strip()
                    }
                )
                
                response.raise_for_status()
                data = response.json()
                
                # Extract embedding from response
                if "data" in data and len(data["data"]) > 0:
                    embedding = data["data"][0].get("embedding")
                    if embedding:
                        # Cache the embedding
                        if use_cache and embedding_config.enable_deduplication:
                            text_hash = _compute_text_hash(text)
                            _embedding_cache[text_hash] = (embedding, datetime.utcnow())
                            logger.debug(f"Embedding cached: hash={text_hash[:8]}...")
                        
                        # Log with metadata if provided
                        if metadata:
                            logger.debug(
                                f"Embedding generated: doc_id={metadata.get('document_id', 'N/A')[:8]}... "
                                f"chunk_index={metadata.get('chunk_index', 'N/A')} "
                                f"text_len={len(text)}"
                            )
                        
                        return embedding
                    else:
                        logger.error("No embedding in OpenRouter response")
                        return None
                else:
                    logger.error(f"Unexpected OpenRouter response format: {data}")
                    return None
                    
        except httpx.TimeoutException as e:
            last_exception = e
            if attempt < embedding_config.max_retries - 1:
                wait_time = embedding_config.retry_backoff ** attempt
                logger.warning(
                    f"Timeout while embedding (attempt {attempt + 1}/{embedding_config.max_retries}), "
                    f"retrying in {wait_time:.1f}s..."
                )
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"Timeout while embedding text after {embedding_config.max_retries} attempts (length: {len(text)})")
                return None
        except httpx.HTTPStatusError as e:
            last_exception = e
            # Don't retry on 4xx errors (client errors)
            if 400 <= e.response.status_code < 500:
                logger.error(f"HTTP client error while embedding: {e.response.status_code} - {e.response.text}")
                return None
            # Retry on 5xx errors (server errors)
            if attempt < embedding_config.max_retries - 1:
                wait_time = embedding_config.retry_backoff ** attempt
                logger.warning(
                    f"HTTP server error while embedding (attempt {attempt + 1}/{embedding_config.max_retries}), "
                    f"retrying in {wait_time:.1f}s..."
                )
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"HTTP error while embedding after {embedding_config.max_retries} attempts: {e.response.status_code} - {e.response.text}")
                return None
        except Exception as e:
            last_exception = e
            if attempt < embedding_config.max_retries - 1:
                wait_time = embedding_config.retry_backoff ** attempt
                logger.warning(
                    f"Error embedding text (attempt {attempt + 1}/{embedding_config.max_retries}), "
                    f"retrying in {wait_time:.1f}s... Error: {str(e)}"
                )
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"Error embedding text after {embedding_config.max_retries} attempts: {str(e)}")
                return None
    
    return None


async def embed_chunks(chunks: List[dict]) -> List[dict]:
    """
    Embed multiple text chunks with batch processing and metadata tracking.
    
    Args:
        chunks: List of chunk dictionaries with:
            - text: chunk text
            - chunk_index: chunk index
            - document_id: document ID (optional, for metadata)
            - section_number: section/page number (optional)
            - token_count: estimated token count (optional)
        
    Returns:
        List of chunks with added 'embedding' key (None if embedding failed)
    """
    embedded_chunks = []
    total_chunks = len(chunks)
    cached_count = 0
    failed_count = 0
    
    # Process in batches
    for batch_start in range(0, total_chunks, embedding_config.batch_size):
        batch_end = min(batch_start + embedding_config.batch_size, total_chunks)
        batch = chunks[batch_start:batch_end]
        
        # Embed batch concurrently
        tasks = []
        for chunk in batch:
            text = chunk.get("text", "")
            metadata = {
                "document_id": chunk.get("document_id"),
                "chunk_index": chunk.get("chunk_index"),
                "section_number": chunk.get("section_number"),
                "token_count": chunk.get("token_count", len(text.split()) * 1.3)
            }
            tasks.append(embed_text(text, metadata=metadata))
        
        # Wait for batch to complete
        embeddings = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        for i, (chunk, embedding) in enumerate(zip(batch, embeddings)):
            chunk_with_embedding = chunk.copy()
            
            if isinstance(embedding, Exception):
                logger.warning(f"Embedding failed for chunk {chunk.get('chunk_index', '?')}: {str(embedding)}")
                chunk_with_embedding["embedding"] = None
                failed_count += 1
            elif embedding is None:
                chunk_with_embedding["embedding"] = None
                failed_count += 1
            else:
                chunk_with_embedding["embedding"] = embedding
                # Check if this was cached (approximate by checking if text hash exists)
                text_hash = _compute_text_hash(chunk.get("text", ""))
                if text_hash in _embedding_cache:
                    cached_count += 1
            
            embedded_chunks.append(chunk_with_embedding)
        
        # Small delay between batches to avoid rate limiting
        if batch_end < total_chunks:
            await asyncio.sleep(0.1)
    
    logger.info(
        f"Embedded {total_chunks} chunks: "
        f"success={total_chunks - failed_count}, "
        f"failed={failed_count}, "
        f"cached={cached_count}"
    )
    
    return embedded_chunks

