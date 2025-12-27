"""
E2E Test: Tam kullanıcı akışı

Bu test gerçek kullanıcı senaryosunu simüle eder:
1. Kullanıcı kaydı
2. Giriş yapma
3. Chat oluşturma
4. Doküman yükleme
5. Chat'te doküman kullanarak soru sorma
6. Mesajları görüntüleme
7. Chat silme

Not: Bu test backend API'yi test eder, frontend UI'ı test etmez.
Frontend testleri için Playwright/Selenium kullanılmalı.
"""
import io
import httpx
import uuid
import pytest


@pytest.mark.integration
def test_full_user_flow(base_url: str, auth_headers: dict):
    """
    Ne işe yarar?
    - Gerçek kullanıcı senaryosunu end-to-end test eder.
    - Tüm sistemin birlikte çalıştığını doğrular.
    
    Olmazsa ne olur?
    - Sistem parçaları ayrı ayrı çalışır ama birlikte çalışmaz
    - Kullanıcı deneyimi kırılır
    """
    # 1) Chat oluştur
    create_chat = httpx.post(
        f"{base_url}/chats",
        headers=auth_headers,
        json={},
        timeout=30,
    )
    assert create_chat.status_code in (200, 201)
    chat = create_chat.json()
    chat_id = chat.get("id") or chat.get("_id")
    assert chat_id is not None
    
    # 2) Doküman yükle (chat'e bağlı)
    file_content = b"This is a test document. It contains information about Python programming language."
    files = {
        "file": ("test_doc.txt", io.BytesIO(file_content), "text/plain")
    }
    
    upload = httpx.post(
        f"{base_url}/documents/upload",
        headers=auth_headers,
        files=files,
        data={"chat_id": chat_id},
        timeout=60,
    )
    assert upload.status_code in (200, 201)
    doc = upload.json()
    doc_id = doc.get("documentId") or doc.get("id")
    assert doc_id is not None
    
    # 3) Chat'te doküman kullanarak soru sor
    client_message_id = str(uuid.uuid4())
    chat_request = httpx.post(
        f"{base_url}/chat",
        headers=auth_headers,
        json={
            "chatId": chat_id,
            "message": "What does this document say about Python?",
            "mode": "qa",
            "documentIds": [doc_id],  # Dokümanı kullan
            "client_message_id": client_message_id,
        },
        timeout=60,
    )
    assert chat_request.status_code in (200, 201)
    chat_response = chat_request.json()
    assert "message" in chat_response
    assert len(chat_response["message"]) > 0
    
    # RAG kullanıldıysa sources olmalı
    if chat_response.get("sources"):
        assert len(chat_response["sources"]) > 0
        assert chat_response["sources"][0].get("documentId") == doc_id
    
    # 4) Mesajları getir
    messages = httpx.get(
        f"{base_url}/chats/{chat_id}/messages",
        headers=auth_headers,
        timeout=30,
    )
    assert messages.status_code == 200
    msgs_data = messages.json()
    msg_list = msgs_data.get("messages", []) if isinstance(msgs_data, dict) else msgs_data
    assert len(msg_list) >= 2  # En az user + assistant mesajı
    
    # 5) Chat listesinde görünüyor mu?
    chat_list = httpx.get(
        f"{base_url}/chats",
        headers=auth_headers,
        timeout=30,
    )
    assert chat_list.status_code == 200
    chats = chat_list.json()
    assert isinstance(chats, list)
    assert any(c.get("id") == chat_id or c.get("_id") == chat_id for c in chats)
    
    # 6) Doküman listede görünüyor mu?
    doc_list = httpx.get(
        f"{base_url}/documents",
        headers=auth_headers,
        timeout=30,
    )
    assert doc_list.status_code == 200
    docs = doc_list.json()
    assert isinstance(docs, list)
    assert any(d.get("id") == doc_id or d.get("_id") == doc_id or d.get("documentId") == doc_id for d in docs)
    
    # 7) Chat'i sil (cascade delete testi)
    delete_chat = httpx.delete(
        f"{base_url}/chats/{chat_id}",
        headers=auth_headers,
        timeout=30,
    )
    assert delete_chat.status_code in (200, 204)
    
    # 8) Chat artık yok
    get_chat = httpx.get(
        f"{base_url}/chats/{chat_id}",
        headers=auth_headers,
        timeout=30,
    )
    assert get_chat.status_code in (404, 410)
    
    # 9) Mesajlar silindi mi?
    msgs_after = httpx.get(
        f"{base_url}/chats/{chat_id}/messages",
        headers=auth_headers,
        timeout=30,
    )
    if msgs_after.status_code == 200:
        msgs_after_data = msgs_after.json()
        msgs_after_list = msgs_after_data.get("messages", []) if isinstance(msgs_after_data, dict) else msgs_after_data
        assert len(msgs_after_list) == 0
    
    # 10) Doküman hala var mı? (user-scoped, chat delete'te silinmez)
    doc_detail = httpx.get(
        f"{base_url}/documents/{doc_id}",
        headers=auth_headers,
        timeout=30,
    )
    assert doc_detail.status_code == 200  # Doküman hala erişilebilir (user-scoped)


