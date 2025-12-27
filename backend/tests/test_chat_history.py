"""
Test suite for ChatGPT-like chat history architecture.

Tests:
1. test_create_chat - Create empty chat
2. test_send_message - Send user + assistant message
3. test_list_chats - List chats with pagination
4. test_get_messages - Get messages with cursor
5. test_delete_chat - Soft delete chat
6. test_ownership - User cannot access other user's chat
7. test_idempotency - Duplicate client_message_id handling
"""
import httpx
import uuid
import pytest
from bson import ObjectId


def test_create_chat(base_url: str, auth_headers: dict):
    """Test creating an empty chat."""
    response = httpx.post(
        f"{base_url}/chats",
        headers=auth_headers,
        json={},
        timeout=30,
    )
    assert response.status_code == 201, f"Create chat failed: {response.status_code} - {response.text[:200]}"
    
    chat = response.json()
    assert "id" in chat, f"Chat missing 'id' field: {chat}"
    assert "title" in chat, f"Chat missing 'title' field: {chat}"
    assert "created_at" in chat, f"Chat missing 'created_at' field: {chat}"
    assert "updated_at" in chat, f"Chat missing 'updated_at' field: {chat}"
    assert "user_id" in chat, f"Chat missing 'user_id' field: {chat}"
    
    # Validate ObjectId format
    chat_id = chat["id"]
    assert ObjectId.is_valid(chat_id), f"Invalid chat_id format: {chat_id}"
    
    # Chat should appear in list immediately (even if empty)
    list_response = httpx.get(
        f"{base_url}/chats",
        headers=auth_headers,
        timeout=30,
    )
    assert list_response.status_code == 200
    chats = list_response.json()
    assert isinstance(chats, list)
    assert any(c["id"] == chat_id for c in chats), "New chat should appear in list"


def test_send_message(base_url: str, auth_headers: dict):
    """Test sending a message in a chat."""
    # Create chat
    create_response = httpx.post(
        f"{base_url}/chats",
        headers=auth_headers,
        json={},
        timeout=30,
    )
    assert create_response.status_code == 201
    chat_id = create_response.json()["id"]
    
    # Send message using new endpoint
    client_message_id = str(uuid.uuid4())
    send_response = httpx.post(
        f"{base_url}/chats/{chat_id}/messages",
        headers=auth_headers,
        json={
            "message": "Test message",
            "client_message_id": client_message_id,
            "mode": "qa",
        },
        timeout=30,
    )
    assert send_response.status_code == 200, f"Send message failed: {send_response.status_code} - {send_response.text[:200]}"
    
    message_response = send_response.json()
    assert "message_id" in message_response
    assert "role" in message_response
    assert "content" in message_response
    assert message_response["role"] == "user"
    
    # Verify message is saved
    get_response = httpx.get(
        f"{base_url}/chats/{chat_id}/messages",
        headers=auth_headers,
        timeout=30,
    )
    assert get_response.status_code == 200
    messages_data = get_response.json()
    assert "messages" in messages_data
    messages = messages_data["messages"]
    assert len(messages) >= 1
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Test message"


def test_list_chats(base_url: str, auth_headers: dict):
    """Test listing chats with pagination."""
    # Create multiple chats
    chat_ids = []
    for i in range(3):
        create_response = httpx.post(
            f"{base_url}/chats",
            headers=auth_headers,
            json={"title": f"Test Chat {i}"},
            timeout=30,
        )
        assert create_response.status_code == 201
        chat_ids.append(create_response.json()["id"])
    
    # List chats
    list_response = httpx.get(
        f"{base_url}/chats",
        headers=auth_headers,
        timeout=30,
    )
    assert list_response.status_code == 200
    chats = list_response.json()
    assert isinstance(chats, list)
    assert len(chats) >= 3, f"Expected at least 3 chats, got {len(chats)}"
    
    # Verify all created chats are in the list
    returned_ids = [c["id"] for c in chats]
    for chat_id in chat_ids:
        assert chat_id in returned_ids, f"Chat {chat_id} not found in list"
    
    # Verify sorting (newest first by updated_at)
    if len(chats) > 1:
        for i in range(len(chats) - 1):
            current_updated = chats[i]["updated_at"]
            next_updated = chats[i + 1]["updated_at"]
            # Should be sorted descending (newest first)
            assert current_updated >= next_updated, "Chats should be sorted by updated_at DESC"


