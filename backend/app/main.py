"""
FastAPI application entry point - MongoDB version.
"""

from fastapi import FastAPI, HTTPException, status, Header, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from typing import Optional, List
from bson import ObjectId
from datetime import datetime
import httpx
import os
import asyncio
import re
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
from app.database import connect_to_mongo, close_mongo_connection, get_database
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
    ErrorResponse,
    ChatRequest,
    ChatResponse,
    SourceInfo,
    MemoryItem,
    MemoryResponse,
    CreateChatRequest,
    UpdateChatRequest,
    ChatListItem,
    ChatDetail,
    GenerationRunStatus,
    GoogleLoginRequest,
    ChatMessageRequest,
    ChatMessageResponse,
    ChatMessagesResponse,
    DeleteChatRequest,
)
from app.rag.embedder import embed_text
from app.rag.vector_store import query_chunks
from app.rag.decision import decide_context
from app.rag.context_builder import manage_context_budget
from app.rag.answer_validator import validate_answer_against_context, generate_self_repair_prompt
from app.rag.config import rag_config
from app.memory import (
    save_message, 
    get_recent_messages, 
    build_context_messages,
    get_or_update_chat_summary,
    resolve_carryover,
    get_conversation_state,
    update_conversation_state
)
from app.utils import (
    call_llm,
    validate_messages,
    validate_katex_output,
    force_compact_math_output,
    compact_markdown_output
)
from app.answer_composer import compose_answer, analyze_intent, QuestionIntent
from app.chat_title import generateAndSetTitle
import logging
import uuid

logger = logging.getLogger(__name__)

# RAG Configuration
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "4"))
RAG_SCORE_THRESHOLD = float(os.getenv("RAG_SCORE_THRESHOLD", "0.25"))

# Context Window Configuration
CONTEXT_MAX_TOKENS = int(os.getenv("CONTEXT_MAX_TOKENS", "2000"))  # Default 2000 tokens
CONTEXT_HARD_LIMIT = int(os.getenv("CONTEXT_HARD_LIMIT", "50"))  # Max 50 messages
from app.routes import documents as documents_router

# In-memory cache for idempotency (production'da Redis kullanılabilir)
# Key format: "{user_id}:{chat_id}:{client_message_id}"
message_cache = {}

# In-memory generation runs (production'da Redis/DB kullanılabilir)
# Format: {run_id: {chat_id, message_id, status, partial_text, completed_text, created_at, updated_at, error}}
generation_runs: dict = {}

# OpenRouter API Configuration
OPENROUTER_API_KEY = os.getenv(
    "OPENROUTER_API_KEY",
    "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",
)
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")  # Default model

# Initialize FastAPI app
app = FastAPI(
    title="Auth API",
    description="Minimal authentication API with MongoDB",
    version="1.0.0",
)

# CORS middleware
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request ID Middleware for logging and traceability
class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())[:8]
        request.state.request_id = request_id

        # Add request_id to response headers
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


app.add_middleware(RequestIDMiddleware)

# Include routers
app.include_router(documents_router.router)


# Startup and shutdown events
@app.on_event("startup")
async def startup_event():
    await connect_to_mongo()


@app.on_event("shutdown")
async def shutdown_event():
    await close_mongo_connection()


# Exception handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    code = exc.headers.get("code", "UNKNOWN_ERROR") if exc.headers else "UNKNOWN_ERROR"
    return JSONResponse(
        status_code=exc.status_code, content={"detail": exc.detail, "code": code}
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    try:
        errors = exc.errors()
    except:
        errors = []
    error_messages = []
    for error in errors:
        field = ".".join(str(x) for x in error.get("loc", []))
        msg = error.get("msg", "Validation error")
        error_messages.append(f"{field}: {msg}")

    detail = "; ".join(error_messages) if error_messages else "Validation error"

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": detail, "code": "VALIDATION_ERROR"},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc: Exception):
    """
    Global exception handler - catches ALL unhandled exceptions.
    CRITICAL: Always returns JSON response, never raises or returns non-JSON.
    """
    import traceback
    import json

    # CRITICAL: Catch any errors in the handler itself to prevent infinite loops
    try:
        error_msg = str(exc)
        error_type = type(exc).__name__
        traceback_str = traceback.format_exc()

        # Log to console immediately (before any file operations)
        print("=" * 50)
        print("[GLOBAL_EXCEPTION] UNEXPECTED ERROR CAUGHT:")
        print(f"Error: {error_msg}")
        print(f"Type: {error_type}")
        print(f"Path: {getattr(request, 'url', 'unknown')}")
        print("Traceback:")
        print(traceback_str)
        print("=" * 50)

        # #region agent log
        try:
            with open(
                r"c:\Users\msg\bitirme\.cursor\debug.log", "a", encoding="utf-8"
            ) as f:
                f.write(
                    json.dumps(
                        {
                            "sessionId": "debug-session",
                            "runId": "run1",
                            "hypothesisId": "GLOBAL",
                            "location": "main.py:general_exception_handler",
                            "message": "global exception handler",
                            "data": {
                                "error_type": error_type,
                                "error_msg": error_msg,
                                "path": (
                                    str(request.url)
                                    if hasattr(request, "url")
                                    else "unknown"
                                ),
                            },
                            "timestamp": int(datetime.utcnow().timestamp() * 1000),
                        }
                    )
                    + "\n"
                )
        except Exception as log_err:
            print(f"[GLOBAL_EXCEPTION] Failed to write debug log: {log_err}")
        # #endregion

        logger.error(
            f"[GLOBAL_EXCEPTION] Global exception handler caught: {error_type}: {error_msg}", exc_info=True
        )

        # CRITICAL: Always return JSONResponse - never raise or return non-JSON
        try:
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "detail": f"Internal server error: {error_msg}",
                    "code": "INTERNAL_ERROR",
                    "error_type": error_type,
                },
            )
        except Exception as json_err:
            # Even JSONResponse creation failed - return minimal JSON
            print(f"[GLOBAL_EXCEPTION] Failed to create JSONResponse: {json_err}")
            logger.error(f"[GLOBAL_EXCEPTION] Failed to create JSONResponse: {json_err}")
            # Return plain text JSON as last resort (should never happen)
            from fastapi.responses import Response
            return Response(
                content=f'{{"detail":"Internal server error: {error_msg}","code":"INTERNAL_ERROR","error_type":"{error_type}"}}',
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                media_type="application/json",
            )
    except Exception as handler_err:
        # If the handler itself fails, return minimal JSON
        print(f"[GLOBAL_EXCEPTION] CRITICAL: Handler itself failed: {handler_err}")
        from fastapi.responses import Response
        return Response(
            content='{"detail":"Internal server error: Exception handler failed","code":"INTERNAL_ERROR","error_type":"HandlerError"}',
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            media_type="application/json",
        )


async def get_current_user(token: str) -> dict:
    """
    Get current user from JWT token.
    """
    # #region agent log
    import json

    try:
        with open(
            r"c:\Users\msg\bitirme\.cursor\debug.log", "a", encoding="utf-8"
        ) as f:
            f.write(
                json.dumps(
                    {
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "hypothesisId": "A",
                        "location": "main.py:167",
                        "message": "get_current_user entry",
                        "data": {"token_len": len(token) if token else 0},
                        "timestamp": int(datetime.utcnow().timestamp() * 1000),
                    }
                )
                + "\n"
            )
    except:
        pass
    # #endregion

    payload = decode_access_token(token)
    if payload is None:
        # #region agent log
        try:
            with open(
                r"c:\Users\msg\bitirme\.cursor\debug.log", "a", encoding="utf-8"
            ) as f:
                f.write(
                    json.dumps(
                        {
                            "sessionId": "debug-session",
                            "runId": "run1",
                            "hypothesisId": "A",
                            "location": "main.py:172",
                            "message": "payload is None",
                            "data": {},
                            "timestamp": int(datetime.utcnow().timestamp() * 1000),
                        }
                    )
                    + "\n"
                )
        except:
            pass
        # #endregion
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Geçersiz veya süresi dolmuş token",
            headers={"code": "UNAUTHORIZED"},
        )

    user_id = payload.get("sub")
    if user_id is None:
        # #region agent log
        try:
            with open(
                r"c:\Users\msg\bitirme\.cursor\debug.log", "a", encoding="utf-8"
            ) as f:
                f.write(
                    json.dumps(
                        {
                            "sessionId": "debug-session",
                            "runId": "run1",
                            "hypothesisId": "A",
                            "location": "main.py:180",
                            "message": "user_id is None",
                            "data": {},
                            "timestamp": int(datetime.utcnow().timestamp() * 1000),
                        }
                    )
                    + "\n"
                )
        except:
            pass
        # #endregion
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Geçersiz token",
            headers={"code": "UNAUTHORIZED"},
        )

    # #region agent log
    try:
        with open(
            r"c:\Users\msg\bitirme\.cursor\debug.log", "a", encoding="utf-8"
        ) as f:
            f.write(
                json.dumps(
                    {
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "hypothesisId": "A",
                        "location": "main.py:187",
                        "message": "before ObjectId conversion",
                        "data": {"user_id": user_id},
                        "timestamp": int(datetime.utcnow().timestamp() * 1000),
                    }
                )
                + "\n"
            )
    except:
        pass
    # #endregion

    db = get_database()
    if db is None:
        # #region agent log
        try:
            with open(
                r"c:\Users\msg\bitirme\.cursor\debug.log", "a", encoding="utf-8"
            ) as f:
                f.write(
                    json.dumps(
                        {
                            "sessionId": "debug-session",
                            "runId": "run1",
                            "hypothesisId": "A",
                            "location": "main.py:188",
                            "message": "db is None in get_current_user",
                            "data": {},
                            "timestamp": int(datetime.utcnow().timestamp() * 1000),
                        }
                    )
                    + "\n"
                )
        except:
            pass
        # #endregion
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database bağlantısı yok",
            headers={"code": "DATABASE_ERROR"},
        )

    try:
        # #region agent log
        try:
            with open(
                r"c:\Users\msg\bitirme\.cursor\debug.log", "a", encoding="utf-8"
            ) as f:
                f.write(
                    json.dumps(
                        {
                            "sessionId": "debug-session",
                            "runId": "run1",
                            "hypothesisId": "A",
                            "location": "main.py:196",
                            "message": "before ObjectId(user_id)",
                            "data": {"user_id": user_id},
                            "timestamp": int(datetime.utcnow().timestamp() * 1000),
                        }
                    )
                    + "\n"
                )
        except:
            pass
        # #endregion

        object_id = ObjectId(user_id)

        # #region agent log
        try:
            with open(
                r"c:\Users\msg\bitirme\.cursor\debug.log", "a", encoding="utf-8"
            ) as f:
                f.write(
                    json.dumps(
                        {
                            "sessionId": "debug-session",
                            "runId": "run1",
                            "hypothesisId": "A",
                            "location": "main.py:196",
                            "message": "before mongo find_one",
                            "data": {"object_id": str(object_id)},
                            "timestamp": int(datetime.utcnow().timestamp() * 1000),
                        }
                    )
                    + "\n"
                )
        except:
            pass
        # #endregion

        user_doc = await db.users.find_one({"_id": object_id})

        # #region agent log
        try:
            with open(
                r"c:\Users\msg\bitirme\.cursor\debug.log", "a", encoding="utf-8"
            ) as f:
                f.write(
                    json.dumps(
                        {
                            "sessionId": "debug-session",
                            "runId": "run1",
                            "hypothesisId": "A",
                            "location": "main.py:196",
                            "message": "after mongo find_one",
                            "data": {"user_doc_exists": user_doc is not None},
                            "timestamp": int(datetime.utcnow().timestamp() * 1000),
                        }
                    )
                    + "\n"
                )
        except:
            pass
        # #endregion

        if user_doc is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Kullanıcı bulunamadı",
                headers={"code": "UNAUTHORIZED"},
            )
        return user_doc
    except HTTPException:
        raise
    except Exception as e:
        # #region agent log
        try:
            with open(
                r"c:\Users\msg\bitirme\.cursor\debug.log", "a", encoding="utf-8"
            ) as f:
                f.write(
                    json.dumps(
                        {
                            "sessionId": "debug-session",
                            "runId": "run1",
                            "hypothesisId": "A",
                            "location": "main.py:204",
                            "message": "get_current_user exception",
                            "data": {
                                "error_type": type(e).__name__,
                                "error_msg": str(e),
                            },
                            "timestamp": int(datetime.utcnow().timestamp() * 1000),
                        }
                    )
                    + "\n"
                )
        except:
            pass
        # #endregion
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Kullanıcı bulunamadı",
            headers={"code": "UNAUTHORIZED"},
        )


@app.get("/")
async def root():
    return {"message": "Auth API", "version": "1.0.0", "database": "MongoDB"}


@app.get("/health")
async def health():
    """
    Health check endpoint with version info and ChromaDB status.
    """
    db = get_database()
    db_ok = False
    if db is not None:
        try:
            await db.command("ping")
            db_ok = True
        except Exception:
            pass

    # Check ChromaDB
    chroma_ok = False
    chroma_count = 0
    try:
        from app.rag.vector_store import get_collection

        collection = get_collection()
        chroma_count = collection.count()
        chroma_ok = True
    except Exception:
        pass

    return {
        "ok": db_ok and chroma_ok,
        "database": "connected" if db_ok else "disconnected",
        "chromadb": {
            "status": "connected" if chroma_ok else "disconnected",
            "chunks": chroma_count,
        },
        "version": "1.0.0",
        "rag_enabled": True,
        "rag_top_k": RAG_TOP_K,
    }


@app.post(
    "/auth/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(request: RegisterRequest):
    """
    Register a new user.
    """
    db = get_database()
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database bağlantısı yok",
            headers={"code": "DATABASE_ERROR"},
        )

    # Validate username
    if not request.username or len(request.username.strip()) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kullanıcı adı boş olamaz",
            headers={"code": "INVALID_USERNAME"},
        )

    # Validate password
    if not request.password or len(request.password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Şifre en az 6 karakter olmalıdır",
            headers={"code": "INVALID_PASSWORD"},
        )

    # Bcrypt has a 72 byte limit
    password_bytes = request.password.encode("utf-8")
    password_byte_length = len(password_bytes)

    if password_byte_length > 72:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Şifre çok uzun (maksimum 72 byte)",
            headers={"code": "PASSWORD_TOO_LONG"},
        )

    username = request.username.strip()

    # Check if username already exists
    existing_user = await db.users.find_one({"username": username})
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bu kullanıcı adı zaten kayıtlı",
            headers={"code": "USERNAME_TAKEN"},
        )

    # Validate and check email (if provided)
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

    # Create user
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
        # Bcrypt password length error
        error_msg = str(e)
        if (
            "72 bytes" in error_msg
            or "longer than 72" in error_msg
            or "cannot be longer" in error_msg
        ) and "password" in error_msg.lower():
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
        import traceback

        error_msg = str(e)
        print(f"Error creating user: {error_msg}")
        print(traceback.format_exc())

        # Check if it's a bcrypt error
        if (
            "72 bytes" in error_msg
            or "longer than 72" in error_msg
            or "cannot be longer" in error_msg
        ) and "password" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Şifre çok uzun (maksimum 72 byte)",
                headers={"code": "PASSWORD_TOO_LONG"},
            )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Kullanıcı oluşturulurken hata: {error_msg}",
            headers={"code": "DATABASE_ERROR"},
        )


