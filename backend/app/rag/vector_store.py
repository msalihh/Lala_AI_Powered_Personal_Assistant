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
            # Collection doesn't exist, create it with cosine distance for similarity search
            _collection = client.create_collection(
                name=COLLECTION_NAME,
                metadata={"description": "Document chunks for RAG"},
                # Use cosine distance for similarity search (distance function)
                # ChromaDB default is L2, but cosine is better for text embeddings
            )
            logger.info(f"Created new ChromaDB collection: {COLLECTION_NAME}")
    
    return _collection


def index_document_chunks(
    document_id: str,
    chunks: List[dict],
    original_filename: str,
    was_truncated: bool,
    user_id: Optional[str] = None,
    source_type: str = "document",
    email_metadata: Optional[dict] = None,
    prompt_module: Optional[str] = None
) -> dict:
    """
    Index document chunks into ChromaDB.
    
    Args:
        document_id: MongoDB document ID or email ID
        chunks: List of chunk dictionaries with:
            - text: chunk text
            - chunk_index: chunk index
            - embedding: embedding vector (can be None)
        original_filename: Original filename or Subject
        was_truncated: Whether document text was truncated
        user_id: User ID for multi-tenant isolation (required for security)
        source_type: "document" or "email"
        email_metadata: Optional dict with subject, sender, date for emails
        
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
        # Enhanced metadata with user_id for multi-tenant isolation
        metadata = {
            "document_id": document_id,
            "original_filename": original_filename,
            "chunk_index": chunk["chunk_index"],
            "truncated": str(was_truncated),
            "text_length": len(chunk["text"]),
            "token_count": chunk.get("token_count", int(len(chunk["text"].split()) * 1.3)),
            "word_count": chunk.get("word_count", len(chunk["text"].split())),
            "source_type": source_type
        }
        
        # Add email metadata if provided
        if email_metadata:
            metadata.update({
                "subject": email_metadata.get("subject", ""),
                "sender": email_metadata.get("sender", ""),
                "date": email_metadata.get("date", "")
            })
            
        # Add user_id for multi-tenant isolation (CRITICAL for security)
        if user_id:
            metadata["user_id"] = user_id
        else:
            logger.warning(f"index_document_chunks: user_id not provided for document {document_id} - multi-tenant isolation may be compromised")
        
        # Add prompt_module for module isolation (CRITICAL for module separation)
        if prompt_module:
            metadata["prompt_module"] = prompt_module
        else:
            metadata["prompt_module"] = "none"  # Default to "none" if not provided
        
        # Add optional metadata if available (only if not None - ChromaDB doesn't accept None values)
        if "text_type" in chunk and chunk["text_type"] is not None:
            metadata["text_type"] = chunk["text_type"]
        if "section_number" in chunk and chunk["section_number"] is not None:
            metadata["section_number"] = chunk["section_number"]
        if "file_type" in chunk and chunk["file_type"] is not None:
            metadata["file_type"] = chunk["file_type"]  # pdf, docx, txt, image
        if "source" in chunk and chunk["source"] is not None:
            metadata["source"] = chunk["source"]  # image_ocr, image_caption, document_text
        
        # CRITICAL: Remove any None values from metadata (ChromaDB doesn't accept None)
        # Convert all values to strings/numbers/bools, remove None
        cleaned_metadata = {}
        for key, value in metadata.items():
            if value is not None:
                # Ensure all values are ChromaDB-compatible types
                if isinstance(value, (str, int, float, bool)):
                    cleaned_metadata[key] = value
                else:
                    # Convert to string if not a basic type
                    cleaned_metadata[key] = str(value)
            # Skip None values entirely
        
        metadatas.append(cleaned_metadata)
        indexed_chunks += 1
    
    # Batch insert into ChromaDB
    if ids:
        try:
            # CRITICAL LOG: Verify user_id is in metadata before indexing
            user_id_in_metadata = any(meta.get("user_id") for meta in metadatas)
            logger.info(
                f"[INDEX_VECTOR_STORE] doc_id={document_id} user_id={user_id} "
                f"total_chunks={total_chunks} indexed_chunks={indexed_chunks} "
                f"failed_chunks={failed_chunks} user_id_in_metadata={user_id_in_metadata} "
                f"metadata_count={len(metadatas)} ids_count={len(ids)}"
            )
            
            if not user_id:
                logger.error(
                    f"[INDEX_VECTOR_STORE] CRITICAL: user_id is None for doc_id={document_id}! "
                    f"Chunks will NOT be searchable with user_id filter."
                )
            
            collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas
            )
            logger.info(
                f"[INDEX_VECTOR_STORE_SUCCESS] doc_id={document_id} user_id={user_id} "
                f"indexed={indexed_chunks} chunks successfully written to ChromaDB"
            )
        except Exception as e:
            logger.error(
                f"[INDEX_VECTOR_STORE_ERROR] doc_id={document_id} user_id={user_id} "
                f"error={str(e)}", exc_info=True
            )
            # Return partial success
            return {
                "total_chunks": total_chunks,
                "indexed_chunks": 0,
                "failed_chunks": total_chunks
            }
    else:
        logger.warning(
            f"[INDEX_VECTOR_STORE] doc_id={document_id} user_id={user_id} "
            f"No chunks to index (ids list is empty)"
        )
    
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
    use_cache: bool = True,
    user_id: Optional[str] = None,
    priority_doc_ids: Optional[List[str]] = None
) -> List[dict]:
    """
    Query ChromaDB for similar chunks with advanced features.
    Multi-tenant safe: filters by user_id in metadata for security isolation.
    
    Args:
        query_embedding: Query text embedding vector
        user_document_ids: List of user's document IDs to filter by (optional if user_id provided)
        top_k: Number of top results to return (uses config default if None)
        min_score: Minimum similarity score threshold (uses config default if None)
        metadata_filters: Additional metadata filters (folder_id, tags, mime_type, etc.)
        use_cache: Whether to use query cache
        user_id: User ID for multi-tenant isolation (if provided, filters by user_id in metadata)
        priority_doc_ids: Optional list of priority document IDs (if provided, only search in these docs)
        
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
            query_hash = _compute_query_hash(query_embedding, user_document_ids if user_document_ids else [user_id] if user_id else [])
            if query_hash in _query_cache:
                cached_results, cached_time = _query_cache[query_hash]
                cache_age = (datetime.utcnow() - cached_time).total_seconds()
                
                if cache_age < rag_config.query_cache_ttl:
                    logger.debug(f"Query cache hit: hash={query_hash[:8]}..., age={cache_age:.1f}s")
                    return cached_results
                else:
                    # Cache expired, remove it
                    del _query_cache[query_hash]
        
        # Build where filter with multi-tenant isolation
        # Priority: user_id filter (most secure) > user_document_ids filter
        where_filter_parts = []
        
        # CRITICAL: Multi-tenant isolation - always filter by user_id if provided
        if user_id:
            where_filter_parts.append({"user_id": user_id})
            logger.debug(f"query_chunks: Using user_id filter for multi-tenant isolation: {user_id}")
        
        # PRIORITY: If priority_doc_ids provided, use only those (for priority search)
        # Otherwise, use user_document_ids (for global search)
        doc_ids_to_filter = priority_doc_ids if priority_doc_ids else user_document_ids
        
        # Also filter by document_ids if provided (for additional precision)
        if doc_ids_to_filter:
            if len(doc_ids_to_filter) == 1:
                where_filter_parts.append({"document_id": doc_ids_to_filter[0]})
            else:
                where_filter_parts.append({
                    "$or": [{"document_id": doc_id} for doc_id in doc_ids_to_filter]
                })
            # Log priority vs global search
            if priority_doc_ids:
                logger.debug(f"query_chunks: Using PRIORITY search with {len(priority_doc_ids)} documents")
            else:
                logger.debug(f"query_chunks: Using GLOBAL search with {len(user_document_ids)} documents")
        elif not user_id:
            # No user_id and no document_ids - cannot safely query
            logger.warning("query_chunks: No user_id or user_document_ids provided - cannot safely query")
            return []
        
        # Combine filters with $and
        if len(where_filter_parts) == 1:
            where_filter = where_filter_parts[0]
        else:
            where_filter = {"$and": where_filter_parts}
        
        # Add metadata filters if provided
        if metadata_filters:
            for key, value in metadata_filters.items():
                if key in ["folder_id", "tags", "mime_type", "is_chat_scoped"]:
                    # Combine with existing filter using $and
                    if "$and" in where_filter:
                        where_filter["$and"].append({key: value})
                    else:
                        where_filter = {"$and": [where_filter, {key: value}]}
        
        logger.info(
            f"[QUERY_CHUNKS_START] user_id={user_id} "
            f"priority_doc_ids_count={len(priority_doc_ids) if priority_doc_ids else 0} "
            f"user_document_ids_count={len(user_document_ids) if user_document_ids else 0} "
            f"top_k={query_top_k} min_score={query_min_score} where_filter={where_filter}"
        )
        
        # Query ChromaDB (request more results for filtering)
        query_results = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(query_top_k * 2, 50),  # Request more for filtering
            where=where_filter
        )
        
        # CRITICAL LOG: Log raw query results
        raw_results_count = len(query_results["ids"][0]) if query_results.get("ids") and len(query_results["ids"]) > 0 else 0
        logger.info(
            f"[QUERY_CHUNKS_RAW] user_id={user_id} raw_results_count={raw_results_count} "
            f"query_embedding_len={len(query_embedding)}"
        )
        
        chunks = []
        if query_results["ids"] and len(query_results["ids"]) > 0:
            for i in range(len(query_results["ids"][0])):
                chunk_id = query_results["ids"][0][i]
                distance = query_results["distances"][0][i] if "distances" in query_results else 1.0
                metadata = query_results["metadatas"][0][i] if "metadatas" in query_results else {}
                document = query_results["documents"][0][i] if "documents" in query_results else ""
                
                # CRITICAL: Check if user_id exists in metadata (for debugging old indexes)
                chunk_user_id = metadata.get("user_id")
                chunk_doc_id = metadata.get("document_id", "")
                
                # Convert distance to score (0-1, higher is better)
                # ChromaDB default uses L2 distance, but we want cosine similarity
                # L2 distance: lower is better, range 0 to infinity
                # Cosine distance: range 0-2 (0=identical, 2=opposite)
                # 
                # For L2: we need to normalize (1 / (1 + distance)) or use negative distance
                # For cosine: score = 1 - (distance / 2)
                #
                # Since ChromaDB default is L2, distance values can be large
                # We'll use a normalized approach: score = 1 / (1 + distance)
                # This gives us 0-1 range where 1 is perfect match (distance=0)
                
                # Alternative: If using cosine, distance is 0-2, so:
                # score = 1 - (distance / 2)
                
                # For now, let's use a more lenient conversion that works for both:
                # Normalize L2 distance: score = 1 / (1 + distance)
                # This works for any distance metric
                if distance <= 2.0:
                    # Likely cosine distance (0-2 range)
                    score = 1.0 - (distance / 2.0)
                else:
                    # Likely L2 distance (0 to infinity)
                    # Normalize: score = 1 / (1 + distance) gives us 0-1 range
                    score = 1.0 / (1.0 + distance)
                
                # Ensure score is in [0, 1] range
                score = max(0.0, min(1.0, score))
                
                # CRITICAL LOG: Log every chunk's score before filtering
                logger.info(
                    f"[QUERY_CHUNKS_SCORE] chunk_{i} doc_id={chunk_doc_id[:8]}... "
                    f"distance={distance:.4f} score={score:.4f} threshold={query_min_score} "
                    f"passes_threshold={score >= query_min_score} user_id_in_meta={chunk_user_id is not None}"
                )
                
                # Apply minimum score threshold
                if score < query_min_score:
                    logger.warning(
                        f"[QUERY_CHUNKS_FILTERED] chunk_{i} doc_id={chunk_doc_id[:8]}... "
                        f"score={score:.4f} < min_score={query_min_score} (FILTERED OUT) "
                        f"distance={distance:.4f}"
                    )
                    continue
                
                chunks.append({
                    "document_id": chunk_doc_id,
                    "original_filename": metadata.get("original_filename", ""),
                    "chunk_index": metadata.get("chunk_index", 0),
                    "text": document,
                    "distance": distance,
                    "score": score,
                    "truncated": metadata.get("truncated", "False") == "True",
                    "text_type": metadata.get("text_type"),
                    "section_number": metadata.get("section_number"),
                    "token_count": metadata.get("token_count", len(document.split()) * 1.3),
                    "user_id_in_metadata": chunk_user_id is not None,  # Debug flag
                    "source_type": metadata.get("source_type", "document"),
                    "subject": metadata.get("subject"),
                    "sender": metadata.get("sender"),
                    "date": metadata.get("date")
                })
                
                # Log first few chunks for debugging
                if i < 3:
                    logger.info(
                        f"[QUERY_CHUNKS_RESULT] chunk_{i} doc_id={chunk_doc_id[:8]}... "
                        f"score={score:.3f} distance={distance:.3f} user_id_in_meta={chunk_user_id is not None} "
                        f"user_id_match={chunk_user_id == user_id if chunk_user_id else False}"
                    )
        
        # Normalize scores
        chunks = _normalize_scores(chunks)
        
        # Sort by score (descending) and limit to top_k
        chunks = sorted(chunks, key=lambda x: x["score"], reverse=True)[:query_top_k]
        
        # CRITICAL LOG: Final results with top score
        top_score = chunks[0]["score"] if chunks else 0.0
        chunks_with_user_id = sum(1 for c in chunks if c.get("user_id_in_metadata", False))
        
        logger.info(
            f"[QUERY_CHUNKS_FINAL] user_id={user_id} returned_chunks={len(chunks)} "
            f"top_score={top_score:.3f} chunks_with_user_id_meta={chunks_with_user_id}/{len(chunks)} "
            f"threshold={query_min_score} threshold_met={top_score >= query_min_score if chunks else False}"
        )
        
        # Cache results
        if use_cache and rag_config.enable_query_cache:
            query_hash = _compute_query_hash(query_embedding, user_document_ids if user_document_ids else [user_id] if user_id else [])
            _query_cache[query_hash] = (chunks, datetime.utcnow())
            logger.debug(f"Query cached: hash={query_hash[:8]}...")
        
        return chunks
    except Exception as e:
        logger.error(f"Error querying chunks: {str(e)}", exc_info=True)
        return []

