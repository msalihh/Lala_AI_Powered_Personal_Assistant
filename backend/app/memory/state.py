"""
Conversation state management.
Tracks last topic, intent, domain, and follow-up context.
"""
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from bson import ObjectId
from dataclasses import dataclass, asdict

from app.database import get_database

logger = logging.getLogger(__name__)


@dataclass
class ConversationState:
    """
    Conversation state for carryover detection.
    """
    last_topic: Optional[str] = None  # Last topic discussed (e.g., "karekök", "radikaller")
    last_intent: Optional[str] = None  # Last intent (qa, summarize, extract)
    last_user_question: Optional[str] = None  # Last user question text
    last_domain: Optional[str] = None  # Domain: "math", "coding", "general"
    unresolved_followup: bool = False  # Flag indicating if there's an unresolved follow-up
    last_document_ids: Optional[list] = None  # Last document IDs used
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationState":
        """Create from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


async def get_conversation_state(user_id: str, chat_id: str) -> ConversationState:
    """
    Get conversation state for a chat.
    
    Args:
        user_id: User ID
        chat_id: Chat ID
        
    Returns:
        ConversationState object
    """
    try:
        db = get_database()
        if db is None:
            return ConversationState()
        
        try:
            chat_object_id = ObjectId(chat_id)
        except Exception:
            logger.warning(f"Memory: Invalid chat_id format: {chat_id}")
            return ConversationState()
        
        state_doc = await db.conversation_states.find_one({
            "user_id": user_id,
            "chat_id": chat_id
        })
        
        if state_doc:
            state_data = state_doc.get("state", {})
            return ConversationState.from_dict(state_data)
        
        return ConversationState()
        
    except Exception as e:
        logger.error(f"Memory: Error getting conversation state: {str(e)}", exc_info=True)
        return ConversationState()


async def update_conversation_state(
    user_id: str,
    chat_id: str,
    state: ConversationState
) -> bool:
    """
    Update conversation state for a chat.
    
    Args:
        user_id: User ID
        chat_id: Chat ID
        state: ConversationState to save
        
    Returns:
        True if successful, False otherwise
    """
    try:
        db = get_database()
        if db is None:
            return False
        
        try:
            chat_object_id = ObjectId(chat_id)
        except Exception:
            logger.warning(f"Memory: Invalid chat_id format: {chat_id}")
            return False
        
        await db.conversation_states.update_one(
            {
                "user_id": user_id,
                "chat_id": chat_id
            },
            {
                "$set": {
                    "state": state.to_dict(),
                    "updated_at": datetime.utcnow()
                }
            },
            upsert=True
        )
        
        logger.debug(f"Memory: Updated conversation state for chat {chat_id[:8]}...")
        return True
        
    except Exception as e:
        logger.error(f"Memory: Error updating conversation state: {str(e)}", exc_info=True)
        return False