@app.post("/auth/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    """
    Login and get JWT token.
    """
    db = get_database()
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database bağlantısı yok",
            headers={"code": "DATABASE_ERROR"},
        )

    # Find user by username
    user_doc = await db.users.find_one({"username": request.username})

    if not user_doc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Geçersiz kullanıcı adı veya şifre",
            headers={"code": "INVALID_CREDENTIALS"},
        )

    # Verify password
    if not verify_password(request.password, user_doc.get("password_hash")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Geçersiz kullanıcı adı veya şifre",
            headers={"code": "INVALID_CREDENTIALS"},
        )

    # Check if user is active
    if not user_doc.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Kullanıcı hesabı aktif değil",
            headers={"code": "USER_INACTIVE"},
        )

    # Create access token
    user_id = str(user_doc["_id"])
    access_token = create_access_token(data={"sub": user_id})

    return TokenResponse(access_token=access_token)


@app.get("/me", response_model=UserResponse)
async def get_me(authorization: Optional[str] = Header(None)):
    """
    Get current user information.
    """
    try:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Eksik veya geçersiz authorization header",
                headers={"code": "UNAUTHORIZED"},
            )

        token = authorization.split(" ")[1]
        user_doc = await get_current_user(token)
        
        logger.info(f"[GET_ME] User lookup success: user_id={str(user_doc.get('_id'))}, username={user_doc.get('username')}")

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
        )
    except HTTPException:
        # Re-raise HTTP exceptions as-is (they will be handled by exception handler)
        raise
    except Exception as e:
        import traceback

        error_trace = traceback.format_exc()
        error_msg = str(e)
        error_type = type(e).__name__

        logger.error(f"[GET_ME] Error in /me endpoint: {error_type}: {error_msg}", exc_info=True)
        logger.error(f"[GET_ME] Full traceback: {error_trace}")

        # CRITICAL FIX: Always return JSON, never raise exception that might return text
        from fastapi.responses import JSONResponse
        try:
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "detail": f"Kullanıcı bilgisi alınamadı: {error_msg}",
                    "code": "USER_INFO_ERROR",
                    "error_type": error_type
                }
            )
        except Exception as json_err:
            # Even JSONResponse creation failed - return minimal JSON as text
            logger.error(f"[GET_ME] Failed to create JSONResponse: {json_err}")
            from fastapi.responses import Response
            return Response(
                content=f'{{"detail":"Kullanıcı bilgisi alınamadı: {error_msg}","code":"USER_INFO_ERROR","error_type":"{error_type}"}}',
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                media_type="application/json",
            )


@app.post("/auth/google", response_model=TokenResponse)
async def google_login(request: GoogleLoginRequest):
    """
    Google OAuth login endpoint.
    Verifies Google ID token, creates/finds user, and issues our JWT.
    """
    from app.utils import append_random_suffix

    db = get_database()
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database bağlantısı yok",
            headers={"code": "DATABASE_ERROR"},
        )

    # Verify Google ID token
    try:
        google_payload = verify_google_token(request.id_token)
    except ValueError as e:
        # Log the actual error for debugging
        logger.error(f"Google token verification failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Google token doğrulaması başarısız: {str(e)}",
            headers={"code": "INVALID_GOOGLE_TOKEN"},
        )

    # Extract info from token
    email = google_payload.get("email")
    google_sub = google_payload.get("sub")
    google_name = google_payload.get("name", "")

    if not email or not google_sub:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google token email veya sub eksik",
            headers={"code": "MISSING_GOOGLE_INFO"},
        )

    # Check if user exists by email
    user_doc = await db.users.find_one({"email": email})

    if user_doc:
        # User exists - link google_sub if not already set
        if not user_doc.get("google_sub"):
            await db.users.update_one(
                {"_id": user_doc["_id"]},
                {"$set": {"google_sub": google_sub, "auth_provider": "google"}},
            )
        user_id = str(user_doc["_id"])
    else:
        # User doesn't exist - create new user
        # Generate unique username from email local-part
        base_username = email.split("@")[0]
        username = base_username

        # Check if username exists, if so append random suffix
        counter = 0
        while await db.users.find_one({"username": username}):
            username = append_random_suffix(base_username)
            counter += 1
            if counter > 10:  # Prevent infinite loop
                username = f"{base_username}_{uuid.uuid4().hex[:4]}"
                break

        # Create new user document
        new_user = {
            "username": username,
            "email": email,
            "password_hash": None,  # Google users don't have passwords
            "auth_provider": "google",
            "google_sub": google_sub,
            "is_active": True,
            "created_at": datetime.utcnow(),
        }

        result = await db.users.insert_one(new_user)
        user_id = str(result.inserted_id)

    # Issue our JWT
    access_token = create_access_token(data={"sub": user_id})

    return TokenResponse(access_token=access_token)


@app.post("/chats", response_model=ChatDetail, status_code=status.HTTP_201_CREATED)
async def create_chat(
    request: CreateChatRequest, authorization: Optional[str] = Header(None)
):
    """
    Create a new chat for the current user.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Eksik veya geçersiz authorization header",
            headers={"code": "UNAUTHORIZED"},
        )

    token = authorization.split(" ")[1]
    user_doc = await get_current_user(token)
    user_id = str(user_doc["_id"])

    db = get_database()
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database bağlantısı yok",
            headers={"code": "DATABASE_ERROR"},
        )

    try:
        chat_doc = {
            "user_id": str(user_id),
            "title": request.title or "Yeni Sohbet",
            "title_source": "manual" if request.title else "pending",
            "title_updates_count": 0,
            "title_last_updated_at": None,
            "last_message_at": None,
            "deleted_at": None,
            "pinned": False,
            "tags": [],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }

        result = await db.chats.insert_one(chat_doc)
        chat_id = str(result.inserted_id)
        logger.info(f"[CREATE_CHAT] Created chat: _id={result.inserted_id}, chat_id={chat_id}, user_id={user_id}, title={chat_doc.get('title')}")
        created_chat = await db.chats.find_one({"_id": result.inserted_id})

        if not created_chat:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Chat oluşturuldu ama geri alınamadı",
                headers={"code": "CHAT_CREATE_ERROR"},
            )

        created_at_str = (
            created_chat["created_at"].isoformat()
            if isinstance(created_chat["created_at"], datetime)
            else str(created_chat["created_at"])
        )
        updated_at_str = (
            created_chat["updated_at"].isoformat()
            if isinstance(created_chat["updated_at"], datetime)
            else str(created_chat["updated_at"])
        )

        return ChatDetail(
            id=chat_id,
            title=created_chat["title"],
            created_at=created_at_str,
            updated_at=updated_at_str,
            user_id=user_id,
            last_message_at=None,
            deleted_at=None,
            pinned=False,
            tags=[],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating chat: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat oluşturulamadı: {str(e)}",
            headers={"code": "CHAT_CREATE_ERROR"},
        )


@app.get("/chats", response_model=List[ChatListItem])
async def list_chats(authorization: Optional[str] = Header(None)):
    """
    List all chats for the current user (user-scoped).
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Eksik veya geçersiz authorization header",
            headers={"code": "UNAUTHORIZED"},
        )

    token = authorization.split(" ")[1]
    user_doc = await get_current_user(token)
    user_id = str(user_doc["_id"])

    db = get_database()
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database bağlantısı yok",
            headers={"code": "DATABASE_ERROR"},
        )

    try:
        # Only return chats that have at least one message (last_message_at is not None)
        query_filter = {
            "user_id": str(user_id),
            "$or": [
                {"deleted_at": None},
                {"deleted_at": {"$exists": False}}
            ],
            "last_message_at": {"$ne": None}  # Only chats with messages
        }

        cursor = db.chats.find(query_filter).sort("updated_at", -1)
        chats = []
        
        async for chat in cursor:
            try:
                chat_id_str = str(chat.get("_id", ""))
                if not chat_id_str:
                    continue

                created_at = chat.get("created_at")
                updated_at = chat.get("updated_at")

                created_at_str = (
                    created_at.isoformat()
                    if isinstance(created_at, datetime)
                    else datetime.utcnow().isoformat() if created_at is None
                    else str(created_at)
                )

                updated_at_str = (
                    updated_at.isoformat()
                    if isinstance(updated_at, datetime)
                    else datetime.utcnow().isoformat() if updated_at is None
                    else str(updated_at)
                )

                title = chat.get("title", "Yeni Sohbet")
                if not title or title.strip() == "":
                    title = "Yeni Sohbet"

                chats.append(
                    ChatListItem(
                        id=chat_id_str,
                        title=title,
                        created_at=created_at_str,
                        updated_at=updated_at_str,
                    )
                )
            except Exception as chat_error:
                logger.warning(f"Error processing chat: {str(chat_error)}")
                continue

        return chats

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[GET_CHATS] Error: {str(e)}", exc_info=True)
        # CRITICAL FIX: Always return JSON, never raise exception that might return text
        from fastapi.responses import JSONResponse
        try:
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "detail": f"Chat listesi alınamadı: {str(e)}",
                    "code": "CHATS_LIST_ERROR"
                }
            )
        except Exception as json_err:
            logger.error(f"[GET_CHATS] Failed to create JSONResponse: {json_err}")
            from fastapi.responses import Response
            return Response(
                content=f'{{"detail":"Chat listesi alınamadı: {str(e)}","code":"CHATS_LIST_ERROR"}}',
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                media_type="application/json",
            )(f"Error listing chats: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat listesi alınamadı: {str(e)}",
            headers={"code": "CHAT_LIST_ERROR"},
        )


@app.get("/chats/{chat_id}", response_model=ChatDetail)
async def get_chat(chat_id: str, authorization: Optional[str] = Header(None)):
    """
    Get a specific chat with ownership verification.
    """
    # Verify authentication
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Eksik veya geçersiz authorization header",
            headers={"code": "UNAUTHORIZED"},
        )

    token = authorization.split(" ")[1]
    user_doc = await get_current_user(token)
    user_id = str(user_doc["_id"])

    db = get_database()
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database bağlantısı yok",
            headers={"code": "DATABASE_ERROR"},
        )

    try:
        # Verify chat_id format
        try:
            chat_object_id = ObjectId(chat_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Geçersiz chat_id formatı",
                headers={"code": "INVALID_CHAT_ID"},
            )

        # Query with ownership check (exclude soft-deleted chats)
        # deleted_at can be None, missing, or a datetime - we want None or missing
        chat = await db.chats.find_one({
            "_id": chat_object_id, 
            "user_id": str(user_id),
            "$or": [
                {"deleted_at": None},
                {"deleted_at": {"$exists": False}},
                {"deleted_at": {"$eq": None}}  # Explicit None check
            ]
        })
        
        # Try ObjectId format if not found (legacy data)
        if not chat:
            try:
                user_object_id = ObjectId(str(user_id))
                chat = await db.chats.find_one({
                    "_id": chat_object_id, 
                    "user_id": user_object_id,
                    "$or": [
                        {"deleted_at": None},
                        {"deleted_at": {"$exists": False}},
                        {"deleted_at": {"$eq": None}}  # Explicit None check
                    ]
                })
            except (ValueError, TypeError):
                pass

        if not chat:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat bulunamadı veya erişim reddedildi",
                headers={"code": "CHAT_NOT_FOUND"},
            )

        created_at_str = (
            chat["created_at"].isoformat()
            if isinstance(chat["created_at"], datetime)
            else str(chat["created_at"])
        )
        updated_at_str = (
            chat["updated_at"].isoformat()
            if isinstance(chat["updated_at"], datetime)
            else str(chat["updated_at"])
        )

        last_message_at = chat.get("last_message_at")
        last_message_at_str = (
            last_message_at.isoformat()
            if isinstance(last_message_at, datetime)
            else str(last_message_at) if last_message_at else None
        )
        
        deleted_at = chat.get("deleted_at")
        deleted_at_str = (
            deleted_at.isoformat()
            if isinstance(deleted_at, datetime)
            else str(deleted_at) if deleted_at else None
        )
        
        return ChatDetail(
            id=str(chat["_id"]),
            title=chat.get("title", "Yeni Sohbet"),
            created_at=created_at_str,
            updated_at=updated_at_str,
            user_id=user_id,
            last_message_at=last_message_at_str,
            deleted_at=deleted_at_str,
            pinned=chat.get("pinned", False),
            tags=chat.get("tags"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting chat: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat alınamadı: {str(e)}",
            headers={"code": "CHAT_GET_ERROR"},
        )


@app.get("/chats/{chat_id}/messages", response_model=ChatMessagesResponse)
async def get_chat_messages(
    chat_id: str,
    authorization: Optional[str] = Header(None),
    limit: int = 50,
    cursor: Optional[str] = None,
):
    """
    Get messages for a specific chat with cursor-based pagination.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Eksik veya geçersiz authorization header",
            headers={"code": "UNAUTHORIZED"},
        )

    token = authorization.split(" ")[1]
    user_doc = await get_current_user(token)
    user_id = str(user_doc["_id"])

    db = get_database()
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database bağlantısı yok",
            headers={"code": "DATABASE_ERROR"},
        )

    try:
        # Convert chat_id to ObjectId
        try:
            chat_object_id = ObjectId(chat_id)
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Geçersiz chat_id formatı",
                headers={"code": "INVALID_CHAT_ID"},
            )

        # Verify chat ownership (exclude soft-deleted)
        chat = await db.chats.find_one({
            "_id": chat_object_id,
            "user_id": str(user_id),
            "$or": [
                {"deleted_at": None},
                {"deleted_at": {"$exists": False}}
            ]
        })

        if not chat:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat bulunamadı veya erişim reddedildi",
                headers={"code": "CHAT_NOT_FOUND"},
            )

        # Query messages: user_id as string, chat_id as string (matches message_store.py)
        # CRITICAL FIX: message_store.py saves chat_id as string, so query must use string too
        query = {
            "user_id": str(user_id),
            "chat_id": chat_id  # String (24 hex) - matches message_store.py
        }

        # Add cursor filter if provided
        if cursor:
            try:
                cursor_object_id = ObjectId(cursor)
                query["_id"] = {"$gt": cursor_object_id}
            except (ValueError, TypeError):
                pass

        # Query messages with limit + 1 to check if there are more
        find_limit = limit + 1
        logger.info(f"[CHATDBG] get_chat_messages chatId={chat_id} userId={user_id} query={query} status=querying")
        messages_cursor = db.chat_messages.find(query).sort("created_at", 1).limit(find_limit)

        messages = []
        message_count = 0
        last_message_id = None

        async for msg in messages_cursor:
            message_count += 1
            if message_count <= limit:
                sources = None
                if msg.get("sources"):
                    try:
                        sources = [SourceInfo(**s) for s in msg.get("sources")]
                    except:
                        sources = None

                created_at = msg.get("created_at")
                created_at_str = (
                    created_at.isoformat()
                    if isinstance(created_at, datetime)
                    else str(created_at) if created_at else ""
                )

                messages.append(
                    ChatMessageResponse(
                        message_id=str(msg.get("_id", "")),
                        role=msg.get("role", "user"),
                        content=msg.get("content", ""),
                        sources=sources,
                        created_at=created_at_str,
                        client_message_id=msg.get("client_message_id"),
                    )
                )
                last_message_id = str(msg.get("_id", ""))
            else:
                break

        has_more = message_count > limit
        next_cursor = last_message_id if has_more else None

        logger.info(f"[CHATDBG] get_chat_messages chatId={chat_id} userId={user_id} count={len(messages)} status=success")
        return ChatMessagesResponse(
            messages=messages,
            cursor=next_cursor,
            has_more=has_more
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting chat messages: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Mesajlar alınamadı: {str(e)}",
            headers={"code": "MESSAGES_GET_ERROR"},
        )


