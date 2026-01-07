"""
LGS-Specific RAG Module.
Isolated RAG for LGS educational materials.
"""
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime

from app.database import get_database
from app.extensions.vector_store.base import get_vector_store
from app.rag.embedder import embed_text

logger = logging.getLogger(__name__)

# LGS-specific ChromaDB collection name
LGS_COLLECTION_NAME = "lgs_materials"


async def index_lgs_resource(
    user_id: str,
    document_id: str,
    filename: str,
    text_content: str,
    resource_type: str = "ders_notu",
    topic: str = "karekok",
    difficulty: str = "medium",
    year: Optional[int] = None
) -> bool:
    """
    Index an LGS educational resource.
    
    Args:
        user_id: User ID
        document_id: Document ID
        filename: Original filename
        text_content: Document text content
        resource_type: "ders_notu" | "cikmas_soru" | "test" | "cozum"
        topic: Math topic (default: "karekok")
        difficulty: "easy" | "medium" | "hard"
        year: LGS year if applicable
        
    Returns:
        True if successful
    """
    try:
        db = get_database()
        if db is None:
            return False
        
        # Store in lgs_resources collection
        resource_doc = {
            "user_id": user_id,
            "document_id": document_id,
            "filename": filename,
            "resource_type": resource_type,
            "topic": topic,
            "difficulty": difficulty,
            "year": year,
            "text_content": text_content,
            "indexed_at": datetime.utcnow()
        }
        
        await db.lgs_resources.update_one(
            {"user_id": user_id, "document_id": document_id},
            {"$set": resource_doc},
            upsert=True
        )
        
        # Chunk and embed for vector search
        chunks = _chunk_text(text_content)
        
        vector_store = get_vector_store()
        if vector_store:
            for i, chunk in enumerate(chunks):
                embedding = await embed_text(chunk)
                if embedding:
                    metadata = {
                        "user_id": user_id,
                        "document_id": document_id,
                        "resource_type": resource_type,
                        "topic": topic,
                        "difficulty": difficulty,
                        "chunk_index": i,
                        "collection": LGS_COLLECTION_NAME
                    }
                    
                    # Note: This uses the main vector store but with LGS-specific metadata
                    # In production, could use a separate collection
                    vector_store.add_documents(
                        ids=[f"lgs_{document_id}_{i}"],
                        documents=[chunk],
                        embeddings=[embedding],
                        metadatas=[metadata]
                    )
        
        logger.info(f"LGS RAG: Indexed resource {filename} with {len(chunks)} chunks")
        return True
        
    except Exception as e:
        logger.error(f"LGS RAG: Error indexing resource: {str(e)}", exc_info=True)
        return False


async def query_lgs_context(
    user_id: str,
    query: str,
    strategy: str = "direct_solve",
    difficulty: Optional[str] = None,
    resource_type: Optional[str] = None,
    top_k: int = 3
) -> List[Dict[str, Any]]:
    """
    Query LGS-specific context based on strategy.
    
    Args:
        user_id: User ID
        query: Search query
        strategy: Current teaching strategy
        difficulty: Filter by difficulty
        resource_type: Filter by resource type
        top_k: Number of results
        
    Returns:
        List of relevant chunks with metadata
    """
    try:
        # Determine filter based on strategy
        filter_params = {"user_id": user_id, "collection": LGS_COLLECTION_NAME}
        
        if strategy == "simplified_explanation":
            filter_params["resource_type"] = "ders_notu"
        elif strategy == "similar_easier":
            filter_params["resource_type"] = {"$in": ["test", "cikmas_soru"]}
            filter_params["difficulty"] = "easy" if difficulty != "easy" else "medium"
        
        if resource_type:
            filter_params["resource_type"] = resource_type
        if difficulty:
            filter_params["difficulty"] = difficulty
        
        # Get embedding for query
        query_embedding = await embed_text(query)
        if not query_embedding:
            return []
        
        vector_store = get_vector_store()
        if not vector_store:
            return []
        
        # Query with LGS-specific filters
        results = vector_store.search(
            query_embedding=query_embedding,
            top_k=top_k,
            filters=filter_params
        )
        
        return results
        
    except Exception as e:
        logger.error(f"LGS RAG: Error querying context: {str(e)}", exc_info=True)
        return []


