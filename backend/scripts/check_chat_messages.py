"""Quick script to check chat messages for a specific chat_id"""
import asyncio
from bson import ObjectId
from app.database import connect_to_mongo, get_database

async def check_chat(chat_id: str):
    await connect_to_mongo()
    db = get_database()
    
    chat_obj = ObjectId(chat_id)
    
    # Check chat
    chat = await db.chats.find_one({'_id': chat_obj})
    print(f"=== Chat Info ===")
    print(f"Chat found: {chat is not None}")
    if chat:
        print(f"Chat _id: {chat.get('_id')}")
        print(f"Chat user_id: {chat.get('user_id')} (type: {type(chat.get('user_id')).__name__})")
        print(f"Chat title: {chat.get('title')}")
        print(f"Chat last_message_at: {chat.get('last_message_at')}")
        print(f"Chat deleted_at: {chat.get('deleted_at')}")
    
    # Check messages with ObjectId
    print(f"\n=== Messages Check ===")
    messages_count_obj = await db.chat_messages.count_documents({'chat_id': chat_obj})
    print(f"Messages with ObjectId chat_id: {messages_count_obj}")
    
    # Check messages with string
    messages_count_str = await db.chat_messages.count_documents({'chat_id': chat_id})
    print(f"Messages with string chat_id: {messages_count_str}")
    
    # Get sample messages
    messages = await db.chat_messages.find({'chat_id': chat_obj}).limit(5).to_list(length=5)
    print(f"\n=== Sample Messages (ObjectId query) ===")
    for msg in messages:
        msg_chat_id = msg.get('chat_id')
        print(f"  - _id: {msg.get('_id')}")
        print(f"    chat_id: {msg_chat_id} (type: {type(msg_chat_id).__name__})")
        print(f"    role: {msg.get('role')}")
        print(f"    content: {msg.get('content', '')[:50]}...")
        print()
    
    # Check all chat_ids in messages collection (sample)
    print(f"=== All chat_id formats in messages (sample) ===")
    all_messages = await db.chat_messages.find({}).limit(10).to_list(length=10)
    chat_id_types = {}
    for msg in all_messages:
        cid = msg.get('chat_id')
        cid_type = type(cid).__name__
        chat_id_types[cid_type] = chat_id_types.get(cid_type, 0) + 1
    print(f"Chat_id type distribution: {chat_id_types}")
    
    # Check user_id matching
    if chat:
        user_id_from_chat = chat.get('user_id')
        print(f"\n=== User ID Matching Check ===")
        print(f"Chat user_id: {user_id_from_chat} (type: {type(user_id_from_chat).__name__})")
        
        messages_with_user = await db.chat_messages.find({'chat_id': chat_obj}).limit(5).to_list(length=5)
        print(f"\nMessages user_id check:")
        for msg in messages_with_user:
            msg_user_id = msg.get('user_id')
            print(f"  Message user_id: {msg_user_id} (type: {type(msg_user_id).__name__})")
            print(f"  Match with chat user_id: {msg_user_id == user_id_from_chat}")
            print(f"  Match with str(chat user_id): {msg_user_id == str(user_id_from_chat)}")
        
        # Test query that backend uses
        query_test = {'user_id': str(user_id_from_chat), 'chat_id': chat_obj}
        count = await db.chat_messages.count_documents(query_test)
        print(f"\nBackend query test: {{user_id: str('{user_id_from_chat}'), chat_id: ObjectId('{chat_id}')}}")
        print(f"Result count: {count}")

if __name__ == "__main__":
    import sys
    chat_id = sys.argv[1] if len(sys.argv) > 1 else "694edac6ba683ba8d0ccf3a4"
    asyncio.run(check_chat(chat_id))