@app.patch("/chats/{chat_id}", response_model=ChatDetail)
async def update_chat(
    chat_id: str,
    request: UpdateChatRequest,
    authorization: Optional[str] = Header(None),
):
    """
    Update a chat (currently only title).
    ChatGPT style: Title is set only once from first message and never changes.
    """
    # Verify authentication
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Eksik veya geçersiz authorization header",
            headers={"code": "UNAUTHORIZED"},
        )

    token = authorization.split(" ")[1]
    user_doc = await get_current_user(token)
    user_id = str(user_doc["_id"])

    db = get_database()
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database bağlantısı yok",
            headers={"code": "DATABASE_ERROR"},
        )

    try:
        # Verify chat_id format
        try:
            chat_object_id = ObjectId(chat_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Geçersiz chat_id formatı",
                headers={"code": "INVALID_CHAT_ID"},
            )

        # Query with ownership check (standardize user_id to string)
        chat = await db.chats.find_one({"_id": chat_object_id, "user_id": str(user_id)})
        
        # Try ObjectId format if not found (legacy data)
        if not chat:
            try:
                user_object_id = ObjectId(str(user_id))
                chat = await db.chats.find_one({"_id": chat_object_id, "user_id": user_object_id})
            except (ValueError, TypeError):
                pass

        if not chat:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat bulunamadı veya erişim reddedildi",
                headers={"code": "CHAT_NOT_FOUND"},
            )

        # Update chat fields
        update_fields = {"updated_at": datetime.utcnow()}
        if request.title is not None:
            update_fields["title"] = request.title
        if request.pinned is not None:
            update_fields["pinned"] = request.pinned
        if request.tags is not None:
            update_fields["tags"] = request.tags
        
        await db.chats.update_one(
            {"_id": chat_object_id, "user_id": str(user_id)},
            {"$set": update_fields},
        )

        # Fetch updated chat
        updated_chat = await db.chats.find_one({"_id": chat_object_id})

        if not updated_chat:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Chat güncellendi ama geri alınamadı",
                headers={"code": "CHAT_UPDATE_ERROR"},
            )

        created_at_str = (
            updated_chat["created_at"].isoformat()
            if isinstance(updated_chat["created_at"], datetime)
            else str(updated_chat["created_at"])
        )
        updated_at_str = (
            updated_chat["updated_at"].isoformat()
            if isinstance(updated_chat["updated_at"], datetime)
            else str(updated_chat["updated_at"])
        )

        last_message_at = updated_chat.get("last_message_at")
        last_message_at_str = (
            last_message_at.isoformat()
            if isinstance(last_message_at, datetime)
            else str(last_message_at) if last_message_at else None
        )
        
        deleted_at = updated_chat.get("deleted_at")
        deleted_at_str = (
            deleted_at.isoformat()
            if isinstance(deleted_at, datetime)
            else str(deleted_at) if deleted_at else None
        )
        
        return ChatDetail(
            id=str(updated_chat["_id"]),
            title=updated_chat["title"],
            created_at=created_at_str,
            updated_at=updated_at_str,
            user_id=user_id,
            last_message_at=last_message_at_str,
            deleted_at=deleted_at_str,
            pinned=updated_chat.get("pinned", False),
            tags=updated_chat.get("tags"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating chat: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat güncellenemedi: {str(e)}",
            headers={"code": "CHAT_UPDATE_ERROR"},
        )


@app.post("/chats/{chat_id}/messages", response_model=ChatMessageResponse)
async def send_chat_message(
    chat_id: str,
    request: ChatMessageRequest,
    authorization: Optional[str] = Header(None),
    http_request: Request = None,
):
    """
    Send a message in a chat. This is the new endpoint that replaces POST /api/chat.
    Saves user message, generates assistant response, and saves assistant message.
    """
    # Get request_id from middleware or generate new one
    request_id = (
        getattr(http_request.state, "request_id", str(uuid.uuid4())[:8])
        if http_request
        else str(uuid.uuid4())[:8]
    )
    
    # Verify authentication
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Eksik veya geçersiz authorization header",
            headers={"code": "UNAUTHORIZED"},
        )
    
    token = authorization.split(" ")[1]
    user_doc = await get_current_user(token)
    user_id = str(user_doc["_id"])
    
    # Validate message
    if not request.message or not request.message.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mesaj boş olamaz",
            headers={"code": "INVALID_MESSAGE"},
        )
    
    # Validate client_message_id
    if not request.client_message_id or not request.client_message_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="client_message_id zorunludur (UUID)",
            headers={"code": "MISSING_CLIENT_MESSAGE_ID"},
        )
    
    db = get_database()
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database bağlantısı yok",
            headers={"code": "DATABASE_ERROR"},
        )
    
    try:
        # Convert chat_id to ObjectId
        try:
            chat_object_id = ObjectId(chat_id)
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Geçersiz chat_id formatı",
                headers={"code": "INVALID_CHAT_ID"},
            )
        
        # Verify chat ownership
        chat_doc = await db.chats.find_one({
            "_id": chat_object_id,
            "user_id": str(user_id),
            "$or": [
                {"deleted_at": None},
                {"deleted_at": {"$exists": False}}
            ]
        })
        
        if not chat_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat bulunamadı veya erişim reddedildi",
                headers={"code": "CHAT_NOT_FOUND"},
            )
        
        # Check for duplicate client_message_id (idempotency)
        # CRITICAL FIX: message_store.py saves chat_id as string, so query must use string too
        existing_message = await db.chat_messages.find_one({
            "user_id": str(user_id),
            "chat_id": chat_id,  # String (24 hex) - matches message_store.py
            "client_message_id": request.client_message_id
        })
        
        if existing_message:
            created_at = existing_message.get("created_at")
            created_at_str = (
                created_at.isoformat()
                if isinstance(created_at, datetime)
                else str(created_at) if created_at else ""
            )
            
            sources = None
            if existing_message.get("sources"):
                try:
                    sources = [SourceInfo(**s) for s in existing_message.get("sources")]
                except:
                    sources = None
            
            return ChatMessageResponse(
                message_id=str(existing_message.get("_id", "")),
                role=existing_message.get("role", "user"),
                content=existing_message.get("content", ""),
                sources=sources,
                created_at=created_at_str,
                client_message_id=existing_message.get("client_message_id"),
            )
        
        # Save user message using message_store (which uses ObjectId)
        user_message_saved = await save_message(
            user_id=str(user_id),
            chat_id=chat_id,  # String, will be converted to ObjectId in save_message
            role="user",
            content=request.message,
            client_message_id=request.client_message_id
        )
        
        if not user_message_saved:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Kullanıcı mesajı kaydedilemedi",
                headers={"code": "MESSAGE_SAVE_ERROR"},
            )
        
        # Get the saved message ID
        # CRITICAL FIX: message_store.py saves chat_id as string, so query must use string too
        user_message = await db.chat_messages.find_one({
            "user_id": str(user_id),
            "chat_id": chat_id,  # String (24 hex) - matches message_store.py
            "client_message_id": request.client_message_id
        })
        user_message_id = str(user_message.get("_id", "")) if user_message else ""
        
        # Update chat: set last_message_at and updated_at
        await db.chats.update_one(
            {"_id": chat_object_id},
            {
                "$set": {
                    "last_message_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        # Generate assistant response by calling legacy /api/chat endpoint logic
        # Convert ChatMessageRequest to ChatRequest
        from app.schemas import ChatRequest
        
        # Create ChatRequest from ChatMessageRequest
        chat_request = ChatRequest(
            message=request.message,
            documentIds=getattr(request, 'documentIds', None),
            chatId=chat_id,
            useDocuments=getattr(request, 'useDocuments', False) or (getattr(request, 'documentIds', None) is not None and len(getattr(request, 'documentIds', [])) > 0),
            client_message_id=request.client_message_id,
            mode=getattr(request, 'mode', 'qa')
        )
        
        # Call legacy chat endpoint function directly
        # Get chat endpoint function from app routes (before chat variable is used)
        chat_endpoint_func = None
        for route in app.routes:
            if hasattr(route, 'path') and route.path == "/chat" and hasattr(route, 'endpoint'):
                chat_endpoint_func = route.endpoint
                break
        
        if not chat_endpoint_func:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Chat endpoint function not found",
                headers={"code": "INTERNAL_ERROR"},
            )
        
        try:
            # Create a mock request object for the legacy endpoint
            class MockRequest:
                def __init__(self):
                    self.state = type('obj', (object,), {'request_id': request_id})()
            
            mock_request = MockRequest()
            
            # Call the legacy chat endpoint function
            chat_response = await chat_endpoint_func(
                request=chat_request,
                authorization=authorization,
                http_request=mock_request
            )
            
            # Convert ChatResponse to ChatMessageResponse
            # The assistant message should already be saved by the legacy endpoint
            # Find the assistant message that was just created - chat_id is string
            # CRITICAL FIX: message_store.py saves chat_id as string, so query must use string too
            assistant_message = await db.chat_messages.find_one(
                {
                    "user_id": str(user_id),
                    "chat_id": chat_id,  # String (24 hex) - matches message_store.py
                    "role": "assistant"
                },
                sort=[("created_at", -1)]  # Get most recent assistant message
            )
            
            if assistant_message:
                created_at = assistant_message.get("created_at")
                created_at_str = (
                    created_at.isoformat()
                    if isinstance(created_at, datetime)
                    else str(created_at) if created_at else ""
                )
                
                sources = None
                if assistant_message.get("sources"):
                    try:
                        sources = [SourceInfo(**s) for s in assistant_message.get("sources")]
                    except:
                        sources = None
                elif chat_response.sources:
                    sources = chat_response.sources
                
                return ChatMessageResponse(
                    message_id=str(assistant_message.get("_id", "")),
                    role="assistant",
                    content=chat_response.message,
                    sources=sources,
                    created_at=created_at_str,
                    client_message_id=request.client_message_id,
                )
            else:
                # Fallback: return response from legacy endpoint even if message not found
                created_at_str = datetime.utcnow().isoformat()
                return ChatMessageResponse(
                    message_id=user_message_id,  # Use user message ID as fallback
                    role="assistant",
                    content=chat_response.message,
                    sources=chat_response.sources,
                    created_at=created_at_str,
                    client_message_id=request.client_message_id,
                )
        except Exception as e:
            logger.error(f"Error calling legacy chat endpoint: {str(e)}", exc_info=True)
            # Fallback: return user message if assistant generation fails
            created_at_str = datetime.utcnow().isoformat()
            return ChatMessageResponse(
                message_id=user_message_id,
                role="user",
                content=request.message,
                sources=None,
                created_at=created_at_str,
                client_message_id=request.client_message_id,
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending chat message: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Mesaj gönderilemedi: {str(e)}",
            headers={"code": "MESSAGE_SEND_ERROR"},
        )


@app.delete("/chats/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(
    chat_id: str,
    authorization: Optional[str] = Header(None),
    hard: bool = False,
):
    """
    Delete a chat with ownership verification.
    Default: soft delete (sets deleted_at). Use hard=true for permanent deletion.
    """
    # Verify authentication
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Eksik veya geçersiz authorization header",
            headers={"code": "UNAUTHORIZED"},
        )

    token = authorization.split(" ")[1]
    user_doc = await get_current_user(token)
    user_id = str(user_doc["_id"])

    db = get_database()
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database bağlantısı yok",
            headers={"code": "DATABASE_ERROR"},
        )

    try:
        # Verify chat_id format
        try:
            chat_object_id = ObjectId(chat_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Geçersiz chat_id formatı",
                headers={"code": "INVALID_CHAT_ID"},
            )

        # Verify ownership before deletion (standardize user_id to string)
        chat = await db.chats.find_one({"_id": chat_object_id, "user_id": str(user_id)})
        
        # Try ObjectId format if not found (legacy data)
        if not chat:
            try:
                user_object_id = ObjectId(str(user_id))
                chat = await db.chats.find_one({"_id": chat_object_id, "user_id": user_object_id})
            except (ValueError, TypeError):
                pass

        if not chat:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat bulunamadı veya erişim reddedildi",
                headers={"code": "CHAT_NOT_FOUND"},
            )

        if hard:
            # Hard delete: permanently remove chat and messages
            # CRITICAL FIX: message_store.py saves chat_id as string, so query must use string too
            deleted_messages_result = await db.chat_messages.delete_many({
                "user_id": str(user_id),
                "chat_id": chat_id  # String (24 hex) - matches message_store.py
            })
            deleted_messages_count = deleted_messages_result.deleted_count
            
            result = await db.chats.delete_one({
                "_id": chat_object_id,
                "user_id": str(user_id)
            })
            
            if result.deleted_count == 0:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Chat silinemedi",
                    headers={"code": "CHAT_DELETE_ERROR"},
                )
            
            logger.info(f"Hard deleted chat {chat_id} and {deleted_messages_count} messages")
        else:
            # Soft delete: set deleted_at timestamp
            result = await db.chats.update_one(
                {"_id": chat_object_id, "user_id": str(user_id)},
                {"$set": {"deleted_at": datetime.utcnow(), "updated_at": datetime.utcnow()}}
            )
            
            if result.matched_count == 0:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Chat bulunamadı",
                    headers={"code": "CHAT_NOT_FOUND"},
                )
        
        return None

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting chat: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat silinemedi: {str(e)}",
            headers={"code": "CHAT_DELETE_ERROR"},
        )


