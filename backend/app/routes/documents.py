"""
Document management endpoints.
"""
from fastapi import APIRouter, HTTPException, status, Header, UploadFile, File, Form, Depends
from typing import Optional, List
from bson import ObjectId
from datetime import datetime
import os

from app.database import get_database
from app.auth import decode_access_token
from app.documents import extract_text_from_file
from app.utils import sanitize_filename, validate_file_signature
from bson import ObjectId
from app.schemas import (
    DocumentUploadResponse,
    DocumentListItem,
    DocumentDetail,
    FolderCreateRequest,
    FolderUpdateRequest,
    FolderResponse,
    DocumentSearchRequest,
    DocumentSearchResponse
)
from app.rag.chunker import chunk_text
from app.rag.embedder import embed_chunks
from app.rag.vector_store import index_document_chunks, delete_document_chunks
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

# Allowed file types - STRICT: Only PDF, DOCX, TXT
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}
ALLOWED_MIME_TYPES = {
    "application/pdf",  # PDF
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # DOCX
    "text/plain"  # TXT
}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


async def get_current_user_id(authorization: Optional[str] = Header(None)) -> str:
    """
    Get current user ID from JWT token.
    """
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
    
    db = get_database()
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database bağlantısı yok",
            headers={"code": "DATABASE_ERROR"}
        )
    
    try:
        user_doc = await db.users.find_one({"_id": ObjectId(user_id)})
        if user_doc is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Kullanıcı bulunamadı",
                headers={"code": "UNAUTHORIZED"}
            )
        return str(user_doc["_id"])
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Kullanıcı bulunamadı",
            headers={"code": "UNAUTHORIZED"}
        )


