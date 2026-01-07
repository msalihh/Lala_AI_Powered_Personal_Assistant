"""
Authentication endpoints.
Extracted from main.py for modularization.
"""
from fastapi import APIRouter, HTTPException, status, Header
from typing import Optional
from datetime import datetime, timezone
from bson import ObjectId
import logging
import uuid
import random
import string

from app.database import get_database
from app.auth import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    verify_google_token,
)
from app.schemas import (
    RegisterRequest,
    RegisterResponse,
    LoginRequest,
    TokenResponse,
    UserResponse,
    GoogleLoginRequest,
    UpdateAvatarRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])


def append_random_suffix(base: str) -> str:
    """Append random suffix to username."""
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
    return f"{base}_{suffix}"


async def get_current_user_from_token(token: str) -> dict:
    """
    Get current user from JWT token.
    Raises HTTPException if not authenticated.
    """
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Geçersiz veya süresi dolmuş token",
            headers={"code": "UNAUTHORIZED"},
        )
    
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Geçersiz token",
            headers={"code": "UNAUTHORIZED"},
        )
    
    db = get_database()
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database bağlantısı yok",
            headers={"code": "DATABASE_ERROR"},
        )
    
    try:
        user_doc = await db.users.find_one({"_id": ObjectId(user_id)})
        if user_doc is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Kullanıcı bulunamadı",
                headers={"code": "USER_NOT_FOUND"},
            )
        return user_doc
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Kullanıcı bulunamadı",
            headers={"code": "USER_NOT_FOUND"},
        )


@router.post(
    "/auth/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(request: RegisterRequest):
    """Register a new user."""
    db = get_database()
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database bağlantısı yok",
            headers={"code": "DATABASE_ERROR"},
        )

    if not request.username or len(request.username.strip()) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kullanıcı adı boş olamaz",
            headers={"code": "INVALID_USERNAME"},
        )

    if not request.password or len(request.password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Şifre en az 6 karakter olmalıdır",
            headers={"code": "INVALID_PASSWORD"},
        )

    password_bytes = request.password.encode("utf-8")
    if len(password_bytes) > 72:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Şifre çok uzun (maksimum 72 byte)",
            headers={"code": "PASSWORD_TOO_LONG"},
        )

    username = request.username.strip()
    existing_user = await db.users.find_one({"username": username})
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bu kullanıcı adı zaten kayıtlı",
            headers={"code": "USERNAME_TAKEN"},
        )

    email = None
    if request.email:
        email = request.email.strip() if request.email else None
        if email and "@" not in email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Geçersiz e-posta formatı",
                headers={"code": "INVALID_EMAIL"},
            )

        if email:
            existing_email = await db.users.find_one({"email": email})
            if existing_email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Bu e-posta adresi zaten kayıtlı",
                    headers={"code": "EMAIL_EXISTS"},
                )

    try:
        hashed_password = hash_password(request.password)
        user_doc = {
            "username": username,
            "email": email,
            "password_hash": hashed_password,
            "is_active": True,
            "created_at": datetime.utcnow(),
        }
        result = await db.users.insert_one(user_doc)
        user_id = result.inserted_id
        return RegisterResponse(
            message="Kullanıcı başarıyla kaydedildi", user_id=str(user_id)
        )
    except ValueError as e:
        error_msg = str(e)
        if "72 bytes" in error_msg or "longer than 72" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Şifre çok uzun (maksimum 72 byte)",
                headers={"code": "PASSWORD_TOO_LONG"},
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Şifre hatası: {error_msg}",
            headers={"code": "PASSWORD_ERROR"},
        )
    except Exception as e:
        logger.error(f"Error creating user: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Kullanıcı oluşturulamadı: {str(e)}",
            headers={"code": "REGISTRATION_ERROR"},
        )


@router.post("/auth/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    """Login and get JWT token."""
    db = get_database()
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database bağlantısı yok",
            headers={"code": "DATABASE_ERROR"},
        )

    user_doc = await db.users.find_one({"username": request.username})
    if not user_doc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Geçersiz kullanıcı adı veya şifre",
            headers={"code": "INVALID_CREDENTIALS"},
        )

    if not user_doc.get("password_hash"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bu hesap Google ile oluşturulmuş. Lütfen Google ile giriş yapın.",
            headers={"code": "USE_GOOGLE_LOGIN"},
        )

    if not verify_password(request.password, user_doc["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Geçersiz kullanıcı adı veya şifre",
            headers={"code": "INVALID_CREDENTIALS"},
        )

    user_id = str(user_doc["_id"])
    access_token = create_access_token(data={"sub": user_id})
    return TokenResponse(access_token=access_token)


@router.get("/me", response_model=UserResponse)
async def get_me(authorization: Optional[str] = Header(None)):
    """Get current user information."""
    try:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Eksik veya geçersiz authorization header",
                headers={"code": "UNAUTHORIZED"},
            )

        token = authorization.split(" ")[1]
        user_doc = await get_current_user_from_token(token)

        created_at = user_doc.get("created_at")
        if isinstance(created_at, datetime):
            created_at_str = created_at.isoformat()
        elif created_at is None:
            created_at_str = ""
        else:
            created_at_str = str(created_at)

        return UserResponse(
            id=str(user_doc["_id"]),
            username=user_doc.get("username", ""),
            email=user_doc.get("email"),
            is_active=user_doc.get("is_active", True),
            created_at=created_at_str,
            avatar_url=user_doc.get("avatar_url"),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[GET_ME] Error in /me endpoint: {type(e).__name__}: {str(e)}", exc_info=True)
        raise


@router.post("/auth/google", response_model=TokenResponse)
async def google_login(request: GoogleLoginRequest):
    """Google OAuth login endpoint."""
    db = get_database()
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database bağlantısı yok",
            headers={"code": "DATABASE_ERROR"},
        )

    try:
        google_payload = verify_google_token(request.id_token)
    except ValueError as e:
        logger.error(f"Google token verification failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Google token doğrulaması başarısız: {str(e)}",
            headers={"code": "INVALID_GOOGLE_TOKEN"},
        )

    email = google_payload.get("email")
    google_sub = google_payload.get("sub")

    if not email or not google_sub:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google token email veya sub eksik",
            headers={"code": "MISSING_GOOGLE_INFO"},
        )

    user_doc = await db.users.find_one({"email": email})

    if user_doc:
        if not user_doc.get("google_sub"):
            await db.users.update_one(
                {"_id": user_doc["_id"]},
                {"$set": {"google_sub": google_sub, "auth_provider": "google"}},
            )
        user_id = str(user_doc["_id"])
    else:
        base_username = email.split("@")[0]
        username = base_username
        counter = 0
        while await db.users.find_one({"username": username}):
            username = append_random_suffix(base_username)
            counter += 1
            if counter > 10:
                username = f"{base_username}_{uuid.uuid4().hex[:4]}"
                break

        new_user = {
            "username": username,
            "email": email,
            "password_hash": None,
            "auth_provider": "google",
            "google_sub": google_sub,
            "is_active": True,
            "created_at": datetime.now(timezone.utc).replace(tzinfo=None),
        }
        result = await db.users.insert_one(new_user)
        user_id = str(result.inserted_id)

    access_token = create_access_token(data={"sub": user_id})
    return TokenResponse(access_token=access_token)