@app.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    authorization: Optional[str] = Header(None),
    http_request: Request = None,
):
    """
    Chat with AI assistant using RAG (Retrieval-Augmented Generation).
    Retrieves relevant document chunks and uses them to answer questions.
    """
    # #region agent log
    try:
        import json

        with open(
            r"c:\Users\msg\bitirme\.cursor\debug.log", "a", encoding="utf-8"
        ) as f:
            f.write(
                json.dumps(
                    {
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "hypothesisId": "A",
                        "location": "main.py:1301",
                        "message": "CHAT ENDPOINT ENTRY",
                        "data": {
                            "has_request": request is not None,
                            "has_auth": authorization is not None,
                            "chat_id": (
                                request.chatId
                                if request and hasattr(request, "chatId")
                                else None
                            ),
                        },
                        "timestamp": int(datetime.utcnow().timestamp() * 1000),
                    }
                )
                + "\n"
            )
    except:
        pass
    # #endregion
    # Get request_id from middleware or generate new one
    request_id = (
        getattr(http_request.state, "request_id", str(uuid.uuid4())[:8])
        if http_request
        else str(uuid.uuid4())[:8]
    )

    # Verify authentication
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Eksik veya geçersiz authorization header",
            headers={"code": "UNAUTHORIZED"},
        )

    token = authorization.split(" ")[1]
    user_doc = await get_current_user(token)
    user_id = str(user_doc["_id"])

    # Validate message - empty message guard
    if not request.message or not request.message.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mesaj boş olamaz",
            headers={"code": "INVALID_MESSAGE"},
        )

    # Validate client_message_id (REQUIRED for idempotency)
    if not request.client_message_id or not request.client_message_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="client_message_id zorunludur (UUID)",
            headers={"code": "MISSING_CLIENT_MESSAGE_ID"},
        )

    logger.info(
        f"[{request_id}] Chat request from user {user_id}, message length: {len(request.message)}, client_message_id: {request.client_message_id}"
    )

    # Validate chat_id is required
    if not request.chatId or not request.chatId.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="chatId zorunludur",
            headers={"code": "MISSING_CHAT_ID"},
        )

    chat_id = request.chatId.strip()

    # Verify chat ownership
    db = get_database()
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database bağlantısı yok",
            headers={"code": "DATABASE_ERROR"},
        )

    # Validate and try to convert chat_id to ObjectId
    # MongoDB ObjectId should be 24 hex characters, but sometimes can be 23 if leading zero is omitted
    chat_object_id = None
    chat = None
    
    # Validate chat_id format: must be 24 hex characters (MongoDB ObjectId standard)
    # Allow 23 characters with leading zero padding fallback for legacy data
    if not chat_id or not isinstance(chat_id, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Geçersiz chat_id formatı: chat_id boş veya string değil. chat_id: {str(chat_id)[:20] if chat_id else 'None'}...",
            headers={"code": "INVALID_CHAT_ID"},
        )
    
    chat_id = chat_id.strip()
    chat_id_len = len(chat_id)
    
    # Validate chat_id length: must be 23 or 24 hex characters
    if chat_id_len not in [23, 24]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Geçersiz chat_id formatı: chat_id uzunluğu {chat_id_len} karakter (23 veya 24 olmalı). chat_id: {chat_id[:20]}...",
            headers={"code": "INVALID_CHAT_ID"},
        )
    
    # Validate hex characters only
    if not all(c in '0123456789abcdefABCDEF' for c in chat_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Geçersiz chat_id formatı: chat_id sadece hex karakterler içermeli (0-9, a-f, A-F). chat_id: {chat_id[:20]}...",
            headers={"code": "INVALID_CHAT_ID"},
        )
    
    # Try to convert to ObjectId
    conversion_attempts = []
    if chat_id_len == 24:
        # Standard 24-character ObjectId
        conversion_attempts.append(chat_id)
    elif chat_id_len == 23:
        # Try with leading zero padding
        conversion_attempts.append("0" + chat_id)
        # Also try original (in case it's valid)
        conversion_attempts.append(chat_id)
    
    # CRITICAL: Use ObjectId from top-level import (line 9)
    # Import locally to avoid any potential UnboundLocalError issues
    from bson import ObjectId as BsonObjectId
    
    for attempt_id in conversion_attempts:
        try:
            # Use BsonObjectId to avoid any scope issues
            chat_object_id = BsonObjectId(attempt_id)
            if attempt_id != chat_id:
                logger.debug(f"[{request_id}] Chat ID normalized: {chat_id} -> {attempt_id}")
            break  # Success, exit loop
        except (ValueError, TypeError) as e:
            # Continue to next attempt
            logger.debug(f"[{request_id}] Failed to convert '{attempt_id}' to ObjectId: {e}")
            continue
        except Exception as e:
            # Unexpected error
            error_type = type(e).__name__
            logger.error(f"[{request_id}] Unexpected error converting chat_id '{attempt_id}' to ObjectId: {error_type}: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Geçersiz chat_id formatı: {error_type}: {str(e)}. chat_id: {chat_id[:20]}... (uzunluk: {chat_id_len})",
                headers={"code": "INVALID_CHAT_ID"},
            )
    
    if chat_object_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Geçersiz chat_id formatı: ObjectId'ye çevrilemedi. chat_id: {chat_id[:20]}... (uzunluk: {chat_id_len})",
            headers={"code": "INVALID_CHAT_ID"},
        )

    # Verify chat ownership - try both string and ObjectId format for user_id
    normalized_user_id = str(user_id)
    chat = await db.chats.find_one({"_id": chat_object_id, "user_id": normalized_user_id})
    
    # If not found, try with ObjectId format for user_id (legacy data)
    if not chat:
        try:
            user_object_id = ObjectId(normalized_user_id)
            chat = await db.chats.find_one({"_id": chat_object_id, "user_id": user_object_id})
        except (ValueError, TypeError):
            pass

    if not chat:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chat bulunamadı veya erişim reddedildi",
            headers={"code": "CHAT_ACCESS_DENIED"},
        )

    # Resolve carryover (follow-up continuity)
    original_message = request.message
    resolved_message, carryover_used = await resolve_carryover(
        user_id=user_id,
        chat_id=chat_id,
        user_message=original_message,
        document_ids=request.documentIds
    )
    
    if carryover_used:
        logger.info(
            f"[{request_id}] CARRYOVER: Original='{original_message[:50]}...' "
            f"→ Rewritten='{resolved_message[:100]}...'"
        )
    
    # Use resolved message for RAG and LLM (but save original to memory)
    query_message = resolved_message
    
    # Save user message to memory (save original, not rewritten)
    user_message_saved = await save_message(
        user_id=user_id,
        chat_id=chat_id,
        role="user",
        content=original_message,
        client_message_id=request.client_message_id,
    )
    
    if not user_message_saved:
        logger.warning(f"[{request_id}] Failed to save user message (chat_id={chat_id})")
    
    # Get message count for summary check
    db = get_database()
    message_count = 0
    if db is not None:
        try:
            # Ensure user_id and chat_id are strings
            normalized_user_id = str(user_id)
            normalized_chat_id = str(chat_id)
            
            # Try string format first
            query = {
                "user_id": normalized_user_id,
                "chat_id": normalized_chat_id
            }
            message_count = await db.chat_messages.count_documents(query)
            
            # If no matches, try ObjectId format for user_id (legacy data)
            if message_count == 0:
                try:
                    from bson import ObjectId
                    user_object_id = ObjectId(normalized_user_id)
                    query_oid = {
                        "user_id": user_object_id,
                        "chat_id": normalized_chat_id
                    }
                    message_count = await db.chat_messages.count_documents(query_oid)
                except (ValueError, TypeError):
                    pass
        except Exception as e:
            logger.warning(f"[{request_id}] Error counting messages: {str(e)}")
    
    # Build dynamic context (with token budget) - parallel with document fetch
    chat_history_task = asyncio.create_task(
        build_context_messages(
            user_id=user_id,
            chat_id=chat_id,
            max_tokens=CONTEXT_MAX_TOKENS,
            hard_limit=CONTEXT_HARD_LIMIT
        )
    )

    # Mark chat as having messages and generate title after first message
    async def mark_chat_active_and_generate_title():
        # #region agent log
        try:
            import json

            with open(
                r"c:\Users\msg\bitirme\.cursor\debug.log", "a", encoding="utf-8"
            ) as f:
                f.write(
                    json.dumps(
                        {
                            "sessionId": "debug-session",
                            "runId": "run1",
                            "hypothesisId": "A",
                            "location": "main.py:1383",
                            "message": "mark_chat_active_and_generate_title ENTRY",
                            "data": {"chat_id": chat_id[:8], "request_id": request_id},
                            "timestamp": int(datetime.utcnow().timestamp() * 1000),
                        }
                    )
                    + "\n"
                )
        except:
            pass
        # #endregion
        try:
            logger.info(
                f"[{request_id}] Starting mark_chat_active_and_generate_title for chat {chat_id[:8]}..."
            )

            # User message is already saved (await above), no retry needed
            # Get user message count for title generation check
            user_message_count = 0
            db = get_database()
            if db is not None:
                try:
                    # Ensure user_id and chat_id are strings
                    normalized_user_id = str(user_id)
                    normalized_chat_id = str(chat_id)
                    
                    # Try string format first
                    query = {
                        "user_id": normalized_user_id,
                        "chat_id": normalized_chat_id,
                        "role": "user"
                    }
                    user_message_count = await db.chat_messages.count_documents(query)
                    
                    # If no matches, try ObjectId format for user_id (legacy data)
                    if user_message_count == 0:
                        try:
                            from bson import ObjectId
                            user_object_id = ObjectId(normalized_user_id)
                            query_oid = {
                                "user_id": user_object_id,
                                "chat_id": normalized_chat_id,
                                "role": "user"
                            }
                            user_message_count = await db.chat_messages.count_documents(query_oid)
                        except (ValueError, TypeError):
                            pass
                except Exception as e:
                    logger.warning(f"[{request_id}] Error counting user messages: {str(e)}")
            
            logger.info(
                f"[{request_id}] User message saved, count: {user_message_count}"
            )

            # Always mark chat as active if this is the first message attempt
            # Check if chat already has messages to avoid duplicate processing
            existing_has_messages = False
            db = get_database()
            if db is not None:
                existing_chat = await db.chats.find_one(
                    {"_id": chat_object_id, "user_id": user_id}
                )
                existing_has_messages = (
                    existing_chat.get("has_messages", False) if existing_chat else False
                )

                if not existing_has_messages:
                    # #region agent log
                    try:
                        import json

                        with open(
                            r"c:\Users\msg\bitirme\.cursor\debug.log",
                            "a",
                            encoding="utf-8",
                        ) as f:
                            f.write(
                                json.dumps(
                                    {
                                        "sessionId": "debug-session",
                                        "runId": "run1",
                                        "hypothesisId": "B",
                                        "location": "main.py:1420",
                                        "message": "BEFORE has_messages update",
                                        "data": {
                                            "chat_id": chat_id[:8],
                                            "existing_has_messages": existing_has_messages,
                                        },
                                        "timestamp": int(
                                            datetime.utcnow().timestamp() * 1000
                                        ),
                                    }
                                )
                                + "\n"
                            )
                    except:
                        pass
                    # #endregion
                    # This is the first message, mark chat as active
                    update_result = await db.chats.update_one(
                        {"_id": chat_object_id, "user_id": user_id},
                        {
                            "$set": {
                                "has_messages": True,
                                "updated_at": datetime.utcnow(),
                            }
                        },
                    )
                    logger.info(
                        f"[{request_id}] Marked chat {chat_id[:8]}... as active (first message). Matched: {update_result.matched_count}, Modified: {update_result.modified_count}"
                    )

                    # #region agent log
                    try:
                        import json

                        with open(
                            r"c:\Users\msg\bitirme\.cursor\debug.log",
                            "a",
                            encoding="utf-8",
                        ) as f:
                            f.write(
                                json.dumps(
                                    {
                                        "sessionId": "debug-session",
                                        "runId": "run1",
                                        "hypothesisId": "B",
                                        "location": "main.py:1426",
                                        "message": "AFTER has_messages update",
                                        "data": {
                                            "chat_id": chat_id[:8],
                                            "matched": update_result.matched_count,
                                            "modified": update_result.modified_count,
                                        },
                                        "timestamp": int(
                                            datetime.utcnow().timestamp() * 1000
                                        ),
                                    }
                                )
                                + "\n"
                            )
                    except:
                        pass
                    # #endregion

                    # Verify the update
                    updated_chat = await db.chats.find_one(
                        {"_id": chat_object_id, "user_id": user_id}
                    )
                    if updated_chat:
                        has_messages_value = updated_chat.get("has_messages")
                        logger.info(
                            f"[{request_id}] Verified: chat has_messages = {has_messages_value}"
                        )
                        # #region agent log
                        try:
                            import json

                            with open(
                                r"c:\Users\msg\bitirme\.cursor\debug.log",
                                "a",
                                encoding="utf-8",
                            ) as f:
                                f.write(
                                    json.dumps(
                                        {
                                            "sessionId": "debug-session",
                                            "runId": "run1",
                                            "hypothesisId": "B",
                                            "location": "main.py:1431",
                                            "message": "VERIFIED has_messages value",
                                            "data": {
                                                "chat_id": chat_id[:8],
                                                "has_messages": has_messages_value,
                                            },
                                            "timestamp": int(
                                                datetime.utcnow().timestamp() * 1000
                                            ),
                                        }
                                    )
                                    + "\n"
                                )
                        except:
                            pass
                        # #endregion
                    else:
                        logger.error(
                            f"[{request_id}] ERROR: Could not verify chat update!"
                        )
                        # #region agent log
                        try:
                            with open(
                                r"c:\Users\msg\bitirme\.cursor\debug.log",
                                "a",
                                encoding="utf-8",
                            ) as f:
                                f.write(
                                    json.dumps(
                                        {
                                            "sessionId": "debug-session",
                                            "runId": "run1",
                                            "hypothesisId": "B",
                                            "location": "main.py:1434",
                                            "message": "VERIFICATION FAILED",
                                            "data": {"chat_id": chat_id[:8]},
                                            "timestamp": int(
                                                datetime.utcnow().timestamp() * 1000
                                            ),
                                        }
                                    )
                                    + "\n"
                                )
                        except:
                            pass
                        # #endregion
                else:
                    logger.info(
                        f"[{request_id}] Chat already has has_messages=True, skipping update"
                    )

            # Generate title if this is the first user message
            # Also generate if message count is 0 (ENABLE_MEMORY might be False, but we still have the message)
            if user_message_count == 1 or (
                user_message_count == 0 and not existing_has_messages
            ):
                # Get document filenames if available
                document_filenames = None
                if request.documentIds and len(request.documentIds) > 0:
                    try:
                        db = get_database()
                        if db is not None:
                            doc_filenames = []
                            for doc_id in request.documentIds[:3]:  # Max 3 filenames
                                try:
                                    doc = await db.documents.find_one(
                                        {"_id": ObjectId(doc_id), "user_id": user_id},
                                        {"filename": 1},
                                    )
                                    if doc:
                                        doc_filenames.append(
                                            doc.get("filename", "unknown")
                                        )
                                except:
                                    pass
                            if doc_filenames:
                                document_filenames = doc_filenames
                    except Exception as e:
                        logger.warning(
                            f"Error fetching document filenames for title: {str(e)}"
                        )

                # Generate title after first message (background task, non-blocking)
                try:
                    # #region agent log
                    try:
                        import json

                        with open(
                            r"c:\Users\msg\bitirme\.cursor\debug.log",
                            "a",
                            encoding="utf-8",
                        ) as f:
                            f.write(
                                json.dumps(
                                    {
                                        "sessionId": "debug-session",
                                        "runId": "run1",
                                        "hypothesisId": "C",
                                        "location": "main.py:1464",
                                        "message": "BEFORE generateAndSetTitle",
                                        "data": {
                                            "chat_id": chat_id[:8],
                                            "user_message_count": user_message_count,
                                        },
                                        "timestamp": int(
                                            datetime.utcnow().timestamp() * 1000
                                        ),
                                    }
                                )
                                + "\n"
                            )
                    except:
                        pass
                    # #endregion
                    generated_title = await generateAndSetTitle(
                        chat_id=chat_id,
                        user_id=user_id,
                        chat_mode=request.mode,
                        document_filenames=document_filenames,
                    )
                    # #region agent log
                    try:
                        import json

                        with open(
                            r"c:\Users\msg\bitirme\.cursor\debug.log",
                            "a",
                            encoding="utf-8",
                        ) as f:
                            f.write(
                                json.dumps(
                                    {
                                        "sessionId": "debug-session",
                                        "runId": "run1",
                                        "hypothesisId": "C",
                                        "location": "main.py:1471",
                                        "message": "AFTER generateAndSetTitle",
                                        "data": {
                                            "chat_id": chat_id[:8],
                                            "generated_title": generated_title,
                                        },
                                        "timestamp": int(
                                            datetime.utcnow().timestamp() * 1000
                                        ),
                                    }
                                )
                                + "\n"
                            )
                    except:
                        pass
                    # #endregion
                    if not generated_title:
                        # If title generation failed, set a fallback title
                        logger.warning(
                            f"[{request_id}] Title generation returned None, setting fallback title"
                        )
                        from app.chat_title import generateFallbackTitle

                        fallback_title = generateFallbackTitle(
                            first_message=request.message,
                            document_filenames=document_filenames,
                        )
                        # Update chat with fallback title
                        await db.chats.update_one(
                            {"_id": chat_object_id, "user_id": user_id},
                            {
                                "$set": {
                                    "title": fallback_title,
                                    "title_source": "fallback",
                                    "updated_at": datetime.utcnow(),
                                }
                            },
                        )
                except Exception as title_error:
                    logger.error(
                        f"[{request_id}] Error generating title: {str(title_error)}",
                        exc_info=True,
                    )
                    # Even if title generation fails, set a basic fallback
                    try:
                        from app.chat_title import generateFallbackTitle

                        fallback_title = generateFallbackTitle(
                            first_message=request.message,
                            document_filenames=document_filenames,
                        )
                        await db.chats.update_one(
                            {"_id": chat_object_id, "user_id": user_id},
                            {
                                "$set": {
                                    "title": fallback_title,
                                    "title_source": "fallback",
                                    "updated_at": datetime.utcnow(),
                                }
                            },
                        )
                    except Exception as fallback_error:
                        logger.error(
                            f"[{request_id}] Even fallback title generation failed: {str(fallback_error)}"
                        )
            else:
                logger.warning(
                    f"[{request_id}] user_message_count is {user_message_count}, not 1. Skipping title generation."
                )
        except Exception as e:
            logger.error(
                f"[{request_id}] ERROR in mark chat active and title generation: {str(e)}",
                exc_info=True,
            )
            import traceback

            logger.error(f"[{request_id}] Full traceback: {traceback.format_exc()}")
            # #region agent log
            try:
                with open(
                    r"c:\Users\msg\bitirme\.cursor\debug.log", "a", encoding="utf-8"
                ) as f:
                    f.write(
                        json.dumps(
                            {
                                "sessionId": "debug-session",
                                "runId": "run1",
                                "hypothesisId": "A",
                                "location": "main.py:1510",
                                "message": "mark_chat_active_and_generate_title EXCEPTION",
                                "data": {"chat_id": chat_id[:8], "error": str(e)},
                                "timestamp": int(datetime.utcnow().timestamp() * 1000),
                            }
                        )
                        + "\n"
                    )
            except:
                pass
            # #endregion

    # Mark chat active and generate title in background (after a short delay to ensure message is saved)
    # #region agent log
    try:
        import json

        with open(
            r"c:\Users\msg\bitirme\.cursor\debug.log", "a", encoding="utf-8"
        ) as f:
            f.write(
                json.dumps(
                    {
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "hypothesisId": "A",
                        "location": "main.py:1515",
                        "message": "CREATING mark_chat_active task",
                        "data": {"chat_id": chat_id[:8]},
                        "timestamp": int(datetime.utcnow().timestamp() * 1000),
                    }
                )
                + "\n"
            )
    except:
        pass
    # #endregion
    asyncio.create_task(mark_chat_active_and_generate_title())

    # Idempotency check: if same (user, chat, client_message_id) seen before, return cached response instead of new run
    cache_key = f"{user_id}:{chat_id}:{request.client_message_id}"
    if cache_key in message_cache:
        cached_response = message_cache[cache_key]
        logger.info(
            f"[{request_id}] [DUPLICATE_REQUEST] Returning cached response for client_message_id={request.client_message_id} "
            f"chat_id={chat_id} user_id={user_id}"
        )
        return cached_response

    # Log first-time request
    logger.info(
        f"[{request_id}] [NEW_REQUEST] New client_message_id: {request.client_message_id}, "
        f"Message: {request.message[:50]}..., Cache key: {cache_key}"
    )

    # Log request payload (without sensitive message content)
    doc_ids_count = len(request.documentIds) if request.documentIds else 0
    incoming_document_ids = request.documentIds if request.documentIds else []
    incoming_chat_id = request.chatId if hasattr(request, "chatId") else None

    logger.info(
        f"[{request_id}] CHAT_REQ user_id={user_id} "
        f"docIds_count={doc_ids_count} message_len={len(request.message)} "
        f"chatId={incoming_chat_id} "
        f"documentIds={incoming_document_ids[:3] if incoming_document_ids else []}..."
    )

    # Hybrid RAG: Always attempt retrieval, but decide relevance based on threshold
    retrieved_chunks = []
    sources = []
    user_document_ids = []
    has_specific_documents = (
        request.documentIds is not None and len(request.documentIds) > 0
    )
    # If documentIds are explicitly provided, set use_documents to True
    # This ensures documents are used even if RAG retrieval fails
    use_documents = bool(has_specific_documents)  # Set to True if documentIds provided

    # Store found documents for fallback (if RAG retrieval fails)
    found_documents_for_fallback = []

    # Debug info for response
    debug_info = {
        "incoming_document_ids": incoming_document_ids,
        "incoming_document_ids_count": doc_ids_count,
        "incoming_chat_id": incoming_chat_id,
        "db_documents_found": 0,
        "db_documents_with_content": 0,
        "db_documents_without_content": 0,
        "retrieved_chunks_count": 0,
        "context_added_to_prompt": False,
        "context_chars": 0,
        "scope_mismatch": False,
        "rag_fallback_used": False,
    }

    try:
        db = get_database()
        if db is not None:
            # Determine which documents to search
            if request.documentIds and len(request.documentIds) > 0:
                # Filter to only selected documents (chat-specific attachments)
                # IMPORTANT: If documentIds are explicitly provided, ignore chat-scoping
                # This allows users to use documents from any chat if they explicitly select them
                try:
                    # Convert documentIds to ObjectId, skip invalid ones
                    valid_object_ids = []
                    for doc_id in request.documentIds:
                        try:
                            valid_object_ids.append(ObjectId(doc_id))
                        except Exception as e:
                            logger.warning(
                                f"[{request_id}] Invalid documentId format: {doc_id}, error: {str(e)}"
                            )
                            continue

                    logger.info(
                        f"[{request_id}] DOC_FETCH_START: "
                        f"received_documentIds_count={len(request.documentIds)} "
                        f"valid_object_ids_count={len(valid_object_ids)} "
                        f"user_id={user_id} "
                        f"chatId={incoming_chat_id}"
                    )

                    if valid_object_ids:
                        # Query WITHOUT chat-scoping (explicit documentIds override scope)
                        # Only check: user_id and _id match
                        query_filter = {
                            "user_id": user_id,
                            "_id": {"$in": valid_object_ids},
                        }

                        logger.info(
                            f"[{request_id}] DOC_FETCH_QUERY: filter={query_filter} "
                            f"(chat-scoping IGNORED because documentIds explicitly provided)"
                        )

                        # Fetch documents with full details for logging
                        cursor = db.documents.find(
                            query_filter,
                            {
                                "_id": 1,
                                "filename": 1,
                                "text_content": 1,
                                "is_chat_scoped": 1,
                                "uploaded_from_chat_id": 1,
                            },
                        )

                        found_docs = []
                        found_doc_ids = []
                        docs_without_text = []
                        scope_mismatches = []

                        async for doc in cursor:
                            doc_id_str = str(doc["_id"])
                            found_doc_ids.append(doc_id_str)
                            user_document_ids.append(doc_id_str)

                            text_content = doc.get("text_content", "")
                            text_length = len(text_content) if text_content else 0
                            text_has_content = bool(
                                text_content and text_content.strip()
                            )

                            is_chat_scoped = doc.get("is_chat_scoped", False)
                            uploaded_from_chat_id = doc.get("uploaded_from_chat_id")

                            doc_info_dict = {
                                "id": doc_id_str,
                                "filename": doc.get("filename", "unknown"),
                                "text_length": text_length,
                                "text_has_content": text_has_content,
                                "is_chat_scoped": is_chat_scoped,
                                "uploaded_from_chat_id": uploaded_from_chat_id,
                                "text_content": text_content,  # Store for fallback
                            }
                            found_docs.append(doc_info_dict)
                            found_documents_for_fallback.append(doc_info_dict)

                            if not text_has_content:
                                docs_without_text.append(doc_id_str)

                            # Check for scope mismatch (for logging only, we still use the doc)
                            if (
                                is_chat_scoped
                                and uploaded_from_chat_id != incoming_chat_id
                            ):
                                scope_mismatches.append(
                                    {
                                        "doc_id": doc_id_str,
                                        "filename": doc.get("filename", "unknown"),
                                        "uploaded_from_chat_id": uploaded_from_chat_id,
                                        "current_chat_id": incoming_chat_id,
                                    }
                                )

                        debug_info["db_documents_found"] = len(found_docs)
                        debug_info["scope_mismatch"] = len(scope_mismatches) > 0

                        # Detailed logging
                        logger.info(
                            f"[{request_id}] DOC_FETCH_RESULT: "
                            f"found_docs_count={len(found_docs)}/{len(request.documentIds)} "
                            f"found_doc_ids={found_doc_ids[:3]}... "
                            f"docs_without_text_count={len(docs_without_text)} "
                            f"scope_mismatches={len(scope_mismatches)}"
                        )

                        # Log each found document
                        for doc_info in found_docs:
                            logger.info(
                                f"[{request_id}] DOC_FOUND: "
                                f"id={doc_info['id'][:8]}... "
                                f"filename={doc_info['filename']} "
                                f"text_length={doc_info['text_length']} "
                                f"text_has_content={doc_info['text_has_content']} "
                                f"is_chat_scoped={doc_info['is_chat_scoped']} "
                                f"uploaded_from_chat_id={doc_info['uploaded_from_chat_id']}"
                            )

                        # Log scope mismatches
                        if scope_mismatches:
                            for mismatch in scope_mismatches:
                                logger.warning(
                                    f"[{request_id}] SCOPE_MISMATCH (OVERRIDDEN): "
                                    f"doc_id={mismatch['doc_id'][:8]}... "
                                    f"filename={mismatch['filename']} "
                                    f"uploaded_from_chat_id={mismatch['uploaded_from_chat_id']} "
                                    f"current_chat_id={mismatch['current_chat_id']} "
                                    f"→ Document used anyway because explicitly selected"
                                )

                        # Log documents without text
                        if docs_without_text:
                            logger.error(
                                f"[{request_id}] DOCS_WITHOUT_TEXT: "
                                f"count={len(docs_without_text)} "
                                f"doc_ids={docs_without_text[:3]}... "
                                f"→ These documents will NOT be searchable"
                            )

                        # Log first 200 chars of text_content for first document (debug only)
                        if found_docs and found_docs[0]["text_has_content"]:
                            try:
                                first_doc = await db.documents.find_one(
                                    {"_id": ObjectId(found_docs[0]["id"])},
                                    {"text_content": 1},
                                )
                                if first_doc:
                                    first_doc_text = first_doc.get("text_content", "")
                                    if first_doc_text:
                                        preview = first_doc_text[:200].replace(
                                            "\n", " "
                                        )
                                        logger.info(
                                            f"[{request_id}] DOC_TEXT_PREVIEW (first doc): "
                                            f"{preview}..."
                                        )
                            except Exception as preview_error:
                                logger.warning(
                                    f"[{request_id}] Error getting text preview: {str(preview_error)}"
                                )

                        if len(found_docs) == 0:
                            logger.error(
                                f"[{request_id}] DOC_FETCH_EMPTY: "
                                f"No documents found! "
                                f"Query filter: {query_filter} "
                                f"→ Check: user_id match, documentIds valid, documents exist in DB"
                            )

                    logger.info(
                        f"[{request_id}] RAG: Using chat-specific documents: "
                        f"{len(user_document_ids)}/{len(request.documentIds)} "
                        f"valid_object_ids={len(valid_object_ids)}"
                    )

                    if len(user_document_ids) < len(request.documentIds):
                        missing_ids = set(request.documentIds) - set(user_document_ids)
                        logger.warning(
                            f"[{request_id}] RAG: Some documentIds not found or not owned by user. "
                            f"Requested: {request.documentIds}, Found: {user_document_ids}, "
                            f"Missing: {list(missing_ids)[:3]}..."
                        )
                except Exception as e:
                    logger.error(
                        f"[{request_id}] Error processing documentIds: {str(e)}",
                        exc_info=True,
                    )
                    # Continue with empty user_document_ids, will use global library
            else:
                # Use all user's documents (global library)
                cursor = db.documents.find({"user_id": user_id}, {"_id": 1})
                async for doc in cursor:
                    user_document_ids.append(str(doc["_id"]))

                debug_info["db_documents_found"] = len(user_document_ids)
                logger.info(
                    f"[{request_id}] RAG: Using global document library: {len(user_document_ids)} documents"
                )

            if user_document_ids:
                # Check document creation times and text content for debugging
                doc_times = {}
                doc_text_lengths = {}
                try:
                    doc_cursor = db.documents.find(
                        {
                            "_id": {
                                "$in": [
                                    ObjectId(doc_id) for doc_id in user_document_ids
                                ]
                            }
                        },
                        {"_id": 1, "created_at": 1, "filename": 1, "text_content": 1},
                    )
                    async for doc in doc_cursor:
                        doc_id_str = str(doc["_id"])
                        created_at = doc.get("created_at")
                        text_content = doc.get("text_content", "")
                        text_length = len(text_content) if text_content else 0
                        text_has_content = bool(text_content and text_content.strip())

                        doc_text_lengths[doc_id_str] = {
                            "text_length": text_length,
                            "has_content": text_has_content,
                            "filename": doc.get("filename", "unknown"),
                        }

                        if isinstance(created_at, datetime):
                            doc_times[doc_id_str] = {
                                "created_at": created_at,
                                "age_seconds": (
                                    datetime.utcnow() - created_at
                                ).total_seconds(),
                                "filename": doc.get("filename", "unknown"),
                            }

                        # CRITICAL: Warn if document has empty text_content
                        if not text_has_content:
                            logger.error(
                                f"[{request_id}] RAG_CRITICAL: Document {doc_id_str[:8]}... "
                                f"({doc.get('filename', 'unknown')}) has EMPTY text_content! "
                                f"This document will NOT be searchable. "
                                f"PDF may be scanned/image-based or extraction failed."
                            )
                except Exception as e:
                    logger.warning(
                        f"[{request_id}] RAG: Error fetching document times: {str(e)}"
                    )

                # Count documents with content
                docs_with_content = sum(
                    1 for d in doc_text_lengths.values() if d.get("has_content", False)
                )
                docs_without_content = len(doc_text_lengths) - docs_with_content

                debug_info["db_documents_with_content"] = docs_with_content
                debug_info["db_documents_without_content"] = docs_without_content

                logger.info(
                    f"[{request_id}] RAG_QUERY_PREP: doc_count={len(user_document_ids)} "
                    f"doc_ids={user_document_ids[:3]}... "
                    f"recent_docs={sum(1 for dt in doc_times.values() if dt['age_seconds'] < 60)} "
                    f"docs_with_content={docs_with_content} docs_without_content={docs_without_content} "
                    f"query='{request.message[:50]}...'"
                )

                # Warn if some documents have no content
                if docs_without_content > 0:
                    logger.warning(
                        f"[{request_id}] RAG_WARNING: {docs_without_content} documents have empty text_content "
                        f"and will NOT be searchable. Check PDF extraction logs."
                    )

                # Use centralized RAG decision function
                # Use resolved message (with carryover) for RAG
                selected_doc_ids = request.documentIds if request.documentIds else []
                rag_result = await decide_context(
                    query=query_message,  # Use resolved message (with carryover)
                    selected_doc_ids=selected_doc_ids,
                    user_id=user_id,
                    user_document_ids=user_document_ids,
                    found_documents_for_fallback=found_documents_for_fallback,
                    mode=request.mode,
                    request_id=request_id,
                )

                # Extract results from decide_context
                context_text = rag_result["context_text"]
                sources = rag_result["sources"]
                retrieved_chunks = rag_result["retrieved_chunks"]
                use_documents = rag_result["should_use_documents"]
                doc_not_found = rag_result.get("doc_not_found", False)
                
                # Update debug info
                debug_info["retrieved_chunks_count"] = rag_result["retrieval_stats"][
                    "retrieved_chunks_count"
                ]
                debug_info["rag_fallback_used"] = (
                    len(retrieved_chunks) > 0
                    and retrieved_chunks[0].get("score") == 1.0
                )
                debug_info["doc_not_found"] = doc_not_found
                debug_info["doc_grounded"] = rag_result["retrieval_stats"].get("doc_grounded", False)
                
                # Handle doc-not-found: if query is doc-grounded and no hits, return early
                if doc_not_found:
                    logger.info(
                        f"[{request_id}] DOC_NOT_FOUND: Doc-grounded query with no hits. "
                        f"Returning doc-not-found response."
                    )
                    
                    doc_not_found_message = "Dokümanlarda bu bilgi bulunmuyor."
                    
                    # Save assistant message
                    await save_message(
                        user_id=user_id,
                        chat_id=chat_id,
                        role="assistant",
                        content=doc_not_found_message,
                        sources=None,
                    )
                    
                    # Update conversation state
                    from app.memory.state import ConversationState
                    state = await get_conversation_state(user_id, chat_id)
                    new_state = ConversationState(
                        last_topic=state.last_topic,
                        last_user_question=original_message,
                        last_domain=state.last_domain,
                        unresolved_followup=False,
                        last_document_ids=request.documentIds
                    )
                    await update_conversation_state(user_id, chat_id, new_state)
                    
                    response = ChatResponse(
                        message=doc_not_found_message,
                        chatId=chat_id,
                        sources=None,
                        debug_info={**debug_info, "doc_not_found": True, "rag_used": False},
                    )
                    
                    # Cache response
                    cache_key = f"{user_id}:{chat_id}:{request.client_message_id}"
                    message_cache[cache_key] = response
                    if len(message_cache) > 100:
                        oldest_key = next(iter(message_cache))
                        del message_cache[oldest_key]
                    
                    return response
            else:
                logger.info(f"[{request_id}] RAG: No documents available for user")
    except Exception as e:
        logger.error(f"[{request_id}] RAG retrieval error: {str(e)}", exc_info=True)
        # Continue without RAG if retrieval fails

    # Build system prompt with RAG context (only if documents are relevant)
    system_prompt = """
ROL TANIMI
Sen ChatGPT kalitesinde, profesyonel, yapılandırılmış ve tatmin edici cevaplar üreten bir AI asistanısın.
Amacın kullanıcılara net, anlaşılır, iyi formatlanmış ve bilgilendirici cevaplar vermektir.

────────────────────────────────────────
1) GENEL DAVRANIŞ
────────────────────────────────────────
- Her cevabı açıklayıcı, yapılandırılmış ve profesyonel şekilde yaz.
- Genel bilgi sorularında başlıklar (##) ve listeler kullan.
- Matematik sorularında adım adım çözüm göster, ama dikey spam yapma.
- Açıklama sorularında en az 2 perspektif sun (örn: halk bilgisi + akademik).
- Kısa cevaplar verme - her zaman yeterli detay ve bağlam sağla.

────────────────────────────────────────
2) ÇIKTI FORMATI — YAPILANDIRILMIŞ VE OKUNABİLİR
────────────────────────────────────────

GENEL BİLGİ SORULARI:
- Her zaman kısa bir giriş paragrafı ile başla (1-2 cümle)
- Ana noktalar için başlıklar (##) kullan
- Uzun paragraflar yerine listeler ve tablolar tercih et
- Tek düz paragraf halinde cevap verme

AÇIKLAMA SORULARI ("nedir", "nereden geliyor"):
- En az 2 perspektif sun (ör: halk bilgisi + akademik)
- Her perspektifi açıkça etiketle
- Kısa bir özet bölümü ekle

MATEMATİK SORULARI:
**Adım 1: [Açıklama]**
$$ <ifade> = <sadeleştirme> = <sonuç> $$

**Adım 2: [Açıklama]**
$$ <devam eden işlem> $$

**Sonuç:**
$$ <final sonuç> $$

ÖNEMLİ:
- Başlıklar (Adım 1, Adım 2, Sonuç) satır başında yazılmalı
- Her adımı ayrı satırlarda göster
- Matematik ifadeleri uzunsa sağa doğru uzayabilir
- "İfade:", "Sadeleştir:", "Birleştir:" gibi dikey spam yapma
- Adımları 1-2 paragraf halinde grupla, 10 satır yapma

────────────────────────────────────────
3) MATEMATİK YAZIM KURALLARI (KaTeX)
────────────────────────────────────────
- Matematik içeren HER ŞEY LaTeX içinde yazılır.
- Satır içi: $...$
- Blok: $$...$$

Zorunlu yazımlar:
- Kök: \\sqrt{...}
- Üs: x^{2}
- Kesir: \\frac{a}{b}
- Çarpım: a \\cdot b

────────────────────────────────────────
4) UZUN SATIR SORUNU — ÇÖZÜM
────────────────────────────────────────
UZUN TEK SATIRLIK MATEMATİK İFADELERİ YAPMA!

Örnek YANLIŞ format (kaydırma çubuğu oluşturur):
$$ √98 + √32 + √18 = 7√2 + 4√2 + 3√2 = 14√2 $$

Örnek DOĞRU format (kaydırma çubuğu yok):
**Adım 1: Kökleri sadeleştir**
$$ √98 = 7√2 $$
$$ √32 = 4√2 $$
$$ √18 = 3√2 $$

**Adım 2: Topla**
$$ 7√2 + 4√2 + 3√2 = 14√2 $$

**Sonuç:**
$$ 14√2 $$

────────────────────────────────────────
5) RAG (DOKÜMAN) DAVRANIŞI
────────────────────────────────────────
Eğer RAG context sağlandıysa:
- Öncelikle dokümanlardaki bilgileri kullan.
- Dokümanlarda bilgi yoksa veya yetersizse, genel bilgilerinle cevap vermeye devam et.
- ASLA "Dokümanlarda bu bilgi bulunmuyor" gibi mesajlar verme - her zaman bir cevap üret.

RAG context yoksa:
- Genel bilgiyle cevap ver.
- Her zaman yeterli detay ve bağlam sağla.

────────────────────────────────────────
6) OKUNABİLİRLİK KURALLARI
────────────────────────────────────────
- Her adım ayrı satırda olsun
- Uzun matematik ifadelerini mantıklı noktalarda böl
- Kaydırma çubuğu oluşturan tek satırlık uzun ifadeler YAPMA
- Düzenli, temiz, anlaşılır format kullan
- Her adımda ne yaptığını açıkla
- Genel bilgi sorularında başlıklar ve listeler kullan
- Tek düz paragraf halinde cevap verme

────────────────────────────────────────
7) KALİTE GARANTİLERİ
────────────────────────────────────────
- Her cevap yeterli uzunlukta olmalı (minimum 100-150 karakter)
- Her cevap yapılandırılmış olmalı (başlıklar, listeler, bölümler)
- Matematik cevapları dikey spam içermemeli
- Genel bilgi cevapları tek paragraf olmamalı
- Her zaman profesyonel ve tatmin edici ton kullan

"""


    logger.info(
        f"[{request_id}] RAG_PROMPT_BUILD: use_documents={use_documents} "
        f"retrieved_chunks={len(retrieved_chunks)} "
        f"has_specific_documents={has_specific_documents} "
        f"mode={request.mode}"
    )

    # Use context from decide_context if available
    if use_documents and context_text:
        try:
            # Get unique document filenames for reference
            unique_docs = []
            for source in sources:
                if source.filename and source.filename not in unique_docs:
                    unique_docs.append(source.filename)

            docs_list = ", ".join(unique_docs) if unique_docs else "Yüklenen dokümanlar"

            # ChatGPT style: RAG is helpful but not required
            # Always allow general knowledge fallback, even if documents are provided
            system_prompt += f"\n\nKullanıcının yüklediği şu dokümanlardan ilgili bölümler verilmiştir: {docs_list}\n\nÖncelikle bu dokümanlarda verilen bilgileri kullanarak cevap ver. Eğer sorunun cevabı bu dokümanlarda yoksa veya dokümanlar yeterli değilse, genel bilgilerinle cevap vermeye devam et. Dokümanlardan bilgi kullanırken hangi dokümandan aldığını belirt. Dokümanlarda bilgi yoksa bile, soruyu genel bilgilerinle cevapla.\n\nÖNEMLİ: Kullanıcıya belge yüklemesini söyleme. documentIds parametresi ile belgeler zaten sağlanmıştır. Bu belgeleri kullanarak cevap ver.\n\nDOKÜMAN İÇERİKLERİ:\n{context_text}"

            # Log RAG usage
            context_length = len(context_text)
            debug_info["context_added_to_prompt"] = True
            debug_info["context_chars"] = context_length
            logger.info(
                f"[{request_id}] RAG_PROMPT_SUCCESS: Context added to system prompt! "
                f"context_length={context_length} chars, "
                f"chunks={len(retrieved_chunks)}, "
                f"docs={len(unique_docs)}, "
                f"system_prompt_length={len(system_prompt)}"
            )
        except Exception as e:
            # If context building fails, log error and continue without document context
            logger.error(
                f"[{request_id}] RAG: Error adding context to prompt: {str(e)}",
                exc_info=True,
            )
            logger.info(
                f"[{request_id}] RAG: Falling back to normal chat mode due to context building error"
            )
            debug_info["context_chars"] = 0
    else:
        # No context available but user provided documents
        debug_info["context_chars"] = 0
        if has_specific_documents:
            logger.info(
                f"[{request_id}] RAG_INFO: User provided documentIds but no relevant context found. "
                f"Answering with general knowledge (ChatGPT style fallback). "
                f"documentIds={request.documentIds[:3] if request.documentIds else []}... "
                f"retrieved_chunks_count={len(retrieved_chunks)}"
            )
            # Always answer from general knowledge - never block
            system_prompt += f"\n\nNOT: Kullanıcı doküman seçmiş ancak soru ile ilgili bilgi bulunamadı. Soruyu genel bilgilerinle cevapla. ASLA 'Dokümanlarda bu bilgi yok' deme."
        else:
            logger.info(
                f"[{request_id}] RAG: Answering without document context (normal chat mode) "
                f"context_chars=0"
            )

    # Handle summarize mode: provide document summary + suggested questions
    suggested_questions = None
    if (
        request.mode == "summarize"
        and has_specific_documents
        and found_documents_for_fallback
    ):
        logger.info(
            f"[{request_id}] SUMMARIZE_MODE: Mode=summarize, "
            f"extracting document summary and generating suggested questions"
        )

        # Extract document summary (first 500-1000 chars per document)
        doc_summaries = []
        for doc_info in found_documents_for_fallback[:3]:  # Max 3 documents
            if doc_info.get("text_has_content"):
                text_content = doc_info.get("text_content", "")
                if text_content:
                    # Take first 800 chars as summary
                    summary = text_content[:800].strip()
                    if len(text_content) > 800:
                        summary += "..."
                    doc_summaries.append(
                        f"[{doc_info.get('filename', 'unknown')}]: {summary}"
                    )

        if doc_summaries:
            doc_summary_text = "\n\n".join(doc_summaries)

            # Generate 3 suggested questions using LLM
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    questions_response = await client.post(
                        OPENROUTER_API_URL,
                        headers={
                            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                            "Content-Type": "application/json",
                            "HTTP-Referer": "http://localhost:3000",
                            "X-Title": "AI Chat App",
                        },
                        json={
                            "model": OPENROUTER_MODEL,
                            "messages": [
                                {
                                    "role": "system",
                                    "content": "Sen yardımcı bir AI asistanısın. Kullanıcıya belge özeti verildiğinde, bu belge hakkında 3 adet kısa ve spesifik soru öner. Sorular Türkçe olmalı ve belgenin içeriğine uygun olmalı.",
                                },
                                {
                                    "role": "user",
                                    "content": f"Şu belge özeti verildi:\n\n{doc_summary_text}\n\nKullanıcı '{request.message}' dedi. Bu belge hakkında 3 adet kısa ve spesifik soru öner. Sadece soruları listele, başka açıklama yapma. Her satırda bir soru olacak şekilde numaralandır (1. 2. 3.).",
                                },
                            ],
                            "temperature": 0.7,
                            "max_tokens": 200,
                        },
                    )
                    questions_response.raise_for_status()
                    questions_data = questions_response.json()

                    if (
                        "choices" in questions_data
                        and len(questions_data["choices"]) > 0
                    ):
                        questions_text = questions_data["choices"][0]["message"][
                            "content"
                        ]
                        # Parse questions (extract lines starting with numbers)
                        import re

                        question_lines = re.findall(
                            r"^\d+\.\s*(.+)$", questions_text, re.MULTILINE
                        )
                        if question_lines:
                            suggested_questions = question_lines[:3]  # Take first 3
                        else:
                            # Fallback: split by newline and take first 3 non-empty lines
                            lines = [
                                line.strip()
                                for line in questions_text.split("\n")
                                if line.strip()
                            ]
                            suggested_questions = (
                                lines[:3] if len(lines) >= 3 else lines
                            )

                        logger.info(
                            f"[{request_id}] SUMMARIZE_MODE: Generated {len(suggested_questions) if suggested_questions else 0} suggested questions"
                        )
            except Exception as e:
                logger.warning(
                    f"[{request_id}] SUMMARIZE_MODE: Failed to generate suggested questions: {str(e)}"
                )
                # Continue without suggested questions

        # Build response with summary + questions
        if doc_summaries and suggested_questions:
            summary_message = (
                f"Belge Özeti:\n\n{doc_summary_text}\n\nŞunları sorabilirsiniz:\n"
            )
            for i, q in enumerate(suggested_questions, 1):
                summary_message += f"{i}. {q}\n"

            # For short messages with suggested questions, RAG is not used
            rag_used = False

            response = ChatResponse(
                message=summary_message,
                chatId=chat_id,
                sources=sources if sources else None,
                debug_info={**debug_info, "rag_used": rag_used},
                suggested_questions=suggested_questions,
            )

            # Update chat updated_at timestamp
            try:
                await db.chats.update_one(
                    {"_id": chat_object_id, "user_id": user_id},
                    {"$set": {"updated_at": datetime.utcnow()}},
                )
            except Exception as e:
                logger.warning(f"Failed to update chat timestamp: {str(e)}")

            # Update chat updated_at timestamp
            try:
                await db.chats.update_one(
                    {"_id": chat_object_id, "user_id": user_id},
                    {"$set": {"updated_at": datetime.utcnow()}},
                )
            except Exception as e:
                logger.warning(f"Failed to update chat timestamp: {str(e)}")

            # Save assistant message to memory (background task - non-blocking)
            asyncio.create_task(
                save_message(
                    user_id=user_id,
                    chat_id=chat_id,
                    role="assistant",
                    content=summary_message,
                    sources=sources if sources else None,
                )
            )

            # Cache response for idempotency (client_message_id is required)
            cache_key = f"{user_id}:{chat_id}:{request.client_message_id}"
            message_cache[cache_key] = response
            if len(message_cache) > 100:
                oldest_key = next(iter(message_cache))
                del message_cache[oldest_key]

            return response

    # Create generation run record for background processing
    run_id = request.client_message_id  # Use client_message_id as run_id
    now = datetime.utcnow()

    generation_runs[run_id] = {
        "run_id": run_id,
        "chat_id": chat_id,
        "message_id": request.client_message_id,
        "status": "running",
        "partial_text": None,
        "completed_text": None,
        "created_at": now,
        "updated_at": now,
        "error": None,
    }

    # Cleanup old runs (keep last 1000)
    if len(generation_runs) > 1000:
        # Remove oldest runs
        sorted_runs = sorted(generation_runs.items(), key=lambda x: x[1]["created_at"])
        for old_run_id, _ in sorted_runs[: len(generation_runs) - 1000]:
            del generation_runs[old_run_id]

    # Call OpenRouter API
    # BACKGROUND PROCESSING: Response generation continues even if client disconnects
    # Generation run is tracked in memory for polling
    try:
        # Await chat history (fetch was started in parallel, now we need the result)
        try:
            chat_history = await chat_history_task
        except Exception as history_error:
            logger.error(f"[{request_id}] Error fetching chat history: {str(history_error)}")
            chat_history = []  # Fallback to empty history

        # Get or update chat summary (if needed)
        summary_text = None
        if message_count >= 40:  # SUMMARY_TRIGGER_COUNT
            # Create LLM call function for summary generation
            async def llm_call_for_summary(summary_messages):
                return await call_llm(
                    messages=summary_messages,
                    model=OPENROUTER_MODEL,
                    api_key=OPENROUTER_API_KEY,
                    api_url=OPENROUTER_API_URL,
                    temperature=0.7,
                    max_tokens=300,  # Short summary
                    timeout=15.0
                )
            
            summary_text = await get_or_update_chat_summary(
                user_id=user_id,
                chat_id=chat_id,
                current_message_count=message_count,
                llm_call_func=llm_call_for_summary
            )

        # Manage context budget (if enabled)
        # Note: RAG context is already in system_prompt, so we extract it for budget management
        rag_context_for_budget = context_text if use_documents and context_text else ""
        budget_result = manage_context_budget(
            system_prompt=system_prompt,
            chat_history=chat_history,
            rag_context=rag_context_for_budget,
            user_message=request.message.strip(),
            max_total_tokens=4000  # LLM context window limit
        )
        
        # Build messages list with budget-managed components
        messages = [
            {"role": "system", "content": budget_result["system_prompt"]}
        ]
        
        # Add summary if available (before chat history)
        if summary_text:
            messages.append({
                "role": "system",
                "content": f"CHAT SUMMARY (önceki konuşma özeti):\n{summary_text}"
            })
        
        # Add budget-managed chat history
        messages.extend(budget_result["chat_history"])
        
        # Log token breakdown
        debug_info["token_breakdown"] = budget_result["token_breakdown"]
        
        # Add current user message
        messages.append({"role": "user", "content": budget_result["user_message"]})
        
        # Validate messages before LLM call
        try:
            validate_messages(messages)
        except ValueError as e:
            logger.error(f"[{request_id}] Message validation failed: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Message validation failed: {str(e)}",
                headers={"code": "VALIDATION_ERROR"},
            )

        # BACKGROUND PROCESSING RULE: Continue response generation regardless of client connection
        logger.info(
            f"[{request_id}] [BACKGROUND] Starting response generation (client connection independent), run_id={run_id}"
        )

        # Update run status
        generation_runs[run_id]["status"] = "running"
        generation_runs[run_id]["updated_at"] = datetime.utcnow()

        # Call LLM using extracted function
        format_warning = False
        try:
            response_message = await call_llm(
                messages=messages,
                model=OPENROUTER_MODEL,
                api_key=OPENROUTER_API_KEY,
                api_url=OPENROUTER_API_URL,
                temperature=0.7,
                max_tokens=1000,
                timeout=30.0
            )
            
            # Additional safety check for None response
            if response_message is None:
                logger.error(f"[{request_id}] call_llm returned None!")
                raise ValueError("LLM returned None response")
            
            if not isinstance(response_message, str):
                logger.error(f"[{request_id}] call_llm returned non-string type: {type(response_message)}")
                raise ValueError(f"LLM returned invalid type: {type(response_message)}")
            
            if not response_message.strip():
                logger.error(f"[{request_id}] call_llm returned empty string")
                raise ValueError("LLM returned empty response")
            
            # Log raw LLM output for debugging
            logger.info(f"[{request_id}] RAW_LLM_OUTPUT: {repr(response_message)[:2000]}")
            
            # ANSWER COMPOSER: Transform raw LLM output into ChatGPT-quality structured answer
            # Get conversation state for intent analysis
            from app.memory.state import get_conversation_state
            state = await get_conversation_state(user_id, chat_id)
            
            # Analyze question intent
            intent = analyze_intent(original_message, state.last_topic)
            
            # Get doc_grounded status and RAG context (from outer scope)
            doc_grounded = debug_info.get("doc_grounded", False)
            rag_context_used = context_text if use_documents and context_text else None
            
            # Compose structured answer
            original_response = response_message
            response_message = compose_answer(
                raw_llm_output=response_message,
                question=original_message,
                intent=intent,
                is_doc_grounded=doc_grounded,
                rag_context=rag_context_used
            )
            
            logger.info(
                f"[{request_id}] ANSWER_COMPOSER: Intent={intent.value}, "
                f"original_length={len(original_response)}, "
                f"composed_length={len(response_message)}, "
                f"doc_grounded={doc_grounded}"
            )
            
            # LAYER 3: Post-check + Self-repair (ChatGPT-style)
            is_valid, katex_error = validate_katex_output(response_message)
            
            if not is_valid:
                logger.warning(f"[{request_id}] LAYER 3: Format issues detected: {katex_error}")
                
                # Self-repair: Ask LLM to fix format (ONE retry only)
                try:
                    # Build correction prompt with specific error details
                    correction_prompt = (
                        f"FORMAT HATASI TESPİT EDİLDİ:\n{katex_error}\n\n"
                        "GÖREV: Yukarıdaki cevabı AYNEN KORUYARAK sadece formatını düzelt.\n"
                        "KURALLAR:\n"
                        "1. ANLAM DEĞİŞMEYECEK - sadece format düzeltilecek\n"
                        "2. Tüm matematik ifadeleri $...$ veya $$...$$ içinde olacak\n"
                        "3. Unicode karakterler (√, ², ₁ vb.) YASAK - LaTeX kullan\n"
                        "4. Matematik dışı metne DOKUNMA\n\n"
                        "Şimdi düzeltilmiş versiyonu yaz:"
                    )
                    
                    correction_messages = messages + [
                        {"role": "assistant", "content": response_message},
                        {"role": "user", "content": correction_prompt}
                    ]
                    
                    logger.info(f"[{request_id}] LAYER 3: Attempting self-repair...")
                    
                    corrected_response = await call_llm(
                        messages=correction_messages,
                        model=OPENROUTER_MODEL,
                        api_key=OPENROUTER_API_KEY,
                        api_url=OPENROUTER_API_URL,
                        temperature=0.3,  # Lower temperature for correction
                        max_tokens=1000,
                        timeout=30.0
                    )
                    
                    # Validate corrected response
                    if corrected_response and isinstance(corrected_response, str) and corrected_response.strip():
                        is_corrected_valid, correction_error = validate_katex_output(corrected_response)
                        if is_corrected_valid:
                            response_message = corrected_response
                            logger.info(f"[{request_id}] LAYER 3: Self-repair SUCCESSFUL")
                        else:
                            format_warning = True
                            logger.warning(
                                f"[{request_id}] LAYER 3: Self-repair FAILED - still has issues: {correction_error}. "
                                "Using original response with warning."
                            )
                    else:
                        logger.warning(f"[{request_id}] LAYER 3: Corrected response invalid, keeping original")
                        format_warning = True
                        
                except Exception as correction_error:
                    logger.error(f"[{request_id}] LAYER 3: Self-repair error: {str(correction_error)}")
                    format_warning = True
            else:
                logger.info(f"[{request_id}] LAYER 3: Format validation PASSED")
            
            # Validate answer against RAG context (if RAG was used)
            validation_result = None
            if use_documents and context_text and sources:
                validation_result = validate_answer_against_context(
                    answer=response_message,
                    rag_context=context_text,
                    sources=[{"documentId": s.documentId, "filename": s.filename} for s in sources]
                )
                
                # Log validation results
                logger.info(
                    f"[{request_id}] ANSWER_VALIDATION: "
                    f"is_valid={validation_result['is_valid']}, "
                    f"confidence={validation_result['confidence']:.2f}, "
                    f"issues={len(validation_result['issues'])}"
                )
                
                # Self-repair if validation found issues
                if not validation_result["is_valid"] and validation_result["confidence"] < 0.6:
                    repair_prompt = generate_self_repair_prompt(
                        original_answer=response_message,
                        validation_result=validation_result,
                        rag_context=context_text
                    )
                    
                    if repair_prompt:
                        try:
                            logger.info(f"[{request_id}] ANSWER_REPAIR: Attempting self-repair...")
                            repair_messages = [
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": repair_prompt}
                            ]
                            
                            repaired_response = await call_llm(
                                messages=repair_messages,
                                model=OPENROUTER_MODEL,
                                api_key=OPENROUTER_API_KEY,
                                api_url=OPENROUTER_API_URL,
                                temperature=0.3,
                                max_tokens=1000,
                                timeout=30.0
                            )
                            
                            if repaired_response and isinstance(repaired_response, str) and repaired_response.strip():
                                # Re-validate repaired response
                                repair_validation = validate_answer_against_context(
                                    answer=repaired_response,
                                    rag_context=context_text,
                                    sources=[{"documentId": s.documentId, "filename": s.filename} for s in sources]
                                )
                                
                                if repair_validation["confidence"] > validation_result["confidence"]:
                                    response_message = repaired_response
                                    validation_result = repair_validation
                                    logger.info(f"[{request_id}] ANSWER_REPAIR: Self-repair successful")
                                else:
                                    logger.warning(f"[{request_id}] ANSWER_REPAIR: Self-repair did not improve confidence")
                        except Exception as repair_error:
                            logger.error(f"[{request_id}] ANSWER_REPAIR: Error during self-repair: {str(repair_error)}")

            # Update generation run with completed text
            generation_runs[run_id]["status"] = "completed"
            generation_runs[run_id]["completed_text"] = response_message
            generation_runs[run_id]["updated_at"] = datetime.utcnow()

            # Save assistant message to memory
            assistant_message_saved = await save_message(
                user_id=user_id,
                chat_id=chat_id,
                role="assistant",
                content=response_message,
                sources=sources if sources else None,
            )
            
            if not assistant_message_saved:
                logger.warning(f"[{request_id}] Failed to save assistant message (chat_id={chat_id})")
            
            # Update conversation state with topic/domain
            from app.memory.state import ConversationState
            state = await get_conversation_state(user_id, chat_id)
            topic = state.last_topic or _extract_topic_from_response(response_message)
            domain = state.last_domain or _detect_domain_from_response(response_message)
            
            new_state = ConversationState(
                last_topic=topic,
                last_user_question=original_message,
                last_domain=domain,
                unresolved_followup=False,
                last_document_ids=request.documentIds
            )
            await update_conversation_state(user_id, chat_id, new_state)

            # Estimate tokens (rough approximation)
            from app.utils import estimate_tokens
            estimated_tokens = estimate_tokens(response_message)
            logger.info(
                f"[{request_id}] Response generated, ~{estimated_tokens} tokens, "
                f"sources: {len(sources)}, "
                f"chat_history: {len(chat_history)} messages, "
                f"debug_info={debug_info}, run_id={run_id}, format_warning={format_warning}"
            )
            
            # Determine if RAG was actually used (chunks retrieved and context added)
            rag_used = (
                debug_info.get("context_added_to_prompt", False)
                and len(retrieved_chunks) > 0
            )

            # Ensure response_message is not None or empty
            if not response_message or not response_message.strip():
                logger.error(f"[{request_id}] response_message is empty or None!")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="LLM'den boş yanıt alındı",
                    headers={"code": "EMPTY_RESPONSE"},
                )

            try:
                response = ChatResponse(
                    message=response_message,
                    chatId=chat_id,  # Include chatId in response so frontend knows which chat to reload
                    sources=sources if sources else None,
                    debug_info={
                        **debug_info,
                        "rag_used": rag_used,  # Add flag to indicate if RAG was actually used
                        "run_id": run_id,  # Include run_id in response for polling
                        "format_warning": format_warning,  # KaTeX format warning flag
                        "validation": validation_result if validation_result else None,  # Answer validation results
                    },
                )
            except Exception as response_error:
                logger.error(f"[{request_id}] Error creating ChatResponse: {str(response_error)}")
                logger.error(f"[{request_id}] response_message type: {type(response_message)}, length: {len(response_message) if response_message else 0}")
                logger.error(f"[{request_id}] debug_info: {debug_info}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Response oluşturma hatası: {str(response_error)}",
                    headers={"code": "RESPONSE_CREATION_ERROR"},
                )

            # Cache response for idempotency (client_message_id is required)
            cache_key = f"{user_id}:{chat_id}:{request.client_message_id}"
            message_cache[cache_key] = response
            # Limit cache size (keep last 100 entries)
            if len(message_cache) > 100:
                # Remove oldest entry (simple FIFO)
                oldest_key = next(iter(message_cache))
                del message_cache[oldest_key]

            return response
            
        except ValueError as e:
            # LLM API returned invalid response
            generation_runs[run_id]["status"] = "failed"
            generation_runs[run_id]["error"] = str(e)
            generation_runs[run_id]["updated_at"] = datetime.utcnow()
            
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"LLM API hatası: {str(e)}",
                headers={"code": "LLM_ERROR"},
            )

    except httpx.TimeoutException:
        # Update run with timeout error
        if run_id in generation_runs:
            generation_runs[run_id]["status"] = "failed"
            generation_runs[run_id]["error"] = "OpenRouter API yanıt vermedi (timeout)"
            generation_runs[run_id]["updated_at"] = datetime.utcnow()

        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="OpenRouter API yanıt vermedi (timeout)",
            headers={"code": "OPENROUTER_TIMEOUT"},
        )
    except httpx.HTTPStatusError as e:
        error_detail = f"OpenRouter API hatası: {e.response.status_code}"
        try:
            error_data = e.response.json()
            if "error" in error_data:
                error_detail = error_data["error"].get("message", error_detail)
        except:
            pass

        # Update run with error
        if run_id in generation_runs:
            generation_runs[run_id]["status"] = "failed"
            generation_runs[run_id]["error"] = error_detail
            generation_runs[run_id]["updated_at"] = datetime.utcnow()

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=error_detail,
            headers={"code": "OPENROUTER_ERROR"},
        )
    except Exception as e:
        import traceback

        error_msg = str(e)
        print(f"OpenRouter API error: {e}")
        print(traceback.format_exc())

        # Update run with error
        if run_id in generation_runs:
            generation_runs[run_id]["status"] = "failed"
            generation_runs[run_id]["error"] = error_msg
            generation_runs[run_id]["updated_at"] = datetime.utcnow()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"OpenRouter API çağrısı başarısız: {error_msg}",
            headers={"code": "OPENROUTER_ERROR"},
        )


