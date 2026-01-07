# Gmail OAuth Entegrasyonu Kurulum Rehberi

Bu dokümantasyon, Gmail OAuth entegrasyonunu gerçekten çalışır hale getirmek için gerekli adımları içerir.

## A) Google Cloud Console Kurulumu

### 1. Google Cloud Console'a Giriş

1. [Google Cloud Console](https://console.cloud.google.com/) adresine gidin
2. Yeni bir proje oluşturun veya mevcut bir projeyi seçin

### 2. OAuth Consent Screen Yapılandırması

1. Sol menüden **APIs & Services** > **OAuth consent screen** seçin
2. **User Type** seçin:
   - **Internal**: Sadece kendi organizasyonunuzdaki kullanıcılar (Google Workspace)
   - **External**: Herkes (genel kullanım için)
3. **App information** doldurun:
   - **App name**: HACE (veya istediğiniz isim)
   - **User support email**: Destek e-postanız
   - **App logo**: (Opsiyonel)
   - **Developer contact information**: E-postanız
4. **Scopes** ekleyin:
   - **Add or Remove Scopes** butonuna tıklayın
   - `https://www.googleapis.com/auth/gmail.readonly` scope'unu ekleyin
   - **Save and Continue** tıklayın
5. **Test users** ekleyin (External için):
   - Test aşamasında kullanılacak Gmail hesaplarını ekleyin
   - Production'a geçmeden önce kaldırılabilir
6. **Summary** sayfasını kontrol edin ve **Back to Dashboard** tıklayın

### 3. OAuth Client ID Oluşturma

1. Sol menüden **APIs & Services** > **Credentials** seçin
2. **+ CREATE CREDENTIALS** > **OAuth client ID** seçin
3. **Application type**: **Web application** seçin
4. **Name**: "HACE Gmail Integration" (veya istediğiniz isim)
5. **Authorized redirect URIs** ekleyin:
   - **Development**: `http://localhost:3000/api/integrations/gmail/callback`
   - **Production**: `https://yourdomain.com/api/integrations/gmail/callback`
   - **Not**: Frontend Next.js proxy kullanıyorsa, backend'e direkt değil frontend URL'ine yönlendirilir
6. **CREATE** tıklayın
7. **Client ID** ve **Client Secret** değerlerini kopyalayın (sadece bir kez gösterilir!)

### 4. Gmail API'yi Etkinleştirme

1. Sol menüden **APIs & Services** > **Library** seçin
2. "Gmail API" arayın
3. **Gmail API**'yi seçin ve **ENABLE** tıklayın

## B) Environment Variables

Backend `.env` dosyasına şu değişkenleri ekleyin:

```env
# Google OAuth Configuration
GOOGLE_CLIENT_ID=your-client-id-here.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret-here
GOOGLE_REDIRECT_URI=http://localhost:3000/api/integrations/gmail/callback
GOOGLE_OAUTH_SCOPES=https://www.googleapis.com/auth/gmail.readonly

# Base URLs (link generation için)
APP_BASE_URL=http://localhost:8000
FRONTEND_BASE_URL=http://localhost:3000

# Encryption Key (token şifreleme için)
# Fernet key oluşturmak için: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
ENCRYPTION_KEY=your-32-byte-base64-encoded-key-here
```

### Encryption Key Oluşturma

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Çıktıyı `ENCRYPTION_KEY` olarak kullanın.

## C) Production Kurulumu

Production için:

1. **OAuth Consent Screen**'de **PUBLISH APP** yapın (External için)
2. **Authorized redirect URIs**'e production URL'ini ekleyin:
   - `https://yourdomain.com/api/integrations/gmail/callback`
3. `.env` dosyasında production URL'lerini kullanın:
   ```env
   GOOGLE_REDIRECT_URI=https://yourdomain.com/api/integrations/gmail/callback
   APP_BASE_URL=https://api.yourdomain.com
   FRONTEND_BASE_URL=https://yourdomain.com
   ```

## D) Backend Endpoint Sözleşmeleri

### GET `/api/integrations/gmail/connect`

**Request:**
- Headers: `Authorization: Bearer <token>`

**Response (200):**
```json
{
  "auth_url": "https://accounts.google.com/o/oauth2/auth?..."
}
```

**Error Responses:**
- `400 GMAIL_NOT_CONFIGURED`: Gmail OAuth yapılandırılmamış
- `401 UNAUTHORIZED`: Token geçersiz

### GET `/api/integrations/gmail/callback?code=...&state=...`

**Request:**
- Query params: `code` (Google'dan gelen), `state` (CSRF koruması)
- Headers: `Authorization: Bearer <token>`

**Response (200):**
```json
{
  "status": "success",
  "email": "user@gmail.com"
}
```

**Error Responses:**
- `400 INVALID_STATE`: State geçersiz veya süresi dolmuş
- `400 GMAIL_NOT_CONFIGURED`: Gmail OAuth yapılandırılmamış
- `401 UNAUTHORIZED`: Token geçersiz

### GET `/api/integrations/gmail/status`

**Request:**
- Headers: `Authorization: Bearer <token>`

**Response (200):**
```json
{
  "is_connected": true,
  "email": "user@gmail.com",
  "last_sync_at": "2024-01-01T12:00:00",
  "sync_status": "connected"
}
```

### POST `/api/integrations/gmail/sync`

**Request:**
- Headers: `Authorization: Bearer <token>`

**Response (200):**
```json
{
  "status": "success",
  "emails_fetched": 10,
  "emails_indexed": 8,
  "duration_ms": 1234.5
}
```

**Error Responses:**
- `400 GMAIL_NOT_CONNECTED`: Gmail bağlı değil
- `401 GMAIL_REAUTH_REQUIRED`: Token yenileme başarısız, tekrar bağlan gerekli

### GET `/api/integrations/gmail/messages?query=...&max=...`

**Request:**
- Query params: `query` (Gmail search query, opsiyonel), `max` (max results, default 50)
- Headers: `Authorization: Bearer <token>`

**Response (200):**
```json
{
  "messages": [
    {
      "id": "message-id",
      "threadId": "thread-id",
      "snippet": "Message preview..."
    }
  ]
}
```

### GET `/api/integrations/gmail/messages/{message_id}`

**Request:**
- Path param: `message_id`
- Headers: `Authorization: Bearer <token>`

**Response (200):**
```json
{
  "id": "message-id",
  "thread_id": "thread-id",
  "subject": "Email Subject",
  "sender": "sender@example.com",
  "date": "Mon, 1 Jan 2024 12:00:00 +0000",
  "snippet": "Message preview...",
  "body": "Cleaned message body text..."
}
```

### POST `/api/integrations/gmail/disconnect`

**Request:**
- Headers: `Authorization: Bearer <token>`

**Response (200):**
```json
{
  "status": "success",
  "message": "Gmail bağlantısı kesildi"
}
```

## E) Frontend Akışı

1. **Bağlan Butonu** (`/app` sayfası):
   - `GET /api/integrations/gmail/connect` çağrılır
   - `auth_url` alınır
   - `window.location.href = auth_url` ile Google OAuth sayfasına yönlendirilir

2. **Callback Sayfası** (`/integrations/gmail`):
   - Google'dan `code` ve `state` parametreleri gelir
   - `GET /api/integrations/gmail/callback?code=...&state=...` çağrılır
   - Başarılıysa `/app` sayfasına yönlendirilir

3. **Status Kontrolü**:
   - `GET /api/integrations/gmail/status` ile bağlantı durumu kontrol edilir
   - UI'da "Bağlı / Bağlı Değil" durumu gösterilir

4. **Senkronizasyon**:
   - `POST /api/integrations/gmail/sync` ile manuel senkronizasyon başlatılır
   - Sonuç toast ile gösterilir

5. **Bağlantıyı Kes**:
   - `POST /api/integrations/gmail/disconnect` ile token'lar silinir
   - Status yenilenir

## F) Hata Kodları

- `GMAIL_NOT_CONFIGURED`: Gmail OAuth yapılandırılmamış (env değişkenleri eksik)
- `GMAIL_NOT_CONNECTED`: Kullanıcının Gmail hesabı bağlı değil
- `GMAIL_REAUTH_REQUIRED`: Token yenileme başarısız, tekrar bağlan gerekli
- `INVALID_STATE`: OAuth state geçersiz veya süresi dolmuş (CSRF koruması)

## G) Test ve Doğrulama

### 1. Env Kontrolü

```bash
# Backend'de
python -c "from app.config import GmailConfig; print('Configured:', GmailConfig.is_configured())"
```

### 2. Connect Endpoint Testi

```bash
curl -X GET http://localhost:8000/integrations/gmail/connect \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Beklenen:**
- Env yoksa: `400 GMAIL_NOT_CONFIGURED`
- Env varsa: `200 {"auth_url": "..."}`

### 3. OAuth Flow Testi

1. Frontend'de "Google ile Bağlan" butonuna tıklayın
2. Google OAuth sayfası açılmalı
3. İzin verin
4. Callback sayfasına yönlendirilmeli
5. "Başarılı" mesajı görünmeli
6. `/app` sayfasında "Bağlı" durumu görünmeli

### 4. Multi-Tenant Testi

1. İki farklı kullanıcı ile giriş yapın
2. Her biri kendi Gmail hesabını bağlasın
3. Bir kullanıcı diğerinin token'ına erişememeli

## H) Troubleshooting

### Problem: "GMAIL_NOT_CONFIGURED" hatası

**Çözüm:**
- `.env` dosyasında `GOOGLE_CLIENT_ID` ve `GOOGLE_CLIENT_SECRET` kontrol edin
- Backend'i yeniden başlatın

### Problem: "INVALID_STATE" hatası

**Çözüm:**
- OAuth state 10 dakika içinde kullanılmalı
- Callback URL'i doğru mu kontrol edin
- MongoDB'de `oauth_states` collection'ı kontrol edin

### Problem: Refresh token alınamıyor

**Çözüm:**
- OAuth flow'da `prompt='consent'` kullanıldığından emin olun
- İlk bağlantıda refresh token alınır, sonraki bağlantılarda alınmayabilir
- Google Console'da "Offline access" scope'unu kontrol edin

### Problem: Token yenileme başarısız

**Çözüm:**
- `GMAIL_REAUTH_REQUIRED` hatası alıyorsanız, kullanıcı tekrar bağlanmalı
- Google Console'da token'ı revoke edip tekrar bağlanmayı deneyin

## I) Güvenlik Notları

1. **ENCRYPTION_KEY**: Production'da mutlaka güçlü bir key kullanın
2. **State Parameter**: CSRF koruması için kullanılır, 10 dakika sonra expire olur
3. **Token Storage**: Token'lar şifrelenmiş olarak MongoDB'de saklanır
4. **Multi-Tenant**: Her kullanıcı sadece kendi token'ına erişebilir
5. **Scope**: Sadece `gmail.readonly` kullanılır (yazma izni yok)

## J) Production Checklist

- [ ] Google Cloud Console'da OAuth Consent Screen yayınlandı
- [ ] Production redirect URI eklendi
- [ ] `.env` dosyasında production URL'leri ayarlandı
- [ ] `ENCRYPTION_KEY` güçlü bir key ile değiştirildi
- [ ] Backend ve frontend production'da çalışıyor
- [ ] Test kullanıcıları kaldırıldı (External için)
- [ ] Error handling test edildi
- [ ] Multi-tenant güvenlik test edildi

