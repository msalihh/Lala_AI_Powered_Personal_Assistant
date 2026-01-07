"""
Gmail integration service.
Handles OAuth, email fetching, normalization, and RAG indexing.
"""
import os
import secrets
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any, Tuple

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from bs4 import BeautifulSoup
import re

from app.database import get_database
from app.config import GmailConfig
from app.exceptions import (
    GmailNotConfiguredError,
    GmailNotConnectedError,
    GmailReauthRequiredError
)
from app.integrations.encryption import encrypt_data, decrypt_data
from app.rag.chunker import chunk_text
from app.rag.embedder import embed_text
from app.rag.vector_store import index_document_chunks
from app.logging_config import setup_logging

logger = logging.getLogger(__name__)

# In-memory cache for Gmail service instances (per request/process)
# Key: user_id, Value: (service, credentials, expires_at)
_service_cache: Dict[str, Tuple[Any, Credentials, datetime]] = {}

def _clear_expired_cache():
    """Clear expired entries from service cache."""
    now = datetime.now(timezone.utc)
    expired_keys = []
    for user_id, (_, _, expires_at) in _service_cache.items():
        if expires_at:
            # Ensure both are timezone-aware for comparison
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at < now:
                expired_keys.append(user_id)
    for key in expired_keys:
        _service_cache.pop(key, None)


def get_gmail_flow() -> Flow:
    """
    Initialize OAuth flow for Gmail.
    Raises GmailNotConfiguredError if not configured.
    """
    if not GmailConfig.is_configured():
        raise GmailNotConfiguredError()
    
    client_config = {
        "web": {
            "client_id": GmailConfig.CLIENT_ID,
            "client_secret": GmailConfig.CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [GmailConfig.REDIRECT_URI]
        }
    }
    
    return Flow.from_client_config(
        client_config,
        scopes=GmailConfig.SCOPES,
        redirect_uri=GmailConfig.REDIRECT_URI
    )


async def create_oauth_state(user_id: str, prompt_module: Optional[str] = None) -> str:
    """
    Create and store OAuth state for CSRF protection.
    Returns the state token.
    """
    db = get_database()
    state = secrets.token_urlsafe(32)
    
    # Store state with user_id and expiration (30 minutes) - increased for OAuth flow completion
    # Convert to UTC naive for MongoDB
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
    expires_at_naive = expires_at.replace(tzinfo=None)
    created_at_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    
    state_doc = {
        "state": state,
        "user_id": user_id,
        "created_at": created_at_naive,
        "expires_at": expires_at_naive
    }
    
    # Add prompt_module if provided (for module isolation)
    if prompt_module:
        state_doc["prompt_module"] = prompt_module
    
    await db.oauth_states.insert_one(state_doc)
    
    logger.info(f"OAuth state created for user {user_id[:8]}..., module={prompt_module}, expires at {expires_at_naive}")
    
    # OAuth state created
    return state