@app.get("/chat/runs/{run_id}", response_model=GenerationRunStatus)
async def get_generation_run(run_id: str, authorization: Optional[str] = Header(None)):
    """
    Get generation run status (for polling).
    Allows frontend to check if background generation is complete.
    """
    # Verify authentication
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Eksik veya geçersiz authorization header",
            headers={"code": "UNAUTHORIZED"},
        )

    token = authorization.split(" ")[1]
    user_doc = await get_current_user(token)
    user_id = str(user_doc["_id"])

    # Check if run exists
    if run_id not in generation_runs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generation run bulunamadı",
            headers={"code": "RUN_NOT_FOUND"},
        )

    run = generation_runs[run_id]

    # Verify ownership (check if chat belongs to user)
    db = get_database()
    if db is not None:
        try:
            chat_object_id = ObjectId(run["chat_id"])
            chat = await db.chats.find_one({"_id": chat_object_id, "user_id": user_id})
            if not chat:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Bu generation run'a erişim izniniz yok",
                    headers={"code": "ACCESS_DENIED"},
                )
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Geçersiz chat_id formatı",
                headers={"code": "INVALID_CHAT_ID"},
            )

    # Format response
    created_at_str = (
        run["created_at"].isoformat()
        if isinstance(run["created_at"], datetime)
        else str(run["created_at"])
    )
    updated_at_str = (
        run["updated_at"].isoformat()
        if isinstance(run["updated_at"], datetime)
        else str(run["updated_at"])
    )

    return GenerationRunStatus(
        run_id=run["run_id"],
        chat_id=run["chat_id"],
        message_id=run["message_id"],
        status=run["status"],
        partial_text=run.get("partial_text"),
        completed_text=run.get("completed_text"),
        created_at=created_at_str,
        updated_at=updated_at_str,
        error=run.get("error"),
    )


