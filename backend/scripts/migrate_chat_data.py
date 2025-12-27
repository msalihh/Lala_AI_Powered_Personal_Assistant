"""
Migration script to normalize chat data formats and populate new fields.

This script:
1. Normalizes user_id formats (ObjectId → string) in chats and chat_messages
2. Normalizes chat_id formats (string → ObjectId) in chat_messages
3. Populates last_message_at in chats collection
4. Updates updated_at if last_message_at is newer

Usage:
    python -m scripts.migrate_chat_data --dry-run  # Preview changes
    python -m scripts.migrate_chat_data              # Apply changes
"""

import asyncio
import sys
import os
from datetime import datetime
from typing import Dict, Any, Optional
from bson import ObjectId

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017/")
DATABASE_NAME = os.getenv("DATABASE_NAME", "auth_db")


class MigrationStats:
    """Track migration statistics."""
    def __init__(self):
        self.chats_updated = 0
        self.messages_updated = 0
        self.user_id_normalized_chats = 0
        self.user_id_normalized_messages = 0
        self.chat_id_normalized_messages = 0
        self.last_message_at_populated = 0
        self.updated_at_updated = 0
        self.errors = []

    def __str__(self):
        return f"""
Migration Statistics:
- Chats updated: {self.chats_updated}
- Messages updated: {self.messages_updated}
- user_id normalized (chats): {self.user_id_normalized_chats}
- user_id normalized (messages): {self.user_id_normalized_messages}
- chat_id normalized (messages): {self.chat_id_normalized_messages}
- last_message_at populated: {self.last_message_at_populated}
- updated_at updated: {self.updated_at_updated}
- Errors: {len(self.errors)}
"""


