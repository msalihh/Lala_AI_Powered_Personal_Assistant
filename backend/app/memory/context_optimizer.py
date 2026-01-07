"""
Professional context window management inspired by ChatGPT/Claude.
Implements sliding window, intelligent compression, and token-aware prioritization.
"""
import logging
from typing import List, Dict, Optional, Tuple, Callable, Awaitable
from app.utils import estimate_tokens

logger = logging.getLogger(__name__)


async def build_optimized_context(
    messages: List[Dict[str, str]],
    max_tokens: int,
    summary: Optional[str] = None,
    preserve_recent: int = 6,  # Always keep last N messages (user + assistant pairs)
    llm_call_func: Optional[Callable[[List[Dict]], Awaitable[str]]] = None  # Optional LLM function for intelligent summarization
) -> Dict[str, any]:
    """
    Build optimized context using ChatGPT-style sliding window + compression.
    
    Strategy:
    1. Always preserve most recent N messages (critical for conversation flow)
    2. Use summary for older context (if available)
    3. Fill remaining budget with middle messages (sliding window)
    4. Compress messages if needed (intelligent truncation)
    
    Args:
        messages: List of messages in chronological order (oldest first)
        max_tokens: Maximum token budget
        summary: Optional summary of older messages
        preserve_recent: Number of recent messages to always preserve
        
    Returns:
        Dict with:
        - messages: Optimized message list
        - used_tokens: Token count
        - compression_applied: Whether compression was used
        - messages_dropped: Number of messages dropped
    """
    if not messages:
        return {
            "messages": [],
            "used_tokens": 0,
            "compression_applied": False,
            "messages_dropped": 0
        }
    
    # Calculate tokens for each message
    message_tokens = []
    for msg in messages:
        tokens = estimate_tokens(msg.get("content", ""))
        message_tokens.append(tokens)
    
    total_tokens = sum(message_tokens)
    
    # If within budget, return as-is
    summary_tokens = estimate_tokens(summary) if summary else 0
    if total_tokens + summary_tokens <= max_tokens:
        result_messages = []
        if summary:
            result_messages.append({
                "role": "system",
                "content": f"Önceki konuşma özeti: {summary}"
            })
        result_messages.extend(messages)
        return {
            "messages": result_messages,
            "used_tokens": total_tokens + summary_tokens,
            "compression_applied": False,
            "messages_dropped": 0
        }
    
    # Budget exceeded - apply optimization
    result_messages = []
    used_tokens = summary_tokens
    messages_dropped = 0
    compression_applied = False
    
    # Step 1: Intelligently create summary if needed and LLM available
    final_summary = summary
    if not final_summary and llm_call_func and len(messages) > preserve_recent + 5:
        # Create intelligent summary of older messages
        try:
            from app.memory.intelligent_summary import summarize_messages
            messages_to_summarize = messages[:-preserve_recent] if len(messages) > preserve_recent else messages
            final_summary = await summarize_messages(
                messages=messages_to_summarize,
                llm_call_func=llm_call_func,
                max_summary_tokens=200,
                preserve_recent=0
            )
        except Exception as e:
            logger.warning(f"Error creating intelligent summary: {str(e)}, using existing summary or none")
    
    # Step 2: Add summary if available
    if final_summary:
        result_messages.append({
            "role": "system",
            "content": f"Önceki konuşma özeti: {final_summary}"
        })
        used_tokens = estimate_tokens(final_summary)
    
    # Step 3: Always preserve most recent messages (critical for conversation flow)
    # Preserve last N messages (user + assistant pairs)
    recent_messages = messages[-preserve_recent:] if len(messages) > preserve_recent else messages
    recent_tokens = sum(message_tokens[-preserve_recent:]) if len(messages) > preserve_recent else total_tokens
    
    # Step 4: Calculate remaining budget for middle messages
    remaining_budget = max_tokens - used_tokens - recent_tokens
    
    # Step 5: Add middle messages (sliding window) if budget allows
    if remaining_budget > 0 and len(messages) > preserve_recent:
        middle_messages = messages[:-preserve_recent]
        middle_tokens = sum(message_tokens[:-preserve_recent])
        
        if middle_tokens <= remaining_budget:
            # All middle messages fit
            result_messages.extend(middle_messages)
            used_tokens += middle_tokens
        else:
            # Add middle messages from end (most recent first) until budget
            added_middle = []
            added_tokens = 0
            for i in range(len(middle_messages) - 1, -1, -1):
                msg = middle_messages[i]
                msg_tokens = message_tokens[i]
                if added_tokens + msg_tokens <= remaining_budget:
                    added_middle.insert(0, msg)
                    added_tokens += msg_tokens
                else:
                    # Try to compress this message if it's the last one
                    if added_tokens < remaining_budget:
                        compressed = _compress_message(msg, remaining_budget - added_tokens)
                        if compressed:
                            added_middle.insert(0, compressed)
                            added_tokens += estimate_tokens(compressed.get("content", ""))
                            compression_applied = True
                    break
            
            result_messages.extend(added_middle)
            used_tokens += added_tokens
            messages_dropped = len(middle_messages) - len(added_middle)
    
    # Step 6: Add recent messages (always preserved)
    result_messages.extend(recent_messages)
    used_tokens += recent_tokens
    
    # Step 7: Final compression if still over budget
    if used_tokens > max_tokens:
        # Compress oldest messages first (except summary and recent)
        compression_needed = used_tokens - max_tokens
        compressed_count = 0
        
        # Start from after summary (if exists)
        start_idx = 1 if summary else 0
        # End before recent messages
        end_idx = len(result_messages) - preserve_recent
        
        for i in range(start_idx, end_idx):
            if compression_needed <= 0:
                break
            
            msg = result_messages[i]
            original_tokens = estimate_tokens(msg.get("content", ""))
            compressed = _compress_message(msg, max(50, original_tokens - compression_needed))
            
            if compressed:
                compressed_tokens = estimate_tokens(compressed.get("content", ""))
                saved = original_tokens - compressed_tokens
                result_messages[i] = compressed
                compression_needed -= saved
                used_tokens -= saved
                compressed_count += 1
                compression_applied = True
        
        # If still over budget, drop oldest messages (except summary and recent)
        while used_tokens > max_tokens and len(result_messages) > (1 if summary else 0) + preserve_recent:
            dropped = result_messages.pop(1 if summary else 0)
            dropped_tokens = estimate_tokens(dropped.get("content", ""))
            used_tokens -= dropped_tokens
            messages_dropped += 1
    
    logger.info(
        f"Context optimized: {len(result_messages)} messages, {used_tokens}/{max_tokens} tokens, "
        f"dropped={messages_dropped}, compressed={compression_applied}"
    )
    
    return {
        "messages": result_messages,
        "used_tokens": used_tokens,
        "compression_applied": compression_applied,
        "messages_dropped": messages_dropped
    }