@router.post("/upload", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    chat_id: Optional[str] = Form(None),  # Optional: if uploaded from chat
    chat_title: Optional[str] = Form(None),  # Optional: chat name/title
    user_id: str = Depends(get_current_user_id)
):
    """
    Upload and process a document (PDF/DOCX/TXT).
    Extracts text and saves to MongoDB.
    """
    db = get_database()
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database bağlantısı yok",
            headers={"code": "DATABASE_ERROR"}
        )
    
    # STRICT validation: Check both extension and MIME type
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dosya adı belirtilmedi",
            headers={"code": "MISSING_FILENAME"}
        )
    
    filename_lower = file.filename.lower()
    file_ext = None
    for ext in ALLOWED_EXTENSIONS:
        if filename_lower.endswith(ext):
            file_ext = ext
            break
    
    if not file_ext:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Desteklenmeyen dosya uzantısı. İzin verilen: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
            headers={"code": "INVALID_FILE_TYPE"}
        )
    
    # STRICT MIME type validation
    if not file.content_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dosya tipi (MIME type) belirtilmedi",
            headers={"code": "MISSING_MIME_TYPE"}
        )
    
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Desteklenmeyen MIME tipi: {file.content_type}. İzin verilen: {', '.join(sorted(ALLOWED_MIME_TYPES))}",
            headers={"code": "INVALID_MIME_TYPE"}
        )
    
    # Cross-validate: extension must match MIME type
    expected_mime_map = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".txt": "text/plain"
    }
    
    expected_mime = expected_mime_map.get(file_ext)
    if expected_mime and file.content_type != expected_mime:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Dosya uzantısı ({file_ext}) ve MIME tipi ({file.content_type}) uyuşmuyor. Beklenen: {expected_mime}",
            headers={"code": "MIME_EXTENSION_MISMATCH"}
        )
    
    # Read file content
    try:
        file_content = await file.read()
        file_size = len(file_content)
        
        # Check file size
        if file_size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Dosya boyutu çok büyük. Maksimum: {MAX_FILE_SIZE / 1024 / 1024}MB",
                headers={"code": "FILE_TOO_LARGE"}
            )
        
        if file_size == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Dosya boş",
                headers={"code": "EMPTY_FILE"}
            )
        
        # Validate file signature (magic bytes)
        is_valid, error_msg = validate_file_signature(file_content, file_ext, file.content_type)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg,
                headers={"code": "INVALID_FILE_SIGNATURE"}
            )
        
        # Sanitize filename
        sanitized_filename = sanitize_filename(file.filename)
        
        # Extract text
        was_truncated = False
        text_length = 0
        text_has_content = False
        try:
            logger.info(f"[UPLOAD] Starting text extraction for {sanitized_filename}")
            text_content, truncated = extract_text_from_file(
                file_content,
                file.content_type or "",
                sanitized_filename
            )
            was_truncated = truncated
            text_length = len(text_content)
            text_has_content = bool(text_content and text_content.strip())
            
            # CRITICAL CHECK: Warn if extracted text is empty
            if not text_has_content:
                logger.error(
                    f"[UPLOAD] CRITICAL WARNING: Extracted text is EMPTY for {sanitized_filename}! "
                    f"text_length={text_length}, "
                    f"This document will be saved but will NOT be searchable. "
                    f"PDF may be scanned/image-based and requires OCR."
                )
            else:
                logger.info(
                    f"[UPLOAD] Text extraction successful: "
                    f"filename={sanitized_filename}, "
                    f"text_length={text_length}, "
                    f"text_has_content={text_has_content}, "
                    f"text_preview={text_content[:100]}..."
                )
        except ValueError as e:
            logger.error(f"[UPLOAD] Text extraction ValueError: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
                headers={"code": "TEXT_EXTRACTION_ERROR"}
            )
        except Exception as e:
            logger.error(f"[UPLOAD] Text extraction Exception: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Metin çıkarma hatası: {str(e)}",
                headers={"code": "EXTRACTION_ERROR"}
            )
        
        # Save to MongoDB (use sanitized filename)
        # GLOBAL DOCUMENT POOL: All documents are user-scoped, but can be associated with a chat
        # Documents persist even if chat is deleted, but we track which chat they came from
        # Validate chat_id if provided
        uploaded_from_chat_id = None
        uploaded_from_chat_title = None
        is_chat_scoped = False
        
        if chat_id:
            # Validate chat_id format and existence
            try:
                chat_object_id = ObjectId(chat_id)
                chat_doc = await db.chats.find_one({"_id": chat_object_id, "user_id": user_id})
                if chat_doc:
                    uploaded_from_chat_id = chat_id
                    # Use provided chat_title or get from chat document
                    uploaded_from_chat_title = chat_title or chat_doc.get("title", "Untitled Chat")
                    is_chat_scoped = True
                else:
                    logger.warning(f"[UPLOAD] chat_id {chat_id} not found or doesn't belong to user {user_id}")
            except Exception as e:
                logger.warning(f"[UPLOAD] Invalid chat_id format {chat_id}: {str(e)}")
        
        # Store mime_type for later use in chunking
        mime_type = file.content_type or "application/octet-stream"
        
        document_doc = {
            "user_id": user_id,
            "filename": sanitized_filename,
            "mime_type": mime_type,
            "size": file_size,
            "text_content": text_content,
            "created_at": datetime.utcnow(),
            "source": "upload",  # Always "upload" - documents are global to user
            "uploaded_from_chat_id": uploaded_from_chat_id,  # Chat association if provided
            "uploaded_from_chat_title": uploaded_from_chat_title,  # Chat title if provided
            "is_chat_scoped": is_chat_scoped,  # True if associated with a chat
            "folder_id": None,  # Optional folder assignment
            "tags": []  # Empty tags array by default
        }
        
        result = await db.documents.insert_one(document_doc)
        document_id = str(result.inserted_id)
        
        # Set status to "processing" before indexing
        status = "processing"
        
        # RAG Indexing: Chunk, embed, and store in vector database
        # This runs synchronously after successful upload
        # Upload succeeds even if indexing partially fails
        indexing_success = False
        indexing_chunks = 0
        indexing_failed_chunks = 0
        indexing_duration_ms = None
        
        import time
        indexing_start_time = time.time()
        
        try:
            logger.info(
                f"[INDEX_START] doc_id={document_id} filename={sanitized_filename} "
                f"size={file_size} chat_id={chat_id or 'N/A'} "
                f"text_length={len(text_content)} text_has_content={bool(text_content.strip())}"
            )
            
            # CRITICAL CHECK: Warn if text_content is empty before chunking
            if not text_content or not text_content.strip():
                logger.error(
                    f"[INDEX_START] CRITICAL: text_content is EMPTY for doc_id={document_id}! "
                    f"This will result in 0 chunks and the document will NOT be searchable."
                )
            
            # Step 1: Chunk the text with adaptive chunking
            chunks = chunk_text(
                text_content,
                chunk_words=None,  # Use config default
                overlap_words=None,  # Use config default
                document_id=document_id,
                mime_type=mime_type
            )
            logger.info(
                f"[INDEX_CHUNK] doc_id={document_id} created_chunks={len(chunks)} "
                f"text_length={len(text_content)}"
            )
            
            # Warn if no chunks created
            if len(chunks) == 0:
                logger.error(
                    f"[INDEX_CHUNK] CRITICAL: No chunks created for doc_id={document_id}! "
                    f"text_length={len(text_content)}, text_preview={text_content[:200]}..."
                )
            
            if chunks:
                # Step 2: Embed chunks
                logger.info(f"[INDEX_EMBED] doc_id={document_id} starting embedding for {len(chunks)} chunks")
                embedded_chunks = await embed_chunks(chunks)
                
                # Count successful embeddings
                successful_embeddings = sum(1 for chunk in embedded_chunks if chunk.get("embedding") is not None)
                failed_embeddings = len(embedded_chunks) - successful_embeddings
                logger.info(f"[INDEX_EMBED] doc_id={document_id} successful={successful_embeddings} failed={failed_embeddings}")
                
                # Step 3: Index in vector store
                logger.info(f"[INDEX_STORE] doc_id={document_id} starting vector store indexing")
                indexing_stats = index_document_chunks(
                    document_id=document_id,
                    chunks=embedded_chunks,
                    original_filename=sanitized_filename,
                    was_truncated=was_truncated
                )
                
                indexing_chunks = indexing_stats.get('indexed_chunks', 0)
                indexing_failed_chunks = indexing_stats.get('failed_chunks', 0)
                indexing_success = indexing_chunks > 0
                
                indexing_duration_ms = (time.time() - indexing_start_time) * 1000
                
                # Set status to "ready" after indexing completes
                status = "ready"
                
                logger.info(
                    f"[INDEX_DONE] doc_id={document_id} chunks={len(chunks)} indexed={indexing_chunks} failed={indexing_failed_chunks} "
                    f"duration_ms={indexing_duration_ms:.2f} success={indexing_success} "
                    f"status={status} chat_id={chat_id or 'N/A'} chat_title={chat_title or 'N/A'}"
                )
            else:
                logger.warning(f"[INDEX_WARN] doc_id={document_id} no chunks created (empty text?)")
                indexing_duration_ms = (time.time() - indexing_start_time) * 1000
                
        except Exception as e:
            # Log error but don't fail the upload
            indexing_duration_ms = (time.time() - indexing_start_time) * 1000
            status = "ready"  # Set to ready even if indexing failed
            logger.error(
                f"[INDEX_ERROR] doc_id={document_id} error={str(e)} duration_ms={indexing_duration_ms:.2f} status={status}",
                exc_info=True
            )
        
        # Final status check: if indexing didn't run, set to ready
        if status == "processing" and not indexing_success and indexing_chunks == 0:
            status = "ready"
        
        logger.info(
            f"[UPLOAD_RESPONSE] doc_id={document_id} "
            f"text_length={text_length} text_has_content={text_has_content} "
            f"status={status} indexing_chunks={indexing_chunks}"
        )
        
        return DocumentUploadResponse(
            documentId=document_id,
            filename=sanitized_filename,
            size=file_size,
            text_length=text_length,
            text_has_content=text_has_content,
            status=status,
            truncated=was_truncated,
            indexing_success=indexing_success,
            indexing_chunks=indexing_chunks,
            indexing_failed_chunks=indexing_failed_chunks,
            indexing_duration_ms=indexing_duration_ms
        )
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"Document upload error: {e}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Dosya yükleme hatası: {str(e)}",
            headers={"code": "UPLOAD_ERROR"}
        )


