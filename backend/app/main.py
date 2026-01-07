"""
FastAPI application entry point - MongoDB version.
Lala - AI Chat Assistant with RAG Support
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, status, Header, BackgroundTasks, UploadFile, File
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from typing import Optional, List, Literal
from bson import ObjectId
from datetime import datetime
import httpx
import os
import asyncio
import re
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Setup centralized logging first
from app.logging_config import setup_logging
setup_logging()

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
    ChatRunResponse,
    GoogleLoginRequest,
    ChatMessageRequest,
    ChatMessageResponse,
    ChatMessagesResponse,
    DeleteChatRequest,
    UpdateAvatarRequest,
    UserSettings,
    UserSettingsResponse,
    GmailStatusResponse,
    GmailSyncResponse,
    GmailSyncCompleteResponse,
)
from app.integrations import gmail as gmail_service
from app.config import GmailConfig
from app.exceptions import (
    GmailNotConfiguredError,
    GmailNotConnectedError,
    GmailReauthRequiredError
)
from app.runs import create_run, get_run, update_run, cancel_run, get_active_runs_for_chat
from app.rag.embedder import embed_text
from app.rag.vector_store import query_chunks
from app.rag.decision import decide_context
from app.rag.context_builder import manage_context_budget
from app.rag.answer_validator import validate_answer_against_context, generate_self_repair_prompt
from app.rag.config import rag_config

# LGS Adaptive Pedagogy Module - Always active, UI handles module selection
from app.lgs import handle as lgs_handle, finalize_lgs_turn as lgs_finalize

from app.memory import (
    save_message, 
    get_recent_messages, 
    build_context_messages,
    get_or_update_chat_summary,
    resolve_carryover,
    get_conversation_state,
    update_conversation_state
)
from app.memory.message_store import save_message as save_message_to_db
from app.utils import (
    call_llm,
    call_llm_streaming,
    validate_messages,
    validate_katex_output,
    force_compact_math_output,
    compact_markdown_output,
    normalize_lgs_math
)
from app.google_ai import call_google_ai, call_google_ai_streaming
from app.answer_composer import compose_answer, analyze_intent, QuestionIntent
from app.chat_title import generateAndSetTitle
from app.response_style import determine_response_style, get_max_tokens_for_style, get_style_prompt_instruction
from app.ambiguous_query import is_ambiguous_query
import logging
import uuid

logger = logging.getLogger(__name__)

# RAG Configuration
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "4"))
RAG_SCORE_THRESHOLD = float(os.getenv("RAG_SCORE_THRESHOLD", "0.35"))

# Context Window Configuration
CONTEXT_MAX_TOKENS = int(os.getenv("CONTEXT_MAX_TOKENS", "2000"))  # Default 2000 tokens
CONTEXT_HARD_LIMIT = int(os.getenv("CONTEXT_HARD_LIMIT", "50"))  # Max 50 messages
from app.routes import documents as documents_router
from app.routes import admin as admin_router
from app.routes import gmail as gmail_router
from app.routes import auth as auth_router

# In-memory cache for idempotency (production'da Redis kullanılabilir)
# Key format: "{user_id}:{chat_id}:{client_message_id}"
message_cache = {}

# In-memory generation runs (production'da Redis/DB kullanılabilir)
# Format: {run_id: {chat_id, message_id, status, partial_text, completed_text, created_at, updated_at, error}}
generation_runs: dict = {}

# OpenRouter API Configuration - SECURITY: No default API key, must be set via environment
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "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")
if not OPENROUTER_API_KEY:
    logger.warning("OPENROUTER_API_KEY not set - LLM features will not work")
else:
    # DEBUG: Log masked key for verification
    masked_key = f"{OPENROUTER_API_KEY[:10]}...{OPENROUTER_API_KEY[-4:]}" if OPENROUTER_API_KEY else "None"
    logger.info(f"Using OpenRouter API Key: {masked_key}")
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-exp:free")  # Default model: Gemini 2.0 Flash (free tier)

# Google AI Studio Configuration
GOOGLE_AI_API_KEY = os.getenv("GOOGLE_AI_API_KEY", "AIzaSyCOsQwlgz9Xdpto-xZBRdEW3JZbVpc_F0I")
if GOOGLE_AI_API_KEY:
    masked_google_key = f"{GOOGLE_AI_API_KEY[:10]}...{GOOGLE_AI_API_KEY[-4:]}" if GOOGLE_AI_API_KEY else "None"
    logger.info(f"Using Google AI API Key: {masked_google_key}")
else:
    logger.warning("GOOGLE_AI_API_KEY not set - Google AI features will not work")


# Lifespan context manager (replaces deprecated @app.on_event)
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown."""
    # Startup
    logger.info("Starting Lala API...")
    await connect_to_mongo()
    logger.info("Lala API started successfully")
    yield
    # Shutdown
    logger.info("Shutting down Lala API...")
    await close_mongo_connection()
    logger.info("Lala API shutdown complete")


# Initialize FastAPI app with lifespan
app = FastAPI(
    title="Lala API",
    description="AI Chat Assistant with RAG Support - Kişisel Bilgi Asistanı",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware - Configure allowed origins from environment
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# Get allowed origins from environment (comma-separated list)
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:3003").split(",")
CORS_ORIGINS = [origin.strip() for origin in CORS_ORIGINS if origin.strip()]

# In development, allow all origins for convenience
if os.getenv("ENVIRONMENT", "development") == "development":
    CORS_ORIGINS = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-Client-Version"],
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

# Rate limiting middleware (optional, enabled via ENABLE_RATE_LIMIT env var)
if os.getenv("ENABLE_RATE_LIMIT", "").lower() == "true" or os.getenv("ENVIRONMENT") == "production":
    from app.middleware.rate_limit import RateLimitMiddleware
    app.add_middleware(RateLimitMiddleware, default_limit=100, window_seconds=60)
    logger.info("Rate limiting middleware enabled")

# Include routers
app.include_router(documents_router.router)
app.include_router(admin_router.router)
app.include_router(gmail_router.router)
app.include_router(auth_router.router)


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

    # CRITICAL: Catch any errors in the handler itself to prevent infinite loops
    try:
        error_msg = str(exc)
        error_type = type(exc).__name__
        
        # Log using proper logger
        logger.error(
            f"[GLOBAL_EXCEPTION] Unhandled exception: {error_type}: {error_msg}",
            exc_info=True,
            extra={
                "path": str(getattr(request, 'url', 'unknown')),
                "error_type": error_type,
            }
        )

        # CRITICAL: Always return JSONResponse - never raise or return non-JSON
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": f"Internal server error: {error_msg}",
                "code": "INTERNAL_ERROR",
                "error_type": error_type,
            },
        )
    except Exception as handler_err:
        # If the handler itself fails, return minimal JSON
        logger.critical(f"[GLOBAL_EXCEPTION] Exception handler failed: {handler_err}")
        from fastapi.responses import Response
        return Response(
            content='{"detail":"Internal server error: Exception handler failed","code":"INTERNAL_ERROR","error_type":"HandlerError"}',
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            media_type="application/json",
        )


async def get_current_user(token: str) -> dict:
    """
    Get current user from JWT token.
    
    Args:
        token: JWT access token
        
    Returns:
        User document from database
        
    Raises:
        HTTPException: If token is invalid or user not found
    """
    payload = decode_access_token(token)
    if payload is None:
        logger.debug("Token decode failed - invalid or expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Geçersiz veya süresi dolmuş token",
            headers={"code": "UNAUTHORIZED"},
        )

    user_id = payload.get("sub")
    if user_id is None:
        logger.debug("Token payload missing 'sub' field")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Geçersiz token",
            headers={"code": "UNAUTHORIZED"},
        )

    db = get_database()
    if db is None:
        logger.error("Database connection unavailable in get_current_user")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database bağlantısı yok",
            headers={"code": "DATABASE_ERROR"},
        )

    try:
        object_id = ObjectId(user_id)
        user_doc = await db.users.find_one({"_id": object_id})

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


@app.get("/")
async def root():
    return {"message": "Auth API", "version": "1.0.0", "database": "MongoDB"}