@pytest.mark.integration
def test_multiple_chats_flow(base_url: str, auth_headers: dict):
    """
    Ne işe yarar?
    - Kullanıcının birden fazla chat oluşturup yönetebildiğini test eder.
    - Chat isolation'ı doğrular (bir chat'teki mesaj diğerinde görünmez).
    """
    # 1) İki chat oluştur
    chat1 = httpx.post(f"{base_url}/chats", headers=auth_headers, json={}, timeout=30)
    chat2 = httpx.post(f"{base_url}/chats", headers=auth_headers, json={}, timeout=30)
    
    assert chat1.status_code in (200, 201)
    assert chat2.status_code in (200, 201)
    
    chat1_id = chat1.json().get("id") or chat1.json().get("_id")
    chat2_id = chat2.json().get("id") or chat2.json().get("_id")
    
    # 2) Her chat'e farklı mesaj gönder
    msg1_id = str(uuid.uuid4())
    msg1 = httpx.post(
        f"{base_url}/chat",
        headers=auth_headers,
        json={
            "chatId": chat1_id,
            "message": "Chat 1 mesajı",
            "mode": "qa",
            "documentIds": [],
            "client_message_id": msg1_id,
        },
        timeout=60,
    )
    
    msg2_id = str(uuid.uuid4())
    msg2 = httpx.post(
        f"{base_url}/chat",
        headers=auth_headers,
        json={
            "chatId": chat2_id,
            "message": "Chat 2 mesajı",
            "mode": "qa",
            "documentIds": [],
            "client_message_id": msg2_id,
        },
        timeout=60,
    )
    
    assert msg1.status_code in (200, 201)
    assert msg2.status_code in (200, 201)
    
    # 3) Chat isolation kontrolü
    msgs1 = httpx.get(f"{base_url}/chats/{chat1_id}/messages", headers=auth_headers, timeout=30)
    msgs2 = httpx.get(f"{base_url}/chats/{chat2_id}/messages", headers=auth_headers, timeout=30)
    
    assert msgs1.status_code == 200
    assert msgs2.status_code == 200
    
    msgs1_data = msgs1.json().get("messages", []) if isinstance(msgs1.json(), dict) else msgs1.json()
    msgs2_data = msgs2.json().get("messages", []) if isinstance(msgs2.json(), dict) else msgs2.json()
    
    # Chat 1'de sadece Chat 1 mesajı olmalı
    chat1_contents = [m.get("content", "").lower() for m in msgs1_data]
    assert "chat 1" in " ".join(chat1_contents)
    assert "chat 2" not in " ".join(chat1_contents)
    
    # Chat 2'de sadece Chat 2 mesajı olmalı
    chat2_contents = [m.get("content", "").lower() for m in msgs2_data]
    assert "chat 2" in " ".join(chat2_contents)
    assert "chat 1" not in " ".join(chat2_contents)

