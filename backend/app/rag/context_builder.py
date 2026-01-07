"""
Context building with token budget management and intelligent ordering.
"""
import logging
from typing import List, Dict, Optional
from app.rag.config import context_config
from app.utils import estimate_tokens

logger = logging.getLogger(__name__)


def build_rag_context(
    retrieved_chunks: List[dict],
    max_tokens: Optional[int] = None,
    include_sources: bool = True
) -> Dict[str, any]:
    """
    Build RAG context with token budget management and intelligent ordering.
    
    Args:
        retrieved_chunks: List of retrieved chunks (sorted by score, descending)
        max_tokens: Maximum tokens for context (uses config default if None)
        include_sources: Whether to include source labels in context
        
    Returns:
        Dict with:
        - context_text: Built context string
        - used_tokens: Number of tokens used
        - chunks_included: Number of chunks included
        - chunks_excluded: Number of chunks excluded due to budget
    """
    if not retrieved_chunks:
        return {
            "context_text": "",
            "used_tokens": 0,
            "chunks_included": 0,
            "chunks_excluded": 0
        }
    
    # Use config default if not provided
    budget_max_tokens = max_tokens or context_config.max_tokens
    
    # Group chunks by document/email for better organization
    # Separate documents and emails for clearer context building
    doc_chunks = {}
    for chunk in retrieved_chunks:
        doc_id = chunk.get('document_id', '')
        if not doc_id:
            continue
        source_type = chunk.get('source_type', 'document')  # 'document' or 'email'
        if doc_id not in doc_chunks:
            # Determine source label based on type
            if source_type == 'email':
                # For emails, use subject or sender as label
                subject = chunk.get('subject', 'E-posta')
                sender = chunk.get('sender', 'Bilinmeyen Gönderen')
                source_label = f"{subject} ({sender})"
            else:
                # For documents, use filename
                source_label = chunk.get('original_filename', 'Bilinmeyen Dosya')
            
            doc_chunks[doc_id] = {
                'filename': source_label,
                'source_type': source_type,
                'chunks': []
            }
        doc_chunks[doc_id]['chunks'].append(chunk)
    
    # Build context with token budget management
    context_parts = []
    used_tokens = 0
    chunks_included = 0
    chunks_excluded = 0
    
    # Process chunks in order (highest score first)
    # Separate documents and emails for better organization
    for doc_id, doc_info in doc_chunks.items():
        filename = doc_info.get('filename', 'Bilinmeyen Dosya')
        source_type = doc_info.get('source_type', 'document')
        chunks_text = []
        
        for chunk in doc_info['chunks']:
            chunk_text = chunk.get('text', '')
            chunk_index = chunk.get('chunk_index', 0)
            chunk_tokens = chunk.get('token_count', estimate_tokens(chunk_text))
            
            # Determine source label based on type
            if source_type == 'email':
                # For emails, use email-specific label
                source_label = f"[E-posta: {filename}]"
            else:
                # For documents, use document-specific label
                source_label = f"[Döküman: {filename}, Bölüm {chunk_index}]"
            
            # Check if adding this chunk would exceed budget
            chunk_with_label = f"{source_label}\n{chunk_text}" if include_sources else chunk_text
            chunk_tokens_with_label = estimate_tokens(chunk_with_label)
            
            if used_tokens + chunk_tokens_with_label > budget_max_tokens:
                # Budget exceeded - exclude this and remaining chunks
                chunks_excluded += len(doc_info['chunks']) - len(chunks_text)
                logger.debug(
                    f"Context budget exceeded: used={used_tokens}, "
                    f"chunk_tokens={chunk_tokens_with_label}, budget={budget_max_tokens}"
                )
                break
            
            # Add chunk
            if include_sources:
                chunks_text.append(f"{source_label}\n{chunk_text}")
            else:
                chunks_text.append(chunk_text)
            
            used_tokens += chunk_tokens_with_label
            chunks_included += 1
        
        if chunks_text:
            context_parts.append("\n\n".join(chunks_text))
    
    # Join context parts
    if context_parts:
        context_text = "\n\n---\n\n".join(context_parts)
    else:
        context_text = ""
    
    logger.info(
        f"Context built: tokens={used_tokens}/{budget_max_tokens}, "
        f"chunks={chunks_included}/{len(retrieved_chunks)}, "
        f"excluded={chunks_excluded}"
    )
    
    return {
        "context_text": context_text,
        "used_tokens": used_tokens,
        "chunks_included": chunks_included,
        "chunks_excluded": chunks_excluded
    }


