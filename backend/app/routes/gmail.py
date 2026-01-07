"""
Gmail integration endpoints.
Extracted from main.py for modularization.
"""
from fastapi import APIRouter, HTTPException, Header
from typing import Optional, Literal
from datetime import datetime, timezone, timedelta
import logging

from app.database import get_database
from app.auth import decode_access_token
from app.integrations import gmail as gmail_service
from app.config import GmailConfig
from app.exceptions import (
    GmailNotConfiguredError,
    GmailNotConnectedError,
    GmailReauthRequiredError
)
from app.schemas import (
    GmailStatusResponse,
    GmailSyncCompleteResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations/gmail", tags=["gmail"])


async def get_current_user_from_token(authorization: Optional[str]) -> dict:
    """
    Get current user from JWT token.
    Raises HTTPException if not authenticated.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized", headers={"code": "UNAUTHORIZED"})
    
    from bson import ObjectId
    token = authorization.split(" ")[1]
    payload = decode_access_token(token)
    
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid token", headers={"code": "UNAUTHORIZED"})
    
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token", headers={"code": "UNAUTHORIZED"})
    
    db = get_database()
    if db is None:
        raise HTTPException(status_code=500, detail="Database connection error", headers={"code": "DATABASE_ERROR"})
    
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=401, detail="User not found", headers={"code": "UNAUTHORIZED"})
    
    return user


@router.get("/connect")
async def gmail_connect(
    prompt_module: Optional[Literal["none", "lgs_karekok"]] = None,
    authorization: Optional[str] = Header(None)
):
    """
    Generate Google OAuth URL for Gmail integration.
    Returns auth_url with state parameter for CSRF protection.
    Optionally filter by prompt_module for module isolation.
    """
    user = await get_current_user_from_token(authorization)
    user_id = str(user["_id"])
    
    try:
        module = prompt_module or "none"
        state = await gmail_service.create_oauth_state(user_id, module)
        
        flow = gmail_service.get_gmail_flow()
        auth_url, _ = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent',
            state=state
        )
        return {"auth_url": auth_url}
    except GmailNotConfiguredError:
        raise
    except Exception as e:
        logger.error(f"Gmail connect error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Gmail bağlantı hatası: {str(e)}",
            headers={"code": "UNKNOWN_ERROR"}
        )


@router.get("/callback")
async def gmail_callback(
    code: str,
    state: str
):
    """
    Handle Google OAuth callback and store tokens.
    Validates state parameter for CSRF protection.
    Note: OAuth callbacks don't include authorization headers, so we get user_id from state.
    """
    try:
        is_valid, user_id, prompt_module = await gmail_service.validate_oauth_state(state)
        
        if not is_valid or not user_id:
            raise HTTPException(
                status_code=400,
                detail="Geçersiz veya süresi dolmuş OAuth state",
                headers={"code": "INVALID_STATE"}
            )
        
        import requests
        from google.oauth2.credentials import Credentials
        
        token_url = "https://oauth2.googleapis.com/token"
        token_data = {
            "code": code,
            "client_id": GmailConfig.CLIENT_ID,
            "client_secret": GmailConfig.CLIENT_SECRET,
            "redirect_uri": GmailConfig.REDIRECT_URI,
            "grant_type": "authorization_code"
        }
        
        try:
            response = requests.post(token_url, data=token_data, timeout=10)
            response.raise_for_status()
            token_response = response.json()
        except requests.exceptions.HTTPError as e:
            error_detail = "Token exchange failed"
            try:
                error_json = e.response.json()
                error_detail = error_json.get("error_description", error_json.get("error", str(e)))
            except:
                error_detail = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
            
            logger.error(f"Gmail token exchange failed: {error_detail}")
            raise HTTPException(
                status_code=400,
                detail=f"Token exchange hatası: {error_detail}",
                headers={"code": "TOKEN_EXCHANGE_FAILED"}
            )
        except Exception as e:
            logger.error(f"Gmail token exchange error: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Token exchange hatası: {str(e)}",
                headers={"code": "TOKEN_EXCHANGE_ERROR"}
            )
        
        granted_scopes = token_response.get("scope", "").split() if token_response.get("scope") else []
        if "https://www.googleapis.com/auth/gmail.readonly" not in granted_scopes:
            logger.error(f"Gmail readonly scope not granted. Granted scopes: {granted_scopes}")
            raise HTTPException(
                status_code=400,
                detail="Gmail readonly scope not granted",
                headers={"code": "SCOPE_MISSING"}
            )
        
        expires_at = None
        if token_response.get("expires_in"):
            expires_at_utc = datetime.now(timezone.utc) + timedelta(seconds=token_response.get("expires_in", 3600))
            expires_at = expires_at_utc.replace(tzinfo=None)
        
        credentials = Credentials(
            token=token_response.get("access_token"),
            refresh_token=token_response.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=GmailConfig.CLIENT_ID,
            client_secret=GmailConfig.CLIENT_SECRET,
            scopes=granted_scopes,
            expiry=expires_at
        )
        logger.info(f"Token fetched successfully, granted scopes: {granted_scopes}")
        
        if not credentials.refresh_token:
            logger.warning(f"No refresh_token received for user {user_id}. This may cause issues later.")
        
        from googleapiclient.discovery import build
        service = build('oauth2', 'v2', credentials=credentials)
        user_info = service.userinfo().get().execute()
        email = user_info.get('email')
        
        expiry_timestamp = None
        if credentials.expiry:
            if credentials.expiry.tzinfo is None:
                expiry_aware = credentials.expiry.replace(tzinfo=timezone.utc)
            else:
                expiry_aware = credentials.expiry
            expiry_timestamp = expiry_aware.timestamp()
        
        credentials_data = {
            "token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "expiry": expiry_timestamp
        }
        
        await gmail_service.store_gmail_tokens(user_id, credentials_data, email, prompt_module)
        logger.info(f"Gmail connected successfully for user {user_id} ({email}), module={prompt_module or 'none'}")
        
        # Redirect to frontend app page after successful connection
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="http://localhost:3003/app?gmail=connected", status_code=302)
    except GmailNotConfiguredError:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="http://localhost:3003/app?gmail=error&code=not_configured", status_code=302)
    except HTTPException as e:
        from fastapi.responses import RedirectResponse
        error_code = e.headers.get("code", "unknown") if e.headers else "unknown"
        return RedirectResponse(url=f"http://localhost:3003/app?gmail=error&code={error_code}", status_code=302)
    except Exception as e:
        logger.error(f"Gmail callback error: {e}")
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="http://localhost:3003/app?gmail=error&code=unknown", status_code=302)


@router.get("/status", response_model=GmailStatusResponse)
async def gmail_status(
    prompt_module: Optional[Literal["none", "lgs_karekok"]] = None,
    authorization: Optional[str] = Header(None)
):
    """
    Check Gmail integration status.
    Optionally filter by prompt_module for module isolation.
    """
    user = await get_current_user_from_token(authorization)
    user_id = str(user["_id"])
    
    try:
        return await gmail_service.get_gmail_status(user_id, prompt_module)
    except Exception as e:
        logger.error(f"Gmail status error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Gmail durum kontrolü hatası: {str(e)}",
            headers={"code": "UNKNOWN_ERROR"}
        )


@router.post("/sync", response_model=GmailSyncCompleteResponse)
async def gmail_manual_sync(
    prompt_module: Optional[Literal["none", "lgs_karekok"]] = None,
    authorization: Optional[str] = Header(None)
):
    """
    Manually trigger Gmail email sync.
    Optionally filter by prompt_module for module isolation.
    """
    user = await get_current_user_from_token(authorization)
    user_id = str(user["_id"])
    
    try:
        result = await gmail_service.sync_emails(user_id, prompt_module=prompt_module)
        if "error" in result:
            error_code = "GMAIL_NOT_CONNECTED" if "not connected" in result["error"].lower() else "SYNC_ERROR"
            error_detail = result["error"]
            if len(error_detail) > 500:
                error_detail = error_detail[:500] + "..."
            raise HTTPException(
                status_code=400,
                detail=error_detail,
                headers={"code": error_code}
            )
        return result
    except GmailNotConnectedError:
        raise
    except GmailReauthRequiredError:
        raise
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Gmail sync error: {e}", exc_info=True)
        error_detail = str(e)
        if len(error_detail) > 500:
            error_detail = error_detail[:500] + "..."
        raise HTTPException(
            status_code=500,
            detail=f"Gmail senkronizasyon hatası: {error_detail}",
            headers={"code": "UNKNOWN_ERROR"}
        )


@router.get("/emails")
async def list_indexed_emails(
    authorization: Optional[str] = Header(None)
):
    """
    List indexed emails for the user (from RAG database).
    """
    user = await get_current_user_from_token(authorization)
    user_id = str(user["_id"])
    
    db = get_database()
    emails = await db.email_sources.find({"user_id": user_id}).sort("date", -1).to_list(100)
    
    for email in emails:
        email["id"] = str(email["_id"])
        del email["_id"]
        if isinstance(email.get("date"), datetime):
            email["date"] = email["date"].isoformat()
        if isinstance(email.get("received_at"), datetime):
            email["received_at"] = email["received_at"].isoformat()
            
    return emails


@router.get("/messages")
async def list_gmail_messages(
    query: str = "",
    max: int = 50,
    prompt_module: Optional[Literal["none", "lgs_karekok"]] = None,
    authorization: Optional[str] = Header(None)
):
    """
    List Gmail messages directly from Gmail API (not indexed).
    Optionally filter by prompt_module for module isolation.
    """
    user = await get_current_user_from_token(authorization)
    user_id = str(user["_id"])
    
    try:
        messages = await gmail_service.list_gmail_messages(user_id, query=query, max_results=max, prompt_module=prompt_module)
        return {"messages": messages}
    except GmailNotConnectedError:
        raise
    except GmailReauthRequiredError:
        raise
    except Exception as e:
        logger.error(f"Gmail list messages error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Gmail mesaj listesi hatası: {str(e)}",
            headers={"code": "UNKNOWN_ERROR"}
        )


@router.get("/messages/{message_id}")
async def get_gmail_message(
    message_id: str,
    prompt_module: Optional[Literal["none", "lgs_karekok"]] = None,
    authorization: Optional[str] = Header(None)
):
    """
    Get a single Gmail message with full content.
    Optionally filter by prompt_module for module isolation.
    """
    user = await get_current_user_from_token(authorization)
    user_id = str(user["_id"])
    
    try:
        message = await gmail_service.get_gmail_message(user_id, message_id, prompt_module=prompt_module)
        return message
    except GmailNotConnectedError:
        raise
    except GmailReauthRequiredError:
        raise
    except Exception as e:
        logger.error(f"Gmail get message error: {e}", exc_info=True)
        error_detail = str(e)
        if len(error_detail) > 500:
            error_detail = error_detail[:500] + "..."
        raise HTTPException(
            status_code=500,
            detail=f"Gmail mesaj hatası: {error_detail}",
            headers={"code": "UNKNOWN_ERROR"}
        )


@router.post("/disconnect")
async def gmail_disconnect(
    authorization: Optional[str] = Header(None)
):
    """
    Disconnect Gmail integration (delete tokens).
    """
    user = await get_current_user_from_token(authorization)
    user_id = str(user["_id"])
    
    try:
        disconnected = await gmail_service.disconnect_gmail(user_id)
        if disconnected:
            return {"status": "success", "message": "Gmail bağlantısı kesildi"}
        else:
            return {"status": "success", "message": "Gmail zaten bağlı değil"}
    except Exception as e:
        logger.error(f"Gmail disconnect error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Gmail bağlantı kesme hatası: {str(e)}",
            headers={"code": "UNKNOWN_ERROR"}
        )
