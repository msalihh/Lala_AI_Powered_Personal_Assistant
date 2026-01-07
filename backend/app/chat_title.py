"""
Automatic chat title generation system.
3-layer approach: Rule-based fallback → LLM-based smart title → Update policy
"""
import os
import re
import logging
from typing import Optional, List, Dict, Literal
from datetime import datetime, timedelta
import httpx

from app.database import get_database
from app.rag.embedder import embed_text
from app.memory import get_recent_messages

logger = logging.getLogger(__name__)

# OpenRouter API Configuration (reuse from main.py)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "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")
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")  # Optimized mini model for title generation

# Title update policy constants
TITLE_UPDATE_SIMILARITY_THRESHOLD = 0.55  # Embedding similarity threshold for topic drift
MAX_TITLE_UPDATES = 2  # Maximum title updates per chat lifetime
TITLE_UPDATE_MAX_AGE_HOURS = 24  # Never update title after chat is older than 24 hours

# Turkish stopwords for title generation
TURKISH_STOPWORDS = {"ve", "ile", "için", "nasıl", "neden", "ne", "bu", "şu", "o", "bir", "de", "da", "mi", "mı", "mu", "mü"}

# Generic titles to reject from LLM
GENERIC_TITLES = {"yardım", "soru", "proje", "chat", "deneme", "sohbet", "mesaj", "yeni", "test"}


# ============================================================
# LAYER A — Rule-based fallback (must always work)
# ============================================================

def generateFallbackTitle(
    first_message: str,
    document_filenames: Optional[List[str]] = None
) -> str:
    """
    Generate a fallback title using rule-based heuristics.
    This function MUST always return a valid title (no exceptions).
    
    Args:
        first_message: First user message content
        document_filenames: Optional list of uploaded document filenames
        
    Returns:
        A valid title string
    """
    if not first_message:
        return f"Sohbet {datetime.utcnow().strftime('%Y-%m-%d')}"
    
    message = first_message.strip()
    
    # Rule 1: File upload detection
    if document_filenames and len(document_filenames) > 0:
        # Use first document filename
        filename = document_filenames[0]
        # Remove extension for cleaner title
        filename_without_ext = filename.rsplit('.', 1)[0] if '.' in filename else filename
        return f"Doküman: {filename_without_ext}"
    
    # Rule 2: Error/debug message detection
    error_keywords = ["ERROR", "Exception", "Traceback", "failed", "404", "500", "error", "hata", "exception"]
    error_symbols = ["{", "}", "(", ")", "[", "]", ":", "\\n", "\\t"]
    
    has_error_keyword = any(keyword.lower() in message.lower() for keyword in error_keywords)
    has_error_symbols = sum(1 for sym in error_symbols if sym in message) >= 3
    
    if has_error_keyword or has_error_symbols:
        # Extract main keyword (first error keyword found)
        main_keyword = None
        for keyword in error_keywords:
            if keyword.lower() in message.lower():
                main_keyword = keyword
                break
        
        if main_keyword:
            return f"Hata Ayıklama: {main_keyword}"
        else:
            return "Hata Ayıklama"
    
    # Rule 3: Extract meaningful words from message (works for both short and long messages)
    # Split into words
    words = re.findall(r'\b\w+\b', message.lower())
    # Remove stopwords
    meaningful_words = [w for w in words if w not in TURKISH_STOPWORDS and len(w) > 2]
    
    if len(meaningful_words) >= 3:
        # Take first 3-6 words (shorter for short messages, longer for long messages)
        max_words = 6 if len(message) >= 80 else 4
        selected_words = meaningful_words[:max_words]
        # Capitalize first letter of first word
        title = " ".join(selected_words)
        if title:
            title = title[0].upper() + title[1:] if len(title) > 1 else title.upper()
            return title
    elif len(meaningful_words) > 0:
        # Even if less than 3 meaningful words, use what we have
        selected_words = meaningful_words[:3]
        title = " ".join(selected_words)
        if title:
            title = title[0].upper() + title[1:] if len(title) > 1 else title.upper()
            return title
    
    # Rule 4: Default fallback - use first few words if message exists
    if message:
        # Take first 3-4 words, remove special chars
        first_words = re.findall(r'\b\w+\b', message)[:4]
        if first_words:
            title = " ".join(first_words)
            if len(title) > 0:
                title = title[0].upper() + title[1:] if len(title) > 1 else title.upper()
                return title
    
    # Rule 5: Ultimate fallback
    return f"Sohbet {datetime.utcnow().strftime('%Y-%m-%d')}"