def manage_context_budget(
    system_prompt: str,
    chat_history: List[Dict[str, str]],
    rag_context: str,
    user_message: str,
    max_total_tokens: int = 4000
) -> Dict[str, any]:
    """
    Manage total context budget across system prompt, chat history, RAG context, and user message.
    
    Args:
        system_prompt: System prompt text
        chat_history: List of chat messages
        rag_context: RAG context text
        user_message: Current user message
        max_total_tokens: Maximum total tokens
        
    Returns:
        Dict with:
        - system_prompt: Adjusted system prompt
        - chat_history: Adjusted chat history (truncated if needed)
        - rag_context: Adjusted RAG context (truncated if needed)
        - user_message: User message (unchanged)
        - token_breakdown: Token counts for each component
    """
    if not context_config.enable_budget_management:
        # Budget management disabled - return as-is
        return {
            "system_prompt": system_prompt,
            "chat_history": chat_history,
            "rag_context": rag_context,
            "user_message": user_message,
            "token_breakdown": {
                "system_prompt": estimate_tokens(system_prompt),
                "chat_history": sum(estimate_tokens(msg.get("content", "")) for msg in chat_history),
                "rag_context": estimate_tokens(rag_context),
                "user_message": estimate_tokens(user_message)
            }
        }
    
    # Estimate tokens for each component
    system_tokens = estimate_tokens(system_prompt)
    chat_tokens = sum(estimate_tokens(msg.get("content", "")) for msg in chat_history)
    rag_tokens = estimate_tokens(rag_context)
    user_tokens = estimate_tokens(user_message)
    
    total_tokens = system_tokens + chat_tokens + rag_tokens + user_tokens
    
    # If within budget, return as-is
    if total_tokens <= max_total_tokens:
        return {
            "system_prompt": system_prompt,
            "chat_history": chat_history,
            "rag_context": rag_context,
            "user_message": user_message,
            "token_breakdown": {
                "system_prompt": system_tokens,
                "chat_history": chat_tokens,
                "rag_context": rag_tokens,
                "user_message": user_tokens,
                "total": total_tokens
            }
        }
    
    # Budget exceeded - prioritize components
    # Priority: system_prompt > user_message > rag_context > chat_history
    
    remaining_budget = max_total_tokens - system_tokens - user_tokens
    
    # Truncate chat history if needed
    adjusted_chat_history = chat_history
    if remaining_budget < chat_tokens + rag_tokens:
        # Need to truncate chat history
        chat_budget = max(0, remaining_budget - rag_tokens)
        adjusted_chat_history = []
        used_chat_tokens = 0
        
        # Keep most recent messages first
        for msg in reversed(chat_history):
            msg_tokens = estimate_tokens(msg.get("content", ""))
            if used_chat_tokens + msg_tokens <= chat_budget:
                adjusted_chat_history.insert(0, msg)
                used_chat_tokens += msg_tokens
            else:
                # Truncate last message if needed
                if used_chat_tokens < chat_budget:
                    content = msg.get("content", "")
                    remaining = chat_budget - used_chat_tokens
                    # Approximate truncation (rough estimate)
                    truncate_chars = int(len(content) * (remaining / msg_tokens)) if msg_tokens > 0 else 0
                    truncated_msg = msg.copy()
                    truncated_msg["content"] = content[:truncate_chars] + "..."
                    adjusted_chat_history.insert(0, truncated_msg)
                break
    else:
        used_chat_tokens = chat_tokens
    
    # Truncate RAG context if needed
    adjusted_rag_context = rag_context
    rag_budget = max(0, remaining_budget - used_chat_tokens)
    if rag_tokens > rag_budget:
        # Truncate RAG context (keep beginning, highest score chunks)
        # Rough truncation - could be improved with chunk-level truncation
        truncate_chars = int(len(rag_context) * (rag_budget / rag_tokens)) if rag_tokens > 0 else 0
        adjusted_rag_context = rag_context[:truncate_chars] + "\n\n[... RAG context truncated due to token limit ...]"
    
    final_tokens = (
        system_tokens +
        sum(estimate_tokens(msg.get("content", "")) for msg in adjusted_chat_history) +
        estimate_tokens(adjusted_rag_context) +
        user_tokens
    )
    
    logger.info(
        f"Context budget managed: original={total_tokens}, final={final_tokens}, "
        f"budget={max_total_tokens}, "
        f"chat_truncated={len(adjusted_chat_history) < len(chat_history)}, "
        f"rag_truncated={len(adjusted_rag_context) < len(rag_context)}"
    )
    
    return {
        "system_prompt": system_prompt,
        "chat_history": adjusted_chat_history,
        "rag_context": adjusted_rag_context,
        "user_message": user_message,
        "token_breakdown": {
            "system_prompt": system_tokens,
            "chat_history": sum(estimate_tokens(msg.get("content", "")) for msg in adjusted_chat_history),
            "rag_context": estimate_tokens(adjusted_rag_context),
            "user_message": user_tokens,
            "total": final_tokens
        }
    }

