# 🤖 Lala - AI-Powered Personal Assistant

<div align="center">
  <img src="frontend/public/lala-icon.png" alt="Lala Logo" width="120" />
  <p><strong>Kişisel AI Asistan ve LGS Matematik Modülü</strong></p>
</div>

---

## 📋 Proje Hakkında

**Lala**, kişisel belgelerinizi ve e-postalarınızı kullanarak sorularınıza cevap veren, RAG (Retrieval-Augmented Generation) destekli bir AI asistan uygulamasıdır.

### ✨ Özellikler

- 🤖 **Kişisel Asistan**: Belgelerinizi yükleyin, sorularınıza akıllı yanıtlar alın
- 📚 **LGS Matematik Modülü**: Karekök ve LGS matematik konularında uzman asistan
- 📧 **Gmail Entegrasyonu**: E-postalarınızı bilgi kaynağı olarak kullanın
- 📄 **Doküman Desteği**: PDF, Word ve metin dosyalarını işleme
- 🔍 **RAG Sistemi**: ChromaDB ile vektör tabanlı arama
- 💾 **Sohbet Geçmişi**: MongoDB ile kalıcı sohbet kayıtları
- 🎨 **Modern UI**: Chakra UI ile premium dark theme tasarım

---

## 🛠️ Teknolojiler

### Backend
- **Python 3.11+**
- **FastAPI** - Modern, hızlı web framework
- **MongoDB** - NoSQL veritabanı
- **ChromaDB** - Vektör veritabanı
- **Google AI (Gemini)** - LLM entegrasyonu

### Frontend
- **Next.js 14** - React framework
- **TypeScript** - Tip güvenli JavaScript
- **Chakra UI** - UI component library
- **Framer Motion** - Animasyonlar

---

## 🚀 Kurulum

### Gereksinimler
- Python 3.11+
- Node.js 18+
- MongoDB (yerel veya Atlas)
- Google AI API Key

### MongoDB Kurulumu

**Yerel MongoDB:**
1. [MongoDB Community Server](https://www.mongodb.com/try/download/community) indirin
2. Kurulumu tamamlayın ve MongoDB servisini başlatın
3. Varsayılan bağlantı: `mongodb://localhost:27017`

**MongoDB Atlas (Bulut):**
1. [MongoDB Atlas](https://www.mongodb.com/cloud/atlas) hesabı oluşturun
2. Ücretsiz cluster oluşturun
3. Bağlantı URI'sini alın: `mongodb+srv://<user>:<password>@cluster.mongodb.net/`

### Backend Kurulumu

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/macOS
pip install -r requirements.txt
```

`.env` dosyası oluşturun:
```env
# Veritabanı
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB=lala

# API Keys
GOOGLE_AI_API_KEY=your_google_ai_key_here
OPENROUTER_API_KEY=your_openrouter_key_here  # Opsiyonel

# Güvenlik
SECRET_KEY=your_random_secret_key_here

# Gmail Entegrasyonu (Opsiyonel)
GMAIL_CLIENT_ID=your_gmail_client_id
GMAIL_CLIENT_SECRET=your_gmail_client_secret
GMAIL_REDIRECT_URI=http://localhost:3003/api/integrations/gmail/callback
```

Sunucuyu başlatın:
```bash
uvicorn app.main:app --reload --port 8000
```

### Frontend Kurulumu

```bash
cd frontend
npm install
```

`.env.local` dosyası oluşturun:
```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Geliştirme sunucusunu başlatın:
```bash
npm run dev
```

---

## 📁 Proje Yapısı

```
bitirme/
├── backend/
│   ├── app/
│   │   ├── main.py           # FastAPI ana uygulama
│   │   ├── auth.py           # Kimlik doğrulama
│   │   ├── database.py       # MongoDB bağlantısı
│   │   ├── documents.py      # Doküman işleme
│   │   ├── rag/              # RAG sistemi
│   │   └── lgs/              # LGS modülü
│   └── data/                 # Veri dosyaları
├── frontend/
│   ├── app/                  # Next.js App Router
│   ├── components/           # React bileşenleri
│   ├── lib/                  # API ve yardımcı fonksiyonlar
│   └── public/               # Statik dosyalar
└── lgs_karekök_rag.json      # LGS soru bankası
```

---

## 📸 Ekran Görüntüleri

| Giriş Ekranı | Sohbet Arayüzü |
|:------------:|:--------------:|
| Premium dark theme login | AI destekli sohbet |

---

## 👨‍💻 Geliştirici

**Muhammed Salih Helvacı**

---

## 📄 Lisans

Bu proje eğitim amaçlı geliştirilmiştir.

---

<div align="center">
  <sub>Built with ❤️ using Next.js, FastAPI, and Google AI</sub>
</div>