# ============================================================
# LAYER B — LLM-based smart title (preferred)
# ============================================================

async def generateLLMTitle(
    user_messages: List[str],
    chat_mode: Literal["qa", "summarize", "extract"] = "qa",
    document_filenames: Optional[List[str]] = None
) -> Optional[str]:
    """
    Generate a smart title using LLM.
    Returns None if LLM fails or returns generic title.
    
    Args:
        user_messages: First 1-3 user messages
        chat_mode: Chat mode (normal / RAG / document / debug)
        document_filenames: Optional list of uploaded document filenames
        
    Returns:
        Title string or None if generation failed
    """
    if not user_messages or len(user_messages) == 0:
        return None
    
    # Prepare context for LLM
    messages_text = "\n".join([f"Kullanıcı: {msg}" for msg in user_messages[:3]])
    
    mode_description = {
        "qa": "normal soru-cevap",
        "summarize": "doküman özetleme",
        "extract": "bilgi çıkarma"
    }.get(chat_mode, "normal")
    
    doc_context = ""
    if document_filenames and len(document_filenames) > 0:
        doc_context = f"\nNot: Kullanıcı şu dosyaları yükledi: {', '.join(document_filenames[:3])}"
    
    system_prompt = """Sen yardımcı bir AI asistanısın. Kullanıcının sohbet başlığı oluşturmana yardım ediyorsun.

GÖREV: Kullanıcının ilk birkaç mesajına bakarak, sohbet için kısa ve anlamlı bir Türkçe başlık oluştur.

KURALLAR:
1. Başlık 3-7 kelime arası olmalı
2. Başlık açık ve spesifik olmalı (genel başlıklar YOK)
3. Fiil + nesne veya konu etiketi tarzında olmalı
4. Sadece başlığı döndür, başka açıklama yapma

YASAK BAŞLIKLAR (bunları ASLA kullanma):
- "Yardım", "Soru", "Proje", "Chat", "Deneme", "Sohbet", "Mesaj", "Yeni", "Test"
- Bu tür genel başlıklar kullanırsan, başlık reddedilir.

ÖRNEKLER:
- "Üslü Sayılarda Çıkarma"
- "Python OAuth Hatası"
- "Algoritma Analizi"
- "Veritabanı Optimizasyonu"

Şimdi kullanıcının mesajlarına bak ve uygun bir başlık oluştur:"""
    
    user_prompt = f"""Sohbet modu: {mode_description}{doc_context}

Kullanıcı mesajları:
{messages_text}

Başlık (sadece başlık, başka açıklama yok):"""
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
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
                            "content": system_prompt
                        },
                        {
                            "role": "user",
                            "content": user_prompt
                        }
                    ],
                    "temperature": 0.7,
                    "max_tokens": 50,  # Short titles only
                }
            )
            response.raise_for_status()
            data = response.json()
            
            if "choices" in data and len(data["choices"]) > 0:
                title = data["choices"][0]["message"]["content"].strip()
                
                # Remove quotes if present
                title = title.strip('"').strip("'").strip()
                
                # Validate title
                if not title or len(title) == 0:
                    logger.warning("LLM returned empty title")
                    return None
                
                # Check for generic titles
                title_lower = title.lower()
                if any(generic in title_lower for generic in GENERIC_TITLES):
                    logger.warning(f"LLM returned generic title: {title}")
                    return None
                
                # Check word count (3-7 words)
                word_count = len(title.split())
                if word_count < 3 or word_count > 7:
                    logger.warning(f"LLM returned title with invalid word count ({word_count}): {title}")
                    return None
                
                # Capitalize first letter
                if len(title) > 0:
                    title = title[0].upper() + title[1:] if len(title) > 1 else title.upper()
                
                logger.info(f"LLM generated title: {title}")
                return title
            else:
                logger.warning("LLM response missing choices")
                return None
                
    except Exception as e:
        logger.error(f"LLM title generation failed: {str(e)}", exc_info=True)
        return None


# ============================================================
# LAYER C — Title update policy (anti-spam)
# ============================================================

