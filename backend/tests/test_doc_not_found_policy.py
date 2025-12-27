"""
Test doc-not-found policy.
Tests that "Dokümanlarda bu bilgi yok" is only shown when appropriate.
"""
import pytest
from app.rag.intent import classify_intent, _detect_doc_grounded
from app.rag.decision import decide_context


@pytest.mark.asyncio
async def test_non_doc_question_no_retrieval_should_not_show_doc_not_found(test_user_id):
    """
    Test: Non-doc question + empty retrieval 
    => must NOT contain "Dokümanlarda"
    """
    query = "Python nedir?"
    document_ids = []
    
    # Classify intent
    intent_result = classify_intent(query, mode="qa", document_ids=document_ids)
    
    # Should not be doc-grounded
    assert intent_result["doc_grounded"] is False, "Non-doc question should not be doc-grounded"
    assert intent_result["doc_grounded_reason"] == "no_document_reference"


@pytest.mark.asyncio
async def test_doc_grounded_empty_retrieval_should_show_doc_not_found(test_user_id, test_chat_id):
    """
    Test: Doc-grounded query + empty retrieval 
    => must contain doc-not-found flag
    """
    query = "bu belgede ne yazıyor?"
    document_ids = ["fake_doc_id"]  # Explicit document reference
    
    # Classify intent
    intent_result = classify_intent(query, mode="qa", document_ids=document_ids)
    
    # Should be doc-grounded
    assert intent_result["doc_grounded"] is True, "Doc reference query should be doc-grounded"
    
    # Test decision (with empty user_document_ids to simulate no hits)
    rag_result = await decide_context(
        query=query,
        selected_doc_ids=document_ids,
        user_id=test_user_id,
        user_document_ids=[],  # Empty = no documents available
        found_documents_for_fallback=[],
        mode="qa",
        request_id="test_request"
    )
    
    # Should have doc_not_found flag
    assert rag_result.get("doc_not_found") is True, "Doc-grounded query with no hits should have doc_not_found=True"


@pytest.mark.asyncio
async def test_doc_reference_patterns():
    """Test that doc reference patterns are detected."""
    doc_queries = [
        "bu belgede ne var?",
        "bu dokümanda ne yazıyor?",
        "bu dosyada hangi bilgiler var?",
        "yüklediğim pdf'de ne var?",
    ]
    
    for query in doc_queries:
        result = _detect_doc_grounded(query, document_ids=None)
        assert result["doc_grounded"] is True, f"'{query}' should be detected as doc-grounded"
        assert result["reason"] == "query_references_document"


@pytest.mark.asyncio
async def test_explicit_document_ids_makes_doc_grounded():
    """Test that explicit document_ids make query doc-grounded."""
    query = "bu nedir?"  # Generic query
    document_ids = ["doc1", "doc2"]
    
    result = _detect_doc_grounded(query, document_ids=document_ids)
    assert result["doc_grounded"] is True, "Explicit document_ids should make query doc-grounded"
    assert result["reason"] == "explicit_document_ids"

