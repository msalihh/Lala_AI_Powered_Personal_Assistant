import httpx
import json

# Test Personal Assistant
print("Testing Personal Assistant (Gemini)...")
print("=" * 60)

url = "http://localhost:8000/api/chat"
headers = {"Content-Type": "application/json"}

# You'll need a valid user_id and chat_id from your system
# This is a simplified test - adjust as needed
payload = {
    "message": "Merhaba, nasılsın?",
    "chat_id": "test_chat_123",
    "prompt_module": "none",  # Personal Assistant
    "client_message_id": "test_msg_1"
}

try:
    response = httpx.post(url, json=payload, headers=headers, timeout=30.0)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text[:500]}")
except Exception as e:
    print(f"Error: {e}")

print("\n" + "=" * 60)
print("\nTesting LGS Module (Qwen3 Coder)...")
print("=" * 60)

payload2 = {
    "message": "5+6 kaç eder?",
    "chat_id": "test_chat_456",
    "prompt_module": "lgs_karekok",  # LGS Module
    "client_message_id": "test_msg_2"
}

try:
    response = httpx.post(url, json=payload2, headers=headers, timeout=30.0)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text[:500]}")
except Exception as e:
    print(f"Error: {e}")