async def shouldUpdateTitle(
    chat_id: str,
    user_id: str,
    current_title: str,
    current_title_source: str,
    title_updates_count: int,
    title_last_updated_at: Optional[datetime]
) -> bool:
    """
    Determine if chat title should be updated based on policy.
    
    Args:
        chat_id: Chat ID
        user_id: User ID
        current_title: Current chat title
        current_title_source: "fallback" or "llm"
        title_updates_count: Number of times title has been updated
        title_last_updated_at: Last update timestamp
        
    Returns:
        True if title should be updated, False otherwise
    """
    # Rule 1: Never update if already at max updates
    if title_updates_count >= MAX_TITLE_UPDATES:
        logger.debug(f"Title update rejected: max updates reached ({title_updates_count})")
        return False
    
    # Rule 2: Never update if chat is older than 24 hours
    if title_last_updated_at:
        age_hours = (datetime.utcnow() - title_last_updated_at).total_seconds() / 3600
        if age_hours > TITLE_UPDATE_MAX_AGE_HOURS:
            logger.debug(f"Title update rejected: chat too old ({age_hours:.1f} hours)")
            return False
    
    # Rule 3: Check topic drift using embeddings
    try:
        db = get_database()
        if db is None:
            return False
        
        # Get last 5 user messages
        recent_messages = await get_recent_messages(user_id=user_id, chat_id=chat_id, limit=10)
        user_messages = [msg["content"] for msg in recent_messages if msg.get("role") == "user"]
        
        if len(user_messages) < 3:
            # Not enough messages to detect drift
            return False
        
        # Get last 5 user messages
        last_5_messages = user_messages[-5:]
        messages_summary = " ".join(last_5_messages)
        
        # Embed current title and recent messages
        title_embedding = await embed_text(current_title)
        messages_embedding = await embed_text(messages_summary)
        
        if not title_embedding or not messages_embedding:
            logger.warning("Failed to generate embeddings for title update check")
            return False
        
        # Calculate cosine similarity
        import numpy as np
        similarity = np.dot(title_embedding, messages_embedding) / (
            np.linalg.norm(title_embedding) * np.linalg.norm(messages_embedding)
        )
        
        logger.debug(f"Title similarity check: {similarity:.3f} (threshold: {TITLE_UPDATE_SIMILARITY_THRESHOLD})")
        
        # Update if similarity is below threshold (topic drift detected)
        if similarity < TITLE_UPDATE_SIMILARITY_THRESHOLD:
            logger.info(f"Topic drift detected (similarity: {similarity:.3f}), title update approved")
            return True
        else:
            logger.debug(f"No topic drift (similarity: {similarity:.3f}), title update rejected")
            return False
            
    except Exception as e:
        logger.error(f"Error checking title update policy: {str(e)}", exc_info=True)
        return False


async def generateAndSetTitle(
    chat_id: str,
    user_id: str,
    chat_mode: Literal["qa", "summarize", "extract"] = "qa",
    document_filenames: Optional[List[str]] = None
) -> Optional[str]:
    """
    Generate and set chat title using 3-layer system.
    Called after 2nd user message.
    
    Args:
        chat_id: Chat ID
        user_id: User ID
        chat_mode: Chat mode
        document_filenames: Optional list of uploaded document filenames
        
    Returns:
        Generated title or None if failed
    """
    try:
        db = get_database()
        if db is None:
            logger.error("Database not available for title generation")
            return None
        
        # Get first 1-3 user messages
        recent_messages = await get_recent_messages(user_id=user_id, chat_id=chat_id, limit=6)
        user_messages = [msg["content"] for msg in recent_messages if msg.get("role") == "user"]
        
        if len(user_messages) == 0:
            logger.warning("No user messages found for title generation")
            return None
        
        # Get first message for fallback
        first_message = user_messages[0]
        
        # Try Layer B (LLM) first -> DISABLED FOR STABILITY
        # CRITICAL FIX: Skip LLM title generation to save rate limits
        # title = await generateLLMTitle(
        #     user_messages=user_messages[:3],
        #     chat_mode=chat_mode,
        #     document_filenames=document_filenames
        # )
        title = None  # Force fallback
        title_source = "fallback"  # Default to fallback immediately
        
        # Fallback to Layer A if LLM fails (or is disabled)
        if not title:
            title = generateFallbackTitle(
                first_message=first_message,
                document_filenames=document_filenames
            )
            title_source = "fallback"
        
        # Ensure title is never empty or "Yeni Sohbet" (must be meaningful)
        if not title or title.strip() == "" or title.strip() == "Yeni Sohbet":
            # Ultimate fallback - use first message words
            if first_message and first_message.strip():
                words = re.findall(r'\b\w+\b', first_message.strip())[:4]
                if words:
                    title = " ".join(words)
                    title = title[0].upper() + title[1:] if len(title) > 1 else title.upper()
                else:
                    title = f"Sohbet {datetime.utcnow().strftime('%Y-%m-%d')}"
            else:
                title = f"Sohbet {datetime.utcnow().strftime('%Y-%m-%d')}"
            title_source = "fallback"
        
        # Update chat document
        from bson import ObjectId
        chat_object_id = ObjectId(chat_id)
        
        update_doc = {
            "title": title,
            "title_source": title_source,
            "title_updates_count": 0,
            "title_last_updated_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        await db.chats.update_one(
            {"_id": chat_object_id, "user_id": user_id},
            {"$set": update_doc}
        )
        
        logger.info(f"Generated and set title for chat {chat_id[:8]}...: '{title}' (source: {title_source})")
        return title
        
    except Exception as e:
        logger.error(f"Error generating title: {str(e)}", exc_info=True)
        return None


