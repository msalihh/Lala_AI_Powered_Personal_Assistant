"""
Message storage for chat history persistence.
Clean, simple implementation for saving and retrieving chat messages.
"""
import logging
from typing import List, Dict, Optional
from datetime import datetime
from bson import ObjectId

from app.database import get_database
from app.schemas import SourceInfo

logger = logging.getLogger(__name__)


async def save_message(
    user_id: str,
    chat_id: str,
    role: str,
    content: str,
    sources: Optional[List[SourceInfo]] = None,
    client_message_id: Optional[str] = None,
    document_ids: Optional[List[str]] = None,  # For user messages: which documents were attached
    used_documents: Optional[bool] = None,  # For assistant messages: whether documents were used
    is_partial: Optional[bool] = None,  # For assistant messages: whether message is partial (streaming/cancelled)
    run_id: Optional[str] = None,  # For assistant messages: associated run_id
    module: Optional[str] = None,  # Module that generated this (e.g., "lgs_karekok", "none")
    model: Optional[str] = None,  # Model used (e.g., "deepseek/deepseek-r1-0528:free")
    system_prompt_version: Optional[str] = None  # System prompt version (e.g., "v1", "v2")
) -> Optional[str]:
    """
    Save a message to chat history.
    
    Args:
        user_id: User ID (string)
        chat_id: Chat ID (string, 24 hex characters - stored as string in MongoDB)
        role: Message role ("user" or "assistant")
        content: Message content
        sources: Optional RAG sources (for assistant messages)
        client_message_id: Optional client message ID for deduplication
        document_ids: Optional list of document IDs attached to user message
        used_documents: Optional flag indicating if assistant used documents (for assistant messages)
        
    Returns:
        Message ID (string) if saved successfully, None otherwise
    """
    try:
        db = get_database()
        if db is None:
            logger.warning("Message store: Database not available")
            return False
        
        # Normalize user_id to string
        normalized_user_id = str(user_id)
        
        # Validate chat_id format (24 hex characters) but keep as string
        # CRITICAL FIX: chat_id is stored as string in MongoDB, not ObjectId
        if not chat_id or not isinstance(chat_id, str):
            logger.error(f"Message store: Invalid chat_id format: chat_id must be string, got {type(chat_id).__name__}")
            return False
        
        chat_id = chat_id.strip()
        if len(chat_id) != 24 or not all(c in '0123456789abcdefABCDEF' for c in chat_id):
            logger.error(f"Message store: Invalid chat_id format: must be 24 hex characters, got length {len(chat_id)}")
            return False
        
        # Keep chat_id as string (don't convert to ObjectId)
        normalized_chat_id = chat_id
        
        # Check for duplicate if client_message_id provided
        if client_message_id:
            existing = await db.chat_messages.find_one({
                "user_id": normalized_user_id,
                "chat_id": normalized_chat_id,  # String
                "client_message_id": client_message_id
            })
            if existing:
                logger.debug(f"Message store: Duplicate message with client_message_id {client_message_id[:8]}... skipped")
                return str(existing["_id"])  # Return existing message ID
        
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
        
        # Create message document
        message_doc = {
            "user_id": normalized_user_id,
            "chat_id": normalized_chat_id,  # String (24 hex)
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
        
        # Add is_partial flag for assistant messages (default: False if not provided)
        if is_partial is not None:
            message_doc["is_partial"] = is_partial
        elif role == "assistant":
            message_doc["is_partial"] = False  # Default to False for assistant messages
        
        # Add run_id for assistant messages
        if run_id is not None:
            message_doc["run_id"] = run_id
        
        # Add metadata for tracking (module, model, prompt version)
        if module is not None:
            message_doc["module"] = module
        if model is not None:
            message_doc["model"] = model
        if system_prompt_version is not None:
            message_doc["system_prompt_version"] = system_prompt_version
        
        # Insert or update message (if run_id provided, try to update existing message)
        if run_id and role == "assistant":
            # Try to find existing message with this run_id
            existing = await db.chat_messages.find_one({
                "user_id": normalized_user_id,
                "chat_id": normalized_chat_id,
                "run_id": run_id,
                "role": "assistant"
            })
            if existing:
                # Update existing message
                await db.chat_messages.update_one(
                    {"_id": existing["_id"]},
                    {"$set": message_doc}
                )
                inserted_id = str(existing["_id"])
                logger.info(f"[CHATDBG] save_message chatId={normalized_chat_id} userId={normalized_user_id} role={role} message_id={inserted_id} run_id={run_id} status=updated")
                return inserted_id
        
        # Insert new message
        result = await db.chat_messages.insert_one(message_doc)
        inserted_id = str(result.inserted_id)
        logger.info(f"[CHATDBG] save_message chatId={normalized_chat_id} userId={normalized_user_id} role={role} inserted_id={inserted_id} run_id={run_id} is_partial={is_partial} status=saved")
        return inserted_id
        
    except Exception as e:
        logger.error(f"Message store: Error saving message: {str(e)}", exc_info=True)
        return None


async def get_recent_messages(
    user_id: str,
    chat_id: str,
    limit: int = 20
) -> List[Dict]:
    """
    Get recent messages from chat history.
    
    Args:
        user_id: User ID (string)
        chat_id: Chat ID (string, 24 hex characters - stored as string in MongoDB)
        limit: Maximum number of messages to return
        
    Returns:
        List of message dictionaries with role and content
    """
    try:
        db = get_database()
        if db is None:
            logger.warning("Message store: Database not available")
            return []
        
        # Validate chat_id format but keep as string
        if not chat_id or not isinstance(chat_id, str) or len(chat_id) != 24:
            logger.warning(f"Message store: Invalid chat_id format: {chat_id}")
            return []
        
        # Normalize user_id to string
        normalized_user_id = str(user_id)
        
        # Verify chat ownership (chats._id is ObjectId, so convert for query)
        try:
            chat_object_id = ObjectId(chat_id)
        except (ValueError, TypeError):
            logger.warning(f"Message store: Invalid chat_id format for ObjectId conversion: {chat_id}")
            return []
        
        chat = await db.chats.find_one({
            "_id": chat_object_id,
            "user_id": normalized_user_id
        })
        
        if not chat:
            logger.warning(f"Message store: Chat {chat_id[:8]}... not found or access denied")
            return []
        
        # Query messages (chat_messages.chat_id is string)
        query = {
            "user_id": normalized_user_id,
            "chat_id": chat_id  # String
        }
        
        cursor = db.chat_messages.find(
            query,
            {
                "role": 1,
                "content": 1,
                "created_at": 1
            }
        ).sort("created_at", 1).limit(limit)
        
        messages = []
        async for msg in cursor:
            # CRITICAL FIX: Only include role and content (JSON serializable fields)
            # created_at is not needed for LLM context and causes JSON serialization errors
            messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", "")
            })
        
        return messages
        
    except Exception as e:
        logger.error(f"Message store: Error getting messages: {str(e)}", exc_info=True)
        return []


