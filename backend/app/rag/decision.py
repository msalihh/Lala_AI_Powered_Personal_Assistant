"""
Centralized RAG decision logic.
Production-grade with intent-aware classification, confidence-based fallback, and context building.
"""
import os
import logging
import time
import re
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from bson import ObjectId

from app.rag.embedder import embed_text
from app.rag.vector_store import query_chunks
from app.rag.intent import classify_intent
from app.rag.context_builder import build_rag_context
from app.rag.config import rag_config, context_config
from app.rag.evidence_gate import decide_use_sources
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
    request_id: str = "",
    prompt_module: Optional[str] = None
) -> Dict:
    """
    Centralized RAG decision function.
    Implements doc-grounded policy to prevent "doküman yok" spam.
    
    SPECIAL HANDLING: "Son maili incele" gibi komutlar için sadece en güncel maili kullanır.
    """
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
    # Use selected_doc_ids as-is (no special handling for emails)
    # Email'ler artık normal dökümanlar gibi user_document_ids listesinde ve genel RAG mantığıyla çalışıyor
    effective_selected_doc_ids = selected_doc_ids.copy() if selected_doc_ids else []
    has_specific_documents = len(effective_selected_doc_ids) > 0
    priority_doc_ids_set = set(effective_selected_doc_ids) if has_specific_documents else set()  # For source_scope determination
    retrieved_chunks = []
    sources = []
    context_text = ""
    
    used_priority_search = False
    priority_sufficient = False
    
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
    
    # If no documents or emails available, return empty context
    # Note: user_document_ids now includes both document IDs and email document IDs (email_{msg_id})
    if not user_document_ids:
        logger.info(f"[{request_id}] RAG_DECISION: No documents or emails available for user")
        return {
            "context_text": "",
            "sources": [],
            "retrieval_stats": retrieval_stats,
            "should_use_documents": False,
            "retrieved_chunks": [],
            "doc_not_found": False
        }
    
    try:
        # PROFESSIONAL: Check semantic cache first (like Perplexity/ChatGPT)
        from app.rag.semantic_cache import get_cached_results, cache_results
        cached_result = await get_cached_results(query.strip())
        cache_hit = False
        query_embedding = None
        
        if cached_result:
            cached_chunks, similarity = cached_result
            logger.info(
                f"[{request_id}] RAG_CACHE_HIT: Using cached results "
                f"(similarity={similarity:.3f}, chunks={len(cached_chunks)})"
            )
            # Use cached chunks but still go through evidence gate
            retrieved_chunks = cached_chunks
            # Skip embedding and query (already have results)
            retrieval_stats["embedding_duration_ms"] = 0.0
            retrieval_stats["query_duration_ms"] = 0.0
            retrieval_stats["cache_hit"] = True
            retrieval_stats["retrieved_chunks_count"] = len(retrieved_chunks)
            retrieval_stats["used_priority_search"] = False
            retrieval_stats["priority_sufficient"] = False
            retrieval_stats["priority_chunks_count"] = 0
            retrieval_stats["global_chunks_count"] = 0
            cache_hit = True
        else:
            retrieval_stats["cache_hit"] = False
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
            if mode in ["summarize", "extract"] or prompt_module == "lgs_karekok":
                # LGS module: increase chunks for better educational context (mimicking MEB style)
                query_top_k = min(rag_config.top_k * 2, 10 if prompt_module != "lgs_karekok" else 15)
            
            # For very short queries (like "incele", "analiz"), lower the min_score threshold
            # to increase chances of finding relevant chunks
            query_min_score = rag_config.min_score_threshold
            
            # MODULE OPTIMIZATION: LGS module needs more inclusive retrieval for pedagogical context
            if prompt_module == "lgs_karekok":
                query_min_score = max(0.1, rag_config.min_score_threshold * 0.7)  # More inclusive for LGS
                logger.info(f"[{request_id}] RAG_DECISION: LGS module optimization, set top_k={query_top_k}, min_score={query_min_score}")

            is_short_query = len(query.strip()) <= 15
            if is_short_query and has_specific_documents:
                # Lower threshold for short queries with explicit documentIds
                query_min_score = min(query_min_score, max(0.1, rag_config.min_score_threshold * 0.5))
                logger.info(
                    f"[{request_id}] RAG_DECISION: Short query detected (len={len(query.strip())}), "
                    f"lowering min_score to {query_min_score}"
                )
            
            # PRIORITY SEARCH: Two-stage retrieval (priority -> global fallback)
            retrieved_chunks = []
            priority_chunks = []
            global_chunks = []
            used_priority_search = False
            priority_sufficient = False
            
            # Stage 1: Priority search (if effective_selected_doc_ids provided)
            if has_specific_documents:
                logger.info(
                    f"[{request_id}] RAG_DECISION_PRIORITY_START: user_id={user_id} "
                    f"priority_doc_ids_count={len(effective_selected_doc_ids)} "
                    f"query_len={len(query.strip())} top_k={query_top_k} min_score={query_min_score}"
                )
                
                # Add prompt_module filter for module isolation
                metadata_filters = {}
                if prompt_module:
                    metadata_filters["prompt_module"] = prompt_module
                
                # Search only in priority documents
                priority_chunks = query_chunks(
                    query_embedding=query_embedding,
                    user_document_ids=user_document_ids,  # Still need user_document_ids for user_id filter
                    top_k=query_top_k,
                    min_score=query_min_score,
                    metadata_filters=metadata_filters if metadata_filters else None,
                    use_cache=True,
                    user_id=user_id,
                    priority_doc_ids=effective_selected_doc_ids  # PRIORITY: Only search in these docs
                )
                
                # Check if priority search is sufficient
                if priority_chunks:
                    top_score = priority_chunks[0]["score"]
                    avg_score = sum(c["score"] for c in priority_chunks) / len(priority_chunks) if priority_chunks else 0.0
                    hit_count = len(priority_chunks)
                    
                    # Decision rule: HIGH_THRESHOLD or (MIN_HITS + LOW_THRESHOLD)
                    if top_score >= rag_config.priority_high_threshold:
                        priority_sufficient = True
                        logger.info(
                            f"[{request_id}] RAG_DECISION_PRIORITY: High score (top_score={top_score:.3f} >= {rag_config.priority_high_threshold}), "
                            f"priority search sufficient"
                        )
                    elif hit_count >= rag_config.priority_min_hits and avg_score >= rag_config.priority_low_threshold:
                        priority_sufficient = True
                        logger.info(
                            f"[{request_id}] RAG_DECISION_PRIORITY: Sufficient hits (hits={hit_count} >= {rag_config.priority_min_hits}, "
                            f"avg_score={avg_score:.3f} >= {rag_config.priority_low_threshold}), priority search sufficient"
                        )
                    else:
                        logger.info(
                            f"[{request_id}] RAG_DECISION_PRIORITY: Insufficient (top_score={top_score:.3f}, "
                            f"hits={hit_count}, avg_score={avg_score:.3f}), falling back to global search"
                        )
                
                if priority_sufficient:
                    retrieved_chunks = priority_chunks
                    used_priority_search = True
                    logger.info(
                        f"[{request_id}] RAG_DECISION_PRIORITY: Using priority results only "
                        f"(chunks={len(retrieved_chunks)})"
                    )
                else:
                    # Stage 2: Global search fallback
                    logger.info(
                        f"[{request_id}] RAG_DECISION_GLOBAL_START: Priority insufficient, "
                        f"expanding to global search (user_doc_ids_count={len(user_document_ids)})"
                    )
                    
                    # Add prompt_module filter for module isolation
                    metadata_filters = {}
                    if prompt_module:
                        metadata_filters["prompt_module"] = prompt_module
                    
                    global_chunks = query_chunks(
                        query_embedding=query_embedding,
                        user_document_ids=user_document_ids,
                        top_k=query_top_k,
                        min_score=query_min_score,
                        metadata_filters=metadata_filters if metadata_filters else None,
                        use_cache=True,
                        user_id=user_id,
                        priority_doc_ids=None  # GLOBAL: Search all user documents
                    )
                    
                    # Combine priority + global (priority first, then global)
                    # Remove duplicates (same document_id + chunk_index)
                    seen_chunks = set()
                    retrieved_chunks = []
                    
                    # Add priority chunks first (even if insufficient, they're still relevant)
                    for chunk in priority_chunks:
                        chunk_key = (chunk["document_id"], chunk["chunk_index"])
                        if chunk_key not in seen_chunks:
                            seen_chunks.add(chunk_key)
                            retrieved_chunks.append(chunk)
                    
                    # Add global chunks (excluding duplicates)
                    for chunk in global_chunks:
                        chunk_key = (chunk["document_id"], chunk["chunk_index"])
                        if chunk_key not in seen_chunks:
                            seen_chunks.add(chunk_key)
                            retrieved_chunks.append(chunk)
                    
                    logger.info(
                        f"[{request_id}] RAG_DECISION_GLOBAL: Combined results "
                        f"(priority={len(priority_chunks)}, global={len(global_chunks)}, "
                        f"combined={len(retrieved_chunks)})"
                    )
            else:
                # No priority documents - use global search directly
                logger.info(
                    f"[{request_id}] RAG_DECISION_QUERY_START: user_id={user_id} "
                    f"user_document_ids_count={len(user_document_ids)} "
                    f"query_len={len(query.strip())} top_k={query_top_k} min_score={query_min_score} "
                    f"(no priority docs, using global search)"
                )
                
                # Add prompt_module filter for module isolation
                metadata_filters = {}
                if prompt_module:
                    metadata_filters["prompt_module"] = prompt_module
                
                retrieved_chunks = query_chunks(
                    query_embedding=query_embedding,
                    user_document_ids=user_document_ids,
                    top_k=query_top_k,
                    min_score=query_min_score,
                    metadata_filters=metadata_filters if metadata_filters else None,
                    use_cache=True,
                    user_id=user_id,
                    priority_doc_ids=None  # GLOBAL search
                )
            
            query_duration = (time.time() - query_start) * 1000
            retrieval_stats["query_duration_ms"] = query_duration
            
            # PROFESSIONAL: Apply hybrid search (vector + BM25 keyword matching)
            # This improves retrieval quality by combining semantic and keyword matching
            if retrieved_chunks:
                from app.rag.hybrid_search import hybrid_search
                vector_scores = [chunk.get("score", 0.0) for chunk in retrieved_chunks]
                retrieved_chunks = hybrid_search(
                    query=query.strip(),
                    chunks=retrieved_chunks,
                    vector_scores=vector_scores,
                    hybrid_weight=0.7  # 70% vector, 30% BM25
                )
                # Update scores to hybrid_score for consistency
                for chunk in retrieved_chunks:
                    chunk["score"] = chunk.get("hybrid_score", chunk.get("score", 0.0))
                logger.info(
                    f"[{request_id}] RAG_HYBRID_SEARCH: Applied hybrid scoring "
                    f"(chunks={len(retrieved_chunks)}, top_score={retrieved_chunks[0].get('score', 0.0):.3f})"
                )
            
            retrieval_stats["retrieved_chunks_count"] = len(retrieved_chunks)
            retrieval_stats["used_priority_search"] = used_priority_search
            retrieval_stats["priority_sufficient"] = priority_sufficient
            retrieval_stats["priority_chunks_count"] = len(priority_chunks) if has_specific_documents else 0
            retrieval_stats["global_chunks_count"] = len(global_chunks) if has_specific_documents and not priority_sufficient else 0
            
            # PROFESSIONAL: Cache results for future similar queries
            if retrieved_chunks and query_embedding:
                cache_results(query.strip(), query_embedding, retrieved_chunks)
        
        # Log retrieval results with detailed info
        top_scores = [chunk["score"] for chunk in retrieved_chunks[:3]] if retrieved_chunks else []
        chunk_doc_ids = list(set(chunk["document_id"] for chunk in retrieved_chunks)) if retrieved_chunks else []
        top_score = retrieved_chunks[0]["score"] if retrieved_chunks else 0.0
        
        # Check how many chunks have user_id in metadata (for debugging old indexes)
        chunks_with_user_id = sum(1 for c in retrieved_chunks if c.get("user_id_in_metadata", False))
        
        query_duration_for_log = retrieval_stats.get("query_duration_ms", 0.0)
        logger.info(
            f"[{request_id}] RAG_DECISION_QUERY_RESULT: user_id={user_id} "
            f"chunks={len(retrieved_chunks)} top_score={top_score:.3f} "
            f"top_scores={top_scores} threshold={rag_config.score_threshold} "
            f"threshold_met={top_score >= rag_config.score_threshold} "
            f"query_duration_ms={query_duration_for_log:.2f} "
            f"matched_doc_ids={chunk_doc_ids[:3]}... "
            f"chunks_with_user_id_meta={chunks_with_user_id}/{len(retrieved_chunks)}"
        )
        
        # Intent-aware RAG decision with doc-grounded detection
        intent_result = classify_intent(query, mode=mode, document_ids=effective_selected_doc_ids)
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
        
        # Skip RAG for general_chat intent (greetings, etc.) - no sources needed
        # Also skip if query is too short or clearly not document-related
        if intent == "general_chat" and not has_specific_documents:
            logger.info(
                f"[{request_id}] RAG_DECISION: General chat intent detected, "
                f"skipping RAG retrieval (no sources needed)"
            )
            return {
                "context_text": "",
                "sources": [],
                "retrieval_stats": retrieval_stats,
                "should_use_documents": False,
                "retrieved_chunks": [],
                "doc_not_found": False
            }
        
        # Additional check: If query is very short and not document-related, skip RAG
        query_words = query.strip().split()
        if len(query_words) <= 3 and not has_specific_documents and intent != "qa":
            logger.info(
                f"[{request_id}] RAG_DECISION: Very short query ({len(query_words)} words) with non-QA intent, "
                f"skipping RAG retrieval"
            )
            return {
                "context_text": "",
                "sources": [],
                "retrieval_stats": retrieval_stats,
                "should_use_documents": False,
                "retrieved_chunks": [],
                "doc_not_found": False
            }
        
        # EVIDENCE GATE: Evidence-based decision to prevent irrelevant sources
        # This is the SINGLE decision point that controls both should_use_documents AND sources
        # Uses query classification, evidence scoring, and term overlap to make intelligent decisions
        
        if retrieved_chunks:
            # Prepare evidence gate config
            evidence_config = {
                "evidence_high": rag_config.evidence_high,
                "evidence_low": rag_config.evidence_low,
                "min_overlap": rag_config.evidence_min_overlap,
                "min_hits": rag_config.evidence_min_hits,
                "generic_query_min_len": rag_config.evidence_generic_query_min_len,
                "allow_sources_for_general_queries": rag_config.evidence_allow_sources_for_general_queries,
            }
            
            # Special case: RAG required (summarize/extract) - allow with lower threshold
            if rag_required:
                # Lower evidence thresholds for required intents
                evidence_config["evidence_high"] = max(rag_config.min_score_threshold, evidence_config["evidence_high"] * 0.8)
                evidence_config["evidence_low"] = max(rag_config.min_score_threshold * 0.7, evidence_config["evidence_low"] * 0.8)
                logger.info(
                    f"[{request_id}] RAG_DECISION: RAG required for intent={intent}, "
                    f"lowering evidence thresholds (high={evidence_config['evidence_high']:.3f}, low={evidence_config['evidence_low']:.3f})"
                )
            
            # Call evidence gate
            evidence_decision = decide_use_sources(
                query=query,
                hits=retrieved_chunks,
                selected_doc_ids=effective_selected_doc_ids if has_specific_documents else None,
                config=evidence_config
            )
            
            should_use_documents = evidence_decision.use_documents
            decision_reason = evidence_decision.reason
            filtered_hits = evidence_decision.sources  # Already filtered by evidence gate
            
            # Update retrieval stats with evidence metrics
            if evidence_decision.evidence_metrics:
                top_metrics = evidence_decision.evidence_metrics
                retrieval_stats["top_vector_score"] = top_metrics.vector_score
                retrieval_stats["top_evidence_score"] = top_metrics.evidence_score
                retrieval_stats["term_overlap"] = top_metrics.term_overlap
                retrieval_stats["has_number_match"] = top_metrics.has_number_match
                retrieval_stats["has_entity_match"] = top_metrics.has_entity_match
                retrieval_stats["query_type"] = evidence_decision.query_type
                retrieval_stats["doc_intent"] = evidence_decision.doc_intent
            
            # Calculate stats from filtered hits
            if filtered_hits:
                top_score = filtered_hits[0]["score"] if filtered_hits else 0.0
                avg_score = sum(c["score"] for c in filtered_hits) / len(filtered_hits) if filtered_hits else 0.0
                hit_count = len(filtered_hits)
            else:
                top_score = retrieved_chunks[0]["score"] if retrieved_chunks else 0.0
                avg_score = sum(c["score"] for c in retrieved_chunks) / len(retrieved_chunks) if retrieved_chunks else 0.0
                hit_count = len(retrieved_chunks)
            
            retrieval_stats["top_score"] = top_score
            retrieval_stats["avg_score"] = avg_score
            retrieval_stats["hit_count"] = hit_count
            
            # CRITICAL: Only build sources if should_use_documents is True
            # This ensures sources array is empty when RAG is OFF
            if should_use_documents and filtered_hits:
                # Build sources list from filtered hits (evidence gate already filtered)
                # Mark sources as priority or global based on which search they came from
                priority_doc_ids_set = set(effective_selected_doc_ids) if has_specific_documents else set()
                
                for chunk in filtered_hits:
                    # Determine source scope: priority if from priority docs, global otherwise
                    chunk_doc_id = chunk["document_id"]
                    source_scope = "priority" if chunk_doc_id in priority_doc_ids_set else "global"
                    
                    # Create snippet (max 240-400 chars) instead of full chunk_text
                    chunk_text = chunk.get("text", "")
                    snippet = chunk_text[:320] + "..." if len(chunk_text) > 320 else chunk_text
                    
                    # Use evidence_score if available, otherwise use vector score
                    evidence_score = chunk.get("evidence_score", chunk.get("score", 0.0))
                    
                    # Determine filename based on source type
                    source_type = chunk.get("source_type", "document")
                    if source_type == "email":
                        # For emails, use subject as filename for better display
                        display_filename = chunk.get("subject", "E-posta")
                    else:
                        # For documents, use original filename
                        display_filename = chunk.get("original_filename", "Bilinmeyen Dosya")
                    
                    # CRITICAL: For email sources, extract message_id from document_id
                    # document_id is in format "email_{msg_id}" for emails, we need just msg_id for frontend
                    document_id_for_frontend = chunk["document_id"]
                    if source_type == "email" and document_id_for_frontend.startswith("email_"):
                        # Extract message_id from "email_{msg_id}" format
                        document_id_for_frontend = document_id_for_frontend.replace("email_", "", 1)
                    
                    sources.append(SourceInfo(
                        documentId=document_id_for_frontend,  # Use msg_id for emails, document_id for documents
                        filename=display_filename,  # Use subject for emails, filename for documents
                        chunkIndex=chunk["chunk_index"],
                        score=evidence_score,  # Use evidence_score instead of vector score
                        preview=snippet,  # Use snippet instead of full chunk_text
                        page=None,
                        chunk_text=None,  # Don't send full chunk_text to UI (reduces payload)
                        source_scope=source_scope,
                        # Email specific fields
                        source_type=source_type,
                        subject=chunk.get("subject"),  # Email subject
                        sender=chunk.get("sender"),  # Email sender
                        date=chunk.get("date")  # Email date (ISO format)
                    ))
                
                logger.info(
                    f"[{request_id}] RAG_DECISION: Evidence gate passed - {decision_reason}, "
                    f"using doc-based answer. Sources count: {len(sources)} (filtered from {len(retrieved_chunks)} hits)"
                )
            else:
                # Gate failed: Clear sources to ensure empty array
                sources = []
                logger.info(
                    f"[{request_id}] RAG_DECISION: Evidence gate failed - {decision_reason}, "
                    f"sources cleared (empty array). Query type: {evidence_decision.query_type}, "
                    f"Doc intent: {evidence_decision.doc_intent}"
                )
            
            # DEBUG LOG: Log evidence gate decision details
            top_scores = [chunk["score"] for chunk in retrieved_chunks[:3]]
            top_evidence_val = evidence_decision.evidence_metrics.evidence_score if evidence_decision.evidence_metrics else 0.0
            term_overlap_val = evidence_decision.evidence_metrics.term_overlap if evidence_decision.evidence_metrics else 0
            logger.info(
                f"[{request_id}] EVIDENCE_GATE_DEBUG: query=\"{query[:100]}\" "
                f"query_type={evidence_decision.query_type} doc_intent={evidence_decision.doc_intent} "
                f"top_vector_scores={top_scores} "
                f"top_evidence={top_evidence_val:.3f} "
                f"term_overlap={term_overlap_val} "
                f"decision={decision_reason} "
                f"use_documents={should_use_documents} "
                f"filtered_hits={len(filtered_hits) if should_use_documents else 0}/{len(retrieved_chunks)}"
            )
        else:
            logger.info(f"[{request_id}] RAG_DECISION: No chunks retrieved")
            should_use_documents = False  # Initialize to False when no chunks
            
            # DOC-GROUNDED POLICY: If query is doc-grounded and no chunks found, mark as doc_not_found
            # EXCEPTION: For very short queries (like "incele", "analiz") with explicit documentIds,
            # use fallback instead of doc-not-found (user explicitly wants to analyze the document)
            doc_not_found = False
            is_short_query = len(query.strip()) <= 15  # Very short queries like "incele", "bu ne", etc.
            
            if doc_grounded and not retrieved_chunks:
                # MARK ONLY: Don't let this block the flow in Soft-RAG mode
                # The LLM prompt now handles "not found" cases gracefully
                doc_not_found = True
                logger.info(
                    f"[{request_id}] RAG_DECISION: Doc-grounded query with no hits. "
                    f"Reason: {doc_grounded_reason}. Flagging for metadata, but flow will continue."
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
                            # Fallback sources are from priority docs if doc_id is in priority list
                            fallback_source_scope = "priority" if doc_info["id"] in priority_doc_ids_set else "global"
                            sources.append(SourceInfo(
                                documentId=doc_info["id"],
                                filename=doc_info["filename"],
                                chunkIndex=0,
                                score=1.0,
                                preview=fallback_text[:200] + "..." if len(fallback_text) > 200 else fallback_text,
                                page=None,
                                chunk_text=fallback_text,
                                source_scope=fallback_source_scope,
                                # Fallback is usually for documents
                                source_type="document"
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
            "doc_not_found": doc_not_found,
            "used_priority_search": used_priority_search,  # Whether priority search was used
            "priority_sufficient": priority_sufficient,  # Whether priority search was sufficient
            "priority_document_ids": effective_selected_doc_ids if has_specific_documents else []  # Priority doc IDs
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

