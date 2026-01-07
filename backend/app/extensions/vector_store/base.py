"""
Vector Store Base Interface and Factory

Provides abstract interface for vector databases and factory function.
Default: Wraps existing Chroma implementation.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class VectorStoreBase(ABC):
    """Abstract base class for vector stores."""
    
    name: str = "base"
    
    @abstractmethod
    def add_documents(
        self,
        ids: List[str],
        embeddings: List[List[float]],
        documents: List[str],
        metadatas: List[Dict[str, Any]]
    ) -> None:
        """Add documents with embeddings to the store."""
        pass
    
    @abstractmethod
    def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for similar documents.
        
        Returns list of dicts with keys: id, document, metadata, score
        """
        pass
    
    @abstractmethod
    def delete(self, ids: List[str]) -> None:
        """Delete documents by ID."""
        pass
    
    @abstractmethod
    def count(self) -> int:
        """Get total document count."""
        pass


class ChromaVectorStore(VectorStoreBase):
    """
    Chroma vector store implementation.
    Wraps existing app/rag/vector_store.py functionality.
    """
    
    name = "chroma"
    
    def __init__(self):
        self._collection = None
    
    def _get_collection(self):
        """Lazy initialization of Chroma collection."""
        if self._collection is None:
            # Import existing Chroma setup
            from app.rag.vector_store import get_collection
            self._collection = get_collection()
        return self._collection
    
    def add_documents(
        self,
        ids: List[str],
        embeddings: List[List[float]],
        documents: List[str],
        metadatas: List[Dict[str, Any]]
    ) -> None:
        collection = self._get_collection()
        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas
        )
    
    def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        collection = self._get_collection()
        
        # Build Chroma where clause from filters
        where = None
        if filters:
            where = filters
        
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"]
        )
        
        # Convert Chroma format to standard format
        output = []
        if results and results.get("ids") and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                output.append({
                    "id": doc_id,
                    "document": results["documents"][0][i] if results.get("documents") else "",
                    "metadata": results["metadatas"][0][i] if results.get("metadatas") else {},
                    "score": 1 - results["distances"][0][i] if results.get("distances") else 0,
                })
        return output
    
    def delete(self, ids: List[str]) -> None:
        collection = self._get_collection()
        collection.delete(ids=ids)
    
    def count(self) -> int:
        collection = self._get_collection()
        return collection.count()


class MockVectorStore(VectorStoreBase):
    """In-memory mock vector store for testing."""
    
    name = "mock"
    
    def __init__(self):
        self._docs: Dict[str, Dict] = {}
    
    def add_documents(
        self,
        ids: List[str],
        embeddings: List[List[float]],
        documents: List[str],
        metadatas: List[Dict[str, Any]]
    ) -> None:
        for i, doc_id in enumerate(ids):
            self._docs[doc_id] = {
                "embedding": embeddings[i],
                "document": documents[i],
                "metadata": metadatas[i],
            }
    
    def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        # Simple cosine similarity for mock
        import math
        
        def cosine_sim(a, b):
            dot = sum(x * y for x, y in zip(a, b))
            norm_a = math.sqrt(sum(x * x for x in a))
            norm_b = math.sqrt(sum(x * x for x in b))
            return dot / (norm_a * norm_b) if norm_a and norm_b else 0
        
        scored = []
        for doc_id, doc in self._docs.items():
            # Apply filters
            if filters:
                metadata = doc["metadata"]
                match = all(metadata.get(k) == v for k, v in filters.items())
                if not match:
                    continue
            
            score = cosine_sim(query_embedding, doc["embedding"])
            scored.append((doc_id, doc, score))
        
        # Sort by score descending
        scored.sort(key=lambda x: x[2], reverse=True)
        
        return [
            {"id": doc_id, "document": doc["document"], "metadata": doc["metadata"], "score": score}
            for doc_id, doc, score in scored[:top_k]
        ]
    
    def delete(self, ids: List[str]) -> None:
        for doc_id in ids:
            self._docs.pop(doc_id, None)
    
    def count(self) -> int:
        return len(self._docs)


# Singleton instance
_vector_store: Optional[VectorStoreBase] = None


def get_vector_store() -> VectorStoreBase:
    """
    Get configured vector store.
    Returns Chroma by default.
    """
    global _vector_store
    
    if _vector_store is not None:
        return _vector_store
    
    try:
        from app.extensions.config import get_extension_config
        config = get_extension_config()
        backend = config.vector_store_backend
    except ImportError:
        backend = "chroma"
    
    if backend == "chroma":
        logger.info("[VECTOR_STORE] Using Chroma (default)")
        _vector_store = ChromaVectorStore()
    elif backend == "qdrant":
        # Qdrant implementation would go here
        logger.warning("[VECTOR_STORE] Qdrant not yet implemented, using Chroma")
        _vector_store = ChromaVectorStore()
    elif backend == "mock":
        logger.info("[VECTOR_STORE] Using Mock (testing)")
        _vector_store = MockVectorStore()
    else:
        logger.info("[VECTOR_STORE] Unknown backend, using Chroma")
        _vector_store = ChromaVectorStore()
    
    return _vector_store