@router.get("", response_model=List[DocumentListItem])
async def list_documents(
    user_id: str = Depends(get_current_user_id)
):
    """
    List all documents for the current user.
    """
    db = get_database()
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database bağlantısı yok",
            headers={"code": "DATABASE_ERROR"}
        )
    
    try:
        cursor = db.documents.find({"user_id": user_id}).sort("created_at", -1)
        documents = []
        async for doc in cursor:
            created_at = doc.get("created_at")
            if isinstance(created_at, datetime):
                created_at_str = created_at.isoformat()
            else:
                created_at_str = str(created_at)
            
            documents.append(DocumentListItem(
                id=str(doc["_id"]),
                filename=doc.get("filename", "unknown"),
                mime_type=doc.get("mime_type", ""),
                size=doc.get("size", 0),
                created_at=created_at_str,
                source=doc.get("source", "upload"),
                is_chat_scoped=doc.get("is_chat_scoped", False),
                uploaded_from_chat_id=doc.get("uploaded_from_chat_id"),
                uploaded_from_chat_title=doc.get("uploaded_from_chat_title"),
                folder_id=doc.get("folder_id"),
                tags=doc.get("tags", [])
            ))
        
        return documents
    except Exception as e:
        import traceback
        print(f"List documents error: {e}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Doküman listesi alınamadı: {str(e)}",
            headers={"code": "LIST_ERROR"}
        )


