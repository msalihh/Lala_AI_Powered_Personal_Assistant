"""
HACE Extensions Module

This module provides optional, plug-and-play extensions for HACE.
All extensions are disabled by default and can be enabled via config.

Available Extensions:
- observability: LLM call tracing and metrics
- ocr: Scanned PDF text extraction
- vector_store: Vector DB abstraction (Chroma/Qdrant)
- tools: Tool routing and agent capabilities
- versioning: Ingestion versioning and re-index
- workflows: Declarative workflow definitions
"""

from app.extensions.config import ExtensionConfig, get_extension_config

__all__ = ["ExtensionConfig", "get_extension_config"]
