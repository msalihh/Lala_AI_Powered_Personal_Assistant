"""
Pydantic schemas for request/response validation.
"""
from pydantic import BaseModel, EmailStr
from typing import Optional, List, Literal
from datetime import datetime


class RegisterRequest(BaseModel):
    """
    User registration request.
    """
    username: str
    email: Optional[str] = None  # Changed from EmailStr to str for more flexibility
    password: str


class RegisterResponse(BaseModel):
    """
    User registration response.
    """
    message: str
    user_id: str  # MongoDB ObjectId as string


class LoginRequest(BaseModel):
    """
    User login request.
    """
    username: str
    password: str


class TokenResponse(BaseModel):
    """
    JWT token response.
    """
    access_token: str
    token_type: str = "bearer"


class GoogleLoginRequest(BaseModel):
    """
    Google OAuth login request (from frontend with Google ID token).
    """
    id_token: str  # Google ID token from NextAuth


class UserResponse(BaseModel):
    """
    User information response.
    """
    id: str  # MongoDB ObjectId as string
    username: str
    email: Optional[str] = None
    is_active: bool
    created_at: str

    class Config:
        from_attributes = True


class ErrorResponse(BaseModel):
    """
    Error response format.
    """
    detail: str
    code: str


class ChatRequest(BaseModel):
    """
    Chat message request.
    """
    message: str
    documentIds: Optional[List[str]] = None
    chatId: Optional[str] = None  # Chat ID for scope checking (optional)
    useDocuments: bool = False  # Opt-in RAG: only use documents if explicitly enabled
    client_message_id: str  # Idempotency: prevent duplicate requests (REQUIRED - UUID from frontend)
    mode: Literal["qa", "summarize", "extract"] = "qa"  # Explicit mode: qa (default), summarize, extract (future)


class SourceInfo(BaseModel):
    """
    Source information for RAG answers.
    """
    documentId: str
    filename: str
    chunkIndex: int
    score: float
    preview: str


class MemoryItem(BaseModel):
    """
    Global memory item for user.
    """
    key: str
    value: str
    created_at: Optional[datetime] = None


class MemoryResponse(BaseModel):
    """
    Global memory response.
    """
    items: List[MemoryItem]  # First 200 chars of chunk text


class ChatResponse(BaseModel):
    """
    Chat message response with optional RAG sources.
    """
    message: str
    role: str = "assistant"
    chatId: Optional[str] = None  # Chat ID (for new chats created by backend)
    sources: Optional[List[SourceInfo]] = None
    debug_info: Optional[dict] = None  # Debug information: documentIds, doc_count, chunk_count, context_added
    suggested_questions: Optional[List[str]] = None  # Suggested questions for short/ambiguous messages
    seq_number: Optional[int] = None  # Optional streaming sequence number for SSE/WebSocket delta events


# Chat management schemas
class CreateChatRequest(BaseModel):
    """
    Request to create a new chat.
    """
    title: Optional[str] = None  # Optional title, will be generated from first message if not provided


class UpdateChatRequest(BaseModel):
    """
    Request to update a chat (title, pinned, tags).
    """
    title: Optional[str] = None  # New title for the chat
    pinned: Optional[bool] = None  # Pin/unpin chat
    tags: Optional[List[str]] = None  # Update tags


class ChatListItem(BaseModel):
    """
    Chat list item response.
    """
    id: str  # Chat ID (MongoDB ObjectId as string)
    title: str
    created_at: str  # ISO format datetime
    updated_at: str  # ISO format datetime


class ChatDetail(BaseModel):
    """
    Chat detail response.
    """
    id: str  # Chat ID (MongoDB ObjectId as string)
    title: str
    created_at: str  # ISO format datetime
    updated_at: str  # ISO format datetime
    user_id: str  # User ID (for ownership verification)
    last_message_at: Optional[str] = None  # Last message timestamp
    deleted_at: Optional[str] = None  # Soft delete timestamp
    pinned: Optional[bool] = False  # Pinned status
    tags: Optional[List[str]] = None  # Tags


