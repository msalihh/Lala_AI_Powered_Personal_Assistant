"""
Vector Store Extension

Provides abstraction layer for vector databases.
Default: Chroma (existing implementation)
"""

from app.extensions.vector_store.base import VectorStoreBase, get_vector_store

__all__ = ["VectorStoreBase", "get_vector_store"]
