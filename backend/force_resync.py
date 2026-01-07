import asyncio
import os
from dotenv import load_dotenv

# Load .env before any imports that might check env vars
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path)

from app.database import connect_to_mongo, get_database
from app.integrations.gmail import sync_emails
from datetime import datetime, timedelta, timezone

async def force_resync():
    # 1. Initialize DB connection
    await connect_to_mongo()
    db = get_database()
    
    if db is None:
        print("Failed to connect to database.")
        return
        
    # 2. Find the first user with Gmail connected
    integration = await db.user_integrations.find_one({"provider": "gmail"})
    if not integration:
        print("No Gmail integration found.")
        return
    
    user_id = integration["user_id"]
    email = integration.get("email", "Unknown")
    print(f"Found user: {user_id} ({email})")
    
    # 3. Delete existing email sources to force re-indexing
    result = await db.email_sources.delete_many({"user_id": user_id})
    print(f"Deleted {result.deleted_count} email sources from MongoDB.")
    
    # 4. Trigger sync
    print(f"Triggering sync_emails for {email} with upsert enabled...")
    sync_result = await sync_emails(user_id, max_emails=100)
    print(f"Sync completed: {sync_result}")

if __name__ == "__main__":
    asyncio.run(force_resync())
