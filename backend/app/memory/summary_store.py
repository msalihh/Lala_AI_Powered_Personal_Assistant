"""
Chat summary storage and management.
Handles rolling summaries for long conversations.
"""
import os
import logging
from typing import Optional
from datetime import datetime

from app.database import get_database

logger = logging.getLogger(__name__)

# Summary configuration
SUMMARY_TRIGGER_COUNT = int(os.getenv("SUMMARY_TRIGGER_COUNT", "40"))  # Create summary after 40 messages
SUMMARY_UPDATE_INTERVAL = int(os.getenv("SUMMARY_UPDATE_INTERVAL", "20"))  # Update summary every 20 new messages
ENABLE_MEMORY = os.getenv("ENABLE_MEMORY", "true").lower() == "true"


async def get_chat_summary(user_id: str, chat_id: str) -> Optional[str]:
    """
    Get chat summary if available.
    
    Args:
        user_id: User ID
        chat_id: Chat ID
        
    Returns:
        Summary text or None
    """
    if not ENABLE_MEMORY:
        return None
    
    try:
        db = get_database()
        if db is None:
            return None
        
        summary_doc = await db.chat_summaries.find_one({
            "user_id": user_id,
            "chat_id": chat_id
        })
        
        if summary_doc:
            return summary_doc.get("summary")
        
        return None
        
    except Exception as e:
        logger.error(f"Memory: Error getting chat summary: {str(e)}", exc_info=True)
        return None


async def get_or_update_chat_summary(
    user_id: str,
    chat_id: str,
    current_message_count: int,
    llm_call_func=None  # Function to call LLM for summary generation
) -> Optional[str]:
    """
    Get or update chat summary based on message count.
    Creates/updates summary if:
    - Message count > SUMMARY_TRIGGER_COUNT
    - Last summary was more than SUMMARY_UPDATE_INTERVAL messages ago
    
    Args:
        user_id: User ID
        chat_id: Chat ID
        current_message_count: Current total message count in chat
        llm_call_func: Optional function to call LLM (for summary generation)
        
    Returns:
        Summary text or None
    """
    if not ENABLE_MEMORY:
        return None
    
    if current_message_count < SUMMARY_TRIGGER_COUNT:
        # Not enough messages for summary
        return await get_chat_summary(user_id, chat_id)
    
    try:
        db = get_database()
        if db is None:
            return None
        
        # Check existing summary
        existing_summary = await db.chat_summaries.find_one({
            "user_id": user_id,
            "chat_id": chat_id
        })
        
        if existing_summary:
            last_count = existing_summary.get("message_count_at_summary", 0)
            if current_message_count - last_count < SUMMARY_UPDATE_INTERVAL:
                # Summary is still fresh
                return existing_summary.get("summary")
        
        # Need to create/update summary
        if not llm_call_func:
            logger.warning("Memory: LLM function not provided, cannot generate summary")
            return existing_summary.get("summary") if existing_summary else None
        
        # Get recent messages for summary (last 30 messages)
        from app.memory.message_store import get_recent_messages
        recent_messages = await get_recent_messages(user_id, chat_id, limit=30)
        if not recent_messages:
            return None
        
        # Build summary prompt
        conversation_text = "\n".join([
            f"{msg['role']}: {msg['content'][:200]}..." if len(msg['content']) > 200 else f"{msg['role']}: {msg['content']}"
            for msg in recent_messages[-20:]  # Last 20 messages
        ])
        
        summary_prompt = f"""Aşağıdaki konuşma geçmişini 10-15 satırlık kısa bir özet haline getir. 
Önemli konuları, soruları ve cevapları özetle. Türkçe yaz.

Konuşma:
{conversation_text}

Özet:"""
        
        try:
            # Call LLM for summary
            summary_messages = [
                {"role": "system", "content": "Sen bir konuşma özetleme asistanısın. Verilen konuşmayı kısa ve öz şekilde özetle."},
                {"role": "user", "content": summary_prompt}
            ]
            
            summary_text = await llm_call_func(summary_messages)
            
            if summary_text:
                # Save/update summary
                await db.chat_summaries.update_one(
                    {
                        "user_id": user_id,
                        "chat_id": chat_id
                    },
                    {
                        "$set": {
                            "summary": summary_text,
                            "message_count_at_summary": current_message_count,
                            "updated_at": datetime.utcnow()
                        }
                    },
                    upsert=True
                )
                
                logger.info(f"Memory: Created/updated summary for chat {chat_id[:8]}...")
                return summary_text
        
        except Exception as e:
            logger.error(f"Memory: Error generating summary: {str(e)}", exc_info=True)
            # Return existing summary if available
            return existing_summary.get("summary") if existing_summary else None
        
        return None
        
    except Exception as e:
        logger.error(f"Memory: Error in get_or_update_chat_summary: {str(e)}", exc_info=True)
        return None

