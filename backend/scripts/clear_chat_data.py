"""
Script to clear all chat-related data from MongoDB.
This removes all chats and chat_messages from the database.
"""
import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import connect_to_mongo, close_mongo_connection, get_database


async def clear_chat_data():
    """Clear all chat and message data from database."""
    try:
        # Connect to database
        await connect_to_mongo()
        db = get_database()
        
        if db is None:
            print("ERROR: Could not connect to database")
            return
        
        # Delete all chat messages
        result_messages = await db.chat_messages.delete_many({})
        print(f"Deleted {result_messages.deleted_count} chat messages")
        
        # Delete all chats
        result_chats = await db.chats.delete_many({})
        print(f"Deleted {result_chats.deleted_count} chats")
        
        # Also clear chat summaries and conversation states if they exist
        if "chat_summaries" in await db.list_collection_names():
            result_summaries = await db.chat_summaries.delete_many({})
            print(f"Deleted {result_summaries.deleted_count} chat summaries")
        
        if "conversation_states" in await db.list_collection_names():
            result_states = await db.conversation_states.delete_many({})
            print(f"Deleted {result_states.deleted_count} conversation states")
        
        print("\n✅ All chat data cleared successfully!")
        
    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        await close_mongo_connection()


if __name__ == "__main__":
    print("⚠️  WARNING: This will delete ALL chat data from the database!")
    print("Press Ctrl+C to cancel, or Enter to continue...")
    try:
        input()
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(0)
    
    asyncio.run(clear_chat_data())

