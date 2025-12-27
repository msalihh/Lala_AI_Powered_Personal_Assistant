"""
ChromaDB vector store operations for RAG indexing.
Production-grade with score normalization, query caching, and metadata filtering.
"""
import os
import chromadb
from chromadb.config import Settings
from typing import List, Optional, Dict, Tuple
import logging
import hashlib
from datetime import datetime, timedelta

from app.rag.config import rag_config

logger = logging.getLogger(__name__)

# ChromaDB persistence directory
CHROMA_PERSIST_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "chroma")
COLLECTION_NAME = "documents"

# Global ChromaDB client and collection
_client: Optional[chromadb.ClientAPI] = None
_collection: Optional[chromadb.Collection] = None

# Query cache for deduplication (production'da Redis kullanılabilir)
_query_cache: Dict[str, Tuple[List[dict], datetime]] = {}


def get_client() -> chromadb.ClientAPI:
    """
    Get or create ChromaDB client (singleton).
    
    Returns:
        ChromaDB client instance
    """
    global _client
    if _client is None:
        # Ensure persistence directory exists
        os.makedirs(CHROMA_PERSIST_DIR, exist_ok=True)
        
        _client = chromadb.PersistentClient(
            path=CHROMA_PERSIST_DIR,
            settings=Settings(anonymized_telemetry=False)
        )
        logger.info(f"ChromaDB client initialized at {CHROMA_PERSIST_DIR}")
    
    return _client


def get_collection() -> chromadb.Collection:
    """
    Get or create ChromaDB collection (singleton).
    
    Returns:
        ChromaDB collection instance
    """
    global _collection
    if _collection is None:
        client = get_client()
        
        # Get existing collection or create new one
        try:
            _collection = client.get_collection(name=COLLECTION_NAME)
            logger.info(f"Using existing ChromaDB collection: {COLLECTION_NAME}")
        except Exception:
            # Collection doesn't exist, create it
            _collection = client.create_collection(
                name=COLLECTION_NAME,
                metadata={"description": "Document chunks for RAG"}
            )
            logger.info(f"Created new ChromaDB collection: {COLLECTION_NAME}")
    
    return _collection


def index_document_chunks(
    document_id: str,
    chunks: List[dict],
    original_filename: str,
    was_truncated: bool
) -> dict:
    """
    Index document chunks into ChromaDB.
    
    Args:
        document_id: MongoDB document ID
        chunks: List of chunk dictionaries with:
            - text: chunk text
            - chunk_index: chunk index
            - embedding: embedding vector (can be None)
        original_filename: Original filename
        was_truncated: Whether document text was truncated
        
    Returns:
        Dictionary with indexing statistics:
        - total_chunks: total number of chunks
        - indexed_chunks: number of successfully indexed chunks
        - failed_chunks: number of chunks that failed embedding
    """
    collection = get_collection()
    
    total_chunks = len(chunks)
    indexed_chunks = 0
    failed_chunks = 0
    
    # Prepare data for batch insertion
    ids = []
    embeddings = []
    documents = []
    metadatas = []
    
    for chunk in chunks:
        chunk_id = f"{document_id}_chunk_{chunk['chunk_index']}"
        embedding = chunk.get("embedding")
        
        # Skip chunks without embeddings
        if embedding is None:
            failed_chunks += 1
            logger.warning(f"Skipping chunk {chunk['chunk_index']} for document {document_id} (no embedding)")
            continue
        
        ids.append(chunk_id)
        embeddings.append(embedding)
        documents.append(chunk["text"])
        # Enhanced metadata
        metadata = {
            "document_id": document_id,
            "original_filename": original_filename,
            "chunk_index": chunk["chunk_index"],
            "truncated": str(was_truncated),
            "text_length": len(chunk["text"]),
            "token_count": chunk.get("token_count", int(len(chunk["text"].split()) * 1.3)),
            "word_count": chunk.get("word_count", len(chunk["text"].split()))
        }
        
        # Add optional metadata if available
        if "text_type" in chunk:
            metadata["text_type"] = chunk["text_type"]
        if "section_number" in chunk:
            metadata["section_number"] = chunk["section_number"]
        
        metadatas.append(metadata)
        indexed_chunks += 1
    
    # Batch insert into ChromaDB
    if ids:
        try:
            collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas
            )
            logger.info(f"Indexed {indexed_chunks} chunks for document {document_id}")
        except Exception as e:
            logger.error(f"Error indexing chunks for document {document_id}: {str(e)}")
            # Return partial success
            return {
                "total_chunks": total_chunks,
                "indexed_chunks": 0,
                "failed_chunks": total_chunks
            }
    
    return {
        "total_chunks": total_chunks,
        "indexed_chunks": indexed_chunks,
        "failed_chunks": failed_chunks
    }