async def validate_oauth_state(state: str, user_id: str = None) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validate OAuth state and return user_id and prompt_module.
    Returns (is_valid, user_id, prompt_module) tuple.
    If user_id is provided, also validates it matches.
    """
    db = get_database()
    if db is None:
        logger.error("Database not available for OAuth state validation")
        return (False, None, None)
    
    state_doc = await db.oauth_states.find_one({"state": state})
    
    if not state_doc:
        logger.warning(f"OAuth state not found: {state[:16]}...")
        return (False, None, None)
    
    # Check expiration - handle both timezone-aware and timezone-naive datetimes
    expires_at = state_doc.get("expires_at")
    if expires_at:
        try:
            if isinstance(expires_at, datetime):
                # Convert both to UTC naive for safe comparison
                if expires_at.tzinfo is not None:
                    expires_at_naive = expires_at.replace(tzinfo=None)
                else:
                    expires_at_naive = expires_at
                
                now_naive = datetime.utcnow()
                
                # Add 1 minute buffer for clock skew
                if expires_at_naive < (now_naive - timedelta(minutes=1)):
                    logger.warning(
                        f"OAuth state expired: {state[:16]}... "
                        f"(expires_at={expires_at_naive}, now={now_naive}, diff={(now_naive - expires_at_naive).total_seconds() / 60:.1f} min)"
                    )
                    await db.oauth_states.delete_one({"state": state})
                    return (False, None)
            else:
                logger.warning(f"OAuth state expires_at is not datetime: {type(expires_at)}")
                await db.oauth_states.delete_one({"state": state})
                return (False, None)
        except Exception as e:
            logger.error(f"Error checking OAuth state expiration: {e}, expires_at type: {type(expires_at)}, value: {expires_at}")
            # If comparison fails, treat as expired for safety
            await db.oauth_states.delete_one({"state": state})
            return (False, None)
    else:
        logger.warning(f"OAuth state missing expires_at: {state[:16]}...")
        # State without expiration is invalid
        await db.oauth_states.delete_one({"state": state})
        return (False, None)
    
    state_user_id = state_doc.get("user_id")
    
    if not state_user_id:
        logger.warning(f"OAuth state missing user_id: {state[:16]}...")
        await db.oauth_states.delete_one({"state": state})
        return (False, None)
    
    # If user_id is provided, validate it matches
    if user_id and state_user_id != user_id:
        logger.warning(f"OAuth state user mismatch: expected {user_id}, got {state_user_id}")
        await db.oauth_states.delete_one({"state": state})
        return (False, None)
    
    # Get prompt_module from state if available
    prompt_module = state_doc.get("prompt_module")
    
    logger.info(f"OAuth state validated successfully for user {state_user_id[:8]}..., module={prompt_module}")
    
    # Clean up used state
    await db.oauth_states.delete_one({"state": state})
    return (True, state_user_id, prompt_module)


async def store_gmail_tokens(user_id: str, credentials_data: Dict[str, Any], email: str, prompt_module: Optional[str] = None):
    """
    Store encrypted tokens in MongoDB.
    """
    db = get_database()
    
    # Ensure refresh_token is present (critical for offline access)
    if not credentials_data.get("refresh_token"):
        logger.warning(f"No refresh_token received for user {user_id}. Token may expire.")
    
    # Handle expires_at - ensure timezone-aware datetime, then convert to UTC naive for MongoDB
    if isinstance(credentials_data.get("expiry"), (int, float)):
        expires_at = datetime.fromtimestamp(credentials_data["expiry"], tz=timezone.utc)
    else:
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    
    # Convert to UTC naive for MongoDB (MongoDB stores as UTC but without timezone info)
    expires_at_naive = expires_at.replace(tzinfo=None) if expires_at.tzinfo else expires_at
    connected_at_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    
    integration_data = {
        "user_id": user_id,
        "provider": "gmail",
        "access_token": encrypt_data(credentials_data["token"]),
        "refresh_token": encrypt_data(credentials_data["refresh_token"]) if credentials_data.get("refresh_token") else None,
        "expires_at": expires_at_naive,
        "connected_at": connected_at_naive,
        "email": email,
        "sync_status": "connected",
        "last_sync_at": None,
        "prompt_module": prompt_module or "none"  # Store module for reference
    }
    
    # Use existing index pattern (user_id + provider) to avoid duplicate key error
    query_filter = {
        "user_id": user_id,
        "provider": "gmail"
    }
    
    await db.user_integrations.update_one(
        query_filter,
        {"$set": integration_data},
        upsert=True
    )
    logger.info(f"Stored Gmail tokens for user {user_id} ({email}), module={prompt_module or 'none'}")



async def get_gmail_service(user_id: str, force_refresh: bool = False, prompt_module: Optional[str] = None):
    """
    Get an authenticated Gmail service instance for the user.
    Handles token refreshing if needed.
    Caches service instance to avoid recreating for each request.
    Raises GmailNotConnectedError if not connected.
    Raises GmailReauthRequiredError if refresh fails.
    
    Args:
        user_id: User ID
        force_refresh: Force token refresh even if not expired (default: False)
        prompt_module: Module to filter by (for module isolation)
    """
    # Clear expired cache entries periodically
    _clear_expired_cache()
    
    # Use module-specific cache key
    cache_key = f"{user_id}:{prompt_module or 'none'}"
    
    # Check cache first (unless force refresh)
    if not force_refresh and cache_key in _service_cache:
        service, creds, cache_expires_at = _service_cache[cache_key]
        # Use cached service if token is still valid (with 5 minute buffer)
        if cache_expires_at:
            # Ensure both are timezone-aware for comparison
            now = datetime.now(timezone.utc)
            if cache_expires_at.tzinfo is None:
                cache_expires_at = cache_expires_at.replace(tzinfo=timezone.utc)
            if now < cache_expires_at - timedelta(minutes=5):
                return service
        # Cache expired, remove it
        _service_cache.pop(cache_key, None)
    
    db = get_database()
    # CRITICAL: Filter by prompt_module for module isolation
    query_filter = {
        "user_id": user_id,
        "provider": "gmail",
        "prompt_module": prompt_module or "none"
    }
    integration = await db.user_integrations.find_one(query_filter)
    
    if not integration:
        raise GmailNotConnectedError()
    
    if not GmailConfig.is_configured():
        raise GmailNotConfiguredError()
    
    access_token = decrypt_data(integration["access_token"])
    refresh_token = decrypt_data(integration["refresh_token"]) if integration.get("refresh_token") else None
    
    if not access_token:
        raise GmailNotConnectedError()
    
    # Get expires_at from DB
    db_expires_at = integration.get("expires_at")
    if db_expires_at:
        if isinstance(db_expires_at, datetime):
            # If timezone-naive, assume UTC
            if db_expires_at.tzinfo is None:
                db_expires_at = db_expires_at.replace(tzinfo=timezone.utc)
        else:
            db_expires_at = None
    
    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GmailConfig.CLIENT_ID,
        client_secret=GmailConfig.CLIENT_SECRET,
        scopes=GmailConfig.SCOPES
    )
    
    # Set expiry if we have it from DB
    # CRITICAL: Google Credentials expects timezone-naive datetime or timezone-aware in UTC
    # Convert db_expires_at to timezone-naive if it's timezone-aware
    if db_expires_at:
        if isinstance(db_expires_at, datetime):
            if db_expires_at.tzinfo is not None:
                # Convert to UTC naive for Google Credentials
                db_expires_at_naive = db_expires_at.replace(tzinfo=None)
            else:
                db_expires_at_naive = db_expires_at
        else:
            db_expires_at_naive = None
        if db_expires_at_naive:
            creds.expiry = db_expires_at_naive
    
    # Proactive refresh: Refresh if expired OR if expires within 5 minutes
    # Don't use creds.expired - it may cause timezone comparison issues
    # Instead, manually check expiry
    needs_refresh = force_refresh
    if not needs_refresh and creds.expiry:
        # CRITICAL: Handle both timezone-aware and timezone-naive datetimes
        # Google Credentials.expiry can be either, so we normalize both to UTC-aware for comparison
        now = datetime.now(timezone.utc)
        expiry = creds.expiry
        
        # Normalize expiry to UTC-aware datetime
        if expiry.tzinfo is None:
            # Timezone-naive: assume it's UTC
            expiry = expiry.replace(tzinfo=timezone.utc)
        elif expiry.tzinfo != timezone.utc:
            # Timezone-aware but not UTC: convert to UTC
            expiry = expiry.astimezone(timezone.utc)
        # If already UTC-aware, use as-is
        
        # Check if expired or expires within 5 minutes
        time_until_expiry = (expiry - now).total_seconds()
        if time_until_expiry <= 0:
            needs_refresh = True
            logger.debug(f"Token expired for user {user_id}")
        elif time_until_expiry < 300:  # 5 minutes
            needs_refresh = True
            logger.debug(f"Proactive token refresh for user {user_id} (expires in {time_until_expiry:.0f}s)")
    
    if needs_refresh:
        if not refresh_token:
            raise GmailReauthRequiredError()
        
        try:
            from google.auth.transport.requests import Request
            creds.refresh(Request())
            
            # Update tokens in DB - convert to UTC naive for MongoDB
            # CRITICAL: Google Credentials.expiry can be timezone-aware or timezone-naive
            # Normalize it to UTC-aware first, then convert to naive for MongoDB
            if creds.expiry:
                expires_at = creds.expiry
                # Normalize to UTC-aware datetime
                if isinstance(expires_at, datetime):
                    if expires_at.tzinfo is None:
                        # Timezone-naive: assume UTC
                        expires_at = expires_at.replace(tzinfo=timezone.utc)
                    elif expires_at.tzinfo != timezone.utc:
                        # Timezone-aware but not UTC: convert to UTC
                        expires_at = expires_at.astimezone(timezone.utc)
                    # If already UTC-aware, use as-is
                else:
                    # Not a datetime, use default
                    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
            else:
                expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
            # Convert to UTC naive for MongoDB (MongoDB stores naive datetimes)
            expires_at_naive = expires_at.replace(tzinfo=None)
            
            await db.user_integrations.update_one(
                {"user_id": user_id, "provider": "gmail"},
                {"$set": {
                    "access_token": encrypt_data(creds.token),
                    "expires_at": expires_at_naive,
                    "sync_status": "connected"
                }}
            )
            logger.info(f"Refreshed Gmail token for user {user_id}")
        except Exception as e:
            logger.error(f"Failed to refresh Gmail token for {user_id}: {e}")
            await db.user_integrations.update_one(
                {"user_id": user_id, "provider": "gmail"},
                {"$set": {"sync_status": "error"}}
            )
            raise GmailReauthRequiredError()
    
    # Build service and cache it
    service = build('gmail', 'v1', credentials=creds)
    
    # Cache service instance with expiry time (use token expiry or 1 hour default)
    # CRITICAL: Normalize creds.expiry to UTC-aware datetime for cache
    if creds.expiry:
        cache_expires_at = creds.expiry
        # Normalize to UTC-aware datetime
        if isinstance(cache_expires_at, datetime):
            if cache_expires_at.tzinfo is None:
                # Timezone-naive: assume UTC
                cache_expires_at = cache_expires_at.replace(tzinfo=timezone.utc)
            elif cache_expires_at.tzinfo != timezone.utc:
                # Timezone-aware but not UTC: convert to UTC
                cache_expires_at = cache_expires_at.astimezone(timezone.utc)
            # If already UTC-aware, use as-is
        else:
            # Not a datetime, use default
            cache_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    else:
        cache_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    
    _service_cache[cache_key] = (service, creds, cache_expires_at)
    
    return service


async def disconnect_gmail(user_id: str, prompt_module: Optional[str] = None):
    """
    Disconnect Gmail integration for a user (delete tokens).
    """
    db = get_database()
    # CRITICAL: Filter by prompt_module for module isolation
    query_filter = {
        "user_id": user_id,
        "provider": "gmail",
        "prompt_module": prompt_module or "none"
    }
    result = await db.user_integrations.delete_one(query_filter)
    
    if result.deleted_count > 0:
        logger.info(f"Disconnected Gmail for user {user_id}")
        return True
    return False


def clean_email_body(html_or_text: str) -> str:
    """
    Clean email body: remove HTML tags, signatures, and quoted replies.
    """
    # 1. Remove HTML
    soup = BeautifulSoup(html_or_text, "html.parser")
    text = soup.get_text(separator=' ')
    
    # 2. Remove common signature patterns
    # Look for "-- " or common Turkish/English signature starters
    text = re.split(r'--\s*\n|---+\s*\n|Best regards|Saygılarımla|Cheers|Sent from my', text, flags=re.IGNORECASE)[0]
    
    # 3. Remove quoted replies (Gmail style: "On ... wrote:")
    text = re.split(r'\nOn\s.*\swrote:|\nTarihinde\s.*\şunu\syazdı:', text, flags=re.IGNORECASE)[0]
    
    # 4. Collapse spaces
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text


async def list_gmail_messages(user_id: str, query: str = "", max_results: int = 50, prompt_module: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    List Gmail messages for a user.
    Returns list of message metadata with subject, sender, date, snippet.
    Optimized: Service instance created once, token refreshed once if needed.
    """
    # Get service instance once - token refresh happens here if needed
    service = await get_gmail_service(user_id, prompt_module=prompt_module)
    
    try:
        # Build query
        gmail_query = query if query else "in:inbox"
        
        results = service.users().messages().list(
            userId='me',
            maxResults=max_results,
            q=gmail_query
        ).execute()
        
        messages = results.get('messages', [])
        
        # Fetch basic metadata for each message sequentially
        # Note: Google API client is not thread-safe, so we fetch sequentially
        # But we use format='metadata' for faster response
        # IMPORTANT: Service instance is reused, so no token refresh per message
        message_list = []
        for msg in messages:
            msg_id = msg['id']
            try:
                # Get message with format='metadata' for faster response
                # Service instance is already authenticated, no token refresh needed
                full_msg = service.users().messages().get(
                    userId='me',
                    id=msg_id,
                    format='metadata',
                    metadataHeaders=['Subject', 'From', 'Date']
                ).execute()
                
                payload = full_msg.get('payload', {})
                headers = payload.get('headers', [])
                
                subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), "Konu yok")
                sender = next((h['value'] for h in headers if h['name'].lower() == 'from'), "Bilinmeyen gönderen")
                date_str = next((h['value'] for h in headers if h['name'].lower() == 'date'), None)
                
                # Extract sender name/email
                sender_name = sender
                sender_email = sender
                if '<' in sender and '>' in sender:
                    # Format: "Name <email@example.com>"
                    parts = sender.split('<')
                    sender_name = parts[0].strip().replace('"', '')
                    sender_email = parts[1].replace('>', '').strip()
                elif '@' in sender:
                    sender_email = sender
                    sender_name = sender.split('@')[0]
                
                message_list.append({
                    "id": msg_id,
                    "threadId": msg.get('threadId'),
                    "snippet": full_msg.get('snippet', ''),
                    "subject": subject,
                    "sender": sender_name,
                    "sender_email": sender_email,
                    "date": date_str,
                    "internalDate": full_msg.get('internalDate')
                })
            except Exception as e:
                # Fallback to basic info
                message_list.append({
                    "id": msg_id,
                    "threadId": msg.get('threadId'),
                    "snippet": "",
                    "subject": "Konu yok",
                    "sender": "Bilinmeyen",
                    "sender_email": "",
                    "date": None,
                    "internalDate": None
                })
        
        return message_list
    except Exception as e:
        logger.error(f"Failed to list Gmail messages for {user_id}: {e}")
        raise


