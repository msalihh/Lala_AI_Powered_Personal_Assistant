"""
Encryption utilities for sensitive data (OAuth tokens).
Uses Fernet symmetric encryption.
"""
import os
from cryptography.fernet import Fernet
import base64
from app.logging_config import setup_logging
import logging

logger = logging.getLogger(__name__)

# SECURITY: Use a dedicated ENCRYPTION_KEY if provided, otherwise fallback to SECRET_KEY
# The key must be a 32-byte string encoded in base64.
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")

def get_fernet() -> Fernet:
    """
    Initialize Fernet with the encryption key.
    If ENCRYPTION_KEY is not set, derive one from SECRET_KEY.
    """
    if ENCRYPTION_KEY:
        try:
            return Fernet(ENCRYPTION_KEY.encode())
        except Exception as e:
            logger.error(f"Invalid ENCRYPTION_KEY: {e}. Falling back to derived key.")
    
    # Derive a 32-byte key from SECRET_KEY for Fernet compliance
    # This is a simple fallback and not recommended for production
    # Pad or truncate SECRET_KEY to 32 bytes and base64 encode it
    key_bytes = SECRET_KEY.encode('utf-8')
    if len(key_bytes) < 32:
        key_bytes = key_bytes.ljust(32, b'0')
    else:
        key_bytes = key_bytes[:32]
    
    fernet_key = base64.urlsafe_b64encode(key_bytes)
    return Fernet(fernet_key)

_fernet = get_fernet()

def encrypt_data(data: str) -> str:
    """
    Encrypt a string and return the encrypted string (base64).
    """
    if not data:
        return ""
    return _fernet.encrypt(data.encode()).decode()

def decrypt_data(encrypted_data: str) -> str:
    """
    Decrypt an encrypted string.
    """
    if not encrypted_data:
        return ""
    try:
        return _fernet.decrypt(encrypted_data.encode()).decode()
    except Exception as e:
        logger.error(f"Decryption failed: {e}")
        return ""