@app.post("/chat/runs/{run_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_generation_run(
    run_id: str, authorization: Optional[str] = Header(None)
):
    """
    Cancel a running generation (user-initiated stop).
    """
    # Verify authentication
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Eksik veya geçersiz authorization header",
            headers={"code": "UNAUTHORIZED"},
        )

    token = authorization.split(" ")[1]
    user_doc = await get_current_user(token)
    user_id = str(user_doc["_id"])

    # Check if run exists
    if run_id not in generation_runs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generation run bulunamadı",
            headers={"code": "RUN_NOT_FOUND"},
        )

    run = generation_runs[run_id]

    # Verify ownership
    db = get_database()
    if db is not None:
        try:
            chat_object_id = ObjectId(run["chat_id"])
            chat = await db.chats.find_one({"_id": chat_object_id, "user_id": user_id})
            if not chat:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Bu generation run'a erişim izniniz yok",
                    headers={"code": "ACCESS_DENIED"},
                )
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Geçersiz chat_id formatı",
                headers={"code": "INVALID_CHAT_ID"},
            )

    # Cancel run (only if still running)
    if run["status"] == "running":
        run["status"] = "cancelled"
        run["updated_at"] = datetime.utcnow()
        run["error"] = "Kullanıcı tarafından iptal edildi"
        logger.info(f"[CANCEL] Generation run {run_id} cancelled by user {user_id}")

    return None