async def get_gmail_message(user_id: str, message_id: str, prompt_module: Optional[str] = None) -> Dict[str, Any]:
    """
    Get a single Gmail message with full content.
    Optimized: Service instance reused from cache if available.
    """
    # Get service instance - uses cache if available, refreshes token once if needed
    service = await get_gmail_service(user_id, prompt_module=prompt_module)
    
    try:
        message = service.users().messages().get(
            userId='me',
            id=message_id,
            format='full'
        ).execute()
        
        # Parse message
        payload = message.get('payload', {})
        headers = payload.get('headers', [])
        
        subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), "No Subject")
        sender = next((h['value'] for h in headers if h['name'].lower() == 'from'), "Unknown Sender")
        date_str = next((h['value'] for h in headers if h['name'].lower() == 'date'), None)
        
        # Extract body - handle nested parts recursively
        def extract_body_from_parts(parts_list):
            """Recursively extract body from message parts"""
            body_text = ""
            body_html = ""
            
            for part in parts_list:
                mime_type = part.get('mimeType', '')
                
                # If this part has nested parts, recurse
                if 'parts' in part and part['parts']:
                    nested_text, nested_html = extract_body_from_parts(part['parts'])
                    if nested_text:
                        body_text = nested_text
                    if nested_html:
                        body_html = nested_html
                else:
                    # This is a leaf part
                    body_data = part.get('body', {}).get('data', '')
                    if body_data:
                        try:
                            import base64
                            decoded = base64.urlsafe_b64decode(body_data).decode('utf-8', errors='ignore')
                            if mime_type == 'text/plain':
                                body_text = decoded
                            elif mime_type == 'text/html':
                                body_html = decoded
                        except Exception as e:
                            logger.warning(f"Failed to decode body part: {e}")
            
            return body_text, body_html
        
        # Extract body
        body = ""
        parts = payload.get('parts', [])
        if not parts:
            # Single part message
            body_data = payload.get('body', {}).get('data', '')
            if body_data:
                try:
                    import base64
                    body = base64.urlsafe_b64decode(body_data).decode('utf-8', errors='ignore')
                except Exception as e:
                    logger.warning(f"Failed to decode single part body: {e}")
        else:
            # Multi-part message - extract recursively
            body_text, body_html = extract_body_from_parts(parts)
            # Prefer plain text, fallback to HTML
            body = body_text if body_text else body_html
        
        clean_body = clean_email_body(body) if body else ""
        
        return {
            "id": message_id,
            "thread_id": message.get('threadId'),
            "subject": subject,
            "sender": sender,
            "date": date_str,
            "snippet": message.get('snippet', ''),
            "body": clean_body,
            "raw": message
        }
    except Exception as e:
        logger.error(f"Failed to get Gmail message {message_id} for {user_id}: {e}", exc_info=True)
        raise