@router.get("/{document_id}", response_model=DocumentDetail)
async def get_document(
    document_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """
    Get document details including text content.
    Only owner can access.
    """
    db = get_database()
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database bağlantısı yok",
            headers={"code": "DATABASE_ERROR"}
        )
    
    try:
        if not ObjectId.is_valid(document_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Geçersiz doküman ID",
                headers={"code": "INVALID_ID"}
            )
        
        doc = await db.documents.find_one({"_id": ObjectId(document_id), "user_id": user_id})
        
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Doküman bulunamadı veya erişim izniniz yok",
                headers={"code": "NOT_FOUND"}
            )
        
        created_at = doc.get("created_at")
        if isinstance(created_at, datetime):
            created_at_str = created_at.isoformat()
        else:
            created_at_str = str(created_at)
        
        return DocumentDetail(
            id=str(doc["_id"]),
            filename=doc.get("filename", "unknown"),
            mime_type=doc.get("mime_type", ""),
            size=doc.get("size", 0),
            text_content=doc.get("text_content", ""),
            created_at=created_at_str,
            source=doc.get("source", "upload"),
            is_chat_scoped=doc.get("is_chat_scoped", False),
            uploaded_from_chat_id=doc.get("uploaded_from_chat_id"),
            uploaded_from_chat_title=doc.get("uploaded_from_chat_title"),
            folder_id=doc.get("folder_id"),
            tags=doc.get("tags", [])
        )
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"Get document error: {e}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Doküman alınamadı: {str(e)}",
            headers={"code": "GET_ERROR"}
        )


