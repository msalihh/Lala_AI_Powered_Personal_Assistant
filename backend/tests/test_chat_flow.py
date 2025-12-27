"""
Kritik akış testi: Chat create → /chat ile mesaj → get messages

Bu test şunları doğrular:
1. Chat oluşturma çalışıyor mu?
2. /chat endpoint'i mesajı kaydediyor mu?
3. Mesajlar getirilebiliyor mu?
"""
import httpx
import uuid


def test_chat_create_chat_message_get_messages(base_url: str, auth_headers: dict):
    """
    Ne işe yarar?
    - Chat oluşturma, mesaj gönderme ve mesajları getirme akışını test eder.
    - /chat endpoint'inin message'ı DB'ye kaydettiğini doğrular.
    
    Olmazsa ne olur?
    - Chat oluşturulur ama mesajlar kaydedilmez (memory sistemi kırık)
    - Frontend'de mesajlar görünmez
    """
    # 1) Chat oluştur
    create = httpx.post(
        f"{base_url}/chats",
        headers=auth_headers,
        json={},  # title optional, otomatik oluşturulacak
        timeout=30,
    )
    assert create.status_code in (200, 201), \
        f"Create chat failed: {create.status_code} - {create.text[:200]}"
    chat = create.json()
    
    # chat_id extraction: bazı backend'ler id, bazıları _id döndürür
    chat_id = chat.get("id") or chat.get("_id")
    assert chat_id is not None, \
        f"Chat ID missing in response: {chat}"
    assert len(chat_id) > 0, "Chat ID is empty"

    # 2) /chat ile mesaj gönder (message save burada tetikleniyor olmalı)
    # KRİTİK: client_message_id zorunlu (UUID)
    client_message_id = str(uuid.uuid4())
    
    send = httpx.post(
        f"{base_url}/chat",
        headers=auth_headers,
        json={
            "chatId": chat_id,  # camelCase - backend'iniz chatId bekliyor
            "message": "Merhaba! Test mesajı.",
            "mode": "qa",
            "documentIds": [],  # Boş liste
            "client_message_id": client_message_id,  # ZORUNLU
        },
        timeout=60,  # /chat timeout 60: model çağrısı sürebilir
    )
    assert send.status_code in (200, 201), \
        f"/chat failed: {send.status_code} - {send.text[:500]}"
    
    # Response kontrolü
    response_data = send.json()
    assert "message" in response_data, \
        f"Response missing 'message' field: {response_data}"

    # 3) Mesajları getir
    msgs = httpx.get(
        f"{base_url}/chats/{chat_id}/messages",
        headers=auth_headers,
        timeout=30,
    )
    assert msgs.status_code == 200, \
        f"Get messages failed: {msgs.status_code} - {msgs.text[:200]}"
    
    # Response format kontrolü
    response = msgs.json()
    # Backend'iniz ChatMessagesResponse döndürüyor mu yoksa direkt list mi?
    if isinstance(response, dict) and "messages" in response:
        items = response["messages"]
    else:
        items = response
    
    # Beklenti: en az 1 kullanıcı mesajı kaydedilmiş olmalı
    assert isinstance(items, list), \
        f"Expected list, got {type(items)}: {items}"
    assert len(items) >= 1, \
        f"Expected at least 1 message, got {len(items)}"
    
    # İlk mesajın kullanıcı mesajı olduğunu doğrula
    first_msg = items[0]
    assert first_msg.get("role") == "user", \
        f"First message should be 'user', got: {first_msg.get('role')}"
    assert "content" in first_msg, \
        f"Message missing 'content' field: {first_msg}"
    assert "test mesajı" in first_msg["content"].lower(), \
        f"Message content mismatch: {first_msg.get('content')}"

