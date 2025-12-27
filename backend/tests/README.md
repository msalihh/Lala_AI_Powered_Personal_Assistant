# Test Dokümantasyonu

Bu klasör backend API için testleri içerir.

## Test Kategorileri

### 1. Smoke Testler (`test_smoke.py`)

Sistemin "ayakta olup olmadığını" kontrol eden temel testler.

**Testler:**
- `test_health_smoke` - `/docs` endpoint kontrolü
- `test_root_endpoint_smoke` - `/` endpoint kontrolü
- `test_health_endpoint_smoke` - `/health` endpoint kontrolü
- `test_auth_register_login_me_flow_smoke` - Auth akışı (register → login → /me)
- `test_chats_endpoints_smoke` - Chat endpoints (create → list → get)
- `test_documents_endpoints_smoke` - Documents endpoints (list)

**Ne zaman çalıştırılır?**
- Her commit'ten önce
- Backend deploy'undan önce
- CI/CD pipeline'ında

### 2. Kritik Akış Testleri

Gerçek kullanım senaryolarını test eden testler.

#### `test_chat_flow.py`
Chat oluşturma → mesaj gönderme → mesajları getirme akışı.

**Doğrular:**
- Chat oluşturma çalışıyor
- `/chat` endpoint'i mesajı kaydediyor
- Mesajlar getirilebiliyor
- Memory sistemi çalışıyor

#### `test_documents_flow.py`
Document upload → list → get detail → delete akışı.

**Doğrular:**
- Document upload çalışıyor
- Text extraction çalışıyor
- Document list'te görünüyor
- Document detail'de text_content var
- Document silme çalışıyor

#### `test_cascade_delete.py`
Chat silindiğinde messages cascade delete.

**Doğrular:**
- Chat silindiğinde messages siliniyor
- Orphan data (sahipsiz mesaj) kalmıyor
- Ownership check çalışıyor

**Not:** Documents user-scoped olduğu için chat delete'te silinmiyor (tasarım kararı).

#### `test_debug_security.py`
Debug endpoint güvenliği.

**Doğrular:**
- Debug endpoint auth gerektiriyor
- Auth'suz erişim kapalı (401/403/404)
- Auth'lu erişim çalışıyor (dev ortamında)

#### `test_chat_response.py`
Chat response format kontrolü.

**Doğrular:**
- Response doğru JSON formatında
- Zorunlu field'lar var (`message`)
- Opsiyonel field'lar doğru tip (`sources`, `debug_info`)

## Ortak Fixtures (`conftest.py`)

Tüm testlerde kullanılan ortak yapılar:

- `base_url` - Test base URL'i
- `auth_token` - Otomatik oluşturulan test user token'ı
- `auth_headers` - Authorization header'ı

**Kullanım:**
```python
def test_example(base_url: str, auth_headers: dict):
    response = httpx.get(f"{base_url}/endpoint", headers=auth_headers)
    assert response.status_code == 200
```

## Çalıştırma

### Tüm Testler
```bash
TEST_BASE_URL=http://localhost:8000 pytest -v
```

### Belirli Bir Test Dosyası
```bash
TEST_BASE_URL=http://localhost:8000 pytest tests/test_smoke.py -v
```

### Belirli Bir Test
```bash
TEST_BASE_URL=http://localhost:8000 pytest tests/test_smoke.py::test_health_smoke -v
```

## Test Gereksinimleri

- Backend çalışıyor olmalı (`http://localhost:8000`)
- MongoDB çalışıyor olmalı
- Test bağımlılıkları yüklü olmalı (`pip install -r requirements-dev.txt`)

## Test Yapısı Prensipleri

1. **Her test bağımsız**: Unique user'lar kullanılır (timestamp-based)
2. **Açıklayıcı hata mesajları**: Assert'lerde detaylı mesajlar
3. **Uygun timeout'lar**: `/chat` için 60s, diğerleri için 30s
4. **DRY prensibi**: Ortak kod `conftest.py`'de

## Sorun Giderme

### Testler "Connection refused" hatası veriyor
- Backend'in çalıştığından emin olun
- `TEST_BASE_URL` environment variable'ını kontrol edin

### Testler "401 Unauthorized" hatası veriyor
- `auth_token` fixture'ının çalıştığından emin olun
- Backend'de JWT secret key doğru mu kontrol edin

### Testler yavaş çalışıyor
- `/chat` endpoint'i model çağrısı yapıyor (60s timeout normal)
- Tüm testler ~110 saniye sürüyor (normal)