@router.delete("/chat/{chat_id}")
async def delete_chat_documents(
    chat_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """
    Delete all documents uploaded from a specific chat (cascade delete).
    Also deletes associated vectors from ChromaDB.
    """
    db = get_database()
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database bağlantısı yok",
            headers={"code": "DATABASE_ERROR"}
        )
    
    try:
        # Find all documents uploaded from this chat (regardless of is_chat_scoped flag)
        # If a document was uploaded from a chat, it should be deleted when the chat is deleted
        cursor = db.documents.find({
            "user_id": user_id,
            "uploaded_from_chat_id": chat_id
            # Removed is_chat_scoped check - delete ALL documents from this chat
        })
        
        deleted_documents_count = 0
        deleted_vectors_count = 0
        document_ids_to_delete = []
        
        async for doc in cursor:
            document_ids_to_delete.append(str(doc["_id"]))
        
        logger.info(f"Cascade delete for chat {chat_id}: Found {len(document_ids_to_delete)} documents to delete (uploaded_from_chat_id={chat_id})")
        
        # Delete documents from MongoDB
        if document_ids_to_delete:
            result = await db.documents.delete_many({
                "_id": {"$in": [ObjectId(doc_id) for doc_id in document_ids_to_delete]},
                "user_id": user_id
            })
            deleted_documents_count = result.deleted_count
            
            # Delete associated vectors from ChromaDB
            for doc_id in document_ids_to_delete:
                try:
                    deleted_chunks = delete_document_chunks(doc_id)
                    deleted_vectors_count += deleted_chunks
                    logger.info(f"Deleted {deleted_chunks} chunks from ChromaDB for document {doc_id}")
                except Exception as e:
                    logger.error(f"Failed to delete chunks for document {doc_id}: {str(e)}")
        
        logger.info(
            f"Cascade delete completed for chat {chat_id}: "
            f"deleted_documents={deleted_documents_count}, deleted_vectors={deleted_vectors_count}"
        )
        
        return {
            "message": f"Deleted {deleted_documents_count} documents and {deleted_vectors_count} vectors",
            "deleted_documents": deleted_documents_count,
            "deleted_vectors": deleted_vectors_count
        }
    except Exception as e:
        logger.error(f"Cascade delete error for chat {chat_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat dokümanları silinemedi: {str(e)}",
            headers={"code": "CASCADE_DELETE_ERROR"}
        )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """
    Delete a document. Only owner can delete.
    """
    db = get_database()
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database bağlantısı yok",
            headers={"code": "DATABASE_ERROR"}
        )
    
    try:
        if not ObjectId.is_valid(document_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Geçersiz doküman ID",
                headers={"code": "INVALID_ID"}
            )
        
        result = await db.documents.delete_one({"_id": ObjectId(document_id), "user_id": user_id})
        
        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Doküman bulunamadı veya erişim izniniz yok",
                headers={"code": "NOT_FOUND"}
            )
        
        # Delete associated chunks from vector store
        try:
            deleted_chunks = delete_document_chunks(document_id)
            logger.info(f"Deleted {deleted_chunks} chunks for document {document_id}")
        except Exception as e:
            # Log error but don't fail the delete operation
            logger.error(f"Error deleting chunks for document {document_id}: {str(e)}")
        
        return None
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"Delete document error: {e}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Doküman silinemedi: {str(e)}",
            headers={"code": "DELETE_ERROR"}
        )


