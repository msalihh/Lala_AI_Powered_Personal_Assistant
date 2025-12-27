"""
Kritik akış testi: /chat endpoint response format

Bu test şunları doğrular:
1. /chat endpoint'i doğru response formatı döndürüyor mu?
2. Response'da gerekli field'lar var mı?
3. Streaming olmasa bile response geçerli mi?

Not: Backend'iniz SSE streaming kullanmıyor, normal JSON response döndürüyor.
Bu test response formatını doğrular.
"""
import httpx
import uuid


def test_chat_response_format(base_url: str, auth_headers: dict):
    """
    Ne işe yarar?
    - /chat endpoint'inin doğru response formatı döndürdüğünü doğrular.
    - Frontend'in beklediği field'ların var olduğunu garanti eder.
    
    Olmazsa ne olur?
    - Frontend response parse edemez
    - UI'da hata mesajları görünür
    - Chat akışı kırılır
    """
    # 1) Chat oluştur
    create = httpx.post(
        f"{base_url}/chats",
        headers=auth_headers,
        json={},
        timeout=30,
    )
    assert create.status_code in (200, 201)
    chat = create.json()
    chat_id = chat.get("id") or chat.get("_id")
    assert chat_id is not None

    # 2) /chat ile mesaj gönder
    client_message_id = str(uuid.uuid4())
    send = httpx.post(
        f"{base_url}/chat",
        headers=auth_headers,
        json={
            "chatId": chat_id,
            "message": "Response format test",
            "mode": "qa",
            "documentIds": [],
            "client_message_id": client_message_id,
        },
        timeout=60,  # Model çağrısı sürebilir
    )
    assert send.status_code in (200, 201), \
        f"/chat failed: {send.status_code} - {send.text[:500]}"
    
    # 3) Response format kontrolü
    response_data = send.json()
    
    # Zorunlu field'lar
    assert "message" in response_data, \
        f"Response missing 'message' field: {response_data}"
    assert isinstance(response_data["message"], str), \
        f"Message should be string, got {type(response_data['message'])}"
    assert len(response_data["message"]) > 0, \
        "Message should not be empty"
    
    # Opsiyonel field'lar (varsa kontrol et)
    if "role" in response_data:
        assert response_data["role"] == "assistant", \
            f"Role should be 'assistant', got {response_data.get('role')}"
    
    # Sources (RAG kullanıldıysa - opsiyonel, None olabilir)
    if "sources" in response_data and response_data["sources"] is not None:
        assert isinstance(response_data["sources"], list), \
            f"Sources should be list or None, got {type(response_data['sources'])}"
    
    # Debug info (varsa)
    if "debug_info" in response_data:
        assert isinstance(response_data["debug_info"], dict), \
            f"Debug info should be dict, got {type(response_data['debug_info'])}"
    
    # 4) Content-Type kontrolü (JSON olmalı)
    content_type = send.headers.get("content-type", "").lower()
    assert "application/json" in content_type, \
        f"Expected JSON response, got content-type: {content_type}"
    
    # 5) Response body geçerli JSON mu?
    assert isinstance(response_data, dict), \
        f"Response should be dict, got {type(response_data)}"

