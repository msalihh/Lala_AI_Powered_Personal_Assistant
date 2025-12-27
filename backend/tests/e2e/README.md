# E2E (End-to-End) Testleri

Bu klasör end-to-end testleri içerir. Bu testler sistemin tamamının birlikte çalıştığını doğrular.

## Test Senaryoları

### `test_full_flow.py`

**test_full_user_flow**: Tam kullanıcı akışı
1. Kullanıcı kaydı (fixture'dan)
2. Chat oluşturma
3. Doküman yükleme (chat'e bağlı)
4. Chat'te doküman kullanarak soru sorma (RAG)
5. Mesajları görüntüleme
6. Chat listesi kontrolü
7. Doküman listesi kontrolü
8. Chat silme (cascade delete)
9. Mesajların silindiğini doğrulama
10. Dokümanın hala erişilebilir olduğunu doğrulama (user-scoped)

**test_multiple_chats_flow**: Çoklu chat yönetimi
1. İki chat oluşturma
2. Her chat'e farklı mesaj gönderme
3. Chat isolation kontrolü (bir chat'teki mesaj diğerinde görünmez)

## Çalıştırma

```bash
# Backend'in çalıştığından emin olun
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# E2E testleri çalıştır
cd backend
TEST_BASE_URL=http://localhost:8000 pytest tests/e2e/ -v -m integration
```

## Notlar

- Bu testler backend API'yi test eder, frontend UI'ı test etmez
- Frontend testleri için Playwright veya Selenium kullanılmalı
- E2E testler daha yavaştır (tam akış test eder)
- `@pytest.mark.integration` marker'ı ile işaretlenmiştir

## Gelecek Geliştirmeler

- Frontend E2E testleri (Playwright)
- Visual regression testleri
- Cross-browser testleri
- Mobile responsive testleri

