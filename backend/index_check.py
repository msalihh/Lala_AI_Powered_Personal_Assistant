import motor.motor_asyncio
import asyncio

async def check_indexes():
    client = motor.motor_asyncio.AsyncIOMotorClient('mongodb://localhost:27017')
    db = client.auth_db
    collection = db.chat_messages
    indexes = await collection.index_information()
    
    print("CURRENT INDEXES for chat_messages:")
    import json
    print(json.dumps(indexes, indent=2))
    
    # Also check other collections
    chats_indexes = await db.chats.index_information()
    print("\nCURRENT INDEXES for chats:")
    print(json.dumps(chats_indexes, indent=2))
    
    # client.close() is not needed in motor as it's managed, but if you want to:
    client.close()

if __name__ == "__main__":
    asyncio.run(check_indexes())