def test_get_messages(base_url: str, auth_headers: dict):
    """Test getting messages with cursor pagination."""
    # Create chat
    create_response = httpx.post(
        f"{base_url}/chats",
        headers=auth_headers,
        json={},
        timeout=30,
    )
    assert create_response.status_code == 201
    chat_id = create_response.json()["id"]
    
    # Send multiple messages
    for i in range(5):
        client_message_id = str(uuid.uuid4())
        send_response = httpx.post(
            f"{base_url}/chats/{chat_id}/messages",
            headers=auth_headers,
            json={
                "message": f"Message {i}",
                "client_message_id": client_message_id,
                "mode": "qa",
            },
            timeout=30,
        )
        assert send_response.status_code == 200
    
    # Get first page (limit=3)
    first_page = httpx.get(
        f"{base_url}/chats/{chat_id}/messages?limit=3",
        headers=auth_headers,
        timeout=30,
    )
    assert first_page.status_code == 200
    first_data = first_page.json()
    assert "messages" in first_data
    assert "cursor" in first_data
    assert "has_more" in first_data
    assert len(first_data["messages"]) == 3
    assert first_data["has_more"] is True
    
    # Get next page using cursor
    cursor = first_data["cursor"]
    assert cursor is not None
    second_page = httpx.get(
        f"{base_url}/chats/{chat_id}/messages?limit=3&cursor={cursor}",
        headers=auth_headers,
        timeout=30,
    )
    assert second_page.status_code == 200
    second_data = second_page.json()
    assert len(second_data["messages"]) >= 2  # At least 2 more messages
    assert second_data["messages"][0]["content"] != first_data["messages"][0]["content"]


def test_delete_chat(base_url: str, auth_headers: dict):
    """Test soft deleting a chat."""
    # Create chat
    create_response = httpx.post(
        f"{base_url}/chats",
        headers=auth_headers,
        json={},
        timeout=30,
    )
    assert create_response.status_code == 201
    chat_id = create_response.json()["id"]
    
    # Send a message
    client_message_id = str(uuid.uuid4())
    send_response = httpx.post(
        f"{base_url}/chats/{chat_id}/messages",
        headers=auth_headers,
        json={
            "message": "Test message",
            "client_message_id": client_message_id,
            "mode": "qa",
        },
        timeout=30,
    )
    assert send_response.status_code == 200
    
    # Soft delete chat
    delete_response = httpx.delete(
        f"{base_url}/chats/{chat_id}",
        headers=auth_headers,
        timeout=30,
    )
    assert delete_response.status_code == 204
    
    # Chat should not appear in list
    list_response = httpx.get(
        f"{base_url}/chats",
        headers=auth_headers,
        timeout=30,
    )
    assert list_response.status_code == 200
    chats = list_response.json()
    assert not any(c["id"] == chat_id for c in chats), "Deleted chat should not appear in list"
    
    # Try to get chat - should return 404
    get_response = httpx.get(
        f"{base_url}/chats/{chat_id}",
        headers=auth_headers,
        timeout=30,
    )
    assert get_response.status_code == 404


def test_ownership(base_url: str, auth_headers: dict, auth_headers_user2: dict):
    """Test that users cannot access each other's chats."""
    # User 1 creates chat
    create_response = httpx.post(
        f"{base_url}/chats",
        headers=auth_headers,
        json={},
        timeout=30,
    )
    assert create_response.status_code == 201
    chat_id = create_response.json()["id"]
    
    # User 2 tries to access User 1's chat - should return 404 or 403
    get_response = httpx.get(
        f"{base_url}/chats/{chat_id}",
        headers=auth_headers_user2,
        timeout=30,
    )
    assert get_response.status_code in [403, 404], f"Expected 403 or 404, got {get_response.status_code}"
    
    # User 2 tries to get messages - should return 404 or 403
    messages_response = httpx.get(
        f"{base_url}/chats/{chat_id}/messages",
        headers=auth_headers_user2,
        timeout=30,
    )
    assert messages_response.status_code in [403, 404], f"Expected 403 or 404, got {messages_response.status_code}"


def test_idempotency(base_url: str, auth_headers: dict):
    """Test that duplicate client_message_id is handled correctly."""
    # Create chat
    create_response = httpx.post(
        f"{base_url}/chats",
        headers=auth_headers,
        json={},
        timeout=30,
    )
    assert create_response.status_code == 201
    chat_id = create_response.json()["id"]
    
    # Send message with client_message_id
    client_message_id = str(uuid.uuid4())
    send_response1 = httpx.post(
        f"{base_url}/chats/{chat_id}/messages",
        headers=auth_headers,
        json={
            "message": "Test message",
            "client_message_id": client_message_id,
            "mode": "qa",
        },
        timeout=30,
    )
    assert send_response1.status_code == 200
    message_id1 = send_response1.json()["message_id"]
    
    # Send same message again with same client_message_id
    send_response2 = httpx.post(
        f"{base_url}/chats/{chat_id}/messages",
        headers=auth_headers,
        json={
            "message": "Test message",
            "client_message_id": client_message_id,
            "mode": "qa",
        },
        timeout=30,
    )
    # Should either return same message (idempotent) or 409
    assert send_response2.status_code in [200, 409]
    
    if send_response2.status_code == 200:
        # If 200, should return same message_id
        message_id2 = send_response2.json()["message_id"]
        assert message_id1 == message_id2, "Duplicate request should return same message_id"
    
    # Verify only one message exists
    get_response = httpx.get(
        f"{base_url}/chats/{chat_id}/messages",
        headers=auth_headers,
        timeout=30,
    )
    assert get_response.status_code == 200
    messages_data = get_response.json()
    messages = messages_data["messages"]
    user_messages = [m for m in messages if m["role"] == "user" and m.get("client_message_id") == client_message_id]
    assert len(user_messages) == 1, f"Expected 1 message with client_message_id, got {len(user_messages)}"

