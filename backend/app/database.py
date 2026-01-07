"""
MongoDB database configuration and connection.
"""
from motor.motor_asyncio import AsyncIOMotorClient
from typing import Optional
import os
import logging

logger = logging.getLogger(__name__)

# MongoDB connection URL
MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017/")
DATABASE_NAME = os.getenv("DATABASE_NAME", "auth_db")

# Global MongoDB client
client: Optional[AsyncIOMotorClient] = None
database = None


async def connect_to_mongo():
    """
    Connect to MongoDB and create indexes for performance.
    """
    global client, database
    try:
        client = AsyncIOMotorClient(MONGODB_URL)
        database = client[DATABASE_NAME]
        # Test connection
        await client.admin.command('ping')
        logger.info(f"MongoDB connected successfully: {DATABASE_NAME}")
        
        # Create indexes for chat_messages collection (performance optimization)
        try:
            # Index for fast chat history queries: (user_id, chat_id, created_at)
            await database.chat_messages.create_index([
                ("user_id", 1),
                ("chat_id", 1),
                ("created_at", 1)
            ])
            # Index for cursor pagination: (chat_id, created_at ASC)
            await database.chat_messages.create_index([
                ("chat_id", 1),
                ("created_at", 1)
            ])
            logger.debug("chat_messages indexes created")
            
            # Unique index for idempotency: (user_id, chat_id, client_message_id)
            try:
                existing_indexes = await database.chat_messages.list_indexes().to_list(length=100)
                index_exists = any(
                    idx.get("name") == "user_id_1_chat_id_1_client_message_id_1"
                    for idx in existing_indexes
                )
                
                if not index_exists:
                    await database.chat_messages.create_index([
                        ("user_id", 1),
                        ("chat_id", 1),
                        ("client_message_id", 1)
                    ], unique=True, partialFilterExpression={"client_message_id": {"$exists": True}})
                    logger.debug("chat_messages unique index created")
            except Exception as unique_e:
                error_str = str(unique_e).lower()
                if "duplicatekey" not in error_str and "e11000" not in error_str:
                    logger.warning(f"Unique index creation issue: {unique_e}")
        except Exception as e:
            logger.warning(f"Index creation issue (may already exist): {e}")
        
        # Create indexes for chats collection (user isolation)
        try:
            await database.chats.create_index([
                ("user_id", 1),
                ("updated_at", -1)
            ])
            await database.chats.create_index([
                ("user_id", 1),
                ("deleted_at", 1)
            ])
            await database.chats.create_index([
                ("user_id", 1),
                ("_id", 1)
            ])
            logger.debug("chats indexes created")
        except Exception as e:
            logger.warning(f"Index creation issue (may already exist): {e}")
        
        # Create indexes for conversation_states collection
        try:
            await database.conversation_states.create_index([
                ("user_id", 1),
                ("chat_id", 1)
            ], unique=True)
            logger.debug("conversation_states index created")
        except Exception as e:
            logger.warning(f"conversation_states index issue (may already exist): {e}")
        
        # Create indexes for chat_summaries collection
        try:
            await database.chat_summaries.create_index([
                ("user_id", 1),
                ("chat_id", 1)
            ], unique=True)
            logger.debug("chat_summaries index created")
        except Exception as e:
            logger.warning(f"chat_summaries index issue (may already exist): {e}")
            
        # Create indexes for oauth_states collection (Gmail OAuth CSRF protection)
        try:
            await database.oauth_states.create_index([
                ("state", 1)
            ], unique=True)
            # TTL index: automatically delete documents after expires_at time
            # expireAfterSeconds=0 means use the expires_at field value directly
            await database.oauth_states.create_index([
                ("expires_at", 1)
            ], expireAfterSeconds=0)  # TTL index for automatic cleanup
            logger.debug("oauth_states indexes created")
        except Exception as e:
            logger.warning(f"oauth_states index issue (may already exist): {e}")
        
        # Create indexes for user_integrations collection (Gmail tokens)
        try:
            await database.user_integrations.create_index([
                ("user_id", 1),
                ("provider", 1)
            ], unique=True)
            logger.debug("user_integrations index created")
        except Exception as e:
            logger.warning(f"user_integrations index issue (may already exist): {e}")
        
        # Create indexes for memory architecture collections
        try:
            # Episodic memory indexes
            await database.episodic_memory.create_index([
                ("user_id", 1),
                ("chat_id", 1),
                ("timestamp", -1)
            ])
            await database.episodic_memory.create_index([
                ("user_id", 1),
                ("episode_type", 1)
            ])
            logger.debug("episodic_memory indexes created")
        except Exception as e:
            logger.warning(f"episodic_memory index issue (may already exist): {e}")
        
        try:
            # Semantic memory indexes
            await database.semantic_memory.create_index([
                ("user_id", 1),
                ("fact_type", 1),
                ("fact_key", 1)
            ], unique=True)
            await database.semantic_memory.create_index([
                ("user_id", 1),
                ("updated_at", -1)
            ])
            logger.debug("semantic_memory indexes created")
        except Exception as e:
            logger.warning(f"semantic_memory index issue (may already exist): {e}")
            
    except Exception as e:
        logger.error(f"MongoDB connection error: {e}")
        raise


async def close_mongo_connection():
    """
    Close MongoDB connection.
    """
    global client
    if client:
        client.close()
        logger.info("MongoDB connection closed")


def get_database():
    """
    Get MongoDB database instance.
    """
    return database

