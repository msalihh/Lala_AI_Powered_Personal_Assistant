"""
Google AI Studio API integration functions.
"""
import httpx
import json
import asyncio
import random
from typing import List, Dict, Optional, Callable
import logging

logger = logging.getLogger(__name__)


async def call_google_ai(
    messages: List[Dict[str, str]],
    model: str,
    api_key: str,
    temperature: float = 0.7,
    max_tokens: int = 1000,
    timeout: float = 60.0,
    retries: int = 3
) -> str:
    """
    Call Google AI Studio API (Gemini models) with retry logic.
    
    Args:
        messages: List of message dicts with 'role' and 'content'
        model: Model name (e.g., 'gemini-2.0-flash-exp', 'gemini-1.5-pro')
        api_key: Google AI API key
        temperature: Temperature for generation
        max_tokens: Maximum tokens to generate
        timeout: Request timeout
        retries: Number of retries on failure
    
    Returns:
        Generated text content
    """
    # Convert OpenAI-style messages to Google AI format
    contents = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        
        # Google AI uses 'user' and 'model' roles
        if role == "assistant":
            role = "model"
        elif role == "system":
            # System messages are prepended to first user message
            if contents and contents[0].get("role") == "user":
                contents[0]["parts"][0]["text"] = f"{content}\n\n{contents[0]['parts'][0]['text']}"
            else:
                contents.insert(0, {
                    "role": "user",
                    "parts": [{"text": content}]
                })
            continue
        
        contents.append({
            "role": role,
            "parts": [{"text": content}]
        })
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    
    payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        }
    }
    
    last_error = None
    
    for attempt in range(retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, json=payload)
                
                if response.status_code == 429:
                    error_msg = f"Google AI API 429 (Attempt {attempt + 1}/{retries + 1})"
                    logger.warning(error_msg)
                    
                    if attempt < retries:
                        wait_time = (2 ** attempt) + (random.random() * 2)
                        logger.info(f"Retrying in {wait_time:.2f}s...")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger.error("Google AI API 429 Persistent.")
                
                response.raise_for_status()
                data = response.json()
                
                # Extract text from Google AI response
                if "candidates" in data and len(data["candidates"]) > 0:
                    candidate = data["candidates"][0]
                    if "content" in candidate and "parts" in candidate["content"]:
                        parts = candidate["content"]["parts"]
                        if len(parts) > 0 and "text" in parts[0]:
                            return parts[0]["text"]
                
                raise ValueError("Invalid response from Google AI API: no text found")
                
        except httpx.HTTPStatusError as e:
            last_error = e
            logger.error(f"Google AI HTTP Error: {e}")
            if attempt < retries:
                await asyncio.sleep(2)
                continue
            raise e
        except Exception as e:
            last_error = e
            logger.warning(f"Google AI Error: {e}")
            if attempt < retries:
                await asyncio.sleep(1)
                continue
            raise e
    
    if last_error:
        raise last_error
    raise ValueError("Google AI call failed after retries")


async def call_google_ai_streaming(
    messages: List[Dict[str, str]],
    model: str,
    api_key: str,
    temperature: float = 0.7,
    max_tokens: int = 1000,
    timeout: float = 120.0,
    on_chunk: Optional[Callable[[str], bool]] = None,
    on_chunk_async: Optional[Callable[[str], any]] = None,
    check_cancelled: Optional[Callable[[], bool]] = None,
    retries: int = 3
) -> str:
    """
    Call Google AI Studio API with streaming support.
    
    Args:
        messages: List of message dicts
        model: Model name
        api_key: Google AI API key
        temperature: Temperature
        max_tokens: Max tokens
        timeout: Timeout
        on_chunk: Sync callback for each chunk
        on_chunk_async: Async callback for each chunk
        check_cancelled: Function to check if cancelled
        retries: Number of retries
    
    Returns:
        Full accumulated text
    """
    import random
    
    # Convert messages to Google AI format
    contents = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        
        if role == "assistant":
            role = "model"
        elif role == "system":
            if contents and contents[0].get("role") == "user":
                contents[0]["parts"][0]["text"] = f"{content}\n\n{contents[0]['parts'][0]['text']}"
            else:
                contents.insert(0, {
                    "role": "user",
                    "parts": [{"text": content}]
                })
            continue
        
        contents.append({
            "role": role,
            "parts": [{"text": content}]
        })
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?key={api_key}&alt=sse"
    
    payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        }
    }
    
    last_error = None
    
    for attempt in range(retries + 1):
        accumulated_text = ""
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("POST", url, json=payload) as response:
                    if response.status_code == 429:
                        error_msg = f"Google AI Streaming 429 (Attempt {attempt + 1}/{retries + 1})"
                        logger.warning(error_msg)
                        
                        if attempt < retries:
                            wait_time = (2 ** attempt) + (random.random() * 2)
                            logger.info(f"Retrying stream in {wait_time:.2f}s...")
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            logger.error("Google AI Streaming 429 Persistent.")
                    
                    response.raise_for_status()
                    
                    async for line in response.aiter_lines():
                        if check_cancelled and check_cancelled():
                            raise RuntimeError("Streaming cancelled by user")
                        
                        if not line.strip():
                            continue
                        
                        # Google AI uses SSE format: "data: {...}"
                        if line.startswith("data: "):
                            data_str = line[6:]
                            
                            try:
                                data = json.loads(data_str)
                                
                                # Extract text from streaming response
                                if "candidates" in data and len(data["candidates"]) > 0:
                                    candidate = data["candidates"][0]
                                    if "content" in candidate and "parts" in candidate["content"]:
                                        parts = candidate["content"]["parts"]
                                        if len(parts) > 0 and "text" in parts[0]:
                                            chunk_text = parts[0]["text"]
                                            
                                            if chunk_text:
                                                accumulated_text += chunk_text
                                                if on_chunk_async:
                                                    await on_chunk_async(chunk_text)
                                                if on_chunk:
                                                    if not on_chunk(chunk_text):
                                                        raise RuntimeError("Streaming cancelled by callback")
                            except json.JSONDecodeError:
                                continue
            
            if not accumulated_text.strip():
                if attempt < retries:
                    continue
                raise ValueError("Google AI returned empty response")
            
            return accumulated_text
            
        except httpx.HTTPStatusError as e:
            last_error = e
            if attempt < retries:
                await asyncio.sleep(2)
                continue
            raise e
            
        except Exception as e:
            last_error = e
            logger.warning(f"Google AI Streaming Error: {e}")
            if attempt < retries:
                await asyncio.sleep(1)
                continue
            raise e
    
    if last_error:
        raise last_error
    raise ValueError("Google AI streaming failed after retries")