# Gmail endpoints moved to app/routes/gmail.py


@app.get("/api/test_llm")
async def test_llm(authorization: Optional[str] = Header(None)):
    """Diagnostic endpoint to test LLM connectivity."""
    if not OPENROUTER_API_KEY:
        return {"error": "API Key not set"}
    
    try:
        from app.utils import call_llm
        result = await call_llm(
            messages=[{"role": "user", "content": "Hi, are you working?"}],
            model=OPENROUTER_MODEL,
            api_key=OPENROUTER_API_KEY,
            api_url=OPENROUTER_API_URL,
            timeout=30.0,
            retries=1
        )
        return {"status": "success", "response": result, "model": OPENROUTER_MODEL}
    except Exception as e:
        logger.error(f"Test LLM failed: {str(e)}")
        return {"status": "error", "message": str(e), "model": OPENROUTER_MODEL}


@app.get("/api/health")
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


# Auth endpoints moved to app/routes/auth.py

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
            "prompt_module": request.prompt_module or "none",  # Store module for chat isolation
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
            prompt_module=created_chat.get("prompt_module", "none"),
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
async def list_chats(
    prompt_module: Optional[Literal["none", "lgs_karekok"]] = None,
    authorization: Optional[str] = Header(None)
):
    """
    List all chats for the current user (user-scoped).
    Optionally filter by prompt_module.
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
        # Exclude archived chats from regular list
        and_conditions = [
            {
                "$or": [
                    {"deleted_at": None},
                    {"deleted_at": {"$exists": False}}
                ]
            },
            {
                "$or": [
                    {"archived": None},
                    {"archived": False},
                    {"archived": {"$exists": False}}
                ]
            }
        ]
        
        # Filter by prompt_module if provided
        if prompt_module is not None:
            and_conditions.append({"prompt_module": prompt_module})
        else:
            # If not specified, default to "none" for backward compatibility
            and_conditions.append({
                "$or": [
                    {"prompt_module": {"$exists": False}},
                    {"prompt_module": None},
                    {"prompt_module": "none"}
                ]
            })
        
        query_filter = {
            "user_id": str(user_id),
            "$and": and_conditions,
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


@app.get("/chats/archived", response_model=List[ChatListItem])
async def list_archived_chats(authorization: Optional[str] = Header(None)):
    """
    List all archived chats for the current user.
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
        # Only return archived chats that have at least one message
        query_filter = {
            "user_id": str(user_id),
            "$or": [
                {"deleted_at": None},
                {"deleted_at": {"$exists": False}}
            ],
            "archived": True,
            "last_message_at": {"$ne": None}  # Only chats with messages
        }

        cursor = db.chats.find(query_filter).sort("archived_at", -1)
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
                logger.warning(f"Error processing archived chat: {str(chat_error)}")
                continue

        return chats

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[GET_ARCHIVED_CHATS] Error: {str(e)}", exc_info=True)
        from fastapi.responses import JSONResponse
        try:
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "detail": f"Arşivlenen chat listesi alınamadı: {str(e)}",
                    "code": "ARCHIVED_CHATS_LIST_ERROR"
                }
            )
        except Exception as json_err:
            logger.error(f"[GET_ARCHIVED_CHATS] Failed to create JSONResponse: {json_err}")
            from fastapi.responses import Response
            return Response(
                content=f'{{"detail":"Arşivlenen chat listesi alınamadı: {str(e)}","code":"ARCHIVED_CHATS_LIST_ERROR"}}',
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                media_type="application/json",
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
            prompt_module=chat.get("prompt_module", "none"),
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

        # Verify chat ownership (exclude soft-deleted, but allow archived chats)
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
        # CRITICAL: Filter out partial messages (is_partial=True) - only show completed messages
        # Partial messages are temporary and will be finalized later
        query["is_partial"] = {"$ne": True}  # Exclude partial messages (show only completed)
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
                        document_ids=msg.get("document_ids"),  # Document IDs attached to user message
                        used_documents=msg.get("used_documents"),  # Whether assistant used documents
                        is_partial=msg.get("is_partial"),  # Whether message is partial (for assistant messages)
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
        if request.archived is not None:
            update_fields["archived"] = request.archived
            if request.archived:
                update_fields["archived_at"] = datetime.utcnow()
            else:
                update_fields["archived_at"] = None
        
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
        
        # CHAT SAVING DISABLED: No longer saving messages to database
        # Just generate response without saving
        user_message_id = ""  # No message ID since we're not saving
        
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
        # CRITICAL FIX: Use a simpler approach - call the chat function logic directly
        # Instead of trying to find the route, we'll extract the core logic
        # But for now, let's try to find the route more reliably
        chat_endpoint_func = None
        
        # Try multiple ways to find the chat endpoint
        for route in app.routes:
            try:
                # Method 1: Check path attribute
                if hasattr(route, 'path') and route.path == "/chat":
                    if hasattr(route, 'endpoint'):
                        chat_endpoint_func = route.endpoint
                        logger.info(f"[{request_id}] Found chat endpoint via path attribute")
                        break
                
                # Method 2: Check if route is a Route object with path_regex
                if hasattr(route, 'path_regex'):
                    import re
                    if route.path_regex and re.match(route.path_regex, "/chat"):
                        if hasattr(route, 'endpoint'):
                            chat_endpoint_func = route.endpoint
                            logger.info(f"[{request_id}] Found chat endpoint via path_regex")
                            break
            except Exception as route_error:
                logger.debug(f"[{request_id}] Error checking route: {str(route_error)}")
                continue
        
        if not chat_endpoint_func:
            logger.error(f"[{request_id}] Chat endpoint function not found in routes")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Chat endpoint function not found - cannot generate assistant response. Please check backend logs.",
                headers={"code": "CHAT_ENDPOINT_NOT_FOUND"},
            )
        
        chat_response = None
        try:
            # Create a proper mock request object for the legacy endpoint
            class MockRequest:
                def __init__(self):
                    self.state = type('obj', (object,), {'request_id': request_id})()
            
            mock_request = MockRequest()
            
            # Call the legacy chat endpoint function
            logger.info(f"[{request_id}] Calling chat endpoint function with chatId={chat_id}")
            try:
                chat_response = await chat_endpoint_func(
                    request=chat_request,
                    authorization=authorization,
                    http_request=mock_request
                )
                logger.info(f"[{request_id}] Chat endpoint returned response: message_length={len(chat_response.message) if chat_response and chat_response.message else 0}")
            except Exception as call_error:
                logger.error(f"[{request_id}] Error calling chat endpoint function: {str(call_error)}", exc_info=True)
                raise  # Re-raise to be caught by outer exception handler
            
            # CHAT SAVING DISABLED: No longer saving messages to database
            # Just return the response without saving
            created_at_str = datetime.utcnow().isoformat()
            return ChatMessageResponse(
                message_id="",  # No message ID since we're not saving
                role="assistant",
                content=chat_response.message,
                sources=chat_response.sources,
                created_at=created_at_str,
                client_message_id=request.client_message_id,
            )
        except HTTPException as http_ex:
            # Re-raise HTTP exceptions as-is
            logger.error(f"[{request_id}] HTTPException from chat endpoint: {http_ex.detail}")
            raise
        except Exception as e:
            error_msg = str(e)
            error_type = type(e).__name__
            logger.error(f"[{request_id}] Error calling legacy chat endpoint: {error_type}: {error_msg}", exc_info=True)
            
            # CRITICAL FIX: If chat_response was created, save and return it
            # Otherwise raise proper error (don't return user message)
            if chat_response and hasattr(chat_response, 'message') and chat_response.message:
                # CHAT SAVING DISABLED: Just return response without saving
                created_at_str = datetime.utcnow().isoformat()
                return ChatMessageResponse(
                    message_id="",
                    role="assistant",
                    content=chat_response.message,
                    sources=chat_response.sources,
                    created_at=created_at_str,
                    client_message_id=request.client_message_id,
                )
            
            # If we can't save or return assistant message, raise proper error
            # Include more details about the error
            detail_msg = f"Assistant cevabı oluşturulamadı: {error_type}: {error_msg[:200]}"
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=detail_msg,
                headers={"code": "ASSISTANT_GENERATION_ERROR"},
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


