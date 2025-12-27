"""
Utility functions for document processing and user management.
"""
import os
import re
import random
import string
from typing import Tuple, List, Dict, Optional
import httpx
import logging

logger = logging.getLogger(__name__)


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent path traversal and other security issues.
    - Extract only basename (remove path)
    - Remove path traversal sequences (.., /, \)
    - Remove special characters
    - Truncate if too long
    """
    if not filename:
        return "unnamed_file"
    
    # Extract basename only (remove any path)
    basename = os.path.basename(filename)
    
    # Remove path traversal sequences
    basename = basename.replace("..", "")
    basename = basename.replace("/", "_")
    basename = basename.replace("\\", "_")
    
    # Remove other dangerous characters but keep alphanumeric, dots, dashes, underscores
    basename = re.sub(r'[^a-zA-Z0-9._-]', '_', basename)
    
    # Remove leading/trailing dots and spaces
    basename = basename.strip('. ')
    
    # Truncate if too long (max 255 chars for filesystem compatibility)
    if len(basename) > 255:
        name, ext = os.path.splitext(basename)
        max_name_len = 255 - len(ext)
        basename = name[:max_name_len] + ext
    
    # If empty after sanitization, use default name
    if not basename or basename == "_":
        basename = "unnamed_file"
    
    return basename


def generate_username_from_email(base_username: str) -> str:
    """
    Generate a unique username from an email local-part.
    If the base username exists, append random alphanumeric suffix.
    
    Args:
        base_username: The base username (email local-part)
        
    Returns:
        A unique username (may have suffix appended)
    """
    # This will be used with database check in main.py
    # For now, just return base with suffix generation logic
    # Caller will check database for uniqueness
    return base_username


def append_random_suffix(base_username: str) -> str:
    """
    Append a random 4-character alphanumeric suffix to a username.
    """
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
    return f"{base_username}_{suffix}"


def validate_file_signature(file_content: bytes, expected_ext: str, mime_type: str) -> Tuple[bool, str]:
    """
    Validate file signature (magic bytes) to ensure file type matches extension/MIME.
    
    Returns: (is_valid, error_message)
    """
    if len(file_content) < 4:
        return False, "Dosya çok kısa, imza kontrol edilemiyor"
    
    # Read first 32 bytes for signature check
    header = file_content[:32]
    
    if expected_ext == ".pdf":
        # PDF signature: %PDF
        if not header.startswith(b"%PDF"):
            return False, "PDF imza kontrolü başarısız: Dosya gerçek bir PDF dosyası değil"
    
    elif expected_ext == ".docx":
        # DOCX is a ZIP container: starts with "PK" (ZIP signature)
        if not header.startswith(b"PK"):
            return False, "DOCX imza kontrolü başarısız: Dosya gerçek bir DOCX dosyası değil"
    
    elif expected_ext == ".txt":
        # TXT: Check for binary content (high null byte ratio)
        null_count = header.count(b"\x00")
        null_ratio = null_count / len(header) if len(header) > 0 else 0
        
        # If more than 1% null bytes, likely binary
        if null_ratio > 0.01:
            return False, "TXT imza kontrolü başarısız: Dosya binary içerik içeriyor, metin dosyası değil"
        
        # Check for other binary indicators
        # If file contains many non-printable characters, it's likely binary
        printable_count = sum(1 for b in header if 32 <= b <= 126 or b in [9, 10, 13])
        printable_ratio = printable_count / len(header) if len(header) > 0 else 0
        
        if printable_ratio < 0.7:  # Less than 70% printable = likely binary
            return False, "TXT imza kontrolü başarısız: Dosya binary içerik içeriyor"
    
    return True, ""


def estimate_tokens(text: str) -> int:
    """
    Estimate token count for text (simple approximation).
    Uses word count * 1.3 as approximation.
    
    Args:
        text: Input text
        
    Returns:
        Estimated token count
    """
    if not text:
        return 0
    word_count = len(text.split())
    return int(word_count * 1.3)


def validate_messages(messages: List[Dict[str, str]]) -> None:
    """
    Validate message list for LLM API call.
    Enforces message contract: role must be system|user|assistant, content must be non-empty string.
    
    Args:
        messages: List of message dicts with 'role' and 'content'
        
    Raises:
        ValueError: If validation fails
    """
    if not messages:
        raise ValueError("Messages list cannot be empty")
    
    valid_roles = {"system", "user", "assistant"}
    max_content_length = 100000  # 100K chars max per message
    
    for i, msg in enumerate(messages):
        if not isinstance(msg, dict):
            raise ValueError(f"Message {i} must be a dictionary")
        
        role = msg.get("role")
        if role not in valid_roles:
            raise ValueError(f"Message {i}: Invalid role '{role}'. Must be one of: {valid_roles}")
        
        content = msg.get("content")
        if not isinstance(content, str):
            raise ValueError(f"Message {i}: Content must be a string")
        
        if not content.strip():
            raise ValueError(f"Message {i}: Content cannot be empty")
        
        if len(content) > max_content_length:
            logger.warning(f"Message {i}: Content too long ({len(content)} chars), truncating to {max_content_length}")
            msg["content"] = content[:max_content_length]


def force_compact_math_output(text: str, is_math_question: bool = True) -> str:
    """
    ChatGPT-style output format guard.
    Forces LLM output into compact 2-line format by removing teacher-style templates.
    
    This is MORE POWERFUL than prompts - it catches model's subconscious template reflexes.
    
    Args:
        text: Raw LLM response text
        is_math_question: Whether this is a math question (apply strict formatting)
        
    Returns:
        Formatted text in compact 2-line format
    """
    if not text or not text.strip():
        return text
    
    # Only apply strict formatting for math questions
    if not is_math_question:
        return text.strip()
    
    original_text = text
    
    # STEP 1: Remove teacher-style headers (case-insensitive)
    # Remove common Turkish math template headers
    teacher_headers = [
        r'İfade\s*:',
        r'Sadeleştir\s*:',
        r'Birleştir\s*:',
        r'Sonuç\s*:',
        r'Üslü\s+sayı\s*:',
        r'Köklü\s+sayı\s*:',
        r'Adım\s+adım\s*:',
        r'Çözüm\s*:',
        r'Kısa\s+çözüm\s*:',
        r'\d+\.\s*',  # Numbered steps (1., 2., etc.)
        r'[-•]\s*',  # Bullet points
    ]
    
    for pattern in teacher_headers:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    
    # STEP 2: Extract all math blocks
    math_blocks = re.findall(r'\$\$[\s\S]*?\$\$', text)
    inline_math = re.findall(r'\$[^\$]+\$', text)
    
    # STEP 3: Merge multiple $$ blocks into single chain
    if len(math_blocks) > 1:
        # Extract content from each block (remove $$)
        block_contents = [b.replace('$$', '').strip() for b in math_blocks]
        
        # Try to create chain equality
        # If blocks contain =, they might be steps
        merged_content = ' = '.join(block_contents)
        
        # Replace all blocks with single merged block
        text = re.sub(r'\$\$[\s\S]*?\$\$', '', text)
        text = f"$$ {merged_content} $$" + text
        text = text.strip()
    
    # STEP 4: Extract final result if exists
    result_match = re.search(r'Sonuç\s*:\s*\$?([^\$]+)\$?', text, re.IGNORECASE)
    final_result = None
    
    if result_match:
        final_result = result_match.group(1).strip()
        # Remove "Sonuç:" line
        text = re.sub(r'Sonuç\s*:.*', '', text, flags=re.IGNORECASE)
    
    # STEP 5: Clean up - remove empty lines and extra whitespace
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    # STEP 6: Force 2-line format
    if len(lines) == 0:
        return original_text  # Fallback if everything was removed
    
    # Find the main math block (should be first or only $$ block)
    main_math_block = None
    for line in lines:
        if '$$' in line:
            main_math_block = line.strip()
            break
    
    # If no math block found, try to construct from inline math
    if not main_math_block and inline_math:
        # Combine inline math expressions
        combined = ' = '.join([m.replace('$', '').strip() for m in inline_math])
        main_math_block = f"$$ {combined} $$"
    
    # If still no math block, return cleaned original (might not be math)
    if not main_math_block:
        # Clean up but don't force format
        cleaned = '\n'.join(lines[:4])  # Max 4 lines
        return cleaned.strip()
    
    # STEP 7: Extract result from math block or use provided
    if not final_result:
        # Try to extract last part after = in math block
        math_content = main_math_block.replace('$$', '').strip()
        if '=' in math_content:
            parts = [p.strip() for p in math_content.split('=')]
            final_result = parts[-1] if parts else None
    
    # STEP 8: Build final 2-line format
    if final_result:
        # Ensure result is in LaTeX if it contains math
        if any(c in final_result for c in ['+', '-', '*', '/', '^', '√', '\\']):
            if not final_result.startswith('$'):
                final_result = f"${final_result}$"
        
        formatted = f"{main_math_block}\nSonuç: {final_result}"
    else:
        # Just the math block (1 line)
        formatted = main_math_block
    
    logger.debug(
        f"Output guard applied: original_lines={len(original_text.split('\n'))}, "
        f"formatted_lines={len(formatted.split('\n'))}, "
        f"removed_headers={len(teacher_headers)}"
    )
    
    return formatted.strip()


def compact_markdown_output(text: str) -> str:
    """
    Post-process answer to enforce readable Markdown.
    Removes accidental character-per-line patterns, collapses excessive newlines,
    breaks long math lines to prevent horizontal scrolling,
    and adds spacing for better frontend rendering.
    
    Args:
        text: Raw answer text
        
    Returns:
        Processed text with proper formatting and spacing
    """
    if not text or not text.strip():
        return text
    
    # Add spacing at the beginning to prevent buttons from overlapping
    # This helps frontend render buttons above the content properly
    if not text.startswith('\n'):
        text = '\n' + text
    
    # Remove character-per-line patterns (accidental waterfall)
    # Pattern: lines with single characters or very short lines (likely accidental)
    lines = text.split('\n')
    compacted_lines = []
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # Skip empty lines (will collapse later)
        if not stripped:
            continue
        
        # If line is very short (1-2 chars) and next line is also short, might be accidental
        # But preserve if it's part of math or special formatting
        if len(stripped) <= 2 and not any(c in stripped for c in ['$', '=', '+', '-', '*', '/', '^', '_', '\\']):
            # Check if this is part of a pattern
            if i + 1 < len(lines) and len(lines[i + 1].strip()) <= 2:
                # Likely accidental, skip this line
                continue
        
        compacted_lines.append(line)
    
    # Join lines
    text = '\n'.join(compacted_lines)
    
    # Don't break long lines - let them extend to the right
    # User wants long answers to extend horizontally (frontend will handle overflow)
    # We only remove character-per-line patterns, not break long math lines
    pass
    
    # Ensure "Adım" and "Sonuç" headers start at the beginning of line (no leading spaces)
    # Remove any leading whitespace before these headers
    lines = text.split('\n')
    processed_lines = []
    for line in lines:
        stripped = line.strip()
        # If line starts with "**Adım" or "**Sonuç", ensure it's at line start
        if stripped.startswith('**Adım') or stripped.startswith('**Sonuç'):
            processed_lines.append(stripped)  # No leading spaces
        else:
            processed_lines.append(line)  # Keep original formatting
    
    text = '\n'.join(processed_lines)
    
    # Add spacing between steps for better readability
    # Add space after "Adım" headers (but keep them at line start)
    text = re.sub(r'(^\*\*Adım \d+[^*]+\*\*)', r'\1\n', text, flags=re.MULTILINE)
    text = re.sub(r'(^\*\*Sonuç:\*\*)', r'\n\1', text, flags=re.MULTILINE)
    
    # Ensure spacing between math blocks and text
    # Add space before math blocks that come after text
    text = re.sub(r'([^\n])\n(\$\$)', r'\1\n\n\2', text)
    # Add space after math blocks that are followed by text
    text = re.sub(r'(\$\$[^\$]+\$\$)\n([^\n$])', r'\1\n\n\2', text)
    
    # Collapse excessive blank lines (max 2 consecutive, but preserve intentional spacing)
    text = re.sub(r'\n{4,}', '\n\n\n', text)
    
    # Ensure at least one blank line at the end for spacing
    if not text.endswith('\n\n'):
        if text.endswith('\n'):
            text += '\n'
        else:
            text += '\n\n'
    
    # Remove only leading whitespace (keep trailing for spacing)
    # But preserve line-start headers
    text = text.lstrip()
    
    return text


def validate_katex_output(text: str) -> Tuple[bool, Optional[str]]:
    """
    LAYER 3: Post-check validator (ChatGPT-style)
    Validate KaTeX output format. Checks for:
    1. Unicode math characters (should be in LaTeX)
    2. Unmatched $ delimiters
    3. Bare numbers/operators outside math blocks
    
    Args:
        text: Response text to validate
        
    Returns:
        (is_valid, error_message)
        is_valid: True if no format issues found
        error_message: Description of issues found, or None if valid
    """
    if not text:
        return True, None
    
    issues = []
    
    # CHECK 1: Unicode math characters (should be in LaTeX)
    unicode_math_patterns = [
        (r'√', 'Unicode square root (√) found - should use $\\sqrt{...}$'),
        (r'[⁰¹²³⁴⁵⁶⁷⁸⁹]', 'Unicode superscript found - should use $x^{n}$'),
        (r'[₀₁₂₃₄₅₆₇₈₉]', 'Unicode subscript found - should use $a_{n}$'),
        (r'×', 'Unicode multiplication (×) found - should use $\\cdot$ or $\\times$'),
        (r'÷', 'Unicode division (÷) found - should use $\\frac{a}{b}$'),
        (r'±', 'Unicode plus-minus (±) found - should use $\\pm$'),
    ]
    
    for pattern, description in unicode_math_patterns:
        if re.search(pattern, text):
            issues.append(description)
    
    # CHECK 2: $ delimiter balance
    # Count $ signs (excluding $$)
    # First, temporarily remove $$ blocks to avoid counting them
    temp_text = re.sub(r'\$\$[^\$]*\$\$', '', text)
    # Count remaining $ signs
    dollar_count = temp_text.count('$')
    if dollar_count % 2 != 0:
        issues.append(f'Unmatched $ delimiters (found {dollar_count}, should be even)')
    
    # CHECK 3: Check for bare math-like content outside LaTeX blocks
    # Look for patterns like: "5√2", "x²", "a₁" appearing in plain text
    # This is a heuristic check - remove all LaTeX blocks first, then check for math symbols
    
    # Remove all LaTeX blocks ($$...$$ and $...$)
    plain_text = re.sub(r'\$\$[^\$]*\$\$', '', text)
    plain_text = re.sub(r'\$[^\$\n]*\$', '', plain_text)
    
    # Check if plain text contains math-like patterns
    # Pattern: digit followed by space and digit (might be "5 2" from stripped "5√2")
    if re.search(r'\d+\s+\d+', plain_text):
        # This could be "5 2" from "5√2" → likely stripped unicode
        issues.append('Possible stripped math: found "number space number" pattern (like "5 2" from "5√2")')
    
    if issues:
        return False, "; ".join(issues)
    
    return True, None


async def call_llm(
    messages: List[Dict[str, str]],
    model: str,
    api_key: str,
    api_url: str,
    temperature: float = 0.7,
    max_tokens: int = 1000,
    timeout: float = 30.0
) -> str:
    """
    Call LLM API (OpenRouter) with validated messages.
    This function is extracted for testability.
    
    Args:
        messages: List of message dicts (validated)
        model: Model name
        api_key: API key
        api_url: API endpoint URL
        temperature: Temperature parameter
        max_tokens: Max tokens to generate
        timeout: Request timeout in seconds
        
    Returns:
        Generated response text
        
    Raises:
        httpx.HTTPStatusError: If API call fails
        httpx.TimeoutException: If request times out
        ValueError: If response is invalid
    """
    # Note: validate_messages should be called by the caller, not here
    # This allows callers to handle validation errors appropriately
    # validate_messages(messages)  # Removed - caller should validate
    
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            api_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost:3000",
                "X-Title": "AI Chat App",
            },
            json={
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )
        
        response.raise_for_status()
        data = response.json()
        
        if "choices" not in data or len(data["choices"]) == 0:
            raise ValueError("Invalid response from LLM API: no choices found")
        
        # Get message from first choice
        message = data["choices"][0].get("message")
        if not message:
            raise ValueError("Invalid response from LLM API: no message found")
        
        # Get content from message
        content = message.get("content")
        
        # Check if content is None or empty
        if content is None:
            raise ValueError("LLM API returned None content")
        
        if not isinstance(content, str):
            raise ValueError(f"LLM API returned invalid content type: {type(content)}")
        
        if not content.strip():
            raise ValueError("LLM API returned empty response")
        
        return content

