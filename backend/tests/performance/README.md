# Performance Testing

Bu klasör performans testleri içerir.

## Locust Load Testing

### Kurulum

```bash
pip install locust
```

### Çalıştırma

```bash
# Backend'in çalıştığından emin olun
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Locust'ı başlat
cd backend
locust -f tests/performance/test_load.py --host=http://localhost:8000
```

Browser'da `http://localhost:8089` açılır ve web UI'dan test parametrelerini ayarlayabilirsiniz.

### Test Senaryoları

1. **QuickTestUser**: Temel endpoint'leri test eder
   - Health check (en sık)
   - Get user info
   - List chats
   - List documents

2. **ChatUser**: Chat işlemlerini test eder
   - List chats (en sık)
   - Create chat
   - Get chat messages

### Headless Mode (CI için)

```bash
locust -f tests/performance/test_load.py \
  --host=http://localhost:8000 \
  --headless \
  --users 10 \
  --spawn-rate 2 \
  --run-time 60s
```

### Metrikler

Locust şu metrikleri sağlar:
- **Requests/s**: Saniyede istek sayısı
- **Response time**: Ortalama/medyan/maksimum yanıt süresi
- **Failure rate**: Başarısız istek yüzdesi
- **RPS**: Requests per second

### Hedefler

- Health check: < 50ms
- Auth endpoints: < 200ms
- Chat endpoints: < 500ms
- Document endpoints: < 300ms