async def get_user_settings(user_id: str) -> dict:
    """
    Get user settings (with defaults if not set).
    Returns dict with settings.
    """
    db = get_database()
    if db is None:
        return {"delete_chat_documents_on_chat_delete": False}
    
    settings_doc = await db.user_settings.find_one({"user_id": user_id})
    if settings_doc:
        return {
            "delete_chat_documents_on_chat_delete": settings_doc.get("delete_chat_documents_on_chat_delete", False)
        }
    return {"delete_chat_documents_on_chat_delete": False}


async def delete_chat_documents(user_id: str, chat_id: str) -> dict:
    """
    Delete all documents associated with a chat.
    Returns dict with deletion stats.
    """
    from app.routes.documents import delete_chat_documents as delete_docs_func
    from app.routes.documents import get_current_user_id
    
    # Create a mock dependency for get_current_user_id
    class MockDep:
        def __init__(self, user_id: str):
            self.user_id = user_id
    
    # Call the existing delete_chat_documents function
    try:
        result = await delete_docs_func(chat_id, MockDep(user_id))
        return result
    except Exception as e:
        logger.error(f"Error deleting chat documents: {str(e)}", exc_info=True)
        return {"deleted_documents": 0, "deleted_vectors": 0}


@app.get("/user/settings", response_model=UserSettingsResponse)
async def get_settings(
    authorization: Optional[str] = Header(None),
):
    """
    Get user settings.
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
    
    settings = await get_user_settings(user_id)
    return UserSettingsResponse(
        delete_chat_documents_on_chat_delete=settings["delete_chat_documents_on_chat_delete"]
    )


@app.put("/user/settings", response_model=UserSettingsResponse)
async def update_settings(
    settings: UserSettings,
    authorization: Optional[str] = Header(None),
):
    """
    Update user settings.
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
    
    await db.user_settings.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "delete_chat_documents_on_chat_delete": settings.delete_chat_documents_on_chat_delete,
                "updated_at": datetime.utcnow()
            },
            "$setOnInsert": {
                "user_id": user_id,
                "created_at": datetime.utcnow()
            }
        },
        upsert=True
    )
    
    return UserSettingsResponse(
        delete_chat_documents_on_chat_delete=settings.delete_chat_documents_on_chat_delete
    )


