"""
MongoDB database configuration and connection.
"""
from motor.motor_asyncio import AsyncIOMotorClient
from typing import Optional
import os

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
        print(f"[OK] MongoDB'ye basariyla baglandi: {DATABASE_NAME}")
        
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
            print("[OK] chat_messages index olusturuldu: (user_id, chat_id, created_at) ve (chat_id, created_at)")
            
            # Unique index for idempotency: (user_id, chat_id, client_message_id)
            # Only create if client_message_id exists (not null)
            # CRITICAL: MongoDB partial indexes don't support $ne, use $exists instead
            try:
                # Check if index already exists
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
                    print("[OK] chat_messages unique index olusturuldu: (user_id, chat_id, client_message_id)")
                else:
                    print("[OK] chat_messages unique index zaten mevcut: (user_id, chat_id, client_message_id)")
            except Exception as unique_e:
                # Check if it's a duplicate key error (index exists but with different format)
                error_str = str(unique_e).lower()
                if "duplicatekey" in error_str or "e11000" in error_str:
                    print("[INFO] Unique index zaten mevcut (farkli format), skip ediliyor")
                else:
                    print(f"[WARN] Unique index olusturma hatasi: {unique_e}")
        except Exception as e:
            print(f"[WARN] Index olusturma hatasi (zaten var olabilir): {e}")
        
        # Create indexes for chats collection (user isolation)
        try:
            # Index for fast chat list queries: (user_id, updated_at DESC)
            await database.chats.create_index([
                ("user_id", 1),
                ("updated_at", -1)
            ])
            # Index for soft delete filter: (user_id, deleted_at)
            await database.chats.create_index([
                ("user_id", 1),
                ("deleted_at", 1)
            ])
            # Index for ownership checks: (user_id, _id)
            await database.chats.create_index([
                ("user_id", 1),
                ("_id", 1)
            ])
            print("[OK] chats index olusturuldu: (user_id, updated_at DESC), (user_id, deleted_at), (user_id, _id)")
        except Exception as e:
            print(f"[WARN] Index olusturma hatasi (zaten var olabilir): {e}")
        
        # Create indexes for conversation_states collection
        try:
            await database.conversation_states.create_index([
                ("user_id", 1),
                ("chat_id", 1)
            ], unique=True)
            print("[OK] conversation_states index olusturuldu: (user_id, chat_id)")
        except Exception as e:
            print(f"[WARN] conversation_states index olusturma hatasi (zaten var olabilir): {e}")
        
        # Create indexes for chat_summaries collection
        try:
            await database.chat_summaries.create_index([
                ("user_id", 1),
                ("chat_id", 1)
            ], unique=True)
            print("[OK] chat_summaries index olusturuldu: (user_id, chat_id)")
        except Exception as e:
            print(f"[WARN] chat_summaries index olusturma hatasi (zaten var olabilir): {e}")
            
    except Exception as e:
        print(f"[ERROR] MongoDB baglanti hatasi: {e}")
        raise


async def close_mongo_connection():
    """
    Close MongoDB connection.
    """
    global client
    if client:
        client.close()
        print("MongoDB bağlantısı kapatıldı")


def get_database():
    """
    Get MongoDB database instance.
    """
    return database
