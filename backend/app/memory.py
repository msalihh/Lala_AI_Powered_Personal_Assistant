"""
Chat history memory persistence.
Stores and retrieves conversation messages for context.
"""
import os
import logging
from typing import List, Dict, Optional
from datetime import datetime
from bson import ObjectId

from app.database import get_database
from app.schemas import SourceInfo
from app.utils import estimate_tokens

logger = logging.getLogger(__name__)

# Environment flag to enable/disable memory
ENABLE_MEMORY = os.getenv("ENABLE_MEMORY", "true").lower() == "true"

# Context window configuration
CONTEXT_MAX_TOKENS = int(os.getenv("CONTEXT_MAX_TOKENS", "2000"))  # Default 2000 tokens
CONTEXT_HARD_LIMIT = int(os.getenv("CONTEXT_HARD_LIMIT", "50"))  # Max 50 messages

# Summary configuration
SUMMARY_TRIGGER_COUNT = int(os.getenv("SUMMARY_TRIGGER_COUNT", "40"))  # Create summary after 40 messages
SUMMARY_UPDATE_INTERVAL = int(os.getenv("SUMMARY_UPDATE_INTERVAL", "20"))  # Update summary every 20 new messages


async def save_message(
    user_id: str,
    chat_id: str,
    role: str,
    content: str,
    sources: Optional[List[SourceInfo]] = None,
    client_message_id: Optional[str] = None,
    document_ids: Optional[List[str]] = None,
    used_documents: Optional[bool] = None
) -> bool:
    """
    Save a message to chat history with idempotency support.
    If client_message_id is provided and already exists, skip duplicate insert.
    
    Args:
        user_id: User ID
        chat_id: Chat ID
        role: Message role ("user" or "assistant")
        content: Message content
        sources: Optional RAG sources
        client_message_id: Optional client message ID for deduplication
        
    Returns:
        True if saved successfully (or already exists), False otherwise
    """
    if not ENABLE_MEMORY:
        return False
    
    try:
        db = get_database()
        if db is None:
            logger.warning("Memory: Database not available, skipping message save")
            return False
        
        # Idempotency check: if client_message_id provided, check for duplicate
        if client_message_id:
            existing = await db.chat_messages.find_one({
                "user_id": user_id,
                "chat_id": chat_id,
                "client_message_id": client_message_id
            })
            if existing:
                logger.debug(f"Memory: Message with client_message_id {client_message_id[:8]}... already exists, skipping duplicate")
                return True  # Already exists, consider it success
        
        # Convert sources to dict for storage
        sources_dict = None
        if sources:
            sources_dict = [
                {
                    "documentId": s.documentId,
                    "filename": s.filename,
                    "chunkIndex": s.chunkIndex,
                    "score": s.score,
                    "preview": s.preview
                }
                for s in sources
            ]
        
        message_doc = {
            "user_id": user_id,
            "chat_id": chat_id,
            "role": role,
            "content": content,
            "sources": sources_dict,
            "client_message_id": client_message_id,
            "created_at": datetime.utcnow()
        }
        
        # Add document_ids for user messages
        if document_ids is not None:
            message_doc["document_ids"] = document_ids
        
        # Add used_documents flag for assistant messages
        if used_documents is not None:
            message_doc["used_documents"] = used_documents
        
        await db.chat_messages.insert_one(message_doc)
        logger.debug(f"Memory: Saved {role} message for chat {chat_id[:8]}...")
        return True
        
    except Exception as e:
        # Handle duplicate key error (if unique index exists)
        error_str = str(e).lower()
        if "duplicate" in error_str or "e11000" in error_str:
            logger.debug(f"Memory: Duplicate message detected (idempotency), skipping: {str(e)}")
            return True  # Duplicate is considered success
        
        logger.error(f"Memory: Error saving message: {str(e)}", exc_info=True)
        return False


async def get_recent_messages(
    user_id: str,
    chat_id: str,
    limit: int = 20
) -> List[Dict]:
    """
    Get recent messages from chat history.
    First verifies chat ownership, then retrieves messages.
    
    Args:
        user_id: User ID
        chat_id: Chat ID
        limit: Maximum number of messages to return (default: 20)
        
    Returns:
        List of message dictionaries with role and content
    """
    if not ENABLE_MEMORY:
        return []
    
    try:
        db = get_database()
        if db is None:
            logger.warning("Memory: Database not available, returning empty history")
            return []
        
        # First verify chat ownership exists
        try:
            chat_object_id = ObjectId(chat_id)
        except Exception:
            logger.warning(f"Memory: Invalid chat_id format: {chat_id}")
            return []
        
        chat = await db.chats.find_one({"_id": chat_object_id, "user_id": user_id})
        
        if not chat:
            logger.warning(f"Memory: Chat {chat_id[:8]}... not found or access denied for user {user_id[:8]}...")
            return []
        
        # Query messages for this user and chat, ordered by creation time
        cursor = db.chat_messages.find(
            {
                "user_id": user_id,
                "chat_id": chat_id
            },
            {
                "role": 1,
                "content": 1,
                "created_at": 1
            }
        ).sort("created_at", 1).limit(limit)
        
        messages = []
        async for msg in cursor:
            messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", "")
            })
        
        logger.debug(f"Memory: Retrieved {len(messages)} messages for chat {chat_id[:8]}...")
        return messages
        
    except Exception as e:
        logger.error(f"Memory: Error retrieving messages: {str(e)}", exc_info=True)
        return []