def _compress_message(msg: Dict[str, str], target_tokens: int) -> Optional[Dict[str, str]]:
    """
    Intelligently compress a message to fit target token budget.
    Preserves key information while reducing length.
    
    Args:
        msg: Message dict with role and content
        target_tokens: Target token count
        
    Returns:
        Compressed message or None if compression not possible
    """
    content = msg.get("content", "")
    if not content:
        return None
    
    current_tokens = estimate_tokens(content)
    if current_tokens <= target_tokens:
        return msg  # No compression needed
    
    # Calculate compression ratio
    ratio = target_tokens / current_tokens
    
    # Strategy: Keep beginning and end, compress middle
    # This preserves question/answer structure
    lines = content.split('\n')
    if len(lines) <= 3:
        # Short message - truncate from end
        target_chars = int(len(content) * ratio)
        compressed_content = content[:target_chars] + "..."
    else:
        # Long message - keep first and last lines, compress middle
        keep_first = max(1, int(len(lines) * 0.2))  # Keep first 20%
        keep_last = max(1, int(len(lines) * 0.2))   # Keep last 20%
        
        first_part = '\n'.join(lines[:keep_first])
        last_part = '\n'.join(lines[-keep_last:])
        
        # Compress middle part
        middle_lines = lines[keep_first:-keep_last]
        middle_text = '\n'.join(middle_lines)
        middle_target = int(len(middle_text) * ratio * 0.6)  # More aggressive compression for middle
        compressed_middle = middle_text[:middle_target] + "..." if middle_target > 0 else "..."
        
        compressed_content = f"{first_part}\n[... özet ...]\n{compressed_middle}\n[... özet ...]\n{last_part}"
    
    return {
        "role": msg.get("role"),
        "content": compressed_content
    }

