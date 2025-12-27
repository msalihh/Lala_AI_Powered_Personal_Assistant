"""
Authentication utilities: password hashing, JWT tokens, Google OAuth.
"""
from jose import JWTError, jwt
from datetime import datetime, timedelta
import os
import bcrypt
from google.auth.transport import requests
from google.oauth2 import id_token

# JWT settings
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30 * 24 * 60  # 30 days

# Google OAuth settings
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")


def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt directly.
    Bcrypt has a 72 byte limit.
    """
    # Bcrypt has a 72 byte limit
    password_bytes = password.encode('utf-8')
    password_byte_length = len(password_bytes)
    
    # Only raise error if actually too long
    if password_byte_length > 72:
        raise ValueError(f"Password cannot be longer than 72 bytes (got {password_byte_length} bytes)")
    
    # Use bcrypt directly
    salt = bcrypt.gensalt()
    hashed_bytes = bcrypt.hashpw(password_bytes, salt)
    return hashed_bytes.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against its hash using bcrypt directly.
    """
    plain_bytes = plain_password.encode('utf-8')
    hashed_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(plain_bytes, hashed_bytes)


def create_access_token(data: dict) -> str:
    """
    Create a JWT access token.
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> dict:
    """
    Decode and verify a JWT access token.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


def verify_google_token(id_token_str: str) -> dict:
    """
    Verify Google ID token signature and return token payload.
    
    Args:
        id_token_str: The Google ID token string from frontend
        
    Returns:
        dict: Token payload containing 'email', 'sub', 'name', etc.
        
    Raises:
        ValueError: If token is invalid or verification fails
    """
    if not GOOGLE_CLIENT_ID:
        raise ValueError("GOOGLE_CLIENT_ID not configured")
    
    try:
        # Verify token signature using Google's public keys
        idinfo = id_token.verify_oauth2_token(
            id_token_str,
            requests.Request(),
            GOOGLE_CLIENT_ID
        )
        
        # Token is valid, return the payload
        return idinfo
    except Exception as e:
        # More detailed error message for debugging
        error_msg = str(e)
        if not GOOGLE_CLIENT_ID:
            error_msg = "GOOGLE_CLIENT_ID not configured in backend environment"
        raise ValueError(f"Invalid Google token: {error_msg}")


