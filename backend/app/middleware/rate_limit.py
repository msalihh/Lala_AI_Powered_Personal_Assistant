"""
Simple in-memory rate limiting middleware.
For production, use Redis-based rate limiting.
"""
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from collections import defaultdict
from datetime import datetime, timedelta
import asyncio
import os
import logging

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware with configurable limits per endpoint.
    
    Uses in-memory storage (suitable for single-instance deployments).
    For multi-instance deployments, consider Redis-based rate limiting.
    """
    
    def __init__(self, app, default_limit: int = 100, window_seconds: int = 60):
        super().__init__(app)
        self.default_limit = default_limit
        self.window_seconds = window_seconds
        self.requests: dict = defaultdict(list)
        self._lock = asyncio.Lock()
        self._cleanup_counter = 0
        
        # Endpoint-specific limits (stricter for auth endpoints)
        self.endpoint_limits = {
            "/auth/login": 10,
            "/auth/register": 5,
            "/auth/google": 10,
            "/chat": 30,
            "/documents/upload": 20,
        }
    
    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting in development (unless explicitly enabled)
        if os.getenv("ENVIRONMENT", "development") == "development":
            if not os.getenv("ENABLE_RATE_LIMIT_DEV", "").lower() == "true":
                return await call_next(request)
        
        # Get client IP
        client_ip = self._get_client_ip(request)
        path = request.url.path
        
        # Skip rate limiting for health check and static files
        if path in ["/", "/health", "/docs", "/redoc", "/openapi.json"]:
            return await call_next(request)
        
        # Get limit for this endpoint
        limit = self._get_limit_for_path(path)
        
        # Check rate limit
        key = f"{client_ip}:{path}"
        now = datetime.utcnow()
        window_start = now - timedelta(seconds=self.window_seconds)
        
        async with self._lock:
            # Periodic cleanup (every 100 requests)
            self._cleanup_counter += 1
            if self._cleanup_counter >= 100:
                await self._cleanup_old_entries(window_start)
                self._cleanup_counter = 0
            
            # Clean old requests for this key
            self.requests[key] = [
                req_time for req_time in self.requests[key]
                if req_time > window_start
            ]
            
            current_count = len(self.requests[key])
            
            # Check if over limit
            if current_count >= limit:
                logger.warning(
                    f"Rate limit exceeded: ip={client_ip}, path={path}, "
                    f"count={current_count}, limit={limit}"
                )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"İstek limiti aşıldı. {self.window_seconds} saniye sonra tekrar deneyin.",
                    headers={
                        "Retry-After": str(self.window_seconds),
                        "X-RateLimit-Limit": str(limit),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(int((window_start + timedelta(seconds=self.window_seconds)).timestamp())),
                        "code": "RATE_LIMIT_EXCEEDED",
                    },
                )
            
            # Record this request
            self.requests[key].append(now)
        
        response = await call_next(request)
        
        # Add rate limit headers to response
        remaining = limit - len(self.requests.get(key, []))
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, remaining))
        
        return response
    
    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address, considering proxy headers."""
        # Check for forwarded IP (behind proxy/load balancer)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first IP in the chain (original client)
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # Fall back to direct client IP
        return request.client.host if request.client else "unknown"
    
    def _get_limit_for_path(self, path: str) -> int:
        """Get the rate limit for a specific path."""
        for endpoint_prefix, endpoint_limit in self.endpoint_limits.items():
            if path.startswith(endpoint_prefix):
                return endpoint_limit
        return self.default_limit
    
    async def _cleanup_old_entries(self, cutoff_time: datetime):
        """Remove old entries from the request cache."""
        keys_to_delete = []
        for key, timestamps in self.requests.items():
            # Filter out old timestamps
            self.requests[key] = [t for t in timestamps if t > cutoff_time]
            # Mark empty keys for deletion
            if not self.requests[key]:
                keys_to_delete.append(key)
        
        # Delete empty keys
        for key in keys_to_delete:
            del self.requests[key]
        
        if keys_to_delete:
            logger.debug(f"Rate limit cleanup: removed {len(keys_to_delete)} empty keys")
