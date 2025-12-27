"""
Basit load test - Locust ile performans testi.

Çalıştırma:
    cd backend
    locust -f tests/performance/test_load.py --host=http://localhost:8000
    # Browser'da http://localhost:8089 açılır
"""
from locust import HttpUser, task, between
import random
import string


def generate_random_string(length=10):
    """Random string generator for unique test data."""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))


class QuickTestUser(HttpUser):
    """
    Hızlı test user - temel endpoint'leri test eder.
    """
    wait_time = between(1, 3)  # Her request arasında 1-3 saniye bekle
    
    def on_start(self):
        """Test başlangıcında bir kere çalışır - user oluştur ve login ol."""
        self.username = f"load_test_{generate_random_string(8)}"
        self.email = f"{self.username}@example.com"
        self.password = "Test123456!"
        self.token = None
        
        # Register
        response = self.client.post(
            "/auth/register",
            json={
                "email": self.email,
                "password": self.password,
                "username": self.username
            },
            name="Register"
        )
        
        # Login
        response = self.client.post(
            "/auth/login",
            json={
                "username": self.username,
                "password": self.password
            },
            name="Login"
        )
        
        if response.status_code == 200:
            self.token = response.json().get("access_token")
            self.headers = {"Authorization": f"Bearer {self.token}"}
        else:
            self.headers = {}
    
    @task(3)
    def get_health(self):
        """Health check - en sık çalışan test."""
        self.client.get("/health", name="Health Check")
    
    @task(2)
    def get_me(self):
        """Get user info - auth gerektirir."""
        if self.token:
            self.client.get("/me", headers=self.headers, name="Get Me")
    
    @task(1)
    def list_chats(self):
        """List chats - auth gerektirir."""
        if self.token:
            self.client.get("/chats", headers=self.headers, name="List Chats")
    
    @task(1)
    def list_documents(self):
        """List documents - auth gerektirir."""
        if self.token:
            self.client.get("/documents", headers=self.headers, name="List Documents")


class ChatUser(HttpUser):
    """
    Chat-focused user - chat işlemlerini test eder.
    """
    wait_time = between(2, 5)  # Chat işlemleri daha yavaş
    
    def on_start(self):
        """Test başlangıcında user oluştur ve chat oluştur."""
        self.username = f"chat_user_{generate_random_string(8)}"
        self.email = f"{self.username}@example.com"
        self.password = "Test123456!"
        self.token = None
        self.chat_id = None
        
        # Register & Login
        self.client.post(
            "/auth/register",
            json={
                "email": self.email,
                "password": self.password,
                "username": self.username
            },
            name="Register"
        )
        
        response = self.client.post(
            "/auth/login",
            json={
                "username": self.username,
                "password": self.password
            },
            name="Login"
        )
        
        if response.status_code == 200:
            self.token = response.json().get("access_token")
            self.headers = {"Authorization": f"Bearer {self.token}"}
            
            # Create chat
            chat_response = self.client.post(
                "/chats",
                headers=self.headers,
                json={},
                name="Create Chat"
            )
            
            if chat_response.status_code in (200, 201):
                self.chat_id = chat_response.json().get("id")
        else:
            self.headers = {}
    
    @task(5)
    def get_chats(self):
        """List chats - en sık çalışan."""
        if self.token:
            self.client.get("/chats", headers=self.headers, name="List Chats")
    
    @task(2)
    def create_chat(self):
        """Create new chat."""
        if self.token:
            self.client.post(
                "/chats",
                headers=self.headers,
                json={},
                name="Create Chat"
            )
    
    @task(1)
    def get_chat_messages(self):
        """Get chat messages - chat_id gerektirir."""
        if self.token and self.chat_id:
            self.client.get(
                f"/chats/{self.chat_id}/messages",
                headers=self.headers,
                name="Get Chat Messages"
            )