@app.delete("/chats/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(
    chat_id: str,
    authorization: Optional[str] = Header(None),
    hard: bool = False,
    delete_documents: Optional[bool] = None,  # Optional: override user setting
):
    """
    Delete a chat with ownership verification.
    Default: soft delete (sets deleted_at). Use hard=true for permanent deletion.
    If delete_documents is provided, it overrides user setting.
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
            
            # Handle document deletion if requested
            should_delete_docs = False
            if delete_documents is not None:
                should_delete_docs = delete_documents
            else:
                # Use user setting
                user_settings = await get_user_settings(user_id)
                should_delete_docs = user_settings.get("delete_chat_documents_on_chat_delete", False)
            
            if should_delete_docs:
                logger.info(f"Deleting documents for chat {chat_id} (user setting or override)")
                try:
                    from app.routes.documents import delete_chat_documents as delete_docs_func
                    # Find documents with source="chat" and chat_id
                    chat_docs = await db.documents.find({
                        "user_id": user_id,
                        "$or": [
                            {"source": "chat", "chat_id": chat_id},
                            {"uploaded_from_chat_id": chat_id}  # Legacy support
                        ]
                    }).to_list(length=None)
                    
                    deleted_docs_count = 0
                    deleted_chunks_count = 0
                    
                    for doc in chat_docs:
                        doc_id = str(doc["_id"])
                        # Delete from vector store
                        from app.rag.vector_store import delete_document_chunks
                        try:
                            chunks_deleted = delete_document_chunks(doc_id)
                            deleted_chunks_count += chunks_deleted
                        except Exception as e:
                            logger.error(f"Failed to delete chunks for doc {doc_id}: {str(e)}")
                        
                        # Delete from MongoDB
                        await db.documents.delete_one({"_id": doc["_id"], "user_id": user_id})
                        deleted_docs_count += 1
                    
                    logger.info(
                        f"Deleted {deleted_docs_count} documents and {deleted_chunks_count} chunks "
                        f"for chat {chat_id}"
                    )
                except Exception as e:
                    logger.error(f"Error deleting chat documents: {str(e)}", exc_info=True)
                    # Don't fail chat deletion if document deletion fails
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
    background_tasks: BackgroundTasks,
    authorization: Optional[str] = Header(None),
    http_request: Request = None,
):
    # CRITICAL: Log prompt_module for debugging
    logger.info(f"[CHAT_REQUEST] prompt_module={request.prompt_module}, message_length={len(request.message) if request.message else 0}")
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
    
    # Determine response style (explicit command > request field > auto-detection)
    response_style, cleaned_message = determine_response_style(
        request.message,
        explicit_style=request.response_style
    )
    logger.info(f"[{request_id}] Response style determined: {response_style}")
    
    # Use cleaned message for LLM (commands removed)
    original_message = request.message
    request.message = cleaned_message

    # CHAT SAVING ENABLED: chatId is required and must be a valid ObjectId
    # If not provided or invalid, create a new chat
    chat_id = request.chatId.strip() if request.chatId and request.chatId.strip() else None
    chat_object_id = None
    chat = None
    
    db = get_database()
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database bağlantısı yok",
            headers={"code": "DATABASE_ERROR"},
        )
    
    # Validate and verify chat if chatId is provided
    if chat_id and len(chat_id) in [23, 24] and all(c in '0123456789abcdefABCDEF' for c in chat_id):
        try:
            from bson import ObjectId as BsonObjectId
            # Try to convert to ObjectId
            if len(chat_id) == 24:
                chat_object_id = BsonObjectId(chat_id)
            elif len(chat_id) == 23:
                try:
                    chat_object_id = BsonObjectId("0" + chat_id)
                    chat_id = "0" + chat_id
                except:
                    chat_object_id = BsonObjectId(chat_id)
            
            if chat_object_id:
                # Verify chat ownership
                normalized_user_id = str(user_id)
                chat = await db.chats.find_one({"_id": chat_object_id, "user_id": normalized_user_id})
                if not chat:
                    try:
                        user_object_id = ObjectId(normalized_user_id)
                        chat = await db.chats.find_one({"_id": chat_object_id, "user_id": user_object_id})
                    except (ValueError, TypeError):
                        pass
                
                if not chat:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Chat bulunamadı veya erişim reddedildi",
                        headers={"code": "CHAT_NOT_FOUND"},
                    )
        except HTTPException:
            raise
        except (ValueError, TypeError):
            # Invalid ObjectId format - create new chat
            logger.info(f"[{request_id}] Invalid chatId format, creating new chat: {chat_id}")
            chat_id = None
            chat_object_id = None
    else:
        # chatId not provided or invalid format - create new chat
        logger.info(f"[{request_id}] No valid chatId provided, creating new chat")
        chat_id = None
        chat_object_id = None
    
    # Create new chat if needed
    if not chat_id or not chat_object_id:
        from app.schemas import CreateChatRequest
        chat_doc = {
            "user_id": str(user_id),
            "title": "Yeni Sohbet",
            "title_source": "pending",
            "title_updates_count": 0,
            "title_last_updated_at": None,
            "last_message_at": None,
            "deleted_at": None,
            "pinned": False,
            "tags": [],
            "prompt_module": request.prompt_module or "none",  # Store module for chat isolation
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        result = await db.chats.insert_one(chat_doc)
        chat_object_id = result.inserted_id
        chat_id = str(chat_object_id)
        chat = await db.chats.find_one({"_id": chat_object_id})
        logger.info(f"[{request_id}] Created new chat: {chat_id}")

    # CHAT SAVING ENABLED: Resolve carryover and build context
    original_message = request.message
    
    # Resolve carryover (follow-up detection)
    resolved_message, carryover_used = await resolve_carryover(
        user_id=user_id,
        chat_id=chat_id,
        user_message=original_message,
        document_ids=request.documentIds
    )
    query_message = resolved_message
    
    # Save user message with document_ids
    user_message_saved = await save_message(
        user_id=user_id,
        chat_id=chat_id,
        role="user",
        content=original_message,
        sources=None,
        client_message_id=request.client_message_id,
        document_ids=request.documentIds if request.documentIds else None,  # Save attached document IDs
        used_documents=None  # Not applicable for user messages
    )
    if not user_message_saved:
        logger.warning(f"[{request_id}] Failed to save user message")
    
    # Initialize used_documents variable (will be set later in RAG flow)
    used_documents = False
    used_priority_documents = None
    priority_document_ids = None
    
    # Get message count for context management
    message_count = 0
    try:
        normalized_user_id = str(user_id)
        query = {
            "user_id": normalized_user_id,
            "chat_id": chat_id,
            "role": "user"
        }
        message_count = await db.chat_messages.count_documents(query)
    except Exception as e:
        logger.warning(f"[{request_id}] Error counting messages: {str(e)}")
    
    # Build chat history (async task for parallel execution)
    # Note: Summary will be fetched in background task and passed to optimized context builder
    async def build_chat_history():
        # Fetch basic history first (summary will be added in background task)
        return await build_context_messages(
            user_id=user_id,
            chat_id=chat_id,
            max_tokens=2000,
            hard_limit=100,  # Fetch more for better optimization
            summary=None  # Summary will be added in background task
        )
    chat_history_task = asyncio.create_task(build_chat_history())

    # Mark chat as having messages and generate title after first message
    async def mark_chat_active_and_generate_title():
        # Add jitter delay (1-3s) to prevent clashing with main response LLM call
        # OpenRouter free tier is extremely sensitive to concurrency
        import random
        await asyncio.sleep(1.0 + random.random() * 2.0)
        
        # SKIP LLM title generation for LGS module to save rate limits
        # But still generate a dynamic title based on the user's message
        if request.prompt_module == "lgs_karekok":
            logger.info(f"[{request_id}] Generating quick title for LGS module chat (no LLM call)")
            
            # Generate title from user's first message
            user_msg = request.message or ""
            if user_msg:
                # Clean up and truncate the message for title
                title_text = user_msg.strip()
                # Remove LaTeX notation for cleaner title
                title_text = title_text.replace("\\(", "").replace("\\)", "").replace("$$", "").replace("$", "")
                title_text = title_text.replace("\\sqrt", "√").replace("\\frac", "")
                # Truncate to reasonable length
                if len(title_text) > 40:
                    title_text = title_text[:37] + "..."
                lgs_title = title_text or "LGS Matematik"
            else:
                lgs_title = "LGS Matematik"
            
            # Update chat with dynamic title
            db = get_database()
            if db is not None:
                await db.chats.update_one(
                    {"_id": chat_object_id, "user_id": user_id},
                    {"$set": {"is_active": True, "title": lgs_title, "updated_at": datetime.utcnow()}}
                )
            return

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
    # CHAT SAVING ENABLED: Mark chat active and generate title in background
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

    # ============================================================
    # START RAG FLOW (CHROMA + MONGODB)
    # ============================================================
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
        "global_rag_enabled": True,
    }

    db = get_database()

    user_document_ids = []
    main_doc_ids = []
    found_documents_for_fallback = []
    
    if db is not None:
        # CRITICAL: Filter documents by BOTH user_id AND prompt_module for strict module isolation
        # This ensures LGS documents are NEVER accessible in Personal Assistant and vice versa
        doc_filter = {"user_id": user_id}
        
        # Add prompt_module filter for module isolation
        if request.prompt_module:
            doc_filter["prompt_module"] = request.prompt_module
        else:
            # If no module specified, default to "none" (Personal Assistant)
            # This matches documents with prompt_module="none", null, or missing field
            doc_filter["$or"] = [
                {"prompt_module": {"$exists": False}},
                {"prompt_module": None},
                {"prompt_module": "none"}
            ]
        
        logger.info(f"[{request_id}] RAG_DOC_FILTER: user_id={user_id} prompt_module={request.prompt_module} filter={doc_filter}")
        
        # Get all user documents for global search + fallback (filtered by module)
        cursor = db.documents.find(doc_filter, {"_id": 1, "filename": 1, "text_content": 1, "is_main": 1})
        async for doc in cursor:
            doc_id = str(doc["_id"])
            user_document_ids.append(doc_id)
            if doc.get("is_main"):
                main_doc_ids.append(doc_id)
            found_documents_for_fallback.append({
                "id": doc_id,
                "filename": doc.get("filename", "unknown"),
                "text_content": doc.get("text_content", ""),
                "text_has_content": bool(doc.get("text_content", "").strip())
            })
            
        # Also include email source document IDs for searching
        email_cursor = db.email_sources.find({"user_id": user_id}, {"message_id": 1})
        async for email in email_cursor:
            # RAG uses "email_{msg_id}" format for email document IDs
            email_doc_id = f"email_{email.get('message_id')}"
            if email_doc_id not in user_document_ids:
                user_document_ids.append(email_doc_id)

    # PRIORITY: If no specific documents selected, prioritize "Main" documents
    effective_selected_doc_ids = incoming_document_ids
    if not effective_selected_doc_ids and main_doc_ids:
        effective_selected_doc_ids = main_doc_ids
        logger.info(f"[{request_id}] RAG_PRIORITY: No docs selected, automatically prioritizing {len(main_doc_ids)} Main documents.")

    # GLOBAL RAG: Always search in ALL user documents (default behavior)
    has_specific_documents = (
        len(effective_selected_doc_ids) > 0
    )

    # Call centralized RAG decision logic

    logger.info(f"[{request_id}] RAG_FLOW_START: user_id={user_id} docs_count={len(user_document_ids)}")
    rag_result = await decide_context(
        query=request.message,
        selected_doc_ids=effective_selected_doc_ids,
        user_id=user_id,
        user_document_ids=user_document_ids,
        found_documents_for_fallback=found_documents_for_fallback,
        mode=request.mode,
        request_id=request_id,
        prompt_module=request.prompt_module
    )
    
    # Update local variables from RAG result
    context_text = rag_result["context_text"]
    sources = rag_result["sources"]
    use_documents = rag_result["should_use_documents"]
    retrieved_chunks = rag_result["retrieved_chunks"]
    used_documents = rag_result["should_use_documents"]
    used_priority_documents = rag_result.get("used_priority_search", False)
    priority_document_ids = rag_result.get("priority_document_ids", [])
    doc_not_found = rag_result.get("doc_not_found", False)
    
    # Update debug info with retrieval stats
    debug_info.update({
        "global_rag_enabled": True,
        "db_documents_found": len(user_document_ids),
        "db_documents_with_content": sum(1 for d in found_documents_for_fallback if d["text_has_content"]),
        "retrieved_chunks_count": len(retrieved_chunks),
        "context_added_to_prompt": use_documents,
        "context_chars": len(context_text),
        "retrieval_stats": rag_result["retrieval_stats"],
        "doc_not_found": doc_not_found
    })

    if doc_not_found:
        logger.info(f"[{request_id}] RAG_DOC_NOT_FOUND: Query is doc-grounded but no relevant context found.")


    # ============================================================
    # MODEL CONFIGURATION - INITIALIZATION
    # ============================================================
    # Default model configuration
    use_google_ai = False
    selected_model = "openai/gpt-4o-mini"
    
    if request.prompt_module == "lgs_karekok":
        # LGS Module: Streaming RE-ENABLED with Atomic Math protection
        # GPT-4o-mini follows formatting instructions very well
        selected_model = "openai/gpt-4o-mini"
        enable_streaming = True
        debug_info["streaming"] = True
        logger.info(f"[{request_id}] LGS_MODULE: Using {selected_model} (streaming ENABLED)")
    else:
        # Personal Assistant: streaming enabled
        enable_streaming = True
        debug_info["streaming"] = True
        logger.info(f"[{request_id}] PERSONAL_ASSISTANT: Using {selected_model} (streaming ENABLED)")

    # ============================================================
    # SYSTEM PROMPT SELECTION (Module-Specific)
    # ============================================================
    if request.prompt_module == "lgs_karekok":
        # ============================================================
        # LGS MODULE: Always active - UI handles module selection
        # ============================================================
        lgs_result = await lgs_handle(
            user_id=user_id, 
            chat_id=chat_id, 
            request_id=request_id,
            user_message=original_message,  # Pass message for pedagogical analysis
            llm_call_func=call_google_ai if use_google_ai else call_llm
        )
        system_prompt = lgs_result["system_prompt"]
        debug_info["lgs_state"] = lgs_result["lgs_state_info"]

    else:
        # HACE Core Assistant: General-purpose help with prioritized personal context
        system_prompt = """Sen HACE, kullanıcının kişisel bilgi asistanısın.