async def build_context_messages(
    user_id: str,
    chat_id: str,
    max_tokens: int = 2000,
    hard_limit: int = 50,
    summary: Optional[str] = None,
    llm_call_func=None  # Optional LLM function for intelligent summarization
) -> List[Dict]:
    """
    Build optimized context messages using ChatGPT-style sliding window + compression.
    Returns messages in chronological order (oldest first).
    
    Professional AI tools (ChatGPT/Claude) use:
    - Sliding window: Keep recent messages + summary of older ones
    - Intelligent compression: Preserve key information while reducing tokens
    - Token-aware prioritization: Most recent messages always preserved
    
    Args:
        user_id: User ID (string)
        chat_id: Chat ID (string, 24 hex characters - stored as string in MongoDB)
        max_tokens: Maximum tokens for context (strictly enforced)
        hard_limit: Maximum number of messages to fetch from DB
        summary: Optional summary of older messages (for compression)
        
    Returns:
        List of message dictionaries with role and content (optimized)
    """
    try:
        db = get_database()
        if db is None:
            logger.warning("Message store: Database not available")
            return []
        
        # Validate chat_id format but keep as string
        if not chat_id or not isinstance(chat_id, str) or len(chat_id) != 24:
            logger.warning(f"Message store: Invalid chat_id format: {chat_id}")
            return []
        
        # Normalize user_id to string
        normalized_user_id = str(user_id)
        
        # Verify chat ownership (chats._id is ObjectId, so convert for query)
        try:
            chat_object_id = ObjectId(chat_id)
        except (ValueError, TypeError):
            logger.warning(f"Message store: Invalid chat_id format for ObjectId conversion: {chat_id}")
            return []
        
        chat = await db.chats.find_one({
            "_id": chat_object_id,
            "user_id": normalized_user_id
        })
        
        if not chat:
            logger.warning(f"Message store: Chat {chat_id[:8]}... not found or access denied")
            return []
        
        # Query messages (newest first, then reverse) - chat_messages.chat_id is string
        query = {
            "user_id": normalized_user_id,
            "chat_id": chat_id,  # String
            "is_partial": {"$ne": True}  # Exclude partial messages
        }
        
        cursor = db.chat_messages.find(
            query,
            {
                "role": 1,
                "content": 1,
                "created_at": 1
            }
        ).sort("created_at", -1).limit(hard_limit)
        
        messages = []
        async for msg in cursor:
            messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
            })
        
        # Reverse to get chronological order (oldest first)
        messages.reverse()
        
        # Apply ChatGPT-style optimization with intelligent summarization
        from app.memory.context_optimizer import build_optimized_context
        optimized = await build_optimized_context(
            messages=messages,
            max_tokens=max_tokens,
            summary=summary,
            preserve_recent=6,  # Always keep last 6 messages (3 user + 3 assistant pairs)
            llm_call_func=llm_call_func  # Pass LLM function for intelligent summarization
        )
        
        return optimized["messages"]
        
    except Exception as e:
        logger.error(f"Message store: Error building context: {str(e)}", exc_info=True)
        return []
