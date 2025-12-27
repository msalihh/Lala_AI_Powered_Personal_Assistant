"""
Test context budget management.
Tests that context builder truncates without breaking.
"""
import pytest
from app.rag.context_builder import build_rag_context, manage_context_budget
from app.utils import estimate_tokens


def test_context_budget_truncates_chunks():
    """Test that context builder truncates when budget is exceeded."""
    # Create many chunks that exceed budget
    chunks = [
        {
            "document_id": "doc1",
            "original_filename": "test.pdf",
            "chunk_index": i,
            "text": "This is a test chunk. " * 100,  # Large chunk
            "score": 0.9 - (i * 0.01),
            "distance": 0.1 + (i * 0.01)
        }
        for i in range(20)  # 20 chunks, should exceed budget
    ]
    
    # Build context with small budget
    result = build_rag_context(
        retrieved_chunks=chunks,
        max_tokens=500,  # Small budget
        include_sources=True
    )
    
    # Should have excluded some chunks
    assert result["chunks_excluded"] > 0, "Should exclude chunks when budget exceeded"
    assert result["used_tokens"] <= 500, "Should respect token budget"
    assert result["chunks_included"] < len(chunks), "Should include fewer chunks than total"


def test_context_budget_manages_total_budget():
    """Test that total context budget is managed across components."""
    system_prompt = "You are a helpful assistant. " * 50  # ~500 tokens
    chat_history = [
        {"role": "user", "content": "Hello " * 200},  # ~260 tokens
        {"role": "assistant", "content": "Hi " * 200},  # ~260 tokens
    ]
    rag_context = "Context " * 500  # ~650 tokens
    user_message = "Question " * 50  # ~65 tokens
    
    # Total: ~1735 tokens, budget: 1000
    result = manage_context_budget(
        system_prompt=system_prompt,
        chat_history=chat_history,
        rag_context=rag_context,
        user_message=user_message,
        max_total_tokens=1000
    )
    
    # Should truncate to fit budget
    total_tokens = result["token_breakdown"]["total"]
    assert total_tokens <= 1000, f"Total tokens ({total_tokens}) should be within budget (1000)"
    
    # System prompt and user message should be preserved (priority)
    assert len(result["system_prompt"]) > 0, "System prompt should be preserved"
    assert len(result["user_message"]) > 0, "User message should be preserved"


def test_context_budget_preserves_priority_components():
    """Test that priority components (system, user) are preserved."""
    system_prompt = "System prompt"
    chat_history = [{"role": "user", "content": "History " * 1000}]  # Very large
    rag_context = "RAG " * 1000  # Very large
    user_message = "User question"
    
    result = manage_context_budget(
        system_prompt=system_prompt,
        chat_history=chat_history,
        rag_context=rag_context,
        user_message=user_message,
        max_total_tokens=100  # Very small budget
    )
    
    # System and user should be preserved
    assert result["system_prompt"] == system_prompt, "System prompt should be preserved"
    assert result["user_message"] == user_message, "User message should be preserved"
    
    # History or RAG should be truncated
    assert len(result["chat_history"]) < len(chat_history) or \
           len(result["rag_context"]) < len(rag_context), \
           "History or RAG should be truncated to fit budget"

