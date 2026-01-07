"""
Professional memory architecture inspired by human memory systems.
Implements working memory, episodic memory, and semantic memory.
"""
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from app.database import get_database

logger = logging.getLogger(__name__)


class WorkingMemory:
    """
    Working memory: Current conversation context (short-term).
    Similar to human working memory - holds current task information.
    """
    
    def __init__(self, chat_id: str, user_id: str):
        self.chat_id = chat_id
        self.user_id = user_id
        self.current_topic: Optional[str] = None
        self.current_documents: List[str] = []
        self.recent_messages: List[Dict] = []
        self.active_queries: List[str] = []
    
    def update_topic(self, topic: str):
        """Update current conversation topic."""
        self.current_topic = topic
    
    def add_document(self, document_id: str):
        """Add document to current context."""
        if document_id not in self.current_documents:
            self.current_documents.append(document_id)
    
    def add_message(self, message: Dict):
        """Add message to recent context (keep last 10)."""
        self.recent_messages.append(message)
        if len(self.recent_messages) > 10:
            self.recent_messages.pop(0)
    
    def get_context(self) -> Dict[str, Any]:
        """Get current working memory context."""
        return {
            "topic": self.current_topic,
            "documents": self.current_documents,
            "recent_message_count": len(self.recent_messages),
            "active_queries": self.active_queries
        }


class EpisodicMemory:
    """
    Episodic memory: Conversation history and events (long-term).
    Stores what happened, when, and in what context.
    """
    
    @staticmethod
    async def store_episode(
        user_id: str,
        chat_id: str,
        episode_type: str,  # "question", "answer", "document_upload", etc.
        content: str,
        metadata: Optional[Dict] = None
    ):
        """Store an episode in memory."""
        try:
            db = get_database()
            if not db:
                return
            
            episode = {
                "user_id": user_id,
                "chat_id": chat_id,
                "episode_type": episode_type,
                "content": content,
                "metadata": metadata or {},
                "timestamp": datetime.utcnow()
            }
            
            await db.episodic_memory.insert_one(episode)
            logger.debug(f"Episodic memory: Stored {episode_type} episode for chat {chat_id[:8]}...")
        except Exception as e:
            logger.error(f"Episodic memory: Error storing episode: {str(e)}", exc_info=True)
    
    @staticmethod
    async def retrieve_recent_episodes(
        user_id: str,
        chat_id: str,
        limit: int = 20
    ) -> List[Dict]:
        """Retrieve recent episodes from memory."""
        try:
            db = get_database()
            if not db:
                return []
            
            cursor = db.episodic_memory.find({
                "user_id": user_id,
                "chat_id": chat_id
            }).sort("timestamp", -1).limit(limit)
            
            episodes = []
            async for episode in cursor:
                episodes.append({
                    "type": episode.get("episode_type"),
                    "content": episode.get("content"),
                    "metadata": episode.get("metadata", {}),
                    "timestamp": episode.get("timestamp")
                })
            
            return episodes
        except Exception as e:
            logger.error(f"Episodic memory: Error retrieving episodes: {str(e)}", exc_info=True)
            return []


class SemanticMemory:
    """
    Semantic memory: Learned patterns, facts, and knowledge (long-term).
    Stores what the system has learned about the user and domain.
    """
    
    @staticmethod
    async def store_fact(
        user_id: str,
        fact_type: str,  # "preference", "knowledge", "pattern"
        fact_key: str,
        fact_value: Any,
        confidence: float = 1.0
    ):
        """Store a semantic fact in memory."""
        try:
            db = get_database()
            if not db:
                return
            
            fact = {
                "user_id": user_id,
                "fact_type": fact_type,
                "fact_key": fact_key,
                "fact_value": fact_value,
                "confidence": confidence,
                "updated_at": datetime.utcnow()
            }
            
            await db.semantic_memory.update_one(
                {"user_id": user_id, "fact_type": fact_type, "fact_key": fact_key},
                {"$set": fact},
                upsert=True
            )
            logger.debug(f"Semantic memory: Stored {fact_type}/{fact_key}")
        except Exception as e:
            logger.error(f"Semantic memory: Error storing fact: {str(e)}", exc_info=True)
    
    @staticmethod
    async def retrieve_facts(
        user_id: str,
        fact_type: Optional[str] = None,
        min_confidence: float = 0.5
    ) -> List[Dict]:
        """Retrieve semantic facts from memory."""
        try:
            db = get_database()
            if not db:
                return []
            
            query = {"user_id": user_id, "confidence": {"$gte": min_confidence}}
            if fact_type:
                query["fact_type"] = fact_type
            
            cursor = db.semantic_memory.find(query).sort("updated_at", -1)
            
            facts = []
            async for fact in cursor:
                facts.append({
                    "type": fact.get("fact_type"),
                    "key": fact.get("fact_key"),
                    "value": fact.get("fact_value"),
                    "confidence": fact.get("confidence")
                })
            
            return facts
        except Exception as e:
            logger.error(f"Semantic memory: Error retrieving facts: {str(e)}", exc_info=True)
            return []


# Global working memory cache (per chat)
_working_memory_cache: Dict[str, WorkingMemory] = {}


def get_working_memory(chat_id: str, user_id: str) -> WorkingMemory:
    """Get or create working memory for a chat."""
    cache_key = f"{user_id}:{chat_id}"
    if cache_key not in _working_memory_cache:
        _working_memory_cache[cache_key] = WorkingMemory(chat_id, user_id)
    return _working_memory_cache[cache_key]