Her soruya yardımcı ve net cevaplar üret. Eğer kullanıcının yüklediği dökümanlar veya e-postalar soruyla ilgili bilgi içeriyorsa, bu bilgileri öncelikli ve doğru şekilde kullanarak cevap ver.

Eğer dökümanlarda veya e-postalarda ilgili bilgi yoksa:
- Kendi genel bilgine dayanarak cevap ver.
- "Belgelerimde yok" veya "Bu dosyayı bulamadım" demek zorunda değilsin, doğrudan yardımcı ol.

KRİTİK KURALLAR:
1. Kaynak bilgisi (döküman/e-posta) ile genel bilgi çelişirse, her zaman dökümanı tercih et.
2. Emin olmadığın yerlerde bunu açıkça belirt.
3. Asla sadece dökümanı özetlemekle kalma, kullanıcının niyetini anlayıp tam cevap üret.
4. Kaynaklar sana "Hatırlatıcı Notlar" olarak sunulacak, onları akıllıca harmanla."""

    # ============================================================
    # MODEL CONFIGURATION - FINAL
    # ============================================================
    # ============================================================
    # RESPONSE STYLE INJECTION (ChatGPT Style)
    # ============================================================
    # Apply style instructions to system prompt
    style_instruction = get_style_prompt_instruction(response_style)
    system_prompt = f"{system_prompt}\n\n{style_instruction}"
    
    # ============================================================
    # MODULE PROMPTS DISABLED
    # ============================================================
    # Use only inline system prompts defined above - no external files
    logger.info(f"[{request_id}] MODULE_PROMPTS_DISABLED: Using inline system prompts only")
    module_prompt = ""  # No additional module prompt


    logger.info(
        f"[{request_id}] RAG_PROMPT_BUILD: use_documents={use_documents} "
        f"retrieved_chunks={len(retrieved_chunks)} "
        f"has_specific_documents={has_specific_documents} "
        f"mode={request.mode}"
    )

    # RAG context will be added as separate system message in messages array (ChatGPT style)
    # No need to add it to system_prompt anymore
    if use_documents and context_text:
        context_length = len(context_text)
        debug_info["context_added_to_prompt"] = True
        debug_info["context_chars"] = context_length
        logger.info(
            f"[{request_id}] RAG_PROMPT_SUCCESS: Context will be added as separate message! "
            f"context_length={context_length} chars, "
            f"chunks={len(retrieved_chunks)}"
        )
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
            if doc_not_found:
                # Query was explicitly about the document but no content was found
                system_prompt += f"\n\nNOT: Kullanıcı özellikle doküman hakkında bir soru sordu ancak ilgili bilgi bulunamadı. Dokümanda bu konuyla ilgili bilgi bulamadığını belirterek genel bilginle yardımcı olmaya çalış."
            else:
                # General query with documents selected, but no context found
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

            # Determine used_documents for summary response (from relevance gate)
            summary_used_documents = use_documents if 'use_documents' in locals() else (len(sources) > 0 if sources else False)
            
            response = ChatResponse(
                message=summary_message,
                chatId=chat_id,
                # CRITICAL: Only include sources if used_documents is True
                sources=(sources if sources else None) if summary_used_documents else None,
                used_documents=summary_used_documents,
                used_priority_documents=used_priority_documents if 'used_priority_documents' in locals() else None,
                priority_document_ids=priority_document_ids if priority_document_ids else None,
                debug_info={**debug_info, "rag_used": rag_used},
                suggested_questions=suggested_questions,
                response_style_used=response_style,
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

            # CHAT SAVING DISABLED: No longer saving messages to database

            # Cache response for idempotency (client_message_id is required)
            cache_key = f"{user_id}:{chat_id}:{request.client_message_id}"
            message_cache[cache_key] = response
            if len(message_cache) > 100:
                oldest_key = next(iter(message_cache))
                del message_cache[oldest_key]

            return response

    # Create generation run record in database
    run_id = request.client_message_id  # Use client_message_id as run_id
    try:
        db_run_id = await create_run(
            user_id=user_id,
            chat_id=chat_id,
            run_id=run_id,  # Pass the UUID as run_id
            status="queued"
        )
        logger.info(f"[{request_id}] Created run in DB: {db_run_id} (client_run_id={run_id})")
    except Exception as run_error:
        logger.error(f"[{request_id}] Failed to create run in DB: {str(run_error)}", exc_info=True)
        # Continue with in-memory run as fallback
        db_run_id = None
    
    # Also keep in-memory for backward compatibility
    now = datetime.utcnow()
    generation_runs[run_id] = {
        "run_id": run_id,
        "db_run_id": db_run_id,  # DB run ID
        "chat_id": chat_id,
        "message_id": None,  # Will be set when assistant message is created
        "status": "queued",
        "partial_text": None,
        "completed_text": None,
        "created_at": now,
        "updated_at": now,
        "error": None,
    }
    
    # Create placeholder assistant message immediately
    assistant_message_id = None
    try:
        assistant_message_id = await save_message_to_db(
            user_id=user_id,
            chat_id=chat_id,
            role="assistant",
            content="",  # Empty content initially
            sources=None,
            client_message_id=None,
            document_ids=None,
            used_documents=None,
            is_partial=True,  # Mark as partial (streaming)
            run_id=db_run_id or run_id  # Use DB run_id if available
        )
        if assistant_message_id:
            logger.info(f"[{request_id}] Created placeholder assistant message: {assistant_message_id} for run {db_run_id or run_id}")
            # Update run with message_id
            if db_run_id:
                await update_run(db_run_id, {"message_id": assistant_message_id}, user_id)
            generation_runs[run_id]["message_id"] = assistant_message_id
    except Exception as msg_error:
        logger.error(f"[{request_id}] Failed to create placeholder message: {str(msg_error)}", exc_info=True)
        # Continue without placeholder message (will be created on finalize)

    # Cleanup old runs (keep last 1000)
    if len(generation_runs) > 1000:
        # Remove oldest runs
        sorted_runs = sorted(generation_runs.items(), key=lambda x: x[1]["created_at"])
        for old_run_id, _ in sorted_runs[: len(generation_runs) - 1000]:
            del generation_runs[old_run_id]

    # STREAMING: Return immediately with run_id and message_id, then start background streaming
    # Frontend will poll for updates
    assistant_message_id = generation_runs[run_id].get("message_id")
    
    # BACKGROUND TASK: Start streaming in background
    async def background_streaming_task():
        """Background task for streaming LLM response."""
        # Await chat history (fetch was started in parallel, now we need the result)
        try:
            chat_history = await chat_history_task
        except Exception as history_error:
            logger.error(f"[{request_id}] Error fetching chat history: {str(history_error)}")
            chat_history = []  # Fallback to empty history

        # Get or update chat summary (if needed) - ChatGPT/Claude style compression
        summary_text = None
        if message_count >= 20:  # Lower threshold for better context management (was 40)
            # Create LLM call function for summary generation
            async def llm_call_for_summary(summary_messages):
                return await call_llm(
                    messages=summary_messages,
                    model=OPENROUTER_MODEL,
                    api_key=OPENROUTER_API_KEY,
                    api_url=OPENROUTER_API_URL,
                    temperature=0.3,  # Lower temperature for more accurate summaries
                    max_tokens=400,  # Longer summary for better context preservation
                    timeout=15.0
                )
            
            summary_text = await get_or_update_chat_summary(
                user_id=user_id,
                chat_id=chat_id,
                current_message_count=message_count,
                llm_call_func=llm_call_for_summary
            )

        # PROFESSIONAL: Use optimized context building (ChatGPT/Claude style)
        # This applies sliding window + intelligent compression automatically
        from app.memory.message_store import build_context_messages
        
        # Create LLM call function for intelligent summarization
        async def llm_call_for_context_summary(summary_messages):
            return await call_llm(
                messages=summary_messages,
                model=OPENROUTER_MODEL,
                api_key=OPENROUTER_API_KEY,
                api_url=OPENROUTER_API_URL,
                temperature=0.3,  # Lower temperature for more accurate summaries
                max_tokens=250,  # Summary tokens
                timeout=15.0
            )
        
        optimized_chat_history = await build_context_messages(
            user_id=user_id,
            chat_id=chat_id,
            max_tokens=1500,  # Token budget for chat history (leaves room for RAG + system prompt)
            hard_limit=100,  # Fetch more messages for better optimization
            summary=summary_text,  # Pass existing summary if available
            llm_call_func=llm_call_for_context_summary  # For intelligent summarization
        )

        # Manage context budget (if enabled)
        # CRITICAL: For LGS module, RAG context is ONLY for information validation
        # Solution method ALWAYS comes from ICL examples, NOT from RAG
        # RAG context will be added as separate system message (ChatGPT style)
        rag_context_for_budget = context_text if use_documents and context_text else ""
        budget_result = manage_context_budget(
            system_prompt=system_prompt,
            chat_history=optimized_chat_history,  # Use optimized history
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
        
        # Add RAG context as separate system message (Soft-RAG style)
        if use_documents and context_text:
            # Separate documents and emails for better labeling
            documents = []
            emails = []
            for chunk in retrieved_chunks:
                source_type = chunk.get('source_type', 'document')
                if source_type == 'email':
                    subject = chunk.get('subject', 'E-posta')
                    sender = chunk.get('sender', 'Bilinmeyen Gönderen')
                    emails.append(f"{subject} ({sender})")
                else:
                    filename = chunk.get('original_filename', 'Bilinmeyen Dosya')
                    documents.append(filename)
            
            # Build source list
            unique_docs = list(set(documents))
            unique_emails = list(set(emails))
            
            sources_list_parts = []
            if unique_docs:
                sources_list_parts.append(f"Dökümanlar: {', '.join(unique_docs)}")
            if unique_emails:
                sources_list_parts.append(f"E-postalar: {', '.join(unique_emails)}")
            sources_list = "\n".join(sources_list_parts) if sources_list_parts else "Yüksek öncelikli notlar"
            
            # CRITICAL: For LGS module, add special instruction about ICL vs RAG
            lgs_module_note = ""
            if request.prompt_module == "lgs_karekok":
                lgs_module_note = """
