"""
LLM Call Tracer

Provides decorators for tracing LLM calls and RAG searches.
When observability is disabled, decorators are NOPs (no overhead).
"""

import functools
import time
import json
import logging
from typing import Any, Callable, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


def _is_enabled() -> bool:
    """Check if observability is enabled (lazy import to avoid circular deps)."""
    try:
        from app.extensions.config import is_observability_enabled
        return is_observability_enabled()
    except ImportError:
        return False


def _get_exporter():
    """Get the configured exporter (lazy import)."""
    try:
        from app.extensions.config import get_extension_config
        config = get_extension_config()
        return config.observability_exporter, config.observability_log_file
    except ImportError:
        return "console", "logs/llm_traces.jsonl"


def _emit_trace(trace_data: Dict[str, Any]) -> None:
    """Emit trace to configured exporter."""
    exporter, log_file = _get_exporter()
    
    if exporter == "console":
        logger.info(f"[TRACE] {json.dumps(trace_data, default=str)}")
    elif exporter == "json_file":
        try:
            import os
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(trace_data, default=str) + "\n")
        except Exception as e:
            logger.warning(f"[TRACE] Failed to write to file: {e}")
    # otlp exporter would go here


def trace_llm_call(func: Optional[Callable] = None, *, name: str = None):
    """
    Decorator to trace LLM calls.
    
    Usage:
        @trace_llm_call
        async def call_llm(...): ...
        
        @trace_llm_call(name="chat_completion")
        async def my_llm_call(...): ...
    
    When observability is DISABLED, this is a NOP (zero overhead).
    """
    def decorator(fn: Callable) -> Callable:
        # Check once at decoration time (not call time) for performance
        # But re-check at call time to support runtime config changes
        
        @functools.wraps(fn)
        async def async_wrapper(*args, **kwargs):
            if not _is_enabled():
                return await fn(*args, **kwargs)
            
            trace_name = name or fn.__name__
            start_time = time.time()
            error = None
            result = None
            
            try:
                result = await fn(*args, **kwargs)
                return result
            except Exception as e:
                error = str(e)
                raise
            finally:
                duration_ms = (time.time() - start_time) * 1000
                trace_data = {
                    "type": "llm_call",
                    "name": trace_name,
                    "timestamp": datetime.utcnow().isoformat(),
                    "duration_ms": round(duration_ms, 2),
                    "success": error is None,
                    "error": error,
                    # Extract model from kwargs if present
                    "model": kwargs.get("model", "unknown"),
                }
                _emit_trace(trace_data)
        
        @functools.wraps(fn)
        def sync_wrapper(*args, **kwargs):
            if not _is_enabled():
                return fn(*args, **kwargs)
            
            trace_name = name or fn.__name__
            start_time = time.time()
            error = None
            
            try:
                result = fn(*args, **kwargs)
                return result
            except Exception as e:
                error = str(e)
                raise
            finally:
                duration_ms = (time.time() - start_time) * 1000
                trace_data = {
                    "type": "llm_call",
                    "name": trace_name,
                    "timestamp": datetime.utcnow().isoformat(),
                    "duration_ms": round(duration_ms, 2),
                    "success": error is None,
                    "error": error,
                    "model": kwargs.get("model", "unknown"),
                }
                _emit_trace(trace_data)
        
        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(fn):
            return async_wrapper
        return sync_wrapper
    
    # Handle both @trace_llm_call and @trace_llm_call(name="...")
    if func is not None:
        return decorator(func)
    return decorator


def trace_rag_search(func: Optional[Callable] = None, *, name: str = None):
    """
    Decorator to trace RAG searches.
    
    Usage:
        @trace_rag_search
        async def search_documents(...): ...
    
    When observability is DISABLED, this is a NOP.
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def async_wrapper(*args, **kwargs):
            if not _is_enabled():
                return await fn(*args, **kwargs)
            
            trace_name = name or fn.__name__
            start_time = time.time()
            error = None
            result_count = 0
            
            try:
                result = await fn(*args, **kwargs)
                if isinstance(result, (list, tuple)):
                    result_count = len(result)
                return result
            except Exception as e:
                error = str(e)
                raise
            finally:
                duration_ms = (time.time() - start_time) * 1000
                trace_data = {
                    "type": "rag_search",
                    "name": trace_name,
                    "timestamp": datetime.utcnow().isoformat(),
                    "duration_ms": round(duration_ms, 2),
                    "success": error is None,
                    "error": error,
                    "result_count": result_count,
                    "query": kwargs.get("query", args[0] if args else "unknown")[:100],
                }
                _emit_trace(trace_data)
        
        @functools.wraps(fn)
        def sync_wrapper(*args, **kwargs):
            if not _is_enabled():
                return fn(*args, **kwargs)
            
            trace_name = name or fn.__name__
            start_time = time.time()
            error = None
            result_count = 0
            
            try:
                result = fn(*args, **kwargs)
                if isinstance(result, (list, tuple)):
                    result_count = len(result)
                return result
            except Exception as e:
                error = str(e)
                raise
            finally:
                duration_ms = (time.time() - start_time) * 1000
                trace_data = {
                    "type": "rag_search",
                    "name": trace_name,
                    "timestamp": datetime.utcnow().isoformat(),
                    "duration_ms": round(duration_ms, 2),
                    "success": error is None,
                    "error": error,
                    "result_count": result_count,
                }
                _emit_trace(trace_data)
        
        import asyncio
        if asyncio.iscoroutinefunction(fn):
            return async_wrapper
        return sync_wrapper
    
    if func is not None:
        return decorator(func)
    return decorator