# Document schemas
class DocumentUploadResponse(BaseModel):
    """
    Document upload response.
    """
    documentId: str
    filename: str
    size: int
    text_length: int = 0  # Extracted text length (0 if empty)
    text_has_content: bool = False  # True if text_content is not empty
    status: str = "ready"  # "processing" or "ready"
    truncated: bool = False  # True if text was truncated due to size limits
    indexing_success: bool = True  # True if RAG indexing completed successfully
    indexing_chunks: int = 0  # Number of chunks successfully indexed
    indexing_failed_chunks: int = 0  # Number of chunks that failed indexing
    indexing_duration_ms: Optional[float] = None  # Indexing duration in milliseconds


class DocumentListItem(BaseModel):
    """
    Document list item (without text_content).
    """
    id: str
    filename: str
    mime_type: str
    size: int
    created_at: str
    source: str
    is_chat_scoped: Optional[bool] = False
    uploaded_from_chat_id: Optional[str] = None
    uploaded_from_chat_title: Optional[str] = None
    folder_id: Optional[str] = None
    tags: Optional[List[str]] = None


class DocumentDetail(BaseModel):
    """
    Document detail (with text_content).
    """
    id: str
    filename: str
    mime_type: str
    size: int
    text_content: str
    created_at: str
    source: str
    is_chat_scoped: Optional[bool] = False
    uploaded_from_chat_id: Optional[str] = None
    uploaded_from_chat_title: Optional[str] = None
    folder_id: Optional[str] = None
    tags: Optional[List[str]] = None


# Folder schemas
class FolderCreateRequest(BaseModel):
    """
    Request to create a folder.
    """
    name: str
    parent_id: Optional[str] = None  # For nested folders (future)


class FolderUpdateRequest(BaseModel):
    """
    Request to update a folder (rename).
    """
    name: str


class FolderResponse(BaseModel):
    """
    Folder response.
    """
    id: str
    name: str
    parent_id: Optional[str] = None
    created_at: str
    document_count: int = 0  # Number of documents in this folder


class DocumentSearchRequest(BaseModel):
    """
    Document search request with filters.
    """
    query: Optional[str] = None  # Search in filename, text content
    folder_id: Optional[str] = None
    mime_types: Optional[List[str]] = None  # Filter by file types
    tags: Optional[List[str]] = None  # Filter by tags
    date_from: Optional[str] = None  # ISO date string
    date_to: Optional[str] = None  # ISO date string
    page: int = 1
    page_size: int = 20


class DocumentSearchResponse(BaseModel):
    """
    Document search response with pagination.
    """
    documents: List[DocumentListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


# Generation run schemas (for background processing)
class GenerationRunStatus(BaseModel):
    """
    Generation run status response.
    """
    run_id: str
    chat_id: str
    message_id: str
    status: str  # "running", "completed", "failed", "cancelled"
    partial_text: Optional[str] = None
    completed_text: Optional[str] = None
    created_at: str
    updated_at: str
    error: Optional[str] = None


# Chat messages schemas (new architecture)
class ChatMessageRequest(BaseModel):
    """
    Request to send a message in a chat.
    """
    message: str
    documentIds: Optional[List[str]] = None
    useDocuments: bool = False
    client_message_id: str  # Idempotency: prevent duplicate requests (REQUIRED - UUID from frontend)
    mode: Literal["qa", "summarize", "extract"] = "qa"


class ChatMessageResponse(BaseModel):
    """
    Response for a chat message.
    """
    message_id: str  # Message ID (MongoDB ObjectId as string)
    role: str  # "user" or "assistant"
    content: str
    sources: Optional[List[SourceInfo]] = None
    created_at: str  # ISO format datetime
    client_message_id: Optional[str] = None  # Client message ID for idempotency


class ChatMessagesResponse(BaseModel):
    """
    Response for paginated chat messages.
    """
    messages: List[ChatMessageResponse]
    cursor: Optional[str] = None  # Cursor for pagination (last message _id)
    has_more: bool  # Whether there are more messages


class DeleteChatRequest(BaseModel):
    """
    Request to delete a chat.
    """
    hard: bool = False  # Hard delete (default: soft delete)

