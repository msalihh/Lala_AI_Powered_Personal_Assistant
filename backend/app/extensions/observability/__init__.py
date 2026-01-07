"""
Observability Extension

Provides LLM call tracing and metrics.
Default: DISABLED (NOP decorators)
"""

from app.extensions.observability.tracer import trace_llm_call, trace_rag_search

__all__ = ["trace_llm_call", "trace_rag_search"]