async def sync_emails(user_id: str, max_emails: int = 200, prompt_module: Optional[str] = None):  # Increased from 50 to 200
    """
    Fetch, clean, and index emails for a user.
    Optimized: Service instance created once, token refreshed once if needed.
    """
    # Get service instance once - token refresh happens here if needed
    service = await get_gmail_service(user_id, prompt_module=prompt_module)
    db = get_database()
    
    # Get list of messages
    try:
        results = service.users().messages().list(
            userId='me',
            maxResults=max_emails,
            q='label:inbox'  # Fetch all inbox emails (both read and unread)
        ).execute()
        messages = results.get('messages', [])
        
        emails_fetched = 0
        emails_indexed = 0
        start_time = datetime.now(timezone.utc)
        
        for msg in messages:
            msg_id = msg['id']
            
            # Check if already indexed (to avoid duplicates) - filter by module
            existing = await db.email_sources.find_one({
                "email_id": msg_id, 
                "user_id": user_id,
                "prompt_module": prompt_module or "none"
            })
            if existing:
                continue
            
            # Fetch message detail
            full_msg = service.users().messages().get(userId='me', id=msg_id).execute()
            payload = full_msg.get('payload', {})
            headers = payload.get('headers', [])
            
            subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), "No Subject")
            sender = next((h['value'] for h in headers if h['name'].lower() == 'from'), "Unknown Sender")
            date_str = next((h['value'] for h in headers if h['name'].lower() == 'date'), None)
            
            # Parse body
            parts = payload.get('parts', [])
            body = ""
            if not parts:
                body = payload.get('body', {}).get('data', '')
            else:
                # Find plain text or html part
                for part in parts:
                    if part['mimeType'] == 'text/plain':
                        body = part.get('body', {}).get('data', '')
                        break
                    elif part['mimeType'] == 'text/html':
                        body = part.get('body', {}).get('data', '')
            
            if body:
                import base64
                body = base64.urlsafe_b64decode(body).decode('utf-8', errors='ignore')
            
            clean_body = clean_email_body(body)
            full_text = f"Subject: {subject}\nFrom: {sender}\nBody: {clean_body}"
            
            # Index to RAG
            chunks = chunk_text(full_text)
            if chunks:
                # Embed and save to vector store
                for chunk in chunks:
                    chunk['embedding'] = await embed_text(chunk['text'])
                
                # We use a virtual document ID for emails
                doc_id = f"email_{msg_id}"
                
                # Prepare email metadata for vector store
                email_metadata = {
                    "subject": subject,
                    "sender": sender,
                    "date": date_str if date_str else ""
                }
                
                # Index to RAG with email source type and metadata
                index_document_chunks(
                    document_id=doc_id,
                    chunks=chunks,
                    original_filename=subject,
                    was_truncated=False,
                    user_id=user_id,
                    source_type="email",  # CRITICAL: Mark as email source
                    email_metadata=email_metadata,  # CRITICAL: Include email metadata
                    prompt_module=prompt_module or "none"  # CRITICAL: Store module for isolation
                )
                
                # Store email metadata - convert to UTC naive for MongoDB
                now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
                email_source = {
                    "user_id": user_id,
                    "email_id": msg_id,
                    "thread_id": full_msg.get('threadId'),
                    "subject": subject,
                    "sender": sender,
                    "date": now_naive,  # Simplified date parsing
                    "received_at": now_naive,
                    "prompt_module": prompt_module or "none"  # Store module for isolation
                }
                await db.email_sources.insert_one(email_source)
                emails_indexed += 1
            
            emails_fetched += 1
        
        # Update integration with module filter
        await db.user_integrations.update_one(
            {
                "user_id": user_id, 
                "provider": "gmail",
                "prompt_module": prompt_module or "none"
            },
            {"$set": {"last_sync_at": datetime.now(timezone.utc).replace(tzinfo=None), "sync_status": "connected"}}
        )
        
        # Calculate duration - both are timezone-aware, so comparison is safe
        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds() * 1000
        
        logger.info(f"Gmail sync completed for {user_id}: fetched={emails_fetched}, indexed={emails_indexed}, duration={duration:.2f}ms")
        
        return {
            "status": "success",
            "emails_fetched": emails_fetched,
            "emails_indexed": emails_indexed,
            "duration_ms": duration
        }
        
    except GmailNotConnectedError:
        logger.warning(f"Gmail sync failed for {user_id}: Gmail not connected")
        return {"error": "Gmail not connected"}
    except GmailReauthRequiredError:
        logger.warning(f"Gmail sync failed for {user_id}: Re-authentication required")
        return {"error": "Gmail re-authentication required"}
    except Exception as e:
        logger.error(f"Gmail sync failed for {user_id}: {e}", exc_info=True)
        # Truncate error message if too long
        error_msg = str(e)
        if len(error_msg) > 500:
            error_msg = error_msg[:500] + "..."
        return {"error": error_msg}