async def get_similar_problems(
    user_id: str,
    current_problem: str,
    difficulty: str = "medium",
    exclude_ids: Optional[List[str]] = None,
    top_k: int = 3
) -> List[Dict[str, Any]]:
    """
    Get similar problems from LGS resources.
    
    Args:
        user_id: User ID
        current_problem: Current problem text
        difficulty: Desired difficulty
        exclude_ids: Document IDs to exclude
        top_k: Number of results
        
    Returns:
        List of similar problems
    """
    try:
        db = get_database()
        if db is None:
            return []
        
        # Query from lgs_resources with text search
        query = {
            "user_id": user_id,
            "resource_type": {"$in": ["test", "cikmas_soru"]},
            "difficulty": difficulty
        }
        
        if exclude_ids:
            query["document_id"] = {"$nin": exclude_ids}
        
        cursor = db.lgs_resources.find(query).limit(top_k)
        results = await cursor.to_list(length=top_k)
        
        return results
        
    except Exception as e:
        logger.error(f"LGS RAG: Error getting similar problems: {str(e)}", exc_info=True)
        return []


def _chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    """Split text into overlapping chunks."""
    if not text:
        return []
    
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        
        # Try to break at sentence boundary
        if end < len(text):
            last_period = chunk.rfind('.')
            if last_period > chunk_size // 2:
                chunk = chunk[:last_period + 1]
                end = start + last_period + 1
        
        chunks.append(chunk.strip())
        start = end - overlap
    
    return [c for c in chunks if c]


# ============================================================
# JSON-Based Kareköklü İfadeler RAG (Isolated)
# Source: lgs_karekök_rag.json
# ============================================================

import json
import os
import re
from pathlib import Path

# Singleton cache for JSON questions
_karekök_questions_cache: Optional[List[Dict[str, Any]]] = None
_karekök_questions_loaded: bool = False

# Trigger patterns for question requests
QUESTION_REQUEST_PATTERNS = {
    "ornek": [
        r"\börnek\s*çöz",
        r"\börnek\s*sor",
        r"\börnek\s*ver",
        r"\börnek\s*göster",
        r"\börnek\s+soru",
    ],
    "benzer": [
        r"\bbenzer\s*soru",
        r"\bbenzer\s*örnek",
        r"\bbenzeri",
    ],
    "cikmis": [
        r"\bçıkmış\s*soru",
        r"\bçıkmışlara\s*benzer",
        r"\bgerçek\s*sınav",
        r"\blgs\s*sorusu",
    ],
    "kazanim": [
        r"\bbu\s*kazanımdan",
        r"\bkazanımla\s*ilgili",
        r"\bkazanım\s*sorusu",
    ],
}


def load_karekök_questions() -> List[Dict[str, Any]]:
    """
    Load questions from lgs_karekök_rag.json.
    Uses singleton pattern - loads only once.
    
    Returns:
        List of question dictionaries, or empty list on error.
    """
    global _karekök_questions_cache, _karekök_questions_loaded
    
    # Return cached if already loaded
    if _karekök_questions_loaded:
        return _karekök_questions_cache or []
    
    _karekök_questions_loaded = True
    
    try:
        # Find the JSON file relative to project root
        # Backend is at: C:\Users\msg\bitirme\backend
        # JSON is at: C:\Users\msg\bitirme\lgs_karekök_rag.json
        current_dir = Path(__file__).resolve().parent  # app/lgs
        project_root = current_dir.parent.parent.parent  # bitirme
        json_path = project_root / "lgs_karekök_rag.json"
        
        if not json_path.exists():
            logger.warning(f"LGS RAG: JSON file not found at {json_path}")
            _karekök_questions_cache = []
            return []
        
        with open(json_path, "r", encoding="utf-8") as f:
            questions = json.load(f)
        
        if not isinstance(questions, list):
            logger.warning("LGS RAG: JSON file is not a list")
            _karekök_questions_cache = []
            return []
        
        _karekök_questions_cache = questions
        logger.info(f"LGS RAG: Loaded {len(questions)} questions from JSON")
        return questions
        
    except Exception as e:
        logger.error(f"LGS RAG: Error loading JSON: {str(e)}")
        _karekök_questions_cache = []
        return []


