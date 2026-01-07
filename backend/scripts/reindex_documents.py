"""
Reindex all documents with user_id metadata.
This script fixes old indexes that don't have user_id in metadata.

Usage:
    python -m scripts.reindex_documents [--user-id USER_ID] [--document-id DOC_ID] [--dry-run]

Options:
    --user-id USER_ID: Reindex only documents for this user
    --document-id DOC_ID: Reindex only this specific document
    --dry-run: Show what would be reindexed without actually doing it
"""
import asyncio
import sys
import os
import argparse
from typing import Optional, List
from bson import ObjectId

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import get_database
from app.rag.chunker import chunk_text
from app.rag.embedder import embed_chunks
from app.rag.vector_store import index_document_chunks, delete_document_chunks, get_collection
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def reindex_document(document_id: str, user_id: str, dry_run: bool = False) -> dict:
    """
    Reindex a single document with user_id metadata.
    
    Args:
        document_id: MongoDB document ID
        user_id: User ID to add to metadata
        dry_run: If True, only show what would be done
        
    Returns:
        Dictionary with reindexing statistics
    """
    db = get_database()
    if db is None:
        raise Exception("Database connection not available")
    
    # Get document from MongoDB
    doc = await db.documents.find_one({"_id": ObjectId(document_id)})
    if not doc:
        logger.warning(f"Document {document_id} not found in MongoDB")
        return {"status": "not_found", "document_id": document_id}
    
    doc_user_id = str(doc.get("user_id", ""))
    if doc_user_id != user_id:
        logger.warning(
            f"Document {document_id} belongs to user {doc_user_id}, not {user_id}. Skipping."
        )
        return {"status": "user_mismatch", "document_id": document_id}
    
    filename = doc.get("filename", "unknown")
    text_content = doc.get("text_content", "")
    
    if not text_content or not text_content.strip():
        logger.warning(f"Document {document_id} ({filename}) has no text_content. Skipping.")
        return {"status": "no_text", "document_id": document_id}
    
    logger.info(
        f"[REINDEX] doc_id={document_id} user_id={user_id} filename={filename} "
        f"text_length={len(text_content)}"
    )
    
    if dry_run:
        logger.info(f"[REINDEX_DRY_RUN] Would reindex document {document_id} with user_id={user_id}")
        return {"status": "dry_run", "document_id": document_id}
    
    try:
        # Step 1: Delete old chunks (without user_id filter - delete all chunks for this doc)
        logger.info(f"[REINDEX] Deleting old chunks for doc_id={document_id}")
        deleted_count = delete_document_chunks(document_id)
        logger.info(f"[REINDEX] Deleted {deleted_count} old chunks")
        
        # Step 2: Chunk the text
        logger.info(f"[REINDEX] Chunking text for doc_id={document_id}")
        chunks = chunk_text(
            text_content,
            chunk_words=None,  # Use config default
            overlap_words=None,  # Use config default
            document_id=document_id,
            mime_type=doc.get("mime_type", "text/plain")
        )
        logger.info(f"[REINDEX] Created {len(chunks)} chunks for doc_id={document_id}")
        
        if not chunks:
            logger.warning(f"[REINDEX] No chunks created for doc_id={document_id}")
            return {"status": "no_chunks", "document_id": document_id}
        
        # Step 3: Embed chunks
        logger.info(f"[REINDEX] Embedding {len(chunks)} chunks for doc_id={document_id}")
        embedded_chunks = await embed_chunks(chunks)
        
        successful_embeddings = sum(1 for chunk in embedded_chunks if chunk.get("embedding") is not None)
        logger.info(f"[REINDEX] Successfully embedded {successful_embeddings}/{len(chunks)} chunks")
        
        # Step 4: Index with user_id
        logger.info(f"[REINDEX] Indexing chunks with user_id={user_id} for doc_id={document_id}")
        indexing_stats = index_document_chunks(
            document_id=document_id,
            chunks=embedded_chunks,
            original_filename=filename,
            was_truncated=False,  # Assume not truncated for reindex
            user_id=user_id  # CRITICAL: Add user_id
        )
        
        indexed_count = indexing_stats.get("indexed_chunks", 0)
        logger.info(
            f"[REINDEX_SUCCESS] doc_id={document_id} user_id={user_id} "
            f"indexed_chunks={indexed_count} total_chunks={indexing_stats.get('total_chunks', 0)}"
        )
        
        return {
            "status": "success",
            "document_id": document_id,
            "indexed_chunks": indexed_count,
            "total_chunks": indexing_stats.get("total_chunks", 0)
        }
        
    except Exception as e:
        logger.error(f"[REINDEX_ERROR] doc_id={document_id} error={str(e)}", exc_info=True)
        return {"status": "error", "document_id": document_id, "error": str(e)}


