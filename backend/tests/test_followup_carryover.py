"""
Test follow-up carryover functionality.
Tests that follow-up triggers correctly inherit last topic.
"""
import pytest
from app.memory.carryover import resolve_carryover, detect_followup_trigger
from app.memory.state import ConversationState, update_conversation_state, get_conversation_state


@pytest.mark.asyncio
async def test_carryover_karekok_to_uzun_soru_coz(test_db, test_user_id, test_chat_id):
    """
    Test: Last topic is "karekök", next message "uzun soru çöz" 
    => rewritten should include karekök
    """
    # Setup: Set last topic to karekök
    state = ConversationState(
        last_topic="karekök",
        last_user_question="karekök nedir?",
        last_domain="math",
        unresolved_followup=False
    )
    await update_conversation_state(test_user_id, test_chat_id, state)
    
    # Test: Follow-up trigger
    user_message = "uzun soru çöz"
    resolved, carryover_used = await resolve_carryover(
        user_id=test_user_id,
        chat_id=test_chat_id,
        user_message=user_message
    )
    
    # Assertions
    assert carryover_used is True, "Carryover should be used"
    assert "karekök" in resolved.lower(), f"Resolved message should include 'karekök', got: {resolved}"
    assert resolved != user_message, "Message should be rewritten"


@pytest.mark.asyncio
async def test_carryover_detects_followup_triggers():
    """Test that follow-up triggers are detected correctly."""
    triggers = [
        "devam",
        "uzun çöz",
        "uzun soru çöz",
        "1 tane daha",
        "bir tane daha",
        "bunu",
        "şunu",
        "aynısı",
        "detaylandır",
    ]
    
    for trigger in triggers:
        assert detect_followup_trigger(trigger) is True, f"'{trigger}' should be detected as follow-up"


@pytest.mark.asyncio
async def test_carryover_no_previous_context(test_db, test_user_id, test_chat_id):
    """
    Test: Follow-up trigger but no previous context
    => should return original message
    """
    # No previous state set
    
    user_message = "uzun soru çöz"
    resolved, carryover_used = await resolve_carryover(
        user_id=test_user_id,
        chat_id=test_chat_id,
        user_message=user_message
    )
    
    # Should not use carryover if no previous context
    assert carryover_used is False or resolved == user_message, "Should not carry over without context"


@pytest.mark.asyncio
async def test_carryover_topic_change(test_db, test_user_id, test_chat_id):
    """
    Test: Last topic is "karekök", next message introduces new topic "python"
    => should NOT carry over
    """
    # Setup: Set last topic to karekök
    state = ConversationState(
        last_topic="karekök",
        last_user_question="karekök nedir?",
        last_domain="math",
        unresolved_followup=False
    )
    await update_conversation_state(test_user_id, test_chat_id, state)
    
    # Test: New topic
    user_message = "python nedir?"
    resolved, carryover_used = await resolve_carryover(
        user_id=test_user_id,
        chat_id=test_chat_id,
        user_message=user_message
    )
    
    # Should not carry over when topic changes
    assert carryover_used is False, "Should not carry over when topic changes"
    assert resolved == user_message, "Message should not be rewritten"

