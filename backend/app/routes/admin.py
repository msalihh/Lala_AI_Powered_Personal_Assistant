"""
Admin endpoints for system maintenance.
"""
from fastapi import APIRouter, HTTPException, status, Header, Depends
from typing import Optional
from bson import ObjectId
import logging

from app.database import get_database
from app.auth import decode_access_token
from scripts.reindex_documents import reindex_document, reindex_all_documents, check_index_status

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


async def get_current_user_id(authorization: Optional[str] = Header(None)) -> str:
    """Get current user ID from JWT token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Eksik veya geçersiz authorization header",
            headers={"code": "UNAUTHORIZED"}
        )
    
    token = authorization.split(" ")[1]
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Geçersiz veya süresi dolmuş token",
            headers={"code": "UNAUTHORIZED"}
        )
    
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Geçersiz token",
            headers={"code": "UNAUTHORIZED"}
        )
    
    return str(user_id)


@router.get("/reindex/status")
async def get_reindex_status(
    user_id: Optional[str] = None,
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Check index status - count chunks with/without user_id metadata.
    Only accessible by authenticated users (checks their own data if user_id provided).
    """
    # If user_id provided, verify it matches current user (security)
    if user_id and user_id != current_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only check your own documents",
            headers={"code": "FORBIDDEN"}
        )
    
    # Use current_user_id if user_id not provided
    check_user_id = user_id or current_user_id
    
    try:
        stats = await check_index_status(user_id=check_user_id)
        return {
            "status": "success",
            "user_id": check_user_id,
            "stats": stats
        }
    except Exception as e:
        logger.error(f"Error checking index status: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error checking index status: {str(e)}",
            headers={"code": "REINDEX_ERROR"}
        )


@router.post("/reindex/document/{document_id}")
async def reindex_single_document(
    document_id: str,
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Reindex a single document with user_id metadata.
    Only accessible by document owner.
    """
    db = get_database()
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database bağlantısı yok",
            headers={"code": "DATABASE_ERROR"}
        )
    
    # Verify document ownership
    try:
        doc = await db.documents.find_one({"_id": ObjectId(document_id)})
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Doküman bulunamadı",
                headers={"code": "NOT_FOUND"}
            )
        
        doc_user_id = str(doc.get("user_id", ""))
        if doc_user_id != current_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bu dokümana erişim izniniz yok",
                headers={"code": "FORBIDDEN"}
            )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Geçersiz doküman ID",
            headers={"code": "INVALID_ID"}
        )
    
    try:
        result = await reindex_document(document_id, current_user_id, dry_run=False)
        return {
            "status": "success",
            "result": result
        }
    except Exception as e:
        logger.error(f"Error reindexing document {document_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Reindex hatası: {str(e)}",
            headers={"code": "REINDEX_ERROR"}
        )


@router.post("/reindex/all")
async def reindex_all_user_documents(
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Reindex all documents for the current user with user_id metadata.
    """
    try:
        result = await reindex_all_documents(user_id=current_user_id, dry_run=False)
        return {
            "status": "success",
            "result": result
        }
    except Exception as e:
        logger.error(f"Error reindexing all documents for user {current_user_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Reindex hatası: {str(e)}",
            headers={"code": "REINDEX_ERROR"}
        )