async def build_context_messages(
    user_id: str,
    chat_id: str,
    max_tokens: int = CONTEXT_MAX_TOKENS,
    hard_limit: int = CONTEXT_HARD_LIMIT
) -> List[Dict]:
    """
    Build context messages with dynamic token budget.
    Fetches messages from newest to oldest, adding until token budget is reached.
    Always includes at least: last user message, last assistant message, and summary if available.
    
    Args:
        user_id: User ID
        chat_id: Chat ID
        max_tokens: Maximum token budget for context (default from env)
        hard_limit: Hard limit on number of messages (default 50)
        
    Returns:
        List of message dictionaries with role and content, ordered chronologically
    """
    if not ENABLE_MEMORY:
        return []
    
    try:
        db = get_database()
        if db is None:
            logger.warning("Memory: Database not available, returning empty context")
            return []
        
        # Verify chat ownership
        try:
            chat_object_id = ObjectId(chat_id)
        except Exception:
            logger.warning(f"Memory: Invalid chat_id format: {chat_id}")
            return []
        
        chat = await db.chats.find_one({"_id": chat_object_id, "user_id": user_id})
        if not chat:
            logger.warning(f"Memory: Chat {chat_id[:8]}... not found or access denied")
            return []
        
        # Fetch recent messages (up to hard_limit, ordered newest first)
        cursor = db.chat_messages.find(
            {
                "user_id": user_id,
                "chat_id": chat_id
            },
            {
                "role": 1,
                "content": 1,
                "created_at": 1
            }
        ).sort("created_at", -1).limit(hard_limit)  # Newest first
        
        all_messages = []
        async for msg in cursor:
            all_messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", "")
            })
        
        if not all_messages:
            return []
        
        # Reverse to get chronological order (oldest first)
        all_messages.reverse()
        
        # Get summary if available
        summary = await get_chat_summary(user_id, chat_id)
        summary_message = None
        if summary:
            summary_message = {
                "role": "system",
                "content": f"CHAT SUMMARY (önceki konuşma özeti):\n{summary}"
            }
        
        # Build context with token budget
        context_messages = []
        current_tokens = 0
        
        # Always include summary first (if available)
        if summary_message:
            summary_tokens = estimate_tokens(summary_message["content"])
            if summary_tokens <= max_tokens:
                context_messages.append(summary_message)
                current_tokens += summary_tokens
        
        # Track required messages (last user and last assistant)
        last_user_idx = None
        last_assistant_idx = None
        for i in range(len(all_messages) - 1, -1, -1):
            if all_messages[i]["role"] == "user" and last_user_idx is None:
                last_user_idx = i
            if all_messages[i]["role"] == "assistant" and last_assistant_idx is None:
                last_assistant_idx = i
            if last_user_idx is not None and last_assistant_idx is not None:
                break
        
        # Add messages from newest to oldest until token budget
        # But always include required messages
        required_indices = set()
        if last_user_idx is not None:
            required_indices.add(last_user_idx)
        if last_assistant_idx is not None:
            required_indices.add(last_assistant_idx)
        
        # First pass: add required messages
        for idx in sorted(required_indices):
            msg = all_messages[idx]
            msg_tokens = estimate_tokens(msg["content"])
            if current_tokens + msg_tokens <= max_tokens:
                context_messages.append(msg)
                current_tokens += msg_tokens
        
        # Second pass: add remaining messages (newest first) until budget
        for i in range(len(all_messages) - 1, -1, -1):
            if i in required_indices:
                continue  # Already added
            
            msg = all_messages[i]
            msg_tokens = estimate_tokens(msg["content"])
            
            if current_tokens + msg_tokens <= max_tokens:
                # Insert before required messages (to maintain chronological order)
                insert_pos = len(context_messages) - len(required_indices)
                context_messages.insert(insert_pos, msg)
                current_tokens += msg_tokens
            else:
                # Budget exceeded, stop
                break
        
        logger.info(
            f"Memory: Built context with {len(context_messages)} messages, "
            f"~{current_tokens} tokens (budget: {max_tokens})"
        )
        
        return context_messages
        
    except Exception as e:
        logger.error(f"Memory: Error building context: {str(e)}", exc_info=True)
        return []


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


async def delete_chat_messages(user_id: str, chat_id: str) -> int:
    """
    Delete all messages for a chat (cleanup).
    
    Args:
        user_id: User ID
        chat_id: Chat ID
        
    Returns:
        Number of messages deleted
    """
    if not ENABLE_MEMORY:
        return 0
    
    try:
        db = get_database()
        if db is None:
            return 0
        
        result = await db.chat_messages.delete_many({
            "user_id": user_id,
            "chat_id": chat_id
        })
        
        deleted_count = result.deleted_count
        logger.info(f"Memory: Deleted {deleted_count} messages for chat {chat_id[:8]}...")
        return deleted_count
        
    except Exception as e:
        logger.error(f"Memory: Error deleting messages: {str(e)}", exc_info=True)
        return 0