def search_karekök_questions(
    query: str,
    zorluk: Optional[str] = None,
    alt_konu: Optional[str] = None,
    etiketler: Optional[List[str]] = None,
    top_k: int = 3
) -> List[Dict[str, Any]]:
    """
    Search questions from the JSON database.
    
    Args:
        query: Search query (searched in soru.metin, siklar, etiketler)
        zorluk: Filter by difficulty ("kolay", "orta", "zor")
        alt_konu: Filter by sub-topic
        etiketler: Filter by tags (any match)
        top_k: Maximum results to return
        
    Returns:
        List of matching questions with metadata.
    """
    questions = load_karekök_questions()
    if not questions:
        return []
    
    results = []
    query_lower = query.lower()
    query_terms = query_lower.split()
    
    for q in questions:
        # Apply filters first
        if zorluk and q.get("zorluk") != zorluk:
            continue
        if alt_konu and alt_konu.lower() not in q.get("alt_konu", "").lower():
            continue
        if etiketler:
            q_tags = [t.lower() for t in q.get("etiketler", [])]
            if not any(tag.lower() in q_tags for tag in etiketler):
                continue
        
        # Calculate relevance score
        score = 0
        soru = q.get("soru", {})
        metin = soru.get("metin", "").lower()
        siklar = soru.get("siklar", {})
        q_etiketler = [t.lower() for t in q.get("etiketler", [])]
        
        # Build searchable text
        searchable = metin + " " + " ".join(siklar.values()) + " " + " ".join(q_etiketler)
        searchable = searchable.lower()
        
        # Score based on query term matches
        for term in query_terms:
            if term in searchable:
                score += 1
            # Boost for tag matches
            if term in q_etiketler:
                score += 2
        
        if score > 0:
            results.append({
                "question": q,
                "score": score
            })
    
    # Sort by score descending
    results.sort(key=lambda x: x["score"], reverse=True)
    
    # Return top_k results
    return [r["question"] for r in results[:top_k]]


def detect_question_request(user_message: str) -> Dict[str, Any]:
    """
    Detect if user is requesting an example question.
    
    Args:
        user_message: User's message
        
    Returns:
        {
            "triggered": bool,
            "type": "ornek" | "benzer" | "cikmis" | "kazanim" | None,
            "zorluk": "kolay" | "orta" | "zor" | None
        }
    """
    if not user_message:
        return {"triggered": False, "type": None, "zorluk": None}
    
    message_lower = user_message.lower()
    
    # Detect request type
    detected_type = None
    for req_type, patterns in QUESTION_REQUEST_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, message_lower):
                detected_type = req_type
                break
        if detected_type:
            break
    
    # Detect difficulty
    zorluk = None
    if "kolay" in message_lower or "basit" in message_lower:
        zorluk = "kolay"
    elif "zor" in message_lower or "zorlu" in message_lower:
        zorluk = "zor"
    elif "orta" in message_lower:
        zorluk = "orta"
    
    return {
        "triggered": detected_type is not None,
        "type": detected_type,
        "zorluk": zorluk
    }


def extract_topic_keywords(user_message: str) -> List[str]:
    """
    Extract topic-related keywords from user message.
    
    Args:
        user_message: User's message
        
    Returns:
        List of detected keywords
    """
    keywords = []
    message_lower = user_message.lower()
    
    # Topic keywords
    topic_patterns = [
        ("tam kare", ["tam kare", "tamkare"]),
        ("karekök", ["karekök", "karekok", "kök"]),
        ("alan", ["alan"]),
        ("çevre", ["çevre", "cevre"]),
        ("sadeleştirme", ["sadeleştir", "sadelestir"]),
        ("toplama", ["toplama", "topla"]),
        ("çıkarma", ["çıkarma", "cikarma"]),
        ("çarpma", ["çarpma", "carpma", "çarpım"]),
        ("bölme", ["bölme", "bolme"]),
        ("tahmin", ["tahmin", "arasında"]),
        ("irrasyonel", ["irrasyonel", "rasyonel"]),
        ("eşlenik", ["eşlenik", "eslenik"]),
        ("paydada", ["payda"]),
    ]
    
    for keyword, patterns in topic_patterns:
        for pattern in patterns:
            if pattern in message_lower:
                keywords.append(keyword)
                break
    
    return keywords


