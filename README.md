# 🩺 Medical Assistant — Intelligent RAG System

**A production-grade, personalized medical information assistant powered by NHS data and Large-Scale RAG.**

Built for accuracy, safety, and exceptional user experience.

---

## Key Features

- **Hybrid RAG Architecture** — Object-as-a-Doc with rich metadata
- **Smart Telegram UX**:
  - Real-time typing animation using Message Drafts
  - All medical sections rendered as **expandable blockquotes**
  - Smart "View Images" button that disappears after use
- **Personalized Retrieval** — Age, chronic conditions, and history-aware
- **Dynamic Model Rotation** — Automatic fallback on rate limits (Gemini models)
- **Zero Information Loss** — Full structured + raw content available
- **High Safety Standards** — Red flag detection, urgency triage, strict disclaimers
- **Fast & Scalable** — Pre-loaded embeddings + FAISS at startup

---

## Architecture

```
Query → Symptom Extraction → Personalized Retrieval → 
LLM Synthesis → Structured Output → Telegram Rich UI
```

**Core Components:**
- **Retriever**: FAISS + BGE embeddings with hybrid scoring (keyword + semantic + personalization)
- **Generator**: Gemini models with intelligent rotation
- **UI Layer**: Aiogram 3.x with expandable blockquotes + dynamic inline keyboards
- **Data Pipeline**: NHS scraper → Structurer → Rich Document Indexer

---

## Tech Stack

- **Backend**: FastAPI + Aiogram 3
- **LLM**: Google Gemini (dynamic multi-model rotation)
- **Embeddings**: `sentence-transformers/all-MiniLM-L6-v2`
- **Vector Store**: FAISS (Object-as-a-Doc)
- **Frontend**: Telegram Bot (Rich HTML + Expandable Blockquotes)
- **Scraping**: BeautifulSoup4 + NHS.uk
- **Others**: LangChain, Pydantic, asyncio, dotenv

---

## Quick Start

### 1. Clone & Setup
```bash
git clone https://github.com/natty4/ai-med-assistant.git
cd ai-medical-assistant
python -m venv venv
source venv/bin/activate    # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Environment Variables (`.env`)
```env
GOOGLE_API_KEY=your_key_here
TELEGRAM_BOT_TOKEN=your_bot_token_here

# Optional
LLM_MODELS=google-gemini-models
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

### 3. Data Pipeline
```bash
# 1. Scrape NHS data
python run_ingestion.sh
 or
python -m scripts.ingest

# 2. Build vector index
python -m scripts.build_index
```

### 4. Run Services

**Telegram Bot:**
```bash
python -m app.bot.main
```

**FastAPI Backend:**
```bash
uvicorn app.api.main:app --host 0.0.0.0 --port 8080 --reload
```

---

## How It Works

1. **User Query** → Early non-medical filter + symptom extraction
2. **Retrieval** → Personalized similarity search (boosts chronic conditions, age, etc.)
3. **Generation** → LLM receives structured markdown + full page context
4. **Response** → Clean summary + urgency + expandable sections
5. **UI** → Telegram message edited dynamically with rich formatting

**Urgency Levels**: LOW (🟢), MEDIUM (🟡), HIGH (🔴) with clear guidance.

---

## Safety & Responsibility

- **Never diagnoses** — Only provides information from official NHS sources
- **Strict red-flag detection** for emergencies
- **Conservative triage** — errs on the side of caution
- **Clear disclaimers** on every response
- **Not a replacement** for professional medical advice

> **⚠️ Always consult a qualified healthcare professional for medical concerns.**

---

## Future Enhancements

- Full raw HTML + semantic chunking strategy
- Voice input support
- Multi-language (starting with Amharic)
- User feedback loop & continuous learning
- Web dashboard + history analytics
- Redis session store for horizontal scaling

---

## Performance

- Cold start: ~4–6 seconds (embeddings + FAISS preload)
- Average response: < 1.8s after warm-up
- Supports concurrent users efficiently

---

“💙 Empowering proactive accessible healthcare information through evidence-based AI.”

---

**Contributing** • **License** • **Disclaimer**

---

