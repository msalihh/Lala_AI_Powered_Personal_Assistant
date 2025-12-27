"""
Smoke tests for backend API endpoints.

Bu testler sistemin "ayakta olup olmadığını" kontrol eder.
Kalite testi değil, "sistem çalışıyor mu?" testidir.

Çalıştırma:
    cd backend
    TEST_BASE_URL=http://localhost:8000 pytest tests/test_smoke.py -v
"""
import os
import pytest
import httpx

BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8000")


def test_health_smoke():
    """
    Ne işe yarar?
    - Sunucu erişilebilir mi kontrol eder. En basit smoke test.

    Olmazsa ne olur?
    - Diğer tüm testler 'connection refused' ile saçmalar, kök sebebi göremezsin.

    Başka örneklerde:
    - /health endpoint'in varsa onu çağırırsın.
    """
    r = httpx.get(f"{BASE_URL}/docs", timeout=5.0)
    assert r.status_code in (200, 302), f"Expected 200 or 302, got {r.status_code}"


def test_root_endpoint_smoke():
    """
    Root endpoint (/) kontrolü.
    """
    r = httpx.get(f"{BASE_URL}/", timeout=5.0)
    assert r.status_code in (200, 404), f"Expected 200 or 404, got {r.status_code}"


def test_health_endpoint_smoke():
    """
    /health endpoint kontrolü (eğer varsa).
    """
    r = httpx.get(f"{BASE_URL}/health", timeout=5.0)
    assert r.status_code in (200, 404), f"Expected 200 or 404, got {r.status_code}"


def test_auth_register_login_me_flow_smoke():
    """
    Ne işe yarar?
    - Sistemin omurgası: register -> login -> /me.
    - Burası çalışmıyorsa proje fiilen çalışmıyor demektir.

    Olmazsa ne olur?
    - 'Her şey çalışıyor' zannederken aslında auth kırık çıkar.

    Başka örneklerde:
    - Email doğrulama varsa burada verify adımı da eklenir.
    """
    import random
    import string
    
    # Unique test user (random suffix ile çakışma önle)
    random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    email = f"test_smoke_{random_suffix}@example.com"
    password = "Test123456!"
    username = f"test_smoke_{random_suffix}"

    # 1) Register (zaten varsa 409/400 olabilir; onu tolere edeceğiz)
    reg = httpx.post(
        f"{BASE_URL}/auth/register",
        json={"email": email, "password": password, "username": username},
        timeout=10.0
    )
    assert reg.status_code in (200, 201, 400, 409), \
        f"Register failed with status {reg.status_code}: {reg.text[:200]}"

    # 2) Login (username ile)
    login = httpx.post(
        f"{BASE_URL}/auth/login",
        json={"username": username, "password": password},
        timeout=10.0
    )
    assert login.status_code == 200, \
        f"Login failed with status {login.status_code}: {login.text[:200]}"
    data = login.json()
    assert "access_token" in data, f"Login response missing access_token: {data}"
    token = data["access_token"]
    assert len(token) > 0, "Token is empty"

    # 3) /me
    me = httpx.get(
        f"{BASE_URL}/me",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10.0
    )
    assert me.status_code == 200, \
        f"/me failed with status {me.status_code}: {me.text[:200]}"
    me_data = me.json()
    assert me_data.get("email") == email or me_data.get("username") == username, \
        f"/me response mismatch: {me_data}"


def test_chats_endpoints_smoke():
    """
    Chat endpoints smoke test: create -> list -> get.
    Auth gerektirir, bu yüzden önce token alınmalı.
    """
    import random
    import string
    
    # Test user oluştur ve login ol
    random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    email = f"test_chat_{random_suffix}@example.com"
    password = "Test123456!"
    username = f"test_chat_{random_suffix}"

    # Register (ignore if exists)
    httpx.post(
        f"{BASE_URL}/auth/register",
        json={"email": email, "password": password, "username": username},
        timeout=10.0
    )

    # Login (username ile)
    login = httpx.post(
        f"{BASE_URL}/auth/login",
        json={"username": username, "password": password},
        timeout=10.0
    )
    assert login.status_code == 200, f"Login failed: {login.text[:200]}"
    token = login.json()["access_token"]

    # Create chat
    create = httpx.post(
        f"{BASE_URL}/chats",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "Test Chat"},
        timeout=10.0
    )
    assert create.status_code in (200, 201), \
        f"Create chat failed: {create.status_code} - {create.text[:200]}"
    chat_data = create.json()
    chat_id = chat_data.get("id")
    assert chat_id, f"Chat ID missing in response: {chat_data}"

    # List chats
    list_chats = httpx.get(
        f"{BASE_URL}/chats",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10.0
    )
    assert list_chats.status_code == 200, \
        f"List chats failed: {list_chats.status_code} - {list_chats.text[:200]}"
    chats = list_chats.json()
    assert isinstance(chats, list), f"Expected list, got {type(chats)}"

    # Get chat
    get_chat = httpx.get(
        f"{BASE_URL}/chats/{chat_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10.0
    )
    assert get_chat.status_code == 200, \
        f"Get chat failed: {get_chat.status_code} - {get_chat.text[:200]}"


def test_documents_endpoints_smoke():
    """
    Documents endpoints smoke test: list (auth gerektirir).
    """
    import random
    import string
    
    # Test user oluştur ve login ol
    random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    email = f"test_doc_{random_suffix}@example.com"
    password = "Test123456!"
    username = f"test_doc_{random_suffix}"

    # Register (ignore if exists)
    httpx.post(
        f"{BASE_URL}/auth/register",
        json={"email": email, "password": password, "username": username},
        timeout=10.0
    )

    # Login (username ile)
    login = httpx.post(
        f"{BASE_URL}/auth/login",
        json={"username": username, "password": password},
        timeout=10.0
    )
    assert login.status_code == 200, f"Login failed: {login.text[:200]}"
    token = login.json()["access_token"]

    # List documents
    list_docs = httpx.get(
        f"{BASE_URL}/documents",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10.0
    )
    assert list_docs.status_code == 200, \
        f"List documents failed: {list_docs.status_code} - {list_docs.text[:200]}"
    docs = list_docs.json()
    assert isinstance(docs, list), f"Expected list, got {type(docs)}"