# Singleton cache for SYNTHETIC questions (separate from real)
_synthetic_questions_cache: Optional[List[Dict[str, Any]]] = None
_synthetic_questions_loaded: bool = False


def load_synthetic_questions() -> List[Dict[str, Any]]:
    """
    Load questions from lgs_karekök_synthetic.json.
    Uses singleton pattern - loads only once.
    SEPARATE from real questions to maintain data integrity.
    
    Returns:
        List of synthetic question dictionaries, or empty list on error.
    """
    global _synthetic_questions_cache, _synthetic_questions_loaded
    
    # Return cached if already loaded
    if _synthetic_questions_loaded:
        return _synthetic_questions_cache or []
    
    _synthetic_questions_loaded = True
    
    try:
        current_dir = Path(__file__).resolve().parent  # app/lgs
        project_root = current_dir.parent.parent.parent  # bitirme
        json_path = project_root / "lgs_karekök_synthetic.json"
        
        if not json_path.exists():
            logger.info(f"LGS RAG: Synthetic JSON not found at {json_path} (this is OK)")
            _synthetic_questions_cache = []
            return []
        
        with open(json_path, "r", encoding="utf-8") as f:
            questions = json.load(f)
        
        if not isinstance(questions, list):
            logger.warning("LGS RAG: Synthetic JSON is not a list")
            _synthetic_questions_cache = []
            return []
        
        # Validate all have sentetik: true
        valid_questions = [q for q in questions if q.get("sentetik") == True]
        if len(valid_questions) != len(questions):
            logger.warning(f"LGS RAG: {len(questions) - len(valid_questions)} synthetic questions missing 'sentetik: true'")
        
        _synthetic_questions_cache = valid_questions
        logger.info(f"LGS RAG: Loaded {len(valid_questions)} synthetic questions from JSON")
        return valid_questions
        
    except Exception as e:
        logger.error(f"LGS RAG: Error loading synthetic JSON: {str(e)}")
        _synthetic_questions_cache = []
        return []


def search_synthetic_questions(
    query: str,
    zorluk: Optional[str] = None,
    alt_konu: Optional[str] = None,
    etiketler: Optional[List[str]] = None,
    top_k: int = 3
) -> List[Dict[str, Any]]:
    """
    Search SYNTHETIC questions from the JSON database.
    Same logic as search_karekök_questions but for synthetic data.
    """
    questions = load_synthetic_questions()
    if not questions:
        return []
    
    results = []
    query_lower = query.lower()
    query_terms = query_lower.split()
    
    for q in questions:
        # Apply filters first
        if zorluk and q.get("zorluk") != zorluk:
            continue
        if alt_konu and alt_konu.lower() not in q.get("alt_konu", "").lower():
            continue
        if etiketler:
            q_tags = [t.lower() for t in q.get("etiketler", [])]
            if not any(tag.lower() in q_tags for tag in etiketler):
                continue
        
        # Calculate relevance score
        score = 0
        soru = q.get("soru", {})
        metin = soru.get("metin", "").lower()
        siklar = soru.get("siklar", {})
        q_etiketler = [t.lower() for t in q.get("etiketler", [])]
        
        searchable = metin + " " + " ".join(siklar.values()) + " " + " ".join(q_etiketler)
        searchable = searchable.lower()
        
        for term in query_terms:
            if term in searchable:
                score += 1
            if term in q_etiketler:
                score += 2
        
        if score > 0:
            results.append({
                "question": q,
                "score": score
            })
    
    results.sort(key=lambda x: x["score"], reverse=True)
    return [r["question"] for r in results[:top_k]]