async def normalize_user_id(value: Any) -> Optional[str]:
    """Convert user_id to string format."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, ObjectId):
        return str(value)
    return str(value)


async def normalize_chat_id(value: Any) -> Optional[ObjectId]:
    """Convert chat_id to ObjectId format."""
    if value is None:
        return None
    if isinstance(value, ObjectId):
        return value
    if isinstance(value, str):
        if ObjectId.is_valid(value):
            return ObjectId(value)
    return None


async def migrate_chats_collection(db, stats: MigrationStats, dry_run: bool = True):
    """Migrate chats collection."""
    print("\n[MIGRATE] Starting chats collection migration...")
    
    chats_collection = db.chats
    total_chats = await chats_collection.count_documents({})
    print(f"[MIGRATE] Found {total_chats} chats to process")
    
    async for chat in chats_collection.find({}):
        chat_id = chat.get("_id")
        updates = {}
        
        # Normalize user_id
        user_id = chat.get("user_id")
        normalized_user_id = await normalize_user_id(user_id)
        if normalized_user_id and normalized_user_id != user_id:
            updates["user_id"] = normalized_user_id
            stats.user_id_normalized_chats += 1
            print(f"[MIGRATE] Chat {chat_id}: Normalizing user_id {user_id} → {normalized_user_id}")
        
        # Add last_message_at if missing (will be populated from messages)
        if "last_message_at" not in chat:
            updates["last_message_at"] = None
        
        # Add deleted_at if missing
        if "deleted_at" not in chat:
            updates["deleted_at"] = None
        
        if updates and not dry_run:
            await chats_collection.update_one(
                {"_id": chat_id},
                {"$set": updates}
            )
            stats.chats_updated += 1
        
        if updates and dry_run:
            print(f"[DRY-RUN] Would update chat {chat_id}: {updates}")


async def migrate_messages_collection(db, stats: MigrationStats, dry_run: bool = True):
    """Migrate chat_messages collection."""
    print("\n[MIGRATE] Starting chat_messages collection migration...")
    
    messages_collection = db.chat_messages
    total_messages = await messages_collection.count_documents({})
    print(f"[MIGRATE] Found {total_messages} messages to process")
    
    async for message in messages_collection.find({}):
        message_id = message.get("_id")
        updates = {}
        
        # Normalize user_id
        user_id = message.get("user_id")
        normalized_user_id = await normalize_user_id(user_id)
        if normalized_user_id and normalized_user_id != user_id:
            updates["user_id"] = normalized_user_id
            stats.user_id_normalized_messages += 1
        
        # Normalize chat_id
        chat_id = message.get("chat_id")
        normalized_chat_id = await normalize_chat_id(chat_id)
        if normalized_chat_id and normalized_chat_id != chat_id:
            updates["chat_id"] = normalized_chat_id
            stats.chat_id_normalized_messages += 1
            print(f"[MIGRATE] Message {message_id}: Normalizing chat_id {chat_id} -> {normalized_chat_id}")
        
        if updates and not dry_run:
            try:
                await messages_collection.update_one(
                    {"_id": message_id},
                    {"$set": updates}
                )
                stats.messages_updated += 1
            except Exception as e:
                error_msg = f"Error updating message {message_id}: {str(e)}"
                stats.errors.append(error_msg)
                print(f"[ERROR] {error_msg}")
        
        if updates and dry_run:
            print(f"[DRY-RUN] Would update message {message_id}: {updates}")


async def populate_last_message_at(db, stats: MigrationStats, dry_run: bool = True):
    """Populate last_message_at in chats from messages."""
    print("\n[MIGRATE] Populating last_message_at from messages...")
    
    chats_collection = db.chats
    messages_collection = db.chat_messages
    
    async for chat in chats_collection.find({}):
        chat_id = chat.get("_id")
        
        # Find last message for this chat (try both ObjectId and string formats)
        last_message = None
        
        # Try ObjectId format
        try:
            cursor = messages_collection.find(
                {"chat_id": chat_id}
            ).sort("created_at", -1).limit(1)
            async for msg in cursor:
                last_message = msg
                break
        except:
            pass
        
        # Try string format if ObjectId didn't work
        if not last_message:
            try:
                cursor = messages_collection.find(
                    {"chat_id": str(chat_id)}
                ).sort("created_at", -1).limit(1)
                async for msg in cursor:
                    last_message = msg
                    break
            except:
                pass
        
        if last_message:
            last_message_at = last_message.get("created_at")
            if last_message_at:
                current_last_message_at = chat.get("last_message_at")
                updates = {}
                
                # Update last_message_at
                if current_last_message_at != last_message_at:
                    updates["last_message_at"] = last_message_at
                    stats.last_message_at_populated += 1
                
                # Update updated_at if last_message_at is newer
                current_updated_at = chat.get("updated_at")
                if isinstance(last_message_at, datetime) and isinstance(current_updated_at, datetime):
                    if last_message_at > current_updated_at:
                        updates["updated_at"] = last_message_at
                        stats.updated_at_updated += 1
                
                if updates and not dry_run:
                    await chats_collection.update_one(
                        {"_id": chat_id},
                        {"$set": updates}
                    )
                    stats.chats_updated += 1
                
                if updates and dry_run:
                    print(f"[DRY-RUN] Would update chat {chat_id}: {updates}")


async def main():
    """Main migration function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Migrate chat data to normalized formats")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without applying")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args()
    
    dry_run = args.dry_run
    skip_confirm = args.yes
    
    if dry_run:
        print("=" * 60)
        print("DRY-RUN MODE: No changes will be applied")
        print("=" * 60)
    else:
        print("=" * 60)
        print("LIVE MODE: Changes will be applied to database")
        print("=" * 60)
        if not skip_confirm:
            response = input("Continue? (yes/no): ")
            if response.lower() != "yes":
                print("Migration cancelled.")
                return
        else:
            print("Auto-confirmed (--yes flag provided)")
    
    stats = MigrationStats()
    
    try:
        # Connect to MongoDB
        client = AsyncIOMotorClient(MONGODB_URL)
        db = client[DATABASE_NAME]
        
        # Test connection
        await client.admin.command('ping')
        print(f"[OK] Connected to MongoDB: {DATABASE_NAME}")
        
        # Step 1: Normalize chats collection
        await migrate_chats_collection(db, stats, dry_run)
        
        # Step 2: Normalize messages collection
        await migrate_messages_collection(db, stats, dry_run)
        
        # Step 3: Populate last_message_at
        await populate_last_message_at(db, stats, dry_run)
        
        # Print statistics
        print("\n" + "=" * 60)
        print(stats)
        print("=" * 60)
        
        if stats.errors:
            print("\nErrors encountered:")
            for error in stats.errors:
                print(f"  - {error}")
        
        if dry_run:
            print("\n[DRY-RUN] No changes were applied. Run without --dry-run to apply changes.")
        else:
            print("\n[MIGRATE] Migration completed successfully!")
        
    except Exception as e:
        print(f"\n[ERROR] Migration failed: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        if 'client' in locals():
            client.close()


if __name__ == "__main__":
    asyncio.run(main())

