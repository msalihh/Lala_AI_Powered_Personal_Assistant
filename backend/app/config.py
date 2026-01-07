"""
Application configuration with environment variable validation.
"""
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class GmailConfig:
    """Gmail OAuth configuration."""
    
    CLIENT_ID: Optional[str] = None
    CLIENT_SECRET: Optional[str] = None
    REDIRECT_URI: Optional[str] = None
    SCOPES: list[str] = []
    BASE_URL: Optional[str] = None
    FRONTEND_BASE_URL: Optional[str] = None
    
    @classmethod
    def load(cls):
        """Load Gmail configuration from environment variables."""
        cls.CLIENT_ID = (os.getenv("GOOGLE_CLIENT_ID") or "").strip()
        cls.CLIENT_SECRET = (os.getenv("GOOGLE_CLIENT_SECRET") or "").strip()
        cls.REDIRECT_URI = os.getenv(
            "GOOGLE_REDIRECT_URI",
            "http://localhost:3003/integrations/gmail"
        ).strip()
        
        # Default scopes
        scopes_str = os.getenv(
            "GOOGLE_OAUTH_SCOPES",
            "https://www.googleapis.com/auth/gmail.readonly"
        )
        cls.SCOPES = [s.strip() for s in scopes_str.split(",") if s.strip()]
        
        # Base URLs for link generation
        cls.BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000").strip()
        cls.FRONTEND_BASE_URL = os.getenv(
            "FRONTEND_BASE_URL",
            "http://localhost:3003"
        ).strip()
        
        logger.debug(
            f"Gmail Config: ID={'Set' if cls.CLIENT_ID else 'Not Set'}, "
            f"Secret={'Set' if cls.CLIENT_SECRET else 'Not Set'}, "
            f"Redirect={cls.REDIRECT_URI}"
        )
    
    @classmethod
    def is_configured(cls) -> bool:
        """Check if Gmail OAuth is properly configured."""
        return bool(cls.CLIENT_ID and cls.CLIENT_SECRET and cls.REDIRECT_URI)


class EncryptionConfig:
    """Encryption configuration."""
    
    ENCRYPTION_KEY: Optional[str] = None
    SECRET_KEY: Optional[str] = None
    
    @classmethod
    def load(cls):
        """Load encryption configuration from environment variables."""
        cls.ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
        cls.SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
        
        if not cls.ENCRYPTION_KEY:
            logger.warning(
                "ENCRYPTION_KEY not set. Using derived key from SECRET_KEY. "
                "Set ENCRYPTION_KEY for production."
            )


# Load configurations on module import
GmailConfig.load()
EncryptionConfig.load()