def delete_document_chunks(document_id: str) -> int:
    """
    Delete all chunks for a document from ChromaDB.
    
    Args:
        document_id: MongoDB document ID
        
    Returns:
        Number of chunks deleted
    """
    collection = get_collection()
    
    try:
        # Query to find all chunks for this document
        results = collection.get(
            where={"document_id": document_id}
        )
        
        if results["ids"]:
            collection.delete(ids=results["ids"])
            deleted_count = len(results["ids"])
            logger.info(f"Deleted {deleted_count} chunks for document {document_id}")
            return deleted_count
        else:
            return 0
    except Exception as e:
        logger.error(f"Error deleting chunks for document {document_id}: {str(e)}")
        return 0


def _normalize_scores(chunks: List[dict]) -> List[dict]:
    """
    Normalize similarity scores using min-max normalization.
    Ensures scores are in [0, 1] range and properly distributed.
    """
    if not chunks or not rag_config.enable_score_normalization:
        return chunks
    
    scores = [chunk["score"] for chunk in chunks]
    if not scores:
        return chunks
    
    min_score = min(scores)
    max_score = max(scores)
    
    # If all scores are the same, return as-is
    if max_score == min_score:
        return chunks
    
    # Normalize to [0, 1] range
    normalized_chunks = []
    for chunk in chunks:
        normalized_score = (chunk["score"] - min_score) / (max_score - min_score)
        chunk_copy = chunk.copy()
        chunk_copy["score"] = normalized_score
        chunk_copy["score_raw"] = chunk["score"]  # Keep original score
        normalized_chunks.append(chunk_copy)
    
    return normalized_chunks


def _compute_query_hash(query_embedding: List[float], user_document_ids: List[str]) -> str:
    """Compute hash of query for caching."""
    # Use first few dimensions of embedding + doc IDs for hash
    embedding_str = ",".join([f"{x:.4f}" for x in query_embedding[:10]])
    doc_ids_str = ",".join(sorted(user_document_ids))
    combined = f"{embedding_str}|{doc_ids_str}"
    return hashlib.sha256(combined.encode('utf-8')).hexdigest()


