"""
Advanced text chunking for RAG indexing.
Supports adaptive chunking, semantic boundaries, and metadata tracking.
Includes whitespace normalization and deduplication.
"""
from typing import List, Dict, Optional, Tuple
import re
import logging
import hashlib

from app.rag.config import chunking_config

logger = logging.getLogger(__name__)


def _detect_semantic_boundaries(text: str) -> List[int]:
    """
    Detect semantic boundaries in text (markdown headers, paragraph breaks, etc.).
    Returns list of character positions where boundaries occur.
    """
    boundaries = []
    
    # Markdown headers (#, ##, ###)
    for match in re.finditer(r'^#{1,6}\s+.+$', text, re.MULTILINE):
        boundaries.append(match.start())
    
    # Double newlines (paragraph breaks)
    for match in re.finditer(r'\n\n+', text):
        boundaries.append(match.start())
    
    # Numbered/bulleted lists
    for match in re.finditer(r'^\s*[-*•]\s+', text, re.MULTILINE):
        boundaries.append(match.start())
    
    # Ordered lists
    for match in re.finditer(r'^\s*\d+[.)]\s+', text, re.MULTILINE):
        boundaries.append(match.start())
    
    return sorted(set(boundaries))


def _find_nearest_boundary(position: int, boundaries: List[int], search_range: int = 50) -> Optional[int]:
    """Find nearest semantic boundary within search_range of position."""
    if not boundaries:
        return None
    
    for boundary in boundaries:
        if abs(boundary - position) <= search_range:
            return boundary
    
    return None


def _detect_text_type(text: str) -> str:
    """
    Detect text type: table, list, paragraph, heading, etc.
    """
    # Check for table-like structure (multiple | characters)
    if text.count('|') >= 3:
        return "table"
    
    # Check for list
    if re.search(r'^\s*[-*•]\s+', text, re.MULTILINE) or re.search(r'^\s*\d+[.)]\s+', text, re.MULTILINE):
        return "list"
    
    # Check for heading
    if re.match(r'^#{1,6}\s+', text.strip()):
        return "heading"
    
    return "paragraph"


