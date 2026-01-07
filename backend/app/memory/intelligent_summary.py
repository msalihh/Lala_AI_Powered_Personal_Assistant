"""
Intelligent summarization for context compression.
Uses LLM to create concise summaries that preserve key information.
"""
import logging
from typing import Optional, List, Dict
from app.utils import estimate_tokens

logger = logging.getLogger(__name__)


async def summarize_messages(
    messages: List[Dict[str, str]],
    llm_call_func,
    max_summary_tokens: int = 200,
    preserve_recent: int = 0  # Number of recent messages to exclude from summary
) -> Optional[str]:
    """
    Intelligently summarize a list of messages using LLM.
    
    This is more sophisticated than simple truncation:
    - Preserves key information (topics, decisions, facts)
    - Maintains conversation flow
    - Compresses redundant information
    
    Args:
        messages: List of messages (oldest first)
        llm_call_func: Async function to call LLM (takes messages list, returns text)
        max_summary_tokens: Maximum tokens for summary
        preserve_recent: Number of recent messages to exclude (already in context)
        
    Returns:
        Summary text or None if summarization fails
    """
    if not messages or len(messages) <= preserve_recent:
        return None
    
    # Messages to summarize (exclude recent ones)
    messages_to_summarize = messages[:-preserve_recent] if preserve_recent > 0 else messages
    
    if not messages_to_summarize:
        return None
    
    # Build conversation text for summarization
    conversation_text = "\n".join([
        f"{msg.get('role', 'user').upper()}: {msg.get('content', '')}"
        for msg in messages_to_summarize
    ])
    
    # Estimate tokens - if already small, no need to summarize
    estimated_tokens = estimate_tokens(conversation_text)
    if estimated_tokens <= max_summary_tokens * 2:  # Only summarize if > 2x target
        logger.debug(f"Messages already concise ({estimated_tokens} tokens), skipping summarization")
        return None
    
    # Create summarization prompt
    summary_prompt = f"""Aşağıdaki konuşma geçmişini {max_summary_tokens // 4} satırlık kısa bir özet haline getir.
ÖNEMLİ: Özet şunları içermeli:
- Ana konular ve sorular
- Önemli kararlar veya sonuçlar
- Kritik bilgiler veya gerçekler
- Konuşmanın genel akışı

Gereksiz detayları atla, sadece önemli bilgileri koru. Türkçe yaz.

Konuşma:
{conversation_text[:3000]}...  # Truncate if too long

Özet:"""
    
    try:
        summary_messages = [
            {
                "role": "system",
                "content": "Sen bir konuşma özetleme uzmanısın. Verilen konuşmayı kısa, öz ve bilgilendirici şekilde özetle. Sadece önemli bilgileri koru."
            },
            {
                "role": "user",
                "content": summary_prompt
            }
        ]
        
        summary_text = await llm_call_func(summary_messages)
        
        if summary_text:
            summary_tokens = estimate_tokens(summary_text)
            logger.info(
                f"Intelligent summary created: {len(messages_to_summarize)} messages → "
                f"{summary_tokens} tokens (compression: {estimated_tokens / summary_tokens:.1f}x)"
            )
            return summary_text
        
    except Exception as e:
        logger.error(f"Error creating intelligent summary: {str(e)}", exc_info=True)
    
    return None


def compress_context_intelligently(
    messages: List[Dict[str, str]],
    max_tokens: int,
    summary: Optional[str] = None
) -> List[Dict[str, str]]:
    """
    Intelligently compress context by:
    1. Using summary for older messages
    2. Keeping recent messages intact
    3. Compressing middle messages if needed
    
    Args:
        messages: List of messages (oldest first)
        max_tokens: Maximum token budget
        summary: Optional summary of older messages
        
    Returns:
        Compressed message list
    """
    if not messages:
        return []
    
    from app.utils import estimate_tokens
    
    # Calculate tokens for each message
    message_tokens = [estimate_tokens(msg.get("content", "")) for msg in messages]
    total_tokens = sum(message_tokens)
    
    # If within budget, return as-is
    summary_tokens = estimate_tokens(summary) if summary else 0
    if total_tokens + summary_tokens <= max_tokens:
        result = []
        if summary:
            result.append({
                "role": "system",
                "content": f"Önceki konuşma özeti: {summary}"
            })
        result.extend(messages)
        return result
    
    # Need compression - use summary + recent messages
    result = []
    if summary:
        result.append({
            "role": "system",
            "content": f"Önceki konuşma özeti: {summary}"
        })
    
    # Add recent messages (from end) until budget
    used_tokens = summary_tokens
    recent_messages = []
    
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        msg_tokens = message_tokens[i]
        if used_tokens + msg_tokens <= max_tokens:
            recent_messages.insert(0, msg)
            used_tokens += msg_tokens
        else:
            break
    
    result.extend(recent_messages)
    
    return result