def query_chunks(
    query_embedding: List[float],
    user_document_ids: List[str],
    top_k: Optional[int] = None,
    min_score: Optional[float] = None,
    metadata_filters: Optional[Dict] = None,
    use_cache: bool = True
) -> List[dict]:
    """
    Query ChromaDB for similar chunks with advanced features.
    
    Args:
        query_embedding: Query text embedding vector
        user_document_ids: List of user's document IDs to filter by
        top_k: Number of top results to return (uses config default if None)
        min_score: Minimum similarity score threshold (uses config default if None)
        metadata_filters: Additional metadata filters (folder_id, tags, mime_type, etc.)
        use_cache: Whether to use query cache
        
    Returns:
        List of chunk dictionaries with:
        - document_id
        - original_filename
        - chunk_index
        - text: chunk text
        - distance: similarity distance (lower is better)
        - score: normalized similarity score (0-1, higher is better)
        - score_raw: raw similarity score before normalization
    """
    collection = get_collection()
    
    # Use config defaults if not provided
    query_top_k = top_k or rag_config.top_k
    query_min_score = min_score or rag_config.min_score_threshold
    
    try:
        # Check query cache
        if use_cache and rag_config.enable_query_cache:
            query_hash = _compute_query_hash(query_embedding, user_document_ids)
            if query_hash in _query_cache:
                cached_results, cached_time = _query_cache[query_hash]
                cache_age = (datetime.utcnow() - cached_time).total_seconds()
                
                if cache_age < rag_config.query_cache_ttl:
                    logger.debug(f"Query cache hit: hash={query_hash[:8]}..., age={cache_age:.1f}s")
                    return cached_results
                else:
                    # Cache expired, remove it
                    del _query_cache[query_hash]
        
        # Query with filter for user's documents only
        if not user_document_ids:
            logger.warning("query_chunks: No user_document_ids provided")
            return []
        
        # Build where filter
        # ChromaDB requires at least 2 items for $or, so handle single document_id case
        if len(user_document_ids) == 1:
            where_filter = {"document_id": user_document_ids[0]}
        else:
            where_filter = {
                "$or": [{"document_id": doc_id} for doc_id in user_document_ids]
            }
        
        # Add metadata filters if provided
        if metadata_filters:
            for key, value in metadata_filters.items():
                if key in ["folder_id", "tags", "mime_type", "is_chat_scoped"]:
                    # If we have a simple filter, combine with $and
                    if len(user_document_ids) == 1:
                        where_filter = {"$and": [where_filter, {key: value}]}
                    else:
                        where_filter[key] = value
        
        logger.debug(
            f"query_chunks: Querying with filter for {len(user_document_ids)} document_ids, "
            f"top_k={query_top_k}, min_score={query_min_score}"
        )
        
        # Query ChromaDB (request more results for filtering)
        query_results = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(query_top_k * 2, 50),  # Request more for filtering
            where=where_filter
        )
        
        chunks = []
        if query_results["ids"] and len(query_results["ids"]) > 0:
            for i in range(len(query_results["ids"][0])):
                chunk_id = query_results["ids"][0][i]
                distance = query_results["distances"][0][i] if "distances" in query_results else 1.0
                metadata = query_results["metadatas"][0][i] if "metadatas" in query_results else {}
                document = query_results["documents"][0][i] if "documents" in query_results else ""
                
                # Convert distance to score (0-1, higher is better)
                # ChromaDB uses cosine distance, so score = 1 - distance
                score = max(0.0, min(1.0, 1.0 - distance))
                
                # Apply minimum score threshold
                if score < query_min_score:
                    continue
                
                chunks.append({
                    "document_id": metadata.get("document_id", ""),
                    "original_filename": metadata.get("original_filename", ""),
                    "chunk_index": metadata.get("chunk_index", 0),
                    "text": document,
                    "distance": distance,
                    "score": score,
                    "truncated": metadata.get("truncated", "False") == "True",
                    "text_type": metadata.get("text_type"),
                    "section_number": metadata.get("section_number"),
                    "token_count": metadata.get("token_count", len(document.split()) * 1.3)
                })
        
        # Normalize scores
        chunks = _normalize_scores(chunks)
        
        # Sort by score (descending) and limit to top_k
        chunks = sorted(chunks, key=lambda x: x["score"], reverse=True)[:query_top_k]
        
        # Cache results
        if use_cache and rag_config.enable_query_cache:
            query_hash = _compute_query_hash(query_embedding, user_document_ids)
            _query_cache[query_hash] = (chunks, datetime.utcnow())
            logger.debug(f"Query cached: hash={query_hash[:8]}...")
        
        logger.debug(
            f"query_chunks: Returned {len(chunks)} chunks from query "
            f"(requested top_k={query_top_k}, filtered by {len(user_document_ids)} document_ids, "
            f"min_score={query_min_score})"
        )
        
        return chunks
    except Exception as e:
        logger.error(f"Error querying chunks: {str(e)}", exc_info=True)
        return []

