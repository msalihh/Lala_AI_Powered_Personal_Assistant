"""
Clear all chat history from MongoDB.
WARNING: This will permanently delete all chats and messages!
"""
import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import connect_to_mongo, close_mongo_connection, get_database
from dotenv import load_dotenv

load_dotenv()


async def clear_all_chat_history():
    """
    Delete all chats and messages from MongoDB.
    """
    # Connect to MongoDB
    await connect_to_mongo()
    
    db = get_database()
    if db is None:
        print("ERROR: Database connection failed")
        return
    
    try:
        # Delete all messages
        messages_result = await db.chat_messages.delete_many({})
        print(f"Deleted {messages_result.deleted_count} messages")
        
        # Delete all chats
        chats_result = await db.chats.delete_many({})
        print(f"Deleted {chats_result.deleted_count} chats")
        
        # Delete all conversation states
        states_result = await db.conversation_states.delete_many({})
        print(f"Deleted {states_result.deleted_count} conversation states")
        
        # Delete all chat summaries
        summaries_result = await db.chat_summaries.delete_many({})
        print(f"Deleted {summaries_result.deleted_count} chat summaries")
        
        print("\n[OK] All chat history cleared successfully!")
        
    except Exception as e:
        print(f"ERROR: Failed to clear chat history: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        # Close MongoDB connection
        await close_mongo_connection()


if __name__ == "__main__":
    print("WARNING: This will delete ALL chat history!")
    print("Press Ctrl+C to cancel, or wait 3 seconds to continue...")
    
    try:
        import time
        time.sleep(3)
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(0)
    
    asyncio.run(clear_all_chat_history())