async def updateChatTitleIfNeeded(
    chat_id: str,
    user_id: str,
    chat_mode: Literal["qa", "summarize", "extract"] = "qa"
) -> Optional[str]:
    """
    Check if title should be updated and update if needed.
    Called periodically or after significant message count.
    
    Args:
        chat_id: Chat ID
        user_id: User ID
        chat_mode: Chat mode
        
    Returns:
        Updated title or None if no update needed
    """
    try:
        db = get_database()
        if db is None:
            return None
        
        from bson import ObjectId
        chat_object_id = ObjectId(chat_id)
        
        # Get current chat document
        chat = await db.chats.find_one({"_id": chat_object_id, "user_id": user_id})
        if not chat:
            logger.warning(f"Chat {chat_id[:8]}... not found for title update")
            return None
        
        current_title = chat.get("title", "Yeni Sohbet")
        current_title_source = chat.get("title_source", "fallback")
        title_updates_count = chat.get("title_updates_count", 0)
        title_last_updated_at = chat.get("title_last_updated_at")
        
        if title_last_updated_at and isinstance(title_last_updated_at, str):
            # Parse ISO string if needed
            try:
                title_last_updated_at = datetime.fromisoformat(title_last_updated_at.replace('Z', '+00:00'))
            except:
                title_last_updated_at = None
        
        # Check if update is needed
        should_update = await shouldUpdateTitle(
            chat_id=chat_id,
            user_id=user_id,
            current_title=current_title,
            current_title_source=current_title_source,
            title_updates_count=title_updates_count,
            title_last_updated_at=title_last_updated_at
        )
        
        if not should_update:
            return None
        
        # Generate new title
        recent_messages = await get_recent_messages(user_id=user_id, chat_id=chat_id, limit=10)
        user_messages = [msg["content"] for msg in recent_messages if msg.get("role") == "user"]
        
        if len(user_messages) == 0:
            return None
        
        # Try LLM first
        title = await generateLLMTitle(
            user_messages=user_messages[-5:],  # Last 5 messages for context
            chat_mode=chat_mode
        )
        title_source = "llm"
        
        # Fallback if LLM fails
        if not title:
            first_message = user_messages[0] if user_messages else ""
            title = generateFallbackTitle(first_message=first_message)
            title_source = "fallback"
        
        # Update chat document
        new_updates_count = title_updates_count + 1
        update_doc = {
            "title": title,
            "title_source": title_source,
            "title_updates_count": new_updates_count,
            "title_last_updated_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        await db.chats.update_one(
            {"_id": chat_object_id, "user_id": user_id},
            {"$set": update_doc}
        )
        
        logger.info(f"Updated title for chat {chat_id[:8]}...: '{title}' (update #{new_updates_count})")
        return title
        
    except Exception as e:
        logger.error(f"Error updating title: {str(e)}", exc_info=True)
        return None

