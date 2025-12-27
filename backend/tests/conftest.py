"""
Pytest configuration and shared fixtures.

Bu dosya tüm testlerde kullanılan ortak yapıları içerir:
- BASE_URL: Testlerin hangi backend'e vuracağını belirler
- auth_token: Tüm "auth gereken" testlere hazır token sağlar
- auth_headers: Authorization header'ını tek yerde üretir
"""
import os
import time
import pytest
import httpx

BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8000")


def _unique_email(prefix: str = "test") -> str:
    """
    Ne işe yarar?
    - Her test koşusunda farklı email üreterek "kullanıcı zaten var" sorununu bitirir.
    
    Olmazsa ne olur?
    - Register 409/400 döner; testlerin bazen geçer bazen kalır (flaky).
    
    Başka örneklerde:
    - UUID kullanabilirsin.
    """
    return f"{prefix}_{int(time.time() * 1000)}@example.com"


@pytest.fixture
def base_url() -> str:
    """
    Ne işe yarar?
    - Testlerin base URL'ini tek yerden yönetir.
    
    Olmazsa ne olur?
    - Her dosyada URL tekrar eder, değişince her yer kırılır.
    """
    return BASE_URL


@pytest.fixture
def auth_token(base_url: str) -> str:
    """
    Ne işe yarar?
    - Tüm "auth gereken" testlere hazır token sağlar.
    
    Olmazsa ne olur?
    - Her testte register/login tekrarı yaparsın.
    """
    email = _unique_email("smoke_user")
    password = "Test123456!"
    username = f"u_{int(time.time())}"

    # Register
    reg = httpx.post(
        f"{base_url}/auth/register",
        json={"email": email, "password": password, "username": username},
        timeout=20,
    )
    assert reg.status_code in (200, 201, 400, 409), \
        f"Register failed: {reg.status_code} - {reg.text[:200]}"

    # Login (username ile - backend'iniz username istiyor)
    login = httpx.post(
        f"{base_url}/auth/login",
        json={"username": username, "password": password},
        timeout=20,
    )
    assert login.status_code == 200, \
        f"Login failed: {login.status_code} - {login.text[:200]}"
    token = login.json()["access_token"]
    assert len(token) > 0, "Token is empty"
    return token


@pytest.fixture
def auth_headers(auth_token: str) -> dict:
    """
    Ne işe yarar?
    - Authorization header'ını tek yerde üretir.
    
    Olmazsa ne olur?
    - Header formatı bir yerde yanlış olur, 401 ile boğuşursun.
    """
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture
def auth_headers_user2(base_url: str) -> dict:
    """
    Fixture for second user's auth headers (for ownership tests).
    """
    email = _unique_email("smoke_user2")
    password = "Test123456!"
    username = f"u2_{int(time.time())}"

    # Register
    reg = httpx.post(
        f"{base_url}/auth/register",
        json={"email": email, "password": password, "username": username},
        timeout=20,
    )
    assert reg.status_code in (200, 201, 400, 409), \
        f"Register failed: {reg.status_code} - {reg.text[:200]}"

    # Login
    login = httpx.post(
        f"{base_url}/auth/login",
        json={"username": username, "password": password},
        timeout=20,
    )
    assert login.status_code == 200, \
        f"Login failed: {login.status_code} - {login.text[:200]}"
    token = login.json()["access_token"]
    assert len(token) > 0, "Token is empty"
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def test_db():
    """
    Fixture for database access in tests.
    Returns database instance.
    """
    from app.database import get_database
    db = get_database()
    if db is None:
        pytest.skip("Database not available")
    return db


@pytest.fixture
def test_user_id(auth_token: str) -> str:
    """
    Fixture for test user ID.
    Extracts user ID from token.
    """
    from app.auth import decode_access_token
    payload = decode_access_token(auth_token)
    return payload.get("sub", "test_user_id")


@pytest.fixture
def test_chat_id(base_url: str, auth_headers: dict) -> str:
    """
    Fixture for test chat ID.
    Creates a new chat and returns its ID.
    """
    import httpx
    response = httpx.post(
        f"{base_url}/chats",
        headers=auth_headers,
        json={"title": "Test Chat"},
        timeout=20
    )
    assert response.status_code in (200, 201), f"Failed to create chat: {response.status_code}"
    return response.json()["id"]