async def reindex_all_documents(user_id: Optional[str] = None, dry_run: bool = False) -> dict:
    """
    Reindex all documents (or all documents for a user) with user_id metadata.
    
    Args:
        user_id: If provided, only reindex documents for this user
        dry_run: If True, only show what would be done
        
    Returns:
        Dictionary with reindexing statistics
    """
    db = get_database()
    if db is None:
        raise Exception("Database connection not available")
    
    # Build query
    query = {}
    if user_id:
        query["user_id"] = user_id
    
    # Get all documents
    cursor = db.documents.find(query, {"_id": 1, "user_id": 1, "filename": 1, "text_content": 1})
    
    documents = []
    async for doc in cursor:
        documents.append({
            "id": str(doc["_id"]),
            "user_id": str(doc.get("user_id", "")),
            "filename": doc.get("filename", "unknown")
        })
    
    logger.info(f"[REINDEX_ALL] Found {len(documents)} documents to reindex (user_id={user_id or 'all'})")
    
    if dry_run:
        logger.info(f"[REINDEX_ALL_DRY_RUN] Would reindex {len(documents)} documents")
        for doc in documents[:10]:  # Show first 10
            logger.info(f"  - {doc['id']} ({doc['filename']}) user_id={doc['user_id']}")
        if len(documents) > 10:
            logger.info(f"  ... and {len(documents) - 10} more")
        return {"status": "dry_run", "count": len(documents)}
    
    # Reindex each document
    results = {
        "total": len(documents),
        "success": 0,
        "failed": 0,
        "no_text": 0,
        "no_chunks": 0,
        "errors": []
    }
    
    for i, doc in enumerate(documents, 1):
        logger.info(f"[REINDEX_ALL] Processing {i}/{len(documents)}: {doc['id']}")
        result = await reindex_document(doc["id"], doc["user_id"], dry_run=False)
        
        if result["status"] == "success":
            results["success"] += 1
        elif result["status"] == "no_text":
            results["no_text"] += 1
        elif result["status"] == "no_chunks":
            results["no_chunks"] += 1
        else:
            results["failed"] += 1
            results["errors"].append(result)
    
    logger.info(
        f"[REINDEX_ALL_COMPLETE] total={results['total']} success={results['success']} "
        f"failed={results['failed']} no_text={results['no_text']} no_chunks={results['no_chunks']}"
    )
    
    return results


async def check_index_status(user_id: Optional[str] = None) -> dict:
    """
    Check how many chunks have user_id in metadata.
    
    Args:
        user_id: If provided, check only chunks for this user
        
    Returns:
        Dictionary with statistics
    """
    collection = get_collection()
    
    # Get all chunks (or chunks for user)
    if user_id:
        results = collection.get(where={"user_id": user_id})
    else:
        results = collection.get()
    
    total_chunks = len(results["ids"]) if results.get("ids") else 0
    
    # Count chunks with/without user_id
    chunks_with_user_id = 0
    chunks_without_user_id = 0
    
    if results.get("metadatas"):
        for metadata in results["metadatas"]:
            if metadata.get("user_id"):
                chunks_with_user_id += 1
            else:
                chunks_without_user_id += 1
    
    logger.info(
        f"[CHECK_INDEX] user_id={user_id or 'all'} total_chunks={total_chunks} "
        f"with_user_id={chunks_with_user_id} without_user_id={chunks_without_user_id}"
    )
    
    return {
        "total_chunks": total_chunks,
        "chunks_with_user_id": chunks_with_user_id,
        "chunks_without_user_id": chunks_without_user_id
    }


async def main():
    parser = argparse.ArgumentParser(description="Reindex documents with user_id metadata")
    parser.add_argument("--user-id", type=str, help="Reindex only documents for this user")
    parser.add_argument("--document-id", type=str, help="Reindex only this specific document")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be reindexed without doing it")
    parser.add_argument("--check", action="store_true", help="Check index status (count chunks with/without user_id)")
    
    args = parser.parse_args()
    
    if args.check:
        # Check status
        await check_index_status(user_id=args.user_id)
        return
    
    if args.document_id:
        # Reindex single document
        if not args.user_id:
            logger.error("--user-id is required when using --document-id")
            return
        
        result = await reindex_document(args.document_id, args.user_id, dry_run=args.dry_run)
        logger.info(f"Result: {result}")
    else:
        # Reindex all documents (or for a user)
        result = await reindex_all_documents(user_id=args.user_id, dry_run=args.dry_run)
        logger.info(f"Result: {result}")


if __name__ == "__main__":
    asyncio.run(main())

