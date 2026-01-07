"""
Custom exceptions for standardized error handling.
"""
from fastapi import HTTPException, status


class AppException(HTTPException):
    """Base exception class for the application."""
    
    def __init__(
        self,
        status_code: int,
        detail: str,
        code: str = "UNKNOWN_ERROR",
        headers: dict = None
    ):
        super().__init__(
            status_code=status_code,
            detail=detail,
            headers={"code": code, **(headers or {})}
        )
        self.code = code


class AuthenticationError(AppException):
    """Authentication failed."""
    
    def __init__(self, detail: str = "Kimlik doğrulama gerekli"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            code="UNAUTHORIZED",
            headers={"WWW-Authenticate": "Bearer"}
        )


class AuthorizationError(AppException):
    """User not authorized for this action."""
    
    def __init__(self, detail: str = "Bu işlem için yetkiniz yok"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
            code="FORBIDDEN"
        )


class NotFoundError(AppException):
    """Resource not found."""
    
    def __init__(self, resource: str = "Kaynak"):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{resource} bulunamadı",
            code="NOT_FOUND"
        )


class ValidationError(AppException):
    """Validation failed."""
    
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
            code="VALIDATION_ERROR"
        )


class DatabaseError(AppException):
    """Database operation failed."""
    
    def __init__(self, detail: str = "Veritabanı hatası"):
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail,
            code="DATABASE_ERROR"
        )


class RateLimitError(AppException):
    """Rate limit exceeded."""
    
    def __init__(self, retry_after: int = 60):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"İstek limiti aşıldı. {retry_after} saniye sonra tekrar deneyin.",
            code="RATE_LIMIT_EXCEEDED",
            headers={"Retry-After": str(retry_after)}
        )


class FileUploadError(AppException):
    """File upload failed."""
    
    def __init__(self, detail: str = "Dosya yükleme hatası"):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
            code="UPLOAD_ERROR"
        )


class ExternalServiceError(AppException):
    """External service (OpenRouter, etc.) failed."""
    
    def __init__(self, service: str = "Harici servis", detail: str = None):
        super().__init__(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=detail or f"{service} ile iletişim kurulamadı",
            code="EXTERNAL_SERVICE_ERROR"
        )


class GmailNotConfiguredError(AppException):
    """Gmail OAuth is not configured."""
    
    def __init__(self, detail: str = "Gmail entegrasyonu yapılandırılmamış. GOOGLE_CLIENT_ID ve GOOGLE_CLIENT_SECRET environment değişkenlerini ayarlayın."):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
            code="GMAIL_NOT_CONFIGURED"
        )


class GmailNotConnectedError(AppException):
    """Gmail is not connected for this user."""
    
    def __init__(self, detail: str = "Gmail hesabınız bağlı değil. Lütfen önce bağlantı kurun."):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
            code="GMAIL_NOT_CONNECTED"
        )


class GmailReauthRequiredError(AppException):
    """Gmail token refresh failed, re-authentication required."""
    
    def __init__(self, detail: str = "Gmail bağlantısı süresi doldu. Lütfen tekrar bağlanın."):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            code="GMAIL_REAUTH_REQUIRED"
        )