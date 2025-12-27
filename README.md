# HACE - Kişisel Bilgi Asistanı

**HACE**, kullanıcıların kişisel dokümanlarını (PDF, Word, TXT) analiz eden, sohbet geçmişini hatırlayan ve RAG (Retrieval-Augmented Generation) teknolojisi ile akıllı cevaplar sunan bir AI chat uygulamasıdır.

---

## 📋 İçindekiler

1. [Proje Özeti](#proje-özeti)
2. [Teknoloji Stack](#teknoloji-stack)
3. [Ana Özellikler](#ana-özellikler)
4. [Proje Yapısı](#proje-yapısı)
5. [Kurulum ve Çalıştırma](#kurulum-ve-çalıştırma)
6. [Sistem Mimarisi](#sistem-mimarisi)
7. [API Dokümantasyonu](#api-dokümantasyonu)
8. [Veritabanı Yapısı](#veritabanı-yapısı)

---

## 🎯 Proje Özeti

HACE, kullanıcıların:
- **Doküman yükleyip** (PDF, DOCX, TXT) analiz edebileceği
- **AI ile sohbet edip** sorular sorabileceği
- **RAG teknolojisi** ile dokümanlardan bilgi çıkarabileceği
- **Sohbet geçmişini** otomatik kaydedip hatırlayabileceği
- **Matematik formülleri** render edebileceği

modern bir web uygulamasıdır.

---

## 🛠 Teknoloji Stack

### Backend
- **FastAPI** - REST API framework
- **MongoDB** - Veritabanı (users, chats, messages, documents)
- **ChromaDB** - Vector database (RAG için embedding'ler)
- **OpenRouter API** - LLM provider (GPT-4o-mini)
- **OpenAI API** - Text embedding (text-embedding-3-small)
- **PyMuPDF, python-docx** - Doküman text extraction

### Frontend
- **Next.js 14** - React framework (App Router)
- **Chakra UI** - UI component library
- **ReactMarkdown + KaTeX** - Markdown ve matematik rendering
- **NextAuth** - Google OAuth authentication
- **TypeScript** - Type safety

---

## ✨ Ana Özellikler

### 1. Kimlik Doğrulama
- Email/Password ile kayıt ve giriş
- Google OAuth ile giriş
- JWT token tabanlı authentication (30 gün geçerli)

**Dosyalar:**
- `backend/app/auth.py` - Password hashing, JWT, Google token verification
- `backend/app/main.py` - `/auth/register`, `/auth/login`, `/auth/google` endpoints
- `frontend/app/login/page.tsx` - Login sayfası
- `frontend/app/register/page.tsx` - Register sayfası

### 2. Chat Sistemi
- Chat oluşturma ve yönetimi
- Otomatik başlık oluşturma (LLM ile)
- Memory sistemi - Chat geçmişi MongoDB'de saklanır
- Cascade delete (chat silindiğinde messages da silinir)
- Streaming response desteği
- Background processing (chat değiştirilse bile streaming devam eder)

**Dosyalar:**
- `backend/app/main.py` - `/chats`, `/chat`, `/chats/{id}/messages` endpoints
- `backend/app/memory/message_store.py` - Message kaydetme ve getirme
- `backend/app/chat_title.py` - 3 katmanlı başlık oluşturma
- `frontend/app/chat/page.tsx` - Ana chat sayfası

### 3. RAG (Retrieval-Augmented Generation)
- Doküman yükleme (PDF, DOCX, TXT)
- Text extraction (PyMuPDF, python-docx)
- Chunking (300 kelime, 50 kelime overlap)
- Embedding (OpenAI text-embedding-3-small, 1536 boyut)
- Vector search (ChromaDB ile semantic search)
- Context building (ilgili chunk'lar prompt'a eklenir)
- Score threshold: 0.25 (relevance threshold)

**Dosyalar:**
- `backend/app/routes/documents.py` - Document endpoints
- `backend/app/documents.py` - Text extraction
- `backend/app/rag/chunker.py` - Text chunking
- `backend/app/rag/embedder.py` - Text embedding
- `backend/app/rag/vector_store.py` - ChromaDB operations
- `backend/app/rag/decision.py` - RAG karar mekanizması

### 4. Doküman Yönetimi
- Upload (PDF, DOCX, TXT, max 10MB)
- List ve detay görüntüleme
- Delete (doküman ve vector'ları siler)
- Klasör sistemi
- Gelişmiş arama (query, folder, mime_type, tags, date range)

**Dosyalar:**
- `backend/app/routes/documents.py` - Tüm document endpoints
- `frontend/app/documents/page.tsx` - Doküman listesi sayfası
- `frontend/components/DocumentPicker.tsx` - Doküman seçici component

### 5. Matematik Rendering
- KaTeX ile LaTeX matematik ifadeleri render edilir
- System prompt matematik format kuralları içerir
- Streaming sırasında delimiter düzeltmeleri

**Dosyalar:**
- `frontend/app/chat/page.tsx` - `normalizeMath()` fonksiyonu
- `backend/app/main.py` - System prompt'ta matematik kuralları

---

## 📁 Proje Yapısı

```
bitirme/
├── backend/
│   ├── app/
│   │   ├── main.py                    # Ana FastAPI app (4000+ satır)
│   │   ├── auth.py                    # Authentication utilities
│   │   ├── database.py                # MongoDB connection
│   │   ├── documents.py               # Text extraction (PDF/DOCX/TXT)
│   │   ├── chat_title.py              # Otomatik başlık oluşturma
│   │   ├── schemas.py                 # Pydantic models
│   │   ├── models.py                  # Database models
│   │   ├── utils.py                   # Utility functions
│   │   ├── memory/                    # Memory sistemi
│   │   │   ├── message_store.py       # Message kaydetme/getirme
│   │   │   ├── state.py               # Conversation state
│   │   │   ├── summary_store.py       # Chat summary
│   │   │   └── carryover.py           # Follow-up continuity
│   │   ├── rag/                       # RAG sistemi
│   │   │   ├── chunker.py             # Text chunking
│   │   │   ├── embedder.py            # Text embedding
│   │   │   ├── vector_store.py        # ChromaDB operations
│   │   │   ├── decision.py            # RAG karar mekanizması
│   │   │   ├── context_builder.py     # Context building
│   │   │   ├── answer_validator.py    # Answer validation
│   │   │   └── intent.py              # Intent detection
│   │   └── routes/
│   │       └── documents.py           # Document endpoints
│   ├── tests/                         # Test dosyaları
│   ├── data/                          # ChromaDB data
│   ├── requirements.txt               # Python dependencies
│   └── README.md                      # Backend dokümantasyonu
│
├── frontend/
│   ├── app/
│   │   ├── chat/page.tsx              # Ana chat sayfası (4000+ satır)
│   │   ├── documents/page.tsx         # Doküman listesi
│   │   ├── login/page.tsx             # Login sayfası
│   │   ├── register/page.tsx          # Register sayfası
│   │   ├── globals.css                # Global CSS
│   │   └── layout.tsx                 # Root layout
│   ├── components/
│   │   ├── chat/
│   │   │   ├── MessageItem.tsx        # Mesaj render component
│   │   │   ├── MessageActions.tsx     # Copy/Info butonları
│   │   │   └── Avatar.tsx              # Avatar component
│   │   ├── layout/
│   │   │   ├── Sidebar.tsx             # Chat listesi
│   │   │   └── Topbar.tsx              # Top bar
│   │   └── DocumentPicker.tsx         # Doküman seçici
│   ├── lib/
│   │   ├── api.ts                     # API client
│   │   └── auth.ts                    # Auth utilities
│   ├── contexts/
│   │   └── SidebarContext.tsx          # Sidebar state
│   ├── providers/
│   │   └── ChakraProvider.tsx          # Chakra UI provider
│   ├── package.json                   # Node dependencies
│   └── next.config.js                  # Next.js config
│
├── START_BACKEND.bat                  # Backend başlatma scripti
├── START_FRONTEND.bat                 # Frontend başlatma scripti
├── README.md                           # Bu dosya
└── PROJE_SUNUMU.md                     # Detaylı proje dokümantasyonu
```

---

## 🚀 Kurulum ve Çalıştırma

### Gereksinimler
- Python 3.9+
- Node.js 18+
- MongoDB (yerel veya cloud)
- ChromaDB (otomatik kurulur)

### Backend Kurulumu

```bash
cd backend
pip install -r requirements.txt
```

### Backend Çalıştırma

```bash
# Windows
START_BACKEND.bat

# veya manuel
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Backend `http://localhost:8000` adresinde çalışır.

### Frontend Kurulumu

```bash
cd frontend
npm install
```

### Frontend Çalıştırma

```bash
# Windows
START_FRONTEND.bat

# veya manuel
npm run dev
```

Frontend `http://localhost:3000` adresinde çalışır.

### Environment Variables

Backend için `.env` dosyası oluşturun:

```env
MONGODB_URL=mongodb://localhost:27017
DATABASE_NAME=auth_db
SECRET_KEY=your-secret-key-here
GOOGLE_CLIENT_ID=your-google-client-id
OPENROUTER_API_KEY=your-openrouter-api-key
OPENROUTER_MODEL=openai/gpt-4o-mini
OPENROUTER_API_URL=https://openrouter.ai/api/v1/chat/completions
```

---

## 🏗 Sistem Mimarisi

### 1. Kullanıcı Kaydı/Girişi
```
Register/Login → JWT token al → Token localStorage'da sakla
```

### 2. Chat Oluşturma
```
POST /chats → Chat ID al → Frontend'de chat aç
```

### 3. Doküman Yükleme
```
Upload file → Text extraction → Chunking → Embedding → ChromaDB'ye kaydet
```

### 4. Chat ile Soru Sorma (RAG Akışı)
```
1. User mesajı gönder
2. Eğer documentIds varsa:
   - Document'ları MongoDB'den getir
   - Query'yi embed et (1536 boyutlu vector)
   - ChromaDB'de semantic search yap (cosine similarity)
   - İlgili chunk'ları bul (score > 0.25)
   - Context'i prompt'a ekle
3. Chat geçmişini getir (son 10 mesaj)
4. OpenRouter API'ye istek gönder (streaming)
5. Response'u kaydet ve döndür
```

### 5. Başlık Oluşturma
```
2. mesajdan sonra:
- LLM ile başlık oluşturmayı dene (3-7 kelime, spesifik)
- Başarısız olursa rule-based fallback kullan
- Chat'i güncelle
```

---

## 📡 API Dokümantasyonu

### Auth Endpoints
- `POST /auth/register` - Kullanıcı kaydı
- `POST /auth/login` - Email/Password giriş
- `POST /auth/google` - Google OAuth giriş
- `GET /me` - Kullanıcı bilgileri

### Chat Endpoints
- `POST /chats` - Chat oluştur
- `GET /chats` - Chat listesi
- `GET /chats/{id}` - Chat detayı
- `GET /chats/{id}/messages` - Mesajları getir
- `PATCH /chats/{id}` - Chat başlığını güncelle
- `DELETE /chats/{id}` - Chat sil (cascade: messages)

### AI Chat Endpoint
- `POST /chat` - AI ile sohbet (RAG destekli)
  - **Request:**
    ```json
    {
      "chatId": "string",
      "message": "string",
      "documentIds": ["string"],
      "client_message_id": "uuid",
      "mode": "normal|summarize"
    }
    ```
  - **Response:**
    ```json
    {
      "message": "string",
      "sources": [...],
      "debug_info": {...},
      "chatId": "string"
    }
    ```

### Documents Endpoints
- `POST /documents/upload` - Doküman yükle
- `GET /documents` - Doküman listesi
- `GET /documents/{id}` - Doküman detayı
- `DELETE /documents/{id}` - Doküman sil
- `POST /documents/search` - Gelişmiş arama

### Debug Endpoints
- `GET /debug/rag` - RAG debug endpoint (auth gerekli)

API dokümantasyonu: `http://localhost:8000/docs` (Swagger UI)

---

## 🗄 Veritabanı Yapısı

### MongoDB Collections

#### users
```json
{
  "_id": "ObjectId",
  "username": "string",
  "email": "string",
  "password_hash": "string",
  "google_sub": "string (optional)",
  "created_at": "datetime"
}
```

#### chats
```json
{
  "_id": "ObjectId",
  "user_id": "string",
  "title": "string",
  "created_at": "datetime",
  "updated_at": "datetime",
  "has_messages": "boolean"
}
```

#### chat_messages
```json
{
  "_id": "ObjectId",
  "user_id": "string",
  "chat_id": "string",
  "role": "user|assistant",
  "content": "string",
  "sources": [...],
  "client_message_id": "string (optional)",
  "created_at": "datetime"
}
```

#### documents
```json
{
  "_id": "ObjectId",
  "user_id": "string",
  "filename": "string",
  "mime_type": "string",
  "text_content": "string",
  "uploaded_from_chat_id": "string (optional)",
  "created_at": "datetime"
}
```

#### folders
```json
{
  "_id": "ObjectId",
  "user_id": "string",
  "name": "string",
  "parent_id": "string (optional)",
  "created_at": "datetime"
}
```

### ChromaDB (Vector Store)
- **Collection**: `documents`
- **Embedding dimension**: 1536 (OpenAI text-embedding-3-small)
- **Metadata**: `document_id`, `chunk_index`, `original_filename`

---

## 🔧 Önemli Konfigürasyonlar

### RAG Ayarları
- `RAG_TOP_K`: 4 (en iyi 4 chunk getir)
- `RAG_SCORE_THRESHOLD`: 0.25 (relevance threshold)
- Chunk size: 300 kelime
- Chunk overlap: 50 kelime

### Limitler
- Max file size: 10MB
- Max text length: 200,000 karakter
- Max PDF pages: 200
- Max DOCX paragraphs: 10,000

### Memory Sistemi
- Chat geçmişi: Son 10 mesaj
- Context window: 2000 tokens
- Hard limit: 50 mesaj

---

## 🎨 Özel Özellikler

1. **Otomatik Başlık Oluşturma** - 3 katmanlı sistem (LLM → Fallback → Rule-based)
2. **Memory Sistemi** - Chat geçmişi otomatik kaydedilir
3. **RAG Fallback** - Vector search başarısız olursa document text_content direkt kullanılır
4. **Background Processing** - Chat response generation client disconnect'ten bağımsız
5. **Idempotency** - `client_message_id` ile duplicate request önleme
6. **Cascade Delete** - Chat silindiğinde messages otomatik silinir
7. **User-scoped Documents** - Documents global pool'da, chat delete'te silinmez
8. **Streaming Support** - Real-time response streaming
9. **Matematik Rendering** - KaTeX ile LaTeX matematik ifadeleri
10. **Responsive Design** - Mobil ve desktop uyumlu

---

## 📊 Test Altyapısı

### Test Dosyaları
- `backend/tests/test_smoke.py` - 6 smoke test
- `backend/tests/test_chat_flow.py` - Chat akış testi
- `backend/tests/test_documents_flow.py` - Document akış testi
- `backend/tests/test_cascade_delete.py` - Cascade delete testi
- `backend/tests/test_debug_security.py` - Güvenlik testi
- `backend/tests/test_chat_response.py` - Response format testi
- `backend/tests/e2e/test_full_flow.py` - E2E testleri

**Toplam: 13 test, hepsi geçiyor**

### Çalıştırma
```bash
cd backend
pip install -r requirements-dev.txt
TEST_BASE_URL=http://localhost:8000 pytest -v
```

---

## 📝 Detaylı Dokümantasyon

Daha detaylı bilgi için:
- `PROJE_SUNUMU.md` - Kapsamlı proje dokümantasyonu
- `backend/README.md` - Backend dokümantasyonu
- `http://localhost:8000/docs` - API Swagger UI

---

## 👥 Geliştirici Notları

### Önemli Dosyalar

**Backend:**
- `backend/app/main.py` - Ana FastAPI app (4000+ satır)
- `backend/app/memory/message_store.py` - Message persistence
- `backend/app/rag/decision.py` - RAG karar mekanizması
- `backend/app/rag/vector_store.py` - ChromaDB operations

**Frontend:**
- `frontend/app/chat/page.tsx` - Ana chat sayfası (4000+ satır)
- `frontend/lib/api.ts` - API client
- `frontend/components/chat/MessageItem.tsx` - Mesaj render component

### Debugging
- Backend logları: Console output
- Frontend logları: Browser console
- API errors: `[API Error]` prefix ile loglanır

---

## 📄 Lisans

Bu proje bitirme projesi olarak geliştirilmiştir.

---

**HACE** - Kişisel Bilgi Asistanı | 2024