def _extract_topic_from_response(response: str) -> Optional[str]:
    """Extract topic from response text (simple heuristic)."""
    response_lower = response.lower()
    
    math_keywords = {
        'karekök': 'karekök',
        'radikal': 'radikaller',
        'üslü': 'üslü sayılar',
        'logaritma': 'logaritma',
        'türev': 'türev',
        'integral': 'integral',
    }
    
    for keyword, topic in math_keywords.items():
        if keyword in response_lower:
            return topic
    
    return None


def _detect_domain_from_response(response: str) -> str:
    """Detect domain from response text."""
    response_lower = response.lower()
    
    math_keywords = ['karekök', 'radikal', 'üslü', 'logaritma', 'türev', 'integral', 'matematik', 'math']
    coding_keywords = ['kod', 'program', 'python', 'javascript', 'function', 'class']
    
    if any(kw in response_lower for kw in math_keywords):
        return "math"
    elif any(kw in response_lower for kw in coding_keywords):
        return "coding"
    else:
        return "general"


@app.get("/debug/rag")
async def debug_rag(
    query: str,
    authorization: Optional[str] = Header(None),
    mode: str = "qa"
):
    """
    Enhanced debug endpoint for RAG retrieval with full observability.
    Returns detailed RAG decision information including intent, scores, and context.
    """
    # Verify authentication
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Eksik veya geçersiz authorization header",
            headers={"code": "UNAUTHORIZED"},
        )

    token = authorization.split(" ")[1]
    user_doc = await get_current_user(token)
    user_id = str(user_doc["_id"])

    if not query or not query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query parametresi gerekli",
            headers={"code": "INVALID_QUERY"},
        )

    # Get user's document IDs
    db = get_database()
    user_document_ids = []
    found_documents = []
    if db is not None:
        cursor = db.documents.find({"user_id": user_id}, {"_id": 1, "filename": 1, "text_content": 1})
        async for doc in cursor:
            doc_id = str(doc["_id"])
            user_document_ids.append(doc_id)
            found_documents.append({
                "id": doc_id,
                "filename": doc.get("filename", "unknown"),
                "text_content": doc.get("text_content", ""),
                "text_has_content": bool(doc.get("text_content", "").strip())
            })

    # Use decide_context for full RAG decision
    rag_result = await decide_context(
        query=query,
        selected_doc_ids=[],
        user_id=user_id,
        user_document_ids=user_document_ids,
        found_documents_for_fallback=found_documents,
        mode=mode,
        request_id="debug"
    )

    # Format response with full observability
    result_chunks = []
    for chunk in rag_result["retrieved_chunks"]:
        result_chunks.append(
            {
                "document_id": chunk["document_id"],
                "filename": chunk["original_filename"],
                "chunk_index": chunk["chunk_index"],
                "score": round(chunk.get("score", 0.0), 4),
                "score_raw": round(chunk.get("score_raw", chunk.get("score", 0.0)), 4) if "score_raw" in chunk else None,
                "distance": round(chunk.get("distance", 1.0), 4),
                "text_type": chunk.get("text_type"),
                "token_count": chunk.get("token_count"),
                "preview": (
                    chunk["text"][:300] + "..."
                    if len(chunk["text"]) > 300
                    else chunk["text"]
                ),
                "truncated": chunk.get("truncated", False),
            }
        )

    return {
        "query": query,
        "mode": mode,
        "user_documents": len(user_document_ids),
        "retrieval_stats": rag_result["retrieval_stats"],
        "should_use_documents": rag_result["should_use_documents"],
        "retrieved_chunks": len(result_chunks),
        "context_length": len(rag_result["context_text"]),
        "context_tokens": rag_result["retrieval_stats"].get("context_tokens", 0),
        "chunks": result_chunks,
        "sources": [
            {
                "documentId": s.documentId,
                "filename": s.filename,
                "chunkIndex": s.chunkIndex,
                "score": s.score,
                "preview": s.preview
            }
            for s in rag_result["sources"]
        ],
        "context_preview": rag_result["context_text"][:500] + "..." if len(rag_result["context_text"]) > 500 else rag_result["context_text"]
    }