async def get_gmail_status(user_id: str, prompt_module: Optional[str] = None):
    """
    Check connection status and last sync for Gmail.
    """
    db = get_database()
    # CRITICAL: Filter by prompt_module for module isolation
    query_filter = {
        "user_id": user_id,
        "provider": "gmail",
        "prompt_module": prompt_module or "none"
    }
    integration = await db.user_integrations.find_one(query_filter)
    
    if not integration:
        return {"is_connected": False, "sync_status": "disconnected"}
    
    # Handle last_sync_at - convert to ISO format safely
    last_sync_at = integration.get("last_sync_at")
    last_sync_at_iso = None
    if last_sync_at:
        try:
            if isinstance(last_sync_at, datetime):
                # If timezone-naive, assume UTC
                if last_sync_at.tzinfo is None:
                    last_sync_at = last_sync_at.replace(tzinfo=timezone.utc)
                last_sync_at_iso = last_sync_at.isoformat()
            else:
                # If it's already a string or other type, convert to string
                last_sync_at_iso = str(last_sync_at)
        except Exception as e:
            logger.warning(f"Error formatting last_sync_at for {user_id}: {e}")
            last_sync_at_iso = None
    
    return {
        "is_connected": True,
        "email": integration.get("email"),
        "last_sync_at": last_sync_at_iso,
        "sync_status": integration.get("sync_status", "connected")
    }
