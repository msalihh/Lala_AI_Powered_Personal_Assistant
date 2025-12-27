# Backend - FastAPI + MongoDB

## Kurulum

### 1. MongoDB'nin çalıştığından emin olun

MongoDB'nin `mongodb://localhost:27017/` adresinde çalıştığından emin olun.

### 2. Python bağımlılıklarını yükleyin

```bash
pip install -r requirements.txt
```

### 3. Backend'i başlatın

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Veritabanı

- **MongoDB URL**: `mongodb://localhost:27017/`
- **Database Adı**: `auth_db`
- **Collection**: `users`

## Environment Variables

`.env` dosyası oluşturarak özelleştirebilirsiniz:

```
MONGODB_URL=mongodb://localhost:27017/
DATABASE_NAME=auth_db
```

## Endpoints

- `GET /` - API bilgisi
- `GET /health` - Health check
- `POST /auth/register` - Kullanıcı kaydı
- `POST /auth/login` - Giriş yap
- `GET /me` - Kullanıcı bilgileri (JWT gerekli)

## Testing

### Test Bağımlılıklarını Yükleme

```bash
pip install -r requirements-dev.txt
```

### Tüm Testleri Çalıştırma

Backend'in çalışıyor olması gerekir.

```bash
# Backend'in çalıştığından emin olun (başka bir terminal'de)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Tüm testleri çalıştır
cd backend
TEST_BASE_URL=http://localhost:8000 pytest -v

# Sadece smoke testler
TEST_BASE_URL=http://localhost:8000 pytest tests/test_smoke.py -v

# Sadece kritik akış testleri
TEST_BASE_URL=http://localhost:8000 pytest tests/test_chat_flow.py tests/test_documents_flow.py -v
```

### Test Kategorileri

- **Smoke Testler** (`test_smoke.py`): Sistemin temel endpoint'lerinin çalışıp çalışmadığını kontrol eder
  - Health check endpoints
  - Auth akışı (register → login → /me)
  - Chat endpoints (create → list → get)
  - Documents endpoints (list)

- **Kritik Akış Testleri**: Gerçek kullanım senaryolarını test eder
  - `test_chat_flow.py`: Chat create → message save → get messages
  - `test_documents_flow.py`: Document upload → list → get detail → delete
  - `test_cascade_delete.py`: Chat delete cascade (messages siliniyor)
  - `test_debug_security.py`: Debug endpoint güvenliği (auth gerektiriyor)
  - `test_chat_response.py`: Chat response format kontrolü

### Test Yapısı

```
backend/
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # Ortak fixtures (auth_token, auth_headers)
│   ├── test_smoke.py            # Smoke testler (6 test)
│   ├── test_chat_flow.py        # Chat akış testi
│   ├── test_documents_flow.py   # Document akış testi
│   ├── test_cascade_delete.py   # Cascade delete testi
│   ├── test_debug_security.py   # Debug endpoint güvenlik testi
│   └── test_chat_response.py    # Chat response format testi
├── pytest.ini                   # Pytest yapılandırması
└── requirements-dev.txt         # Test bağımlılıkları
```

### Test İstatistikleri

- **Toplam Test**: 11 test
- **Smoke Testler**: 6 test
- **Kritik Akış Testleri**: 5 test
- **Ortalama Çalışma Süresi**: ~110 saniye (tüm testler)

### Test Markers

```bash
# Sadece smoke testler
pytest -m smoke

# Sadece integration testler (E2E)
pytest -m integration

# Yavaş testleri atla
pytest -m "not slow"
```

### Test Coverage

```bash
# Coverage raporu oluştur
pytest --cov=app --cov-report=html

# HTML raporunu aç
# Windows: start htmlcov/index.html
# Linux/Mac: open htmlcov/index.html
```

### Performance Testing

```bash
# Locust load test
cd backend
locust -f tests/performance/test_load.py --host=http://localhost:8000
# Browser'da http://localhost:8089 açılır
```

### E2E Testing

```bash
# End-to-end testleri çalıştır
pytest tests/e2e/ -v -m integration
```