import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os

MONGODB_URL = "mongodb://localhost:27017/"
DATABASE_NAME = "auth_db"

async def fix_indexes():
    print(f"Connecting to {MONGODB_URL}...")
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client[DATABASE_NAME]
    
    collection = db.chat_messages
    index_name = "user_id_1_chat_id_1_client_message_id_1"
    
    print(f"Checking for index: {index_name}")
    indexes = await collection.list_indexes().to_list(length=100)
    exists = any(idx.get("name") == index_name for idx in indexes)
    
    if exists:
        print(f"Dropping existing index: {index_name}")
        await collection.drop_index(index_name)
    
    print(f"Creating partial unique index: {index_name}")
    await collection.create_index([
        ("user_id", 1),
        ("chat_id", 1),
        ("client_message_id", 1)
    ], unique=True, partialFilterExpression={"client_message_id": {"$type": "string"}})
    
    print("Index fixed successfully!")
    client.close()

if __name__ == "__main__":
    asyncio.run(fix_indexes())
