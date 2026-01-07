"""
Centralized FastAPI dependencies for authentication and authorization.
"""
from fastapi import Depends, HTTPException, status, Header
from typing import Optional
from bson import ObjectId
import logging

from app.auth import decode_access_token
from app.database import get_database

logger = logging.getLogger(__name__)


async def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    """
    FastAPI dependency for getting current authenticated user.
    
    Usage:
        @app.get("/protected")
        async def protected_route(user: dict = Depends(get_current_user)):
            return {"user_id": str(user["_id"])}
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Eksik veya geçersiz authorization header",
            headers={"WWW-Authenticate": "Bearer", "code": "UNAUTHORIZED"},
        )
    
    token = authorization.split(" ")[1]
    payload = decode_access_token(token)
    
    if payload is None:
        logger.debug("Token decode failed - invalid or expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Geçersiz veya süresi dolmuş token",
            headers={"WWW-Authenticate": "Bearer", "code": "UNAUTHORIZED"},
        )
    
    user_id = payload.get("sub")
    if not user_id:
        logger.debug("Token payload missing 'sub' field")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Geçersiz token payload",
            headers={"code": "UNAUTHORIZED"},
        )
    
    db = get_database()
    if db is None:
        logger.error("Database connection unavailable in get_current_user")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database bağlantısı yok",
            headers={"code": "DATABASE_ERROR"},
        )
    
    try:
        user_doc = await db.users.find_one({"_id": ObjectId(user_id)})
        if user_doc is None:
            logger.warning(f"User not found: {user_id}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Kullanıcı bulunamadı",
                headers={"code": "UNAUTHORIZED"},
            )
        return user_doc
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Kullanıcı bulunamadı",
            headers={"code": "UNAUTHORIZED"},
        )


async def get_current_user_id(user: dict = Depends(get_current_user)) -> str:
    """
    FastAPI dependency for getting current user ID only.
    More lightweight than get_current_user for endpoints that only need user_id.
    """
    return str(user["_id"])


async def get_optional_user(authorization: Optional[str] = Header(None)) -> Optional[dict]:
    """
    FastAPI dependency for optionally getting current user.
    Returns None if no valid auth token is provided (instead of raising exception).
    Useful for endpoints that work differently for authenticated vs anonymous users.
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None
    
    try:
        token = authorization.split(" ")[1]
        payload = decode_access_token(token)
        
        if payload is None:
            return None
        
        user_id = payload.get("sub")
        if not user_id:
            return None
        
        db = get_database()
        if db is None:
            return None
        
        user_doc = await db.users.find_one({"_id": ObjectId(user_id)})
        return user_doc
    except Exception:
        return None
