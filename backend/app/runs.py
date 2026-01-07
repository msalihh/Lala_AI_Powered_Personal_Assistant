"""
Generation runs management - persistent storage for background LLM generation jobs.
"""
from typing import Optional, Dict, Any
from bson import ObjectId
from datetime import datetime
import logging
from app.database import get_database

logger = logging.getLogger(__name__)


async def create_run(
    user_id: str,
    chat_id: str,
    run_id: Optional[str] = None,  # Optional client-provided ID (UUID)
    status: str = "queued"
) -> str:
    """
    Create a new generation run in the database.
    
    Args:
        user_id: User ID
        chat_id: Chat ID
        status: Initial status (default: "queued")
        
    Returns:
        Run ID (MongoDB ObjectId as string)
    """
    db = get_database()
    if db is None:
        raise RuntimeError("Database not available")
    
    run_doc = {
        "user_id": str(user_id),
        "chat_id": str(chat_id),
        "run_id": run_id,  # Optional UUID from client
        "status": status,
        "content_so_far": "",
        "sources": None,
        "used_documents": None,
        "is_partial": False,
        "message_id": None,
        "error": None,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "cancelled_at": None,
    }
    
    result = await db.generation_runs.insert_one(run_doc)
    run_id = str(result.inserted_id)
    logger.info(f"[RUNS] Created run {run_id} for chat {chat_id}, user {user_id}, status={status}")
    return run_id


async def get_run(run_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Get a generation run by ID.
    
    Args:
        run_id: Run ID
        user_id: Optional user ID for verification
        
    Returns:
        Run document or None if not found
    """
    db = get_database()
    if db is None:
        return None
    
    # Try looking up by ObjectId first
    query = {}
    try:
        run_object_id = ObjectId(run_id)
        query = {"_id": run_object_id}
    except:
        # If not a valid ObjectId, assume it's a client_run_id (UUID)
        query = {"run_id": run_id}
    
    if user_id:
        query["user_id"] = str(user_id)
    
    run = await db.generation_runs.find_one(query)
    
    # Fallback: if not found by primary index, try explicit run_id filter if we used _id
    if not run and "_id" in query:
        fallback_query = {"run_id": run_id}
        if user_id: fallback_query["user_id"] = str(user_id)
        run = await db.generation_runs.find_one(fallback_query)

    if run:
        run["run_id"] = run.get("run_id") or str(run["_id"])
        run["_id"] = str(run["_id"])
    return run


async def update_run(
    run_id: str,
    updates: Dict[str, Any],
    user_id: Optional[str] = None
) -> bool:
    """
    Update a generation run.
    
    Args:
        run_id: Run ID
        updates: Dictionary of fields to update
        user_id: Optional user ID for verification
        
    Returns:
        True if updated, False otherwise
    """
    db = get_database()
    if db is None:
        return False
    
    # Try lookup to get local reference
    query = {}
    try:
        run_object_id = ObjectId(run_id)
        query = {"_id": run_object_id}
    except:
        query = {"run_id": run_id}
    
    if user_id:
        query["user_id"] = str(user_id)
    
    updates["updated_at"] = datetime.utcnow()
    
    # Try update
    result = await db.generation_runs.update_one(
        query,
        {"$set": updates}
    )
    
    # Fallback to UUID update if _id failed (could be we had a valid hex string that wasn't the _id)
    if result.matched_count == 0 and "_id" in query:
        fallback_query = {"run_id": run_id}
        if user_id: fallback_query["user_id"] = str(user_id)
        result = await db.generation_runs.update_one(
            fallback_query,
            {"$set": updates}
        )
    
    if result.modified_count > 0:
        logger.debug(f"[RUNS] Updated run {run_id}: {updates}")
        return True
    else:
        logger.warning(f"[RUNS] Run {run_id} not found or not modified")
        return False


async def cancel_run(run_id: str, user_id: Optional[str] = None) -> bool:
    """
    Cancel a generation run.
    
    Args:
        run_id: Run ID
        user_id: Optional user ID for verification
        
    Returns:
        True if cancelled, False otherwise
    """
    updates = {
        "status": "cancelled",
        "is_partial": True,
        "cancelled_at": datetime.utcnow()
    }
    return await update_run(run_id, updates, user_id)


async def get_active_runs_for_chat(chat_id: str, user_id: Optional[str] = None) -> list:
    """
    Get all active (queued or running) runs for a chat.
    
    Args:
        chat_id: Chat ID
        user_id: Optional user ID for verification
        
    Returns:
        List of run documents
    """
    db = get_database()
    if db is None:
        return []
    
    query = {
        "chat_id": str(chat_id),
        "status": {"$in": ["queued", "running"]}
    }
    if user_id:
        query["user_id"] = str(user_id)
    
    cursor = db.generation_runs.find(query).sort("created_at", -1)
    runs = []
    async for run in cursor:
        run["run_id"] = str(run["_id"])
        run["_id"] = str(run["_id"])
        runs.append(run)
    
    return runs