# Folder endpoints
@router.post("/folders", response_model=FolderResponse, status_code=status.HTTP_201_CREATED)
async def create_folder(
    request: FolderCreateRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Create a new folder for organizing documents.
    """
    db = get_database()
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database bağlantısı yok",
            headers={"code": "DATABASE_ERROR"}
        )
    
    try:
        # Validate folder name
        if not request.name or not request.name.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Klasör adı boş olamaz",
                headers={"code": "INVALID_FOLDER_NAME"}
            )
        
        folder_name = request.name.strip()
        
        # Check if folder with same name already exists (for same user, same parent)
        existing = await db.folders.find_one({
            "user_id": user_id,
            "name": folder_name,
            "parent_id": request.parent_id
        })
        
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Bu isimde bir klasör zaten var",
                headers={"code": "FOLDER_EXISTS"}
            )
        
        # Validate parent_id if provided
        if request.parent_id:
            try:
                parent_object_id = ObjectId(request.parent_id)
            except Exception:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Geçersiz parent_id formatı",
                    headers={"code": "INVALID_PARENT_ID"}
                )
            
            parent_folder = await db.folders.find_one({
                "_id": parent_object_id,
                "user_id": user_id
            })
            
            if not parent_folder:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Üst klasör bulunamadı",
                    headers={"code": "PARENT_NOT_FOUND"}
                )
        
        # Create folder
        folder_doc = {
            "user_id": user_id,
            "name": folder_name,
            "parent_id": ObjectId(request.parent_id) if request.parent_id else None,
            "created_at": datetime.utcnow()
        }
        
        result = await db.folders.insert_one(folder_doc)
        folder_id = str(result.inserted_id)
        
        created_at_str = folder_doc["created_at"].isoformat()
        
        return FolderResponse(
            id=folder_id,
            name=folder_name,
            parent_id=request.parent_id,
            created_at=created_at_str,
            document_count=0
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating folder: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Klasör oluşturulamadı: {str(e)}",
            headers={"code": "FOLDER_CREATE_ERROR"}
        )


@router.get("/folders", response_model=List[FolderResponse])
async def list_folders(
    user_id: str = Depends(get_current_user_id)
):
    """
    List all folders for the current user.
    """
    db = get_database()
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database bağlantısı yok",
            headers={"code": "DATABASE_ERROR"}
        )
    
    try:
        cursor = db.folders.find({"user_id": user_id}).sort("created_at", -1)
        folders = []
        
        async for folder in cursor:
            # Count documents in this folder
            doc_count = await db.documents.count_documents({
                "user_id": user_id,
                "folder_id": str(folder["_id"])
            })
            
            created_at = folder.get("created_at")
            if isinstance(created_at, datetime):
                created_at_str = created_at.isoformat()
            else:
                created_at_str = str(created_at)
            
            folders.append(FolderResponse(
                id=str(folder["_id"]),
                name=folder.get("name", "Unnamed"),
                parent_id=str(folder["parent_id"]) if folder.get("parent_id") else None,
                created_at=created_at_str,
                document_count=doc_count
            ))
        
        return folders
    except Exception as e:
        logger.error(f"Error listing folders: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Klasör listesi alınamadı: {str(e)}",
            headers={"code": "FOLDER_LIST_ERROR"}
        )


@router.put("/folders/{folder_id}", response_model=FolderResponse)
async def update_folder(
    folder_id: str,
    request: FolderUpdateRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Rename a folder.
    """
    db = get_database()
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database bağlantısı yok",
            headers={"code": "DATABASE_ERROR"}
        )
    
    try:
        if not ObjectId.is_valid(folder_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Geçersiz klasör ID",
                headers={"code": "INVALID_FOLDER_ID"}
            )
        
        if not request.name or not request.name.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Klasör adı boş olamaz",
                headers={"code": "INVALID_FOLDER_NAME"}
            )
        
        folder_object_id = ObjectId(folder_id)
        
        # Verify ownership
        folder = await db.folders.find_one({
            "_id": folder_object_id,
            "user_id": user_id
        })
        
        if not folder:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Klasör bulunamadı veya erişim izniniz yok",
                headers={"code": "FOLDER_NOT_FOUND"}
            )
        
        new_name = request.name.strip()
        
        # Check if another folder with same name exists (same parent)
        existing = await db.folders.find_one({
            "user_id": user_id,
            "name": new_name,
            "parent_id": folder.get("parent_id"),
            "_id": {"$ne": folder_object_id}
        })
        
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Bu isimde bir klasör zaten var",
                headers={"code": "FOLDER_EXISTS"}
            )
        
        # Update folder
        await db.folders.update_one(
            {"_id": folder_object_id, "user_id": user_id},
            {"$set": {"name": new_name}}
        )
        
        # Get updated folder
        updated_folder = await db.folders.find_one({"_id": folder_object_id})
        
        # Count documents
        doc_count = await db.documents.count_documents({
            "user_id": user_id,
            "folder_id": folder_id
        })
        
        created_at = updated_folder.get("created_at")
        if isinstance(created_at, datetime):
            created_at_str = created_at.isoformat()
        else:
            created_at_str = str(created_at)
        
        return FolderResponse(
            id=folder_id,
            name=new_name,
            parent_id=str(updated_folder["parent_id"]) if updated_folder.get("parent_id") else None,
            created_at=created_at_str,
            document_count=doc_count
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating folder: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Klasör güncellenemedi: {str(e)}",
            headers={"code": "FOLDER_UPDATE_ERROR"}
        )


@router.delete("/folders/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder(
    folder_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """
    Delete a folder (soft delete: move documents to root).
    """
    db = get_database()
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database bağlantısı yok",
            headers={"code": "DATABASE_ERROR"}
        )
    
    try:
        if not ObjectId.is_valid(folder_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Geçersiz klasör ID",
                headers={"code": "INVALID_FOLDER_ID"}
            )
        
        folder_object_id = ObjectId(folder_id)
        
        # Verify ownership
        folder = await db.folders.find_one({
            "_id": folder_object_id,
            "user_id": user_id
        })
        
        if not folder:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Klasör bulunamadı veya erişim izniniz yok",
                headers={"code": "FOLDER_NOT_FOUND"}
            )
        
        # Move all documents in this folder to root (set folder_id to None)
        await db.documents.update_many(
            {"user_id": user_id, "folder_id": folder_id},
            {"$set": {"folder_id": None}}
        )
        
        # Delete folder
        result = await db.folders.delete_one({
            "_id": folder_object_id,
            "user_id": user_id
        })
        
        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Klasör silinemedi",
                headers={"code": "FOLDER_DELETE_ERROR"}
            )
        
        return None
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting folder: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Klasör silinemedi: {str(e)}",
            headers={"code": "FOLDER_DELETE_ERROR"}
        )