LGS MODULU ICIN KRITİK:
- "KULLANICININ BELGELERİNDEN İLGİLİ NOTLAR" senin SORU HAVUZUNDUR.
- Soru üretirken veya örnek verirken (Adım 4 ve 5), MÜMKÜN OLDUĞUNCA bu notlardaki soru tiplerini ve sayısal değerleri kullan.
- Ancak bu soruları sunarken MUTLAKA 5 adımlı (İskelet->Analiz->Çözüm...) pedagojik formatı kullan.
- Dökümanlardaki zor soruları "basitleştirerek" veya "LGS formatına uyarlayarak" sun.
"""
            
            rag_context_message = f"""KULLANICININ BELGELERİNDEN İLGİLİ NOTLAR (Yüksek Öncelikli):
{sources_list}

Aşağıdaki bilgiler kullanıcının kendi döküman ve e-postalarından alınmıştır. Cevap üretirken bu bilgileri birincil kaynak olarak kullan.

NOTLAR:
{context_text}
{lgs_module_note}
CEVAP STRATEJİSİ:
1. Bu notlardaki bilgiler ile genel bilgini harmanla.
2. Belgelerde geçen spesifik detayları (tarih, isim, rakam) mutlaka kullan.
3. Eğer belgelerde aranan bilgi yoksa, kendi genel bilgini kullanarak akıcı bir cevap üret. 
4. "Belgelerde yok" demek yerine, yardımcı olmaya odaklan."""
            
            messages.append({"role": "system", "content": rag_context_message})
            logger.info(f"[{request_id}] Soft-RAG context added as supporting memory")
        
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

        # Update run status to running
        generation_runs[run_id]["status"] = "running"
        generation_runs[run_id]["updated_at"] = datetime.utcnow()
        # Get db_run_id from generation_runs dict
        db_run_id = generation_runs[run_id].get("db_run_id")
        if db_run_id:
            await update_run(db_run_id, {"status": "running"}, user_id)

        # Call LLM with streaming support
        format_warning = False
        accumulated_content = ""  # Accumulated streaming content
        last_update_time = datetime.utcnow()
        update_throttle_ms = 100  # Throttle DB updates to every 100ms (faster, smoother streaming)
        
        # Check if run is cancelled (async version for DB check)
        async def check_cancelled_async() -> bool:
            db_run_id_local = generation_runs[run_id].get("db_run_id")
            if db_run_id_local:
                run = await get_run(db_run_id_local, user_id)
                if run and run.get("status") == "cancelled":
                    return True
            return generation_runs.get(run_id, {}).get("status") == "cancelled"
        
        # Sync version for quick in-memory check (used by call_llm_streaming)
        def check_cancelled_sync() -> bool:
            return generation_runs.get(run_id, {}).get("status") == "cancelled"
        
        # Throttled update function
        async def update_content_throttled(new_content: str):
            nonlocal last_update_time, accumulated_content
            accumulated_content = new_content
            
            now = datetime.utcnow()
            time_since_last_update = (now - last_update_time).total_seconds() * 1000
            
            if time_since_last_update >= update_throttle_ms:
                # Update run.content_so_far
                db_run_id_local = generation_runs[run_id].get("db_run_id")
                if db_run_id_local:
                    await update_run(db_run_id_local, {"content_so_far": new_content}, user_id)
                
                # Update placeholder message (throttled)
                assistant_message_id = generation_runs[run_id].get("message_id")
                if assistant_message_id:
                    try:
                        await save_message_to_db(
                            user_id=user_id,
                            chat_id=chat_id,
                            role="assistant",
                            content=new_content,
                            sources=None,  # Sources only on final
                            client_message_id=None,
                            document_ids=None,
                            used_documents=None,  # Only on final
                            is_partial=True,  # Still partial during streaming
                            run_id=generation_runs[run_id].get("db_run_id") or run_id
                        )
                    except Exception as update_error:
                        logger.warning(f"[{request_id}] Failed to update message during streaming: {str(update_error)}")
                
                last_update_time = now
        
        try:
            # Get max_tokens based on response style
            max_tokens = get_max_tokens_for_style(response_style)
            
            # CRITICAL: For LGS module, set max_tokens to a safe limit for current credits
            if request.prompt_module == "lgs_karekok":
                # Reduced from 4000 to 2000 to stay within credit limits
                max_tokens = 2000
                logger.info(f"[{request_id}] LGS module detected - using max_tokens={max_tokens} (credit-limited)")
            
            logger.info(f"[{request_id}] Using max_tokens={max_tokens} for response_style={response_style}, model={selected_model}")
            
            # Temperature: Module-specific
            if request.prompt_module == "lgs_karekok":
                temperature = 0.1  # Set to minimum for extreme correctness
                top_p = 0.9        # Stabilize output
            else:
                temperature = 0.7  # Higher for Personal Assistant (conversational)
                top_p = 1.0        # Default
            
            # ============================================================
            # LLM CALL: Streaming vs Non-Streaming Based on Module
            # ============================================================
            if enable_streaming:
                # Personal Assistant: Streaming enabled
                async def on_chunk_async(chunk_text: str):
                    nonlocal accumulated_content
                    accumulated_content += chunk_text
                    # Check cancellation (async DB check)
                    if await check_cancelled_async():
                        raise RuntimeError("Streaming cancelled by user")
                    # Throttled update (every 300ms)
                    await update_content_throttled(accumulated_content)
                
                # Call LLM with streaming
                logger.info(f"[{request_id}] Calling LLM with STREAMING enabled (model: {selected_model})")
                
                # Use Google AI or OpenRouter based on configuration
                if use_google_ai:
                    raw_response_message = await call_google_ai_streaming(
                        messages=messages,
                        model=selected_model,
                        api_key=GOOGLE_AI_API_KEY,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        timeout=180.0,
                        on_chunk_async=on_chunk_async,
                        check_cancelled=check_cancelled_sync
                    )
                else:
                    raw_response_message = await call_llm_streaming(
                        messages=messages,
                        model=selected_model,
                        api_key=OPENROUTER_API_KEY,
                        api_url=OPENROUTER_API_URL,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        timeout=180.0,
                        on_chunk_async=on_chunk_async,
                        check_cancelled=check_cancelled_sync
                    )
                
                # Final update with complete content (ensure last chunk is saved)
                await update_content_throttled(raw_response_message)
            else:
                # Non-streaming mode
                logger.info(f"[{request_id}] Calling LLM with STREAMING DISABLED (model: {selected_model})")
                # For non-streaming, we still update placeholder but don't stream
                # Wait for complete response
                
                # Use Google AI or OpenRouter
                if use_google_ai:
                    raw_response_message = await call_google_ai(
                        messages=messages,
                        model=selected_model,
                        api_key=GOOGLE_AI_API_KEY,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        timeout=300.0
                    )
                else:
                    raw_response_message = await call_llm(
                        messages=messages,
                        model=selected_model,
                        api_key=OPENROUTER_API_KEY,
                        api_url=OPENROUTER_API_URL,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        timeout=300.0  # Longer timeout for reasoning models
                    )
                
                # Update placeholder with complete response immediately
                if raw_response_message:
                    await update_content_throttled(raw_response_message)
            
            # Additional safety check for None response
            if raw_response_message is None:
                logger.error(f"[{request_id}] call_llm_streaming returned None!")
                raise ValueError("LLM returned None response")
            
            if not isinstance(raw_response_message, str):
                logger.error(f"[{request_id}] call_llm_streaming returned non-string type: {type(raw_response_message)}")
                raise ValueError(f"LLM returned invalid type: {type(raw_response_message)}")
            
            if not raw_response_message.strip():
                logger.error(f"[{request_id}] call_llm_streaming returned empty string")
                raise ValueError("LLM returned empty response")
            
            # Log raw LLM output for debugging
            logger.info(f"[{request_id}] RAW_LLM_OUTPUT: {repr(raw_response_message)[:2000]}")
            
            # Use raw response for post-processing
            response_message = raw_response_message
            
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
            # LGS module now uses compose_answer for professional layout
            response_message = compose_answer(
                raw_llm_output=response_message,
                question=original_message,
                intent=intent,
                is_doc_grounded=doc_grounded,
                rag_context=rag_context_used
            )
            
            # LGS Normalization Guard: Ensure KaTeX delimiters are \[ \] and \( \)
            if request.prompt_module == "lgs_karekok":
                response_message = normalize_lgs_math(response_message)
                logger.info(f"[{request_id}] LGS_RAG: Robust math normalization applied via utils")
            
            logger.info(
                f"[{request_id}] ANSWER_COMPOSER: Intent={intent.value}, "
                f"original_length={len(original_response)}, "
                f"composed_length={len(response_message)}, "
                f"doc_grounded={doc_grounded}"
            )
            
            # LAYER 3: Post-check + Self-repair (ChatGPT-style)
            # CRITICAL: For LGS module, skip strict validation (ICL format may not pass strict checks)
            # LGS module uses ICL examples which have their own format
            if request.prompt_module == "lgs_karekok":
                # LGS module: Skip validation, trust ICL format
                logger.info(f"[{request_id}] LGS_MODULE: Skipping strict KaTeX validation (using ICL format)")
                is_valid = True
                katex_error = None
            else:
                is_valid, katex_error = validate_katex_output(response_message)
            
            if not is_valid:
                logger.warning(f"[{request_id}] LAYER 3: Format issues detected: {katex_error}")
                
                # Self-repair: Ask LLM to fix format (ONE retry only)
                # CRITICAL: For LGS module, skip self-repair (preserve ICL format)
                if request.prompt_module == "lgs_karekok":
                    logger.info(f"[{request_id}] LGS_MODULE: Skipping self-repair (preserving ICL format)")
                    format_warning = True
                else:
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

            # CRITICAL: MESSAGE LIFECYCLE - DB write MUST happen BEFORE run completion
            # Step 1: Save message to database FIRST (await to ensure persistence)
            try:
                # CRITICAL: For LGS module, never show sources (educational module, no document sources)
                # CRITICAL: Only save sources if used_documents is True AND not LGS module
                if request.prompt_module == "lgs_karekok":
                    sources_to_save = None  # LGS module never shows sources
                else:
                    sources_to_save = (sources if sources else None) if used_documents else None
                assistant_message_id = generation_runs[run_id].get("message_id")
                
                # CRITICAL: Await DB write - message is NOT completed until DB write succeeds
                if assistant_message_id:
                    # Update existing placeholder message
                    await save_message_to_db(
                        user_id=user_id,
                        chat_id=chat_id,
                        role="assistant",
                        content=response_message,
                        sources=sources_to_save,
                        client_message_id=None,
                        document_ids=None,
                        used_documents=used_documents,
                        is_partial=False,  # Finalize: no longer partial
                        run_id=generation_runs[run_id].get("db_run_id") or run_id,
                        module=request.prompt_module,  # Track which module generated this
                        model=selected_model,  # Track which model was used
                        system_prompt_version="v2" if request.prompt_module == "lgs_karekok" else "v1"  # Prompt version
                    )
                    logger.info(f"[{request_id}] Finalized assistant message {assistant_message_id} for chat {chat_id[:8]}... (DB persisted)")
                else:
                    # Create new message if placeholder wasn't created
                    assistant_message_id = await save_message_to_db(
                        user_id=user_id,
                        chat_id=chat_id,
                        role="assistant",
                        content=response_message,
                        sources=sources_to_save,
                        client_message_id=None,
                        document_ids=None,
                        used_documents=used_documents,
                        is_partial=False,
                        run_id=generation_runs[run_id].get("db_run_id") or run_id,
                        module=request.prompt_module,  # Track which module generated this
                        model=selected_model,  # Track which model was used
                        system_prompt_version="v2" if request.prompt_module == "lgs_karekok" else "v1"  # Prompt version
                    )
                    if assistant_message_id:
                        logger.info(f"[{request_id}] Created final assistant message {assistant_message_id} for chat {chat_id[:8]}... (DB persisted)")
                        db_run_id_local = generation_runs[run_id].get("db_run_id")
                        if db_run_id_local:
                            await update_run(db_run_id_local, {"message_id": assistant_message_id}, user_id)
            except Exception as save_error:
                logger.error(f"[{request_id}] CRITICAL: Error saving message to DB: {str(save_error)}", exc_info=True)
                # CRITICAL: If DB save fails, message is NOT completed - do NOT mark run as completed
                # This ensures message lifecycle is correct
                raise  # Re-raise to prevent run completion without DB persistence
            
            # Step 2: ONLY AFTER DB write succeeds, mark run as completed
            generation_runs[run_id]["status"] = "completed"
            generation_runs[run_id]["completed_text"] = response_message
            generation_runs[run_id]["updated_at"] = datetime.utcnow()
            
            # Step 3: Update run in database (after message is persisted)
            db_run_id = generation_runs[run_id].get("db_run_id")
            if db_run_id:
                await update_run(
                    db_run_id,
                    {
                        "status": "completed",
                        "content_so_far": response_message,
                        "is_partial": False,
                        "sources": None if request.prompt_module == "lgs_karekok" else ([s.dict() for s in sources] if sources and used_documents else None),
                        "used_documents": used_documents if request.prompt_module != "lgs_karekok" else False
                    },
                    user_id
                )
            
            if False:  # Removed check - always continue
                logger.warning(f"[{request_id}] Failed to save assistant message")
            
            # Update chat's last_message_at
            try:
                await db.chats.update_one(
                    {"_id": chat_object_id, "user_id": user_id},
                    {
                        "$set": {
                            "last_message_at": datetime.utcnow(),
                            "updated_at": datetime.utcnow()
                        }
                    }
                )
            except Exception as e:
                logger.warning(f"[{request_id}] Failed to update chat last_message_at: {str(e)}")
            
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

            # Step 5: For LGS module, finalize Turn (save new problem context)
            if request.prompt_module == "lgs_karekok":
                try:
                    await lgs_finalize(user_id, chat_id, response_message)
                    logger.info(f"[{request_id}] LGS_TURN_FINALIZED: Saved new problem context for chat {chat_id[:8]}...")
                except Exception as lgs_error:
                    logger.error(f"[{request_id}] LGS_TURN_ERROR: Failed to save problem context: {str(lgs_error)}")

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
                    # CRITICAL: For LGS module, never show sources (educational module, no document sources)
                    # CRITICAL: Only include sources if used_documents is True AND not LGS module
                    sources=None if request.prompt_module == "lgs_karekok" else ((sources if sources else None) if used_documents else None),
                    used_documents=False if request.prompt_module == "lgs_karekok" else used_documents,  # LGS module never uses documents
                    used_priority_documents=used_priority_documents if 'used_priority_documents' in locals() else None,
                    priority_document_ids=priority_document_ids if priority_document_ids else None,
                    debug_info={
                        **debug_info,
                        "rag_used": rag_used,  # Add flag to indicate if RAG was actually used
                        "run_id": run_id,  # Include run_id in response for polling
                        "format_warning": format_warning,  # KaTeX format warning flag
                        "validation": validation_result if validation_result else None,  # Answer validation results
                    },
                    response_style_used=response_style,
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
            db_run_id_local = generation_runs[run_id].get("db_run_id")
            if db_run_id_local:
                await update_run(db_run_id_local, {
                    "status": "failed",
                    "error": str(e)
                }, user_id)
            generation_runs[run_id]["status"] = "failed"
            generation_runs[run_id]["error"] = str(e)
            generation_runs[run_id]["updated_at"] = datetime.utcnow()
            logger.error(f"[{request_id}] Background streaming task failed: {str(e)}")
            
            # Return error response to user
            return ChatResponse(
                message=f"LLM API hatası: {str(e)}",
                chatId=chat_id,
                sources=None,
                used_documents=False,
                debug_info={**debug_info, "error": str(e), "run_id": db_run_id or run_id},
                response_style_used=response_style,
            )
            
        except httpx.TimeoutException:
            # Update run with timeout error
            error_msg_timeout = "API yanıt vermedi (timeout). Lütfen tekrar deneyin."
            db_run_id_local = generation_runs[run_id].get("db_run_id")
            if db_run_id_local:
                await update_run(db_run_id_local, {
                    "status": "failed",
                    "error": error_msg_timeout
                }, user_id)
            if run_id in generation_runs:
                generation_runs[run_id]["status"] = "failed"
                generation_runs[run_id]["error"] = error_msg_timeout
                generation_runs[run_id]["updated_at"] = datetime.utcnow()
            logger.error(f"[{request_id}] Background streaming task timeout")
            
            # Return error response to user
            return ChatResponse(
                message=error_msg_timeout,
                chatId=chat_id,
                sources=None,
                used_documents=False,
                debug_info={**debug_info, "error": "timeout", "run_id": db_run_id or run_id},
                response_style_used=response_style,
            )
            
        except httpx.HTTPStatusError as e:
            error_detail = f"API hatası: {e.response.status_code}"
            try:
                error_data = e.response.json()
                if "error" in error_data:
                    error_detail = error_data["error"].get("message", error_detail)
            except:
                pass

            # Update run with error
            db_run_id_local = generation_runs[run_id].get("db_run_id")
            if db_run_id_local:
                await update_run(db_run_id_local, {
                    "status": "failed",
                    "error": error_detail
                }, user_id)
            if run_id in generation_runs:
                generation_runs[run_id]["status"] = "failed"
                generation_runs[run_id]["error"] = error_detail
                generation_runs[run_id]["updated_at"] = datetime.utcnow()
            logger.error(f"[{request_id}] Background streaming task HTTP error: {error_detail}")
            
            # Return error response to user
            return ChatResponse(
                message=f"Bir hata oluştu: {error_detail}",
                chatId=chat_id,
                sources=None,
                used_documents=False,
                debug_info={**debug_info, "error": error_detail, "run_id": db_run_id or run_id},
                response_style_used=response_style,
            )
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"[{request_id}] Background streaming task error: {error_msg}", exc_info=True)

            # Update run with error
            db_run_id_local = generation_runs[run_id].get("db_run_id")
            if db_run_id_local:
                await update_run(db_run_id_local, {
                    "status": "failed",
                    "error": error_msg
                }, user_id)
            if run_id in generation_runs:
                generation_runs[run_id]["status"] = "failed"
                generation_runs[run_id]["error"] = error_msg
                generation_runs[run_id]["updated_at"] = datetime.utcnow()
            
            # Return error response to user
            return ChatResponse(
                message=f"Bir hata oluştu: {error_msg[:200]}",
                chatId=chat_id,
                sources=None,
                used_documents=False,
                debug_info={**debug_info, "error": error_msg, "run_id": db_run_id or run_id},
                response_style_used=response_style,
            )
    
    # RESTORE ASYNC ARCHITECTURE: Use BackgroundTasks to start generation and return immediately
    # This fixes the "Stopped" (Durduruldu) error by providing a run_id ASAP
    background_tasks.add_task(background_streaming_task)
    
    # Return initial status response with run_id for polling
    return ChatResponse(
        message="",
        chatId=chat_id,
        sources=None,
        used_documents=False,
        debug_info={
            **debug_info,
            "run_id": run_id,
            "message_id": assistant_message_id,
            "status": "queued",
        },
        response_style_used=response_style,
    )


@app.get("/chat/runs/{run_id}", response_model=GenerationRunStatus)
async def get_generation_run(run_id: str, authorization: Optional[str] = Header(None)):
    """
    Get generation run status (for polling).
    Allows frontend to check if background generation is complete.
    Uses persistent DB storage instead of in-memory dict.
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

    # Get run from DB
    run = await get_run(run_id, user_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generation run bulunamadı",
            headers={"code": "RUN_NOT_FOUND"},
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
        message_id=run.get("message_id"),
        status=run["status"],
        content_so_far=run.get("content_so_far"),
        sources=None,  # Sources will be in the final message
        used_documents=run.get("used_documents"),
        is_partial=run.get("is_partial", False),
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

    # Get run from DB
    run = await get_run(run_id, user_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generation run bulunamadı",
            headers={"code": "RUN_NOT_FOUND"},
        )

    # Cancel run (only if still running or queued)
    if run["status"] in ["running", "queued"]:
        # Get current content_so_far before cancelling
        content_so_far = run.get("content_so_far", "")
        
        cancelled = await cancel_run(run_id, user_id)
        if cancelled:
            # Update run with partial content
            await update_run(run_id, {
                "content_so_far": content_so_far,
                "is_partial": True
            }, user_id)
            
            # Update assistant message with partial content
            message_id = run.get("message_id")
            if message_id:
                from app.memory.message_store import save_message_to_db
                chat_id = run.get("chat_id")
                if chat_id:
                    await save_message_to_db(
                        user_id=user_id,
                        chat_id=chat_id,
                        role="assistant",
                        content=content_so_far,
                        sources=None,
                        client_message_id=None,
                        document_ids=None,
                        used_documents=None,
                        is_partial=True,
                        run_id=run_id
                    )
            
            logger.info(f"[CANCEL] Generation run {run_id} cancelled by user {user_id}, partial content saved")
        else:
            logger.warning(f"[CANCEL] Failed to cancel run {run_id}")

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
    # Debug endpoint for last resolved query and carryover rewrite.

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