def get_question_context(
    user_message: str,
    chat_context: Optional[str] = None
) -> Optional[str]:
    """
    Main orchestration function for JSON-based RAG.
    Detects triggers, searches questions, formats context.
    
    RETRIEVAL PRIORITY:
    1. Real questions (MEB) - lgs_karekök_rag.json
    2. Synthetic questions - lgs_karekök_synthetic.json
    3. LLM fallback (returns None)
    
    Args:
        user_message: User's current message
        chat_context: Optional previous chat context
        
    Returns:
        Formatted context string for LLM, or None if no relevant questions found.
    """
    # Step 1: Detect if this is a question request
    detection = detect_question_request(user_message)
    
    # Extract keywords for search regardless of trigger
    keywords = extract_topic_keywords(user_message)
    
    # If not triggered and no keywords, return None
    if not detection["triggered"] and not keywords:
        return None
    
    # Step 2: Build search query
    search_query = user_message
    if keywords:
        search_query = " ".join(keywords) + " " + user_message
    
    # Step 3: PRIORITY-BASED RETRIEVAL
    # First: Real MEB questions
    real_results = search_karekök_questions(
        query=search_query,
        zorluk=detection.get("zorluk"),
        top_k=3
    )
    
    # Second: Synthetic questions (only if real < 3)
    synthetic_results = []
    if len(real_results) < 3:
        synthetic_results = search_synthetic_questions(
            query=search_query,
            zorluk=detection.get("zorluk"),
            top_k=3 - len(real_results)
        )
    
    # Combine results
    all_results = []
    for q in real_results:
        q["_source"] = "MEB"
        all_results.append(q)
    for q in synthetic_results:
        q["_source"] = "SENTETIK"
        all_results.append(q)
    
    if not all_results:
        logger.info("LGS RAG: No matching questions found in JSON (real or synthetic)")
        return None
    
    # Step 4: Format context with source labels
    context_parts = []
    context_parts.append("=" * 40)
    context_parts.append("MEB SORU BANKASI - REFERANS SORULAR")
    context_parts.append("(Bu sorular REFERANS içindir. Kopyalama, yeniden anlat.)")
    context_parts.append("=" * 40)
    
    for i, q in enumerate(all_results, 1):
        soru = q.get("soru", {})
        siklar = soru.get("siklar", {})
        source = q.get("_source", "MEB")
        
        # Source label
        if source == "SENTETIK":
            source_label = "🔄 SENTETİK VARYASYON"
        else:
            source_label = "📚 MEB KAYNAK"
        
        context_parts.append(f"\n{source_label}")
        context_parts.append(f"📌 REFERANS SORU {i} [{q.get('id', 'N/A')}]")
        context_parts.append(f"Alt Konu: {q.get('alt_konu', 'N/A')}")
        context_parts.append(f"Zorluk: {q.get('zorluk', 'N/A')}")
        context_parts.append(f"Etiketler: {', '.join(q.get('etiketler', []))}")
        context_parts.append(f"\nSoru: {soru.get('metin', 'N/A')}")
        
        if siklar:
            context_parts.append("Şıklar:")
            for key, val in siklar.items():
                context_parts.append(f"  {key}) {val}")
        
        context_parts.append(f"\n✓ DOĞRU CEVAP: {q.get('dogru_cevap', 'N/A')}")
        
        # Show referans_id for synthetic
        if source == "SENTETIK" and q.get("referans_id"):
            context_parts.append(f"Referans: {q.get('referans_id')}")
        
        context_parts.append("-" * 30)
    
    # Summary
    real_count = sum(1 for q in all_results if q.get("_source") == "MEB")
    synthetic_count = sum(1 for q in all_results if q.get("_source") == "SENTETIK")
    
    context_parts.append("\n" + "=" * 40)
    context_parts.append(f"KAYNAK: {real_count} MEB + {synthetic_count} Sentetik")
    context_parts.append("ÖNEMLİ:")
    context_parts.append("- Soruları BİREBİR kopyalama")
    context_parts.append("- Pedagojik olarak yeniden anlat")
    context_parts.append("- Çözümü MEB tarzında yap")
    context_parts.append("- Doğru cevabı yukarıdaki bilgiyle doğrula")
    if synthetic_count > 0:
        context_parts.append("- Sentetik sorular gerçek MEB sorularından türetilmiştir")
    context_parts.append("=" * 40)
    
    logger.info(f"LGS RAG: Retrieved {real_count} real + {synthetic_count} synthetic questions")
    return "\n".join(context_parts)


