"""
Centralized RAG decision logic.
Production-grade with intent-aware classification, confidence-based fallback, and context building.
"""
import os
import logging
import time
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from bson import ObjectId

from app.rag.embedder import embed_text
from app.rag.vector_store import query_chunks
from app.rag.intent import classify_intent
from app.rag.context_builder import build_rag_context
from app.rag.config import rag_config, context_config
from app.schemas import SourceInfo
from app.database import get_database

logger = logging.getLogger(__name__)


async def decide_context(
    query: str,
    selected_doc_ids: List[str],
    user_id: str,
    user_document_ids: List[str],
    found_documents_for_fallback: List[Dict],
    mode: str = "qa",
    request_id: str = ""
) -> Dict:
    """
    Centralized RAG decision function.
    Implements doc-grounded policy to prevent "doküman yok" spam.
    
    Args:
        query: User query text
        selected_doc_ids: Explicitly selected document IDs (if any)
        user_id: User ID for logging
        user_document_ids: All user document IDs to search
        found_documents_for_fallback: Documents found in DB (for fallback)
        mode: Request mode ("qa" or "summarize")
        request_id: Request ID for logging
        
    Returns:
        {
            "context_text": str,  # Built context string (empty if no relevant chunks)
            "sources": List[SourceInfo],  # Source citations
            "retrieval_stats": dict,  # Stats: chunks_count, top_score, etc.
            "should_use_documents": bool,  # Whether to include doc context in prompt
            "retrieved_chunks": List[dict],  # Raw retrieved chunks
            "doc_not_found": bool,  # True if doc-grounded query has no hits (should show doc-not-found message)
        }
    """
    has_specific_documents = len(selected_doc_ids) > 0
    retrieved_chunks = []
    sources = []
    context_text = ""
    
    retrieval_stats = {
        "retrieved_chunks_count": 0,
        "top_score": 0.0,
        "avg_score": 0.0,
        "threshold": rag_config.score_threshold,
        "should_use_documents": False,
        "intent": "qa",
        "rag_priority": 0.7,
        "rag_required": False,
        "embedding_duration_ms": 0.0,
        "query_duration_ms": 0.0
    }
    
    # If no documents available, return empty context
    if not user_document_ids:
        logger.info(f"[{request_id}] RAG_DECISION: No documents available for user")
        return {
            "context_text": "",
            "sources": [],
            "retrieval_stats": retrieval_stats,
            "should_use_documents": False,
            "retrieved_chunks": [],
            "doc_not_found": False
        }
    
    try:
        # Embed the query
        import time
        embed_start = time.time()
        query_embedding = await embed_text(query.strip())
        embed_duration = (time.time() - embed_start) * 1000
        
        if not query_embedding:
            logger.warning(f"[{request_id}] RAG_DECISION: Failed to generate query embedding")
            return {
                "context_text": "",
                "sources": [],
                "retrieval_stats": retrieval_stats,
                "should_use_documents": False,
                "retrieved_chunks": [],
                "doc_not_found": False
            }
        
        retrieval_stats["embedding_duration_ms"] = embed_duration
        
        logger.info(
            f"[{request_id}] RAG_DECISION_EMBED: success=True duration_ms={embed_duration:.2f} "
            f"embedding_len={len(query_embedding)}"
        )
        
        # Query vector store with intent-aware top_k
        query_start = time.time()
        # Adjust top_k based on intent (summarize/extract may need more chunks)
        query_top_k = rag_config.top_k
        if mode in ["summarize", "extract"]:
            query_top_k = min(rag_config.top_k * 2, 10)  # More chunks for summarize/extract
        
        # For very short queries (like "incele", "analiz"), lower the min_score threshold
        # to increase chances of finding relevant chunks
        query_min_score = rag_config.min_score_threshold
        is_short_query = len(query.strip()) <= 15
        if is_short_query and has_specific_documents:
            # Lower threshold for short queries with explicit documentIds
            query_min_score = max(0.1, rag_config.min_score_threshold * 0.5)  # Half the threshold, min 0.1
            logger.info(
                f"[{request_id}] RAG_DECISION: Short query detected (len={len(query.strip())}), "
                f"lowering min_score from {rag_config.min_score_threshold} to {query_min_score}"
            )
        
        retrieved_chunks = query_chunks(
            query_embedding=query_embedding,
            user_document_ids=user_document_ids,
            top_k=query_top_k,
            min_score=query_min_score,  # Use adjusted threshold
            use_cache=True
        )
        query_duration = (time.time() - query_start) * 1000
        retrieval_stats["query_duration_ms"] = query_duration
        retrieval_stats["retrieved_chunks_count"] = len(retrieved_chunks)
        
        # Log retrieval results
        top_scores = [chunk["score"] for chunk in retrieved_chunks[:3]] if retrieved_chunks else []
        chunk_doc_ids = list(set(chunk["document_id"] for chunk in retrieved_chunks)) if retrieved_chunks else []
        
        logger.info(
            f"[{request_id}] RAG_DECISION_QUERY: chunks={len(retrieved_chunks)} "
            f"top_scores={top_scores} threshold={rag_config.score_threshold} "
            f"query_duration_ms={query_duration:.2f} "
            f"matched_doc_ids={chunk_doc_ids[:3]}..."
        )
        
        # Intent-aware RAG decision with doc-grounded detection
        intent_result = classify_intent(query, mode=mode, document_ids=selected_doc_ids)
        intent = intent_result["intent"]
        rag_priority = intent_result["rag_priority"]
        rag_required = intent_result["rag_required"]
        doc_grounded = intent_result.get("doc_grounded", False)
        doc_grounded_reason = intent_result.get("doc_grounded_reason", "unknown")
        
        retrieval_stats["intent"] = intent
        retrieval_stats["rag_priority"] = rag_priority
        retrieval_stats["rag_required"] = rag_required
        retrieval_stats["doc_grounded"] = doc_grounded
        retrieval_stats["doc_grounded_reason"] = doc_grounded_reason
        
        # Decide relevance using intent-aware threshold
        should_use_documents = False
        
        if retrieved_chunks:
            top_score = retrieved_chunks[0]["score"]
            avg_score = sum(c["score"] for c in retrieved_chunks) / len(retrieved_chunks) if retrieved_chunks else 0.0
            retrieval_stats["top_score"] = top_score
            retrieval_stats["avg_score"] = avg_score
            
            # Dynamic threshold based on intent
            effective_threshold = rag_config.score_threshold * rag_priority
            
            # Confidence-based decision
            # If RAG is required (summarize/extract), use lower threshold
            if rag_required:
                effective_threshold = min(effective_threshold, rag_config.min_score_threshold)
            
            # Decision logic
            if rag_required:
                # RAG is required - use documents even with low scores
                should_use_documents = True
                logger.info(
                    f"[{request_id}] RAG_DECISION: RAG required for intent={intent}, "
                    f"using documents (top_score={top_score:.3f})"
                )
            elif has_specific_documents:
                # User explicitly selected documents - always use them
                should_use_documents = True
                logger.info(
                    f"[{request_id}] RAG_DECISION: Specific documents selected, "
                    f"using documents (top_score={top_score:.3f})"
                )
            elif top_score >= effective_threshold:
                # High relevance - use documents
                should_use_documents = True
                logger.info(
                    f"[{request_id}] RAG_DECISION: High relevance (top_score={top_score:.3f} >= {effective_threshold:.3f}), "
                    f"using documents"
                )
            elif avg_score >= effective_threshold * 0.8 and len(retrieved_chunks) >= 2:
                # Moderate relevance with multiple chunks - use documents
                should_use_documents = True
                logger.info(
                    f"[{request_id}] RAG_DECISION: Moderate relevance (avg_score={avg_score:.3f}, "
                    f"chunks={len(retrieved_chunks)}), using documents"
                )
            else:
                # Low relevance - confidence-based fallback
                should_use_documents = False
                logger.info(
                    f"[{request_id}] RAG_DECISION: Low relevance (top_score={top_score:.3f} < {effective_threshold:.3f}), "
                    f"falling back to general knowledge"
                )
            
            if should_use_documents:
                # Build sources list
                for chunk in retrieved_chunks:
                    sources.append(SourceInfo(
                        documentId=chunk["document_id"],
                        filename=chunk["original_filename"],
                        chunkIndex=chunk["chunk_index"],
                        score=chunk["score"],
                        preview=chunk["text"][:200] + "..." if len(chunk["text"]) > 200 else chunk["text"]
                    ))
                
                reason = []
                if rag_required:
                    reason.append(f"intent_required({intent})")
                if top_score >= rag_config.score_threshold:
                    reason.append(f"score({top_score:.3f})>={rag_config.score_threshold}")
                if has_specific_documents:
                    reason.append("specific_docs")
                
                logger.info(
                    f"[{request_id}] RAG_DECISION: Documents relevant (top_score={top_score:.3f}, "
                    f"threshold={rag_config.score_threshold}, intent={intent}), using doc-based answer. "
                    f"Reason: {', '.join(reason)}"
                )
            else:
                # Low relevance: confidence-based fallback
                # If intent requires RAG but scores are low, still provide sources but warn
                if rag_required:
                    logger.warning(
                        f"[{request_id}] RAG_DECISION: RAG required but low scores (top_score={top_score:.3f}), "
                        f"using documents with warning"
                    )
                    should_use_documents = True  # Force use for required intents
                else:
                    logger.info(
                        f"[{request_id}] RAG_DECISION: Low relevance (top_score={top_score:.3f}), "
                        f"falling back to general knowledge. User will be informed."
                    )
                    # Still include top source for citation (optional)
                    if retrieved_chunks and retrieved_chunks[0]["score"] >= rag_config.min_score_threshold:
                        sources.append(SourceInfo(
                            documentId=retrieved_chunks[0]["document_id"],
                            filename=retrieved_chunks[0]["original_filename"],
                            chunkIndex=retrieved_chunks[0]["chunk_index"],
                            score=retrieved_chunks[0]["score"],
                            preview=retrieved_chunks[0]["text"][:200] + "..." if len(retrieved_chunks[0]["text"]) > 200 else retrieved_chunks[0]["text"]
                        ))
        else:
            logger.info(f"[{request_id}] RAG_DECISION: No chunks retrieved")
            
            # DOC-GROUNDED POLICY: If query is doc-grounded and no chunks found, mark as doc_not_found
            # EXCEPTION: For very short queries (like "incele", "analiz") with explicit documentIds,
            # use fallback instead of doc-not-found (user explicitly wants to analyze the document)
            doc_not_found = False
            is_short_query = len(query.strip()) <= 15  # Very short queries like "incele", "bu ne", etc.
            
            if doc_grounded and not retrieved_chunks:
                # Special case: Short queries with explicit documentIds should use fallback
                if is_short_query and has_specific_documents:
                    doc_not_found = False
                    logger.info(
                        f"[{request_id}] RAG_DECISION: Short doc-grounded query (len={len(query.strip())}) "
                        f"with explicit documentIds. Using fallback instead of doc-not-found."
                    )
                else:
                    doc_not_found = True
                    logger.info(
                        f"[{request_id}] RAG_DECISION: Doc-grounded query with no hits. "
                        f"Reason: {doc_grounded_reason}. Will return doc-not-found response."
                    )
            
            # FALLBACK: If RAG retrieval returns 0 chunks but we have documents with content,
            # use document text_content directly (first 2000 chars per document)
            # BUT: Only if NOT doc-grounded (doc-grounded queries should show doc-not-found)
            # EXCEPTION: Short queries with explicit documentIds use fallback
            if has_specific_documents and found_documents_for_fallback and not doc_not_found:
                logger.warning(
                    f"[{request_id}] RAG_DECISION_FALLBACK: No chunks retrieved, "
                    f"using document text_content directly. "
                    f"found_documents_count={len(found_documents_for_fallback)}"
                )
                
                # Get documents with content
                fallback_docs = []
                for doc_info in found_documents_for_fallback:
                    if doc_info.get("text_has_content"):
                        fallback_docs.append(doc_info)
                
                if fallback_docs:
                    logger.info(
                        f"[{request_id}] RAG_DECISION_FALLBACK: Found {len(fallback_docs)} documents with content, "
                        f"using text_content directly (first 2000 chars per doc)"
                    )
                    
                    # Use document text_content directly
                    should_use_documents = True  # Force use_documents for fallback
                    
                    # Build fallback chunks from text_content
                    retrieved_chunks = []
                    for doc_info in fallback_docs:
                        text_content = doc_info.get("text_content", "")
                        if text_content:
                            fallback_text = text_content[:2000]
                            retrieved_chunks.append({
                                "document_id": doc_info["id"],
                                "original_filename": doc_info["filename"],
                                "chunk_index": 0,
                                "text": fallback_text,
                                "score": 1.0,  # Perfect score for direct text
                                "distance": 0.0,
                                "truncated": len(text_content) > 2000
                            })
                            sources.append(SourceInfo(
                                documentId=doc_info["id"],
                                filename=doc_info["filename"],
                                chunkIndex=0,
                                score=1.0,
                                preview=fallback_text[:200] + "..." if len(fallback_text) > 200 else fallback_text
                            ))
                            logger.info(
                                f"[{request_id}] RAG_DECISION_FALLBACK: Added doc {doc_info['id'][:8]}... "
                                f"({doc_info['filename']}) text_length={len(fallback_text)} "
                                f"truncated={len(text_content) > 2000}"
                            )
        
        # Build context text from retrieved chunks with budget management
        if should_use_documents and retrieved_chunks:
            context_result = build_rag_context(
                retrieved_chunks=retrieved_chunks,
                max_tokens=context_config.max_tokens,
                include_sources=True
            )
            context_text = context_result["context_text"]
            
            # Update stats
            retrieval_stats["context_tokens"] = context_result["used_tokens"]
            retrieval_stats["chunks_included"] = context_result["chunks_included"]
            retrieval_stats["chunks_excluded"] = context_result["chunks_excluded"]
            
            logger.info(
                f"[{request_id}] RAG_DECISION_CONTEXT: Context built successfully! "
                f"context_tokens={context_result['used_tokens']}, "
                f"chunks_included={context_result['chunks_included']}, "
                f"chunks_excluded={context_result['chunks_excluded']}"
            )
        
        retrieval_stats["should_use_documents"] = should_use_documents
        
        # Determine doc_not_found flag
        doc_not_found = False
        if doc_grounded and not retrieved_chunks and not should_use_documents:
            doc_not_found = True
        
        return {
            "context_text": context_text,
            "sources": sources,
            "retrieval_stats": retrieval_stats,
            "should_use_documents": should_use_documents,
            "retrieved_chunks": retrieved_chunks,
            "doc_not_found": doc_not_found
        }
        
    except Exception as e:
        logger.error(f"[{request_id}] RAG_DECISION error: {str(e)}", exc_info=True)
        # Return empty context on error (graceful fallback)
        return {
            "context_text": "",
            "sources": [],
            "retrieval_stats": retrieval_stats,
            "should_use_documents": False,
            "retrieved_chunks": [],
            "doc_not_found": False
        }