@router.post("/search", response_model=DocumentSearchResponse)
async def search_documents(
    request: DocumentSearchRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Search documents with filters (query, folder, mime_type, tags, date range).
    """
    db = get_database()
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database bağlantısı yok",
            headers={"code": "DATABASE_ERROR"}
        )
    
    try:
        # Build query filter
        query_filter: dict = {"user_id": user_id}
        
        # Folder filter
        if request.folder_id:
            if not ObjectId.is_valid(request.folder_id):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Geçersiz folder_id formatı",
                    headers={"code": "INVALID_FOLDER_ID"}
                )
            query_filter["folder_id"] = request.folder_id
        else:
            # If no folder_id specified, show all documents (including those in folders)
            # To show only root documents, use folder_id: None explicitly
            pass
        
        # MIME type filter
        if request.mime_types and len(request.mime_types) > 0:
            query_filter["mime_type"] = {"$in": request.mime_types}
        
        # Tags filter
        if request.tags and len(request.tags) > 0:
            query_filter["tags"] = {"$in": request.tags}
        
        # Date range filter
        if request.date_from or request.date_to:
            date_filter: dict = {}
            if request.date_from:
                try:
                    date_from = datetime.fromisoformat(request.date_from.replace("Z", "+00:00"))
                    date_filter["$gte"] = date_from
                except Exception:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Geçersiz date_from formatı (ISO format bekleniyor)",
                        headers={"code": "INVALID_DATE_FORMAT"}
                    )
            if request.date_to:
                try:
                    date_to = datetime.fromisoformat(request.date_to.replace("Z", "+00:00"))
                    date_filter["$lte"] = date_to
                except Exception:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Geçersiz date_to formatı (ISO format bekleniyor)",
                        headers={"code": "INVALID_DATE_FORMAT"}
                    )
            query_filter["created_at"] = date_filter
        
        # Text search (filename or text_content)
        if request.query and request.query.strip():
            search_query = request.query.strip()
            # MongoDB text search (requires text index)
            # For now, use regex on filename and text_content
            query_filter["$or"] = [
                {"filename": {"$regex": search_query, "$options": "i"}},
                {"text_content": {"$regex": search_query, "$options": "i"}}
            ]
        
        # Count total matching documents
        total = await db.documents.count_documents(query_filter)
        
        # Pagination
        page = max(1, request.page)
        page_size = max(1, min(100, request.page_size))  # Limit to 100 per page
        skip = (page - 1) * page_size
        total_pages = (total + page_size - 1) // page_size
        
        # Fetch documents
        cursor = db.documents.find(query_filter).sort("created_at", -1).skip(skip).limit(page_size)
        documents = []
        
        async for doc in cursor:
            created_at = doc.get("created_at")
            if isinstance(created_at, datetime):
                created_at_str = created_at.isoformat()
            else:
                created_at_str = str(created_at)
            
            documents.append(DocumentListItem(
                id=str(doc["_id"]),
                filename=doc.get("filename", "unknown"),
                mime_type=doc.get("mime_type", ""),
                size=doc.get("size", 0),
                created_at=created_at_str,
                source=doc.get("source", "upload"),
                is_chat_scoped=doc.get("is_chat_scoped", False),
                uploaded_from_chat_id=doc.get("uploaded_from_chat_id"),
                uploaded_from_chat_title=doc.get("uploaded_from_chat_title"),
                folder_id=doc.get("folder_id"),
                tags=doc.get("tags", [])
            ))
        
        return DocumentSearchResponse(
            documents=documents,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error searching documents: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Doküman arama hatası: {str(e)}",
            headers={"code": "SEARCH_ERROR"}
        )