@app.get("/debug/memory")
async def debug_memory(
    chat_id: str,
    authorization: Optional[str] = Header(None),
):
    """
    Debug endpoint for memory/chat history.
    Returns conversation state, recent messages, and summary.
    """
    # Verify authentication
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Eksik veya geçersiz authorization header",
            headers={"code": "UNAUTHORIZED"},
        )
    
    token = authorization.split(" ")[1]
    user_doc = await get_current_user(token)
    user_id = str(user_doc["_id"])
    
    # Verify chat ownership
    try:
        chat_object_id = ObjectId(chat_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Geçersiz chat_id formatı",
            headers={"code": "INVALID_CHAT_ID"},
        )
    
    db = get_database()
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database bağlantısı yok",
            headers={"code": "DATABASE_ERROR"},
        )
    
    chat = await db.chats.find_one({"_id": chat_object_id, "user_id": user_id})
    if not chat:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chat bulunamadı veya erişim reddedildi",
            headers={"code": "CHAT_ACCESS_DENIED"},
        )
    
    # Get conversation state
    state = await get_conversation_state(user_id, chat_id)
    
    # Get recent messages
    recent_messages = await get_recent_messages(user_id, chat_id, limit=20)
    
    # Get summary
    from app.memory.summary_store import get_chat_summary
    summary = await get_chat_summary(user_id, chat_id)
    
    # Get message count - ensure user_id and chat_id are strings
    normalized_user_id = str(user_id)
    normalized_chat_id = str(chat_id)
    
    # Try string format first
    query = {
        "user_id": normalized_user_id,
        "chat_id": normalized_chat_id
    }
    message_count = await db.chat_messages.count_documents(query)
    
    # If no matches, try ObjectId format for user_id (legacy data)
    if message_count == 0:
        try:
            from bson import ObjectId
            user_object_id = ObjectId(normalized_user_id)
            query_oid = {
                "user_id": user_object_id,
                "chat_id": normalized_chat_id
            }
            message_count = await db.chat_messages.count_documents(query_oid)
        except (ValueError, TypeError):
            pass
    
    return {
        "chat_id": chat_id,
        "message_count": message_count,
        "conversation_state": state.to_dict(),
        "recent_messages": recent_messages[:10],  # Last 10 messages
        "summary": summary,
        "has_summary": summary is not None
    }


@app.get("/debug/last")
async def debug_last(
    chat_id: str,
    authorization: Optional[str] = Header(None),
):
    """
    Debug endpoint for last resolved query and carryover rewrite.
    Shows what the user sent vs what was actually used for RAG.
    """
    # Verify authentication
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Eksik veya geçersiz authorization header",
            headers={"code": "UNAUTHORIZED"},
        )
    
    token = authorization.split(" ")[1]
    user_doc = await get_current_user(token)
    user_id = str(user_doc["_id"])
    
    # Verify chat ownership
    try:
        chat_object_id = ObjectId(chat_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Geçersiz chat_id formatı",
            headers={"code": "INVALID_CHAT_ID"},
        )
    
    db = get_database()
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database bağlantısı yok",
            headers={"code": "DATABASE_ERROR"},
        )
    
    chat = await db.chats.find_one({"_id": chat_object_id, "user_id": user_id})
    if not chat:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chat bulunamadı veya erişim reddedildi",
            headers={"code": "CHAT_ACCESS_DENIED"},
        )
    
    # Get conversation state (contains last resolved query)
    state = await get_conversation_state(user_id, chat_id)
    
    # Get last user message - ensure user_id and chat_id are strings
    normalized_user_id = str(user_id)
    normalized_chat_id = str(chat_id)
    
    # Try string format first
    query = {
        "user_id": normalized_user_id,
        "chat_id": normalized_chat_id,
        "role": "user"
    }
    last_user_msg = await db.chat_messages.find_one(
        query,
        sort=[("created_at", -1)]
    )
    
    # If not found, try ObjectId format for user_id (legacy data)
    if not last_user_msg:
        try:
            from bson import ObjectId
            user_object_id = ObjectId(normalized_user_id)
            query_oid = {
                "user_id": user_object_id,
                "chat_id": normalized_chat_id,
                "role": "user"
            }
            last_user_msg = await db.chat_messages.find_one(
                query_oid,
                sort=[("created_at", -1)]
            )
        except (ValueError, TypeError):
            pass
    
    return {
        "chat_id": chat_id,
        "last_user_question": state.last_user_question,
        "last_topic": state.last_topic,
        "last_domain": state.last_domain,
        "last_document_ids": state.last_document_ids,
        "last_user_message_from_db": last_user_msg.get("content") if last_user_msg else None,
        "last_user_message_timestamp": last_user_msg.get("created_at").isoformat() if last_user_msg and last_user_msg.get("created_at") else None
    }