def chunk_text(
    text: str,
    chunk_words: Optional[int] = None,
    overlap_words: Optional[int] = None,
    document_id: Optional[str] = None,
    mime_type: Optional[str] = None
) -> List[dict]:
    """
    Split text into chunks with adaptive sizing and semantic boundary awareness.
    
    Args:
        text: Input text to chunk
        chunk_words: Target number of words per chunk (uses config default if None)
        overlap_words: Number of words to overlap between chunks (uses config default if None)
        document_id: Document ID for metadata
        mime_type: MIME type for adaptive chunking
        
    Returns:
        List of chunk dictionaries with:
        - text: chunk text
        - chunk_index: 0-based index
        - word_count: number of words in chunk
        - token_count: estimated token count
        - text_type: detected text type (table, list, paragraph, heading)
        - section_number: section/page number if detected
        - document_id: document ID
    """
    if not text or not text.strip():
        return []
    
    # Normalize whitespace: collapse excessive newlines, preserve paragraph breaks
    # This prevents weird newline tokens that cause UI waterfall
    text = re.sub(r'\n{3,}', '\n\n', text)  # Max 2 consecutive newlines
    text = re.sub(r'[ \t]+', ' ', text)  # Collapse multiple spaces/tabs
    text = text.strip()
    
    # Use config defaults if not provided
    target_chunk_words = chunk_words or chunking_config.default_chunk_words
    target_overlap_words = overlap_words or chunking_config.default_overlap_words
    
    # Detect semantic boundaries if enabled
    boundaries = []
    if chunking_config.enable_semantic_boundaries:
        boundaries = _detect_semantic_boundaries(text)
        logger.debug(f"Detected {len(boundaries)} semantic boundaries")
    
    # Split text into words
    words = text.split()
    
    if len(words) == 0:
        return []
    
    chunks = []
    chunk_index = 0
    i = 0
    
    while i < len(words):
        # Calculate end position for this chunk
        end = min(i + target_chunk_words, len(words))
        
        # If adaptive chunking is enabled, try to adjust boundaries
        if chunking_config.enable_adaptive and boundaries:
            # Find character position of current word
            char_pos = len(" ".join(words[:i]))
            nearest_boundary = _find_nearest_boundary(char_pos, boundaries, search_range=200)
            
            if nearest_boundary:
                # Adjust chunk to start/end at boundary
                # This is approximate - we'd need character-level tracking for exact match
                pass  # Simplified for now
        
        # Extract words for this chunk
        chunk_words_list = words[i:end]
        chunk_text_content = " ".join(chunk_words_list)
        
        # Skip empty chunks
        if not chunk_text_content.strip():
            i = end
            continue
        
        # Detect text type
        text_type = _detect_text_type(chunk_text_content)
        
        # Adaptive sizing: merge very short chunks with next chunk
        if chunking_config.enable_adaptive:
            word_count = len(chunk_words_list)
            if word_count < chunking_config.min_chunk_words and i + target_chunk_words < len(words):
                # Try to extend chunk
                extend_end = min(i + chunking_config.max_chunk_words, len(words))
                extended_words = words[i:extend_end]
                extended_text = " ".join(extended_words)
                
                # Only extend if it doesn't break semantic boundaries too much
                if len(extended_words) <= chunking_config.max_chunk_words:
                    chunk_words_list = extended_words
                    chunk_text_content = extended_text
                    end = extend_end
        
        # Split very long chunks
        if len(chunk_words_list) > chunking_config.max_chunk_words:
            # Split at sentence boundary if possible
            sentences = re.split(r'[.!?]\s+', chunk_text_content)
            if len(sentences) > 1:
                # Split into multiple chunks
                current_sentence = ""
                for sentence in sentences:
                    sentence_words = len(sentence.split())
                    if len(current_sentence.split()) + sentence_words > chunking_config.max_chunk_words:
                        if current_sentence.strip():
                            chunks.append({
                                "text": current_sentence.strip(),
                                "chunk_index": chunk_index,
                                "word_count": len(current_sentence.split()),
                                "token_count": int(len(current_sentence.split()) * 1.3),
                                "text_type": _detect_text_type(current_sentence),
                                "document_id": document_id
                            })
                            chunk_index += 1
                        current_sentence = sentence
                    else:
                        current_sentence += " " + sentence if current_sentence else sentence
                
                if current_sentence.strip():
                    chunk_text_content = current_sentence.strip()
                    chunk_words_list = current_sentence.split()
            else:
                # Force split at word boundary
                chunk_words_list = chunk_words_list[:chunking_config.max_chunk_words]
                chunk_text_content = " ".join(chunk_words_list)
        
        # Create chunk with metadata
        # Add dedup hash to prevent repeated embeddings
        chunk_hash = hashlib.sha256(chunk_text_content.encode('utf-8')).hexdigest()[:16]
        
        chunks.append({
            "text": chunk_text_content,
            "chunk_index": chunk_index,
            "word_count": len(chunk_words_list),
            "token_count": int(len(chunk_words_list) * 1.3),
            "text_type": text_type,
            "document_id": document_id,
            "section_number": None,  # Could be enhanced with PDF page numbers
            "dedup_hash": chunk_hash,  # For deduplication
            "char_range": (i, end)  # Character range in original text (approximate)
        })
        chunk_index += 1
        
        # Move to next chunk with overlap
        if end >= len(words):
            break
        
        # Move back by overlap_words to create overlap
        i = end - target_overlap_words
        
        # Ensure we don't go backwards
        if i <= (chunk_index - 1) * (target_chunk_words - target_overlap_words):
            i = (chunk_index - 1) * (target_chunk_words - target_overlap_words) + target_chunk_words - target_overlap_words
    
    # Post-process: merge very short chunks with adjacent chunks
    if chunking_config.enable_adaptive and len(chunks) > 1:
        merged_chunks = []
        i = 0
        while i < len(chunks):
            current_chunk = chunks[i]
            
            # If chunk is too short, try to merge with next
            if current_chunk["word_count"] < chunking_config.min_chunk_words and i + 1 < len(chunks):
                next_chunk = chunks[i + 1]
                combined_words = current_chunk["word_count"] + next_chunk["word_count"]
                
                if combined_words <= chunking_config.max_chunk_words:
                    # Merge chunks
                    merged_text = current_chunk["text"] + " " + next_chunk["text"]
                    merged_chunks.append({
                        "text": merged_text,
                        "chunk_index": len(merged_chunks),
                        "word_count": combined_words,
                        "token_count": int(combined_words * 1.3),
                        "text_type": current_chunk.get("text_type", "paragraph"),
                        "document_id": document_id,
                        "section_number": None
                    })
                    i += 2  # Skip next chunk as it's merged
                    continue
            
            # Keep chunk as-is
            current_chunk["chunk_index"] = len(merged_chunks)
            merged_chunks.append(current_chunk)
            i += 1
        
        chunks = merged_chunks
    
    logger.info(
        f"Chunked text: total_chunks={len(chunks)}, "
        f"avg_words={sum(c['word_count'] for c in chunks) / len(chunks) if chunks else 0:.1f}, "
        f"text_types={dict((t, sum(1 for c in chunks if c.get('text_type') == t)) for t in ['table', 'list', 'paragraph', 'heading'])}"
    )
    
    return chunks


def generate_chunk_id(document_id: str, chunk_index: int) -> str:
    """
    Generate deterministic chunk ID.
    
    Args:
        document_id: MongoDB document ID
        chunk_index: 0-based chunk index
        
    Returns:
        Deterministic chunk ID string
    """
    return f"{document_id}_chunk_{chunk_index}"

