# S&P Compliance Discord Bot - Complete Implementation Game Plan
**Version:** 2.0 (Grok-4 + RAG Enhanced)
**Date:** 2025-09-29
**Status:** Ready to Build

---

## 📋 EXECUTIVE SUMMARY

**What We're Building:**
A production-grade Discord bot that answers S&P compliance questions using Grok-4-latest AI with RAG (Retrieval-Augmented Generation) for accurate, citation-backed responses.

**Architecture:**
- **Frontend:** Discord bot (discord.py 2.6.3+)
- **Backend API:** FastAPI 0.115.2 on Heroku
- **AI Engine:** Grok-4-latest (xAI API)
- **Knowledge Base:** RAG with Redis vector store + sentence-transformers
- **Database:** PostgreSQL 16 (user data, audit logs)
- **Deployment:** Heroku with CI/CD via GitHub Actions

**Key Constraints (Iron Rules):**
✅ Must use Docker for development isolation
✅ Must deploy to Heroku (not AWS/GCP)
✅ Must use Grok-4-latest (not GPT-4/Claude)
✅ Must have RAG for accurate compliance answers
✅ Budget: <$100/month @ 10k daily active users
✅ Must be SOC-2 audit ready

---

## 🎯 BASE ARCHITECTURE (from DETAILED_TECHNICAL_BREAKDOWN.md)

### Component 1: Heroku API Backend (FastAPI)

**Purpose:** AI processing, RAG retrieval, database operations, admin interface

**File Structure:**
```
heroku-api/
├── app/
│   ├── __init__.py
│   ├── models/
│   │   └── exceptions.py              # Custom exceptions (7 classes)
│   ├── services/
│   │   └── grok4_rag_service.py       # NEW: Grok-4 + RAG (replaces model_service.py)
│   ├── rag/                           # NEW: RAG System
│   │   ├── __init__.py
│   │   ├── splitter.py                # Text chunking (512 tokens, 50 overlap)
│   │   ├── embedder.py                # sentence-transformers (thenlper/gte-small)
│   │   ├── store.py                   # Redis vector storage
│   │   ├── retriever.py               # Hybrid search (vector + BM25)
│   │   └── ingest.py                  # PDF ingestion pipeline
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── health.py                  # Health checks (5 endpoints)
│   │   ├── query.py                   # Main compliance queries
│   │   └── admin.py                   # Admin interface (7 endpoints)
│   └── database/
│       ├── __init__.py
│       ├── connection.py              # Async SQLAlchemy setup
│       └── models.py                  # 5 models: User, QueryLog, QueryFeedback,
│                                      #            ComplianceDocument, SystemAuditLog
├── alembic/
│   ├── versions/
│   ├── env.py
│   └── script.py.mako
├── main.py                            # FastAPI app entry point
├── requirements.txt                   # UPDATED: Grok-4 + RAG deps
├── Procfile                           # UPDATED: granian (not gunicorn)
├── runtime.txt                        # Python 3.12
├── alembic.ini
├── app.json                           # Heroku manifest
├── Dockerfile                         # Dev environment
└── .env.example
```

**Key Database Models (from markdown):**
1. **User** (25 fields): Discord auth, RBAC, permissions
2. **QueryLog** (20 fields): Full query/response audit trail
3. **QueryFeedback** (12 fields): User ratings, accuracy feedback
4. **ComplianceDocument** (18 fields): Policy storage, versioning
5. **SystemAuditLog** (15 fields): Admin actions, security events

**API Endpoints (from markdown):**
- **Health:** `/health`, `/health/detailed`, `/health/ready`, `/health/live`, `/health/metrics`
- **Query:** `POST /api/v1/query`, `POST /api/v1/feedback`, `GET /api/v1/history/{user_id}`
- **Admin:** `GET /admin/stats`, `GET /admin/users`, `PUT /admin/users/{user_id}`,
             `GET /admin/queries/flagged`, `GET /admin/audit-log`,
             `POST /admin/model/retrain`, `DELETE /admin/users/{user_id}/queries`

---

### Component 2: Discord Bot (discord.py)

**Purpose:** User interaction via slash commands, event handling

**File Structure:**
```
discord-bot/
├── bot/
│   ├── __init__.py
│   ├── commands/
│   │   ├── __init__.py
│   │   ├── compliance.py              # /ask command
│   │   └── admin.py                   # /stats, /health commands
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── events.py                  # on_ready, on_guild_join, etc.
│   │   └── errors.py                  # Error handling
│   └── utils/
│       ├── __init__.py
│       ├── api_client.py              # HTTP client for Heroku API
│       └── formatting.py              # Discord embed formatting
├── main.py                            # Bot entry point
├── requirements.txt
└── .env.example
```

**Discord Commands:**
- `/ask <question>` - Ask compliance question
- `/feedback <rating>` - Rate last answer
- `/stats` - Bot statistics (admin only)
- `/health` - API health status (admin only)

---

## 🚀 UPGRADES FROM TXT/HTML (Grok-4 + RAG)

### Change 1: Replace OpenAI with Grok-4-latest

**Old (markdown):**
```python
# Used: openai==1.54.0+
from openai import AsyncOpenAI
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
```

**New (txt):**
```python
# Use: xai==1.0.3
from xai import AsyncXAI
client = AsyncXAI(api_key=os.getenv("XAI_API_KEY"))
model = "grok-4-latest"  # Always latest version
```

---

### Change 2: Add RAG System

**Why:** Ensures answers are grounded in actual compliance documents with citations

**Components:**

1. **Embedder** (`app/rag/embedder.py`):
   - Model: `thenlper/gte-small` (384-dim, 14MB, CPU-friendly)
   - 60 chunks/second on free Heroku dyno

2. **Splitter** (`app/rag/splitter.py`):
   - 512 tokens per chunk
   - 50 token overlap
   - Preserves context between chunks

3. **Vector Store** (`app/rag/store.py`):
   - Redis with RediSearch module
   - 100k chunks free tier
   - Stores: [chunk_text, embedding_vector, metadata]

4. **Retriever** (`app/rag/retriever.py`):
   - **Hybrid search:** Vector similarity + BM25 keyword matching
   - Returns top 5 chunks with sources
   - Reciprocal Rank Fusion for combining results

5. **Ingestion** (`app/rag/ingest.py`):
   - Downloads PDFs from SEC.gov, internal policies
   - Extracts text, splits, embeds, stores
   - Run once initially, then on policy updates

**RAG Flow:**
```
User Query → Retriever → Top 5 Relevant Chunks →
Grok-4 (with chunks as context) → Answer + Citations
```

---

### Change 3: Faster ASGI Server

**Old:** `gunicorn` with `uvicorn` workers
**New:** `granian==1.5.2` (50% faster cold starts)

**Procfile change:**
```
web: granian heroku-api.main:app --interface asgi --workers 2 --loop uvloop --host 0.0.0.0 --port $PORT
```

---

### Change 4: Observability with OpenTelemetry

**Add:**
```python
# requirements.txt
opentelemetry-distro==0.47b0
opentelemetry-instrumentation-fastapi==0.47b0

# main.py
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
FastAPIInstrumentor.instrument_app(app)
```

**Traces → Papertrail (7-day retention, free tier)**

---

## 📦 COMPLETE DEPENDENCIES (requirements.txt)

### Heroku API
```
# ASGI / Web
fastapi[all]==0.115.2
granian==1.5.2

# AI - Grok-4
xai==1.0.3

# RAG System
sentence-transformers==3.0.1
redis[hiredis]==5.0.6
rank-bm25==0.2.2

# Database
sqlalchemy[asyncio]==2.0.36
alembic==1.13.2
asyncpg==0.30.0

# Observability
structlog==24.4.0
opentelemetry-distro==0.47b0
opentelemetry-instrumentation-fastapi==0.47b0

# Utilities
pydantic==2.10.3
python-dotenv==1.0.1
httpx==0.28.0
```

### Discord Bot
```
# Discord
discord.py[voice]==2.6.3

# HTTP Client
httpx==0.28.0
aiohttp==3.10.11

# Utilities
structlog==24.4.0
rich==13.9.4
python-dotenv==1.0.1
```

---

## 🔐 ENVIRONMENT VARIABLES

### Heroku API (.env)
```bash
# Grok-4
XAI_API_KEY=xai-xxxxxxxxxxxxxxxxx

# RAG
REDIS_VECTOR_URL=redis://...  # Auto-set by Heroku Redis addon
EMBED_MODEL=thenlper/gte-small
EMBED_DIM=384
CHUNK_SIZE=512
CHUNK_OVERLAP=50
TOP_K_RAG=5
GROK_TEMP=0.7
GROK_TIMEOUT=28

# Database
DATABASE_URL=postgresql://...  # Auto-set by Heroku Postgres addon

# Security
ADMIN_TOKEN=random-secure-token-here
CORS_ORIGINS=https://discord.com

# Environment
ENVIRONMENT=production
PYTHON_RUNTIME_VERSION=3.12
```

### Discord Bot (.env)
```bash
# Discord
DISCORD_TOKEN=your-discord-bot-token
DISCORD_CLIENT_ID=your-client-id

# API
HEROKU_API_URL=https://sp-compliance-prod.herokuapp.com
ADMIN_TOKEN=same-as-heroku-api

# Logging
LOG_LEVEL=INFO
```

---

## 🏗️ BUILD ORDER (Step-by-Step)

### Phase 1: Foundation (Files 1-10)
1. ✅ `PROJECT_LOG.md` - Already created
2. ✅ `IMPLEMENTATION_GAMEPLAN.md` - This file
3. `heroku-api/.gitignore`
4. `heroku-api/requirements.txt`
5. `heroku-api/runtime.txt`
6. `heroku-api/Procfile`
7. `heroku-api/.env.example`
8. `heroku-api/Dockerfile`
9. `docker-compose.yml`
10. `heroku-api/app/__init__.py`

### Phase 2: Database Layer (Files 11-15)
11. `heroku-api/app/database/__init__.py`
12. `heroku-api/app/database/connection.py`
13. `heroku-api/app/database/models.py` (5 models, 311 lines from markdown)
14. `heroku-api/alembic.ini`
15. `heroku-api/alembic/env.py`

### Phase 3: RAG System (Files 16-21) **NEW**
16. `heroku-api/app/rag/__init__.py`
17. `heroku-api/app/rag/splitter.py`
18. `heroku-api/app/rag/embedder.py`
19. `heroku-api/app/rag/store.py`
20. `heroku-api/app/rag/retriever.py`
21. `heroku-api/app/rag/ingest.py`

### Phase 4: Core Services (Files 22-24)
22. `heroku-api/app/models/__init__.py`
23. `heroku-api/app/models/exceptions.py` (78 lines, 7 exception classes from markdown)
24. `heroku-api/app/services/grok4_rag_service.py` **UPDATED** (replaces model_service.py)

### Phase 5: API Routers (Files 25-28)
25. `heroku-api/app/routers/__init__.py`
26. `heroku-api/app/routers/health.py` (198 lines, 5 endpoints from markdown)
27. `heroku-api/app/routers/query.py` (346 lines, 3 endpoints from markdown)
28. `heroku-api/app/routers/admin.py` (427 lines, 7 endpoints from markdown)

### Phase 6: FastAPI App (File 29)
29. `heroku-api/main.py` (184 lines from markdown, add OTel instrumentation)

### Phase 7: Discord Bot (Files 30-40)
30. `discord-bot/.gitignore`
31. `discord-bot/requirements.txt`
32. `discord-bot/.env.example`
33. `discord-bot/bot/__init__.py`
34. `discord-bot/bot/utils/__init__.py`
35. `discord-bot/bot/utils/api_client.py`
36. `discord-bot/bot/utils/formatting.py`
37. `discord-bot/bot/commands/__init__.py`
38. `discord-bot/bot/commands/compliance.py`
39. `discord-bot/bot/handlers/__init__.py`
40. `discord-bot/bot/handlers/events.py`
41. `discord-bot/main.py` (313 lines from markdown)

### Phase 8: Deployment (Files 42-45)
42. `heroku-api/app.json` (Heroku manifest)
43. `.github/workflows/deploy.yml` (CI/CD)
44. `README.md`
45. Root `.gitignore`

---

## 🧪 TESTING PLAN

### Local Testing (Docker)
```bash
# Start services
docker-compose up -d

# Test API health
curl http://localhost:8000/health/detailed

# Test RAG ingestion
docker-compose exec api python -m app.rag.ingest

# Test query
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"query":"Can I trade during blackout?","user_id":"test"}'

# Test Discord bot
python discord-bot/main.py
```

### Heroku Testing
```bash
# Create Heroku apps
heroku create sp-compliance-prod --stack heroku-24
heroku create sp-compliance-stage --stack heroku-24

# Add addons
heroku addons:create heroku-postgresql:mini -a sp-compliance-prod
heroku addons:create heroku-redis:mini -a sp-compliance-prod
heroku addons:create papertrail:choklad -a sp-compliance-prod

# Set config
heroku config:set XAI_API_KEY=xai-xxx -a sp-compliance-prod
heroku config:set ADMIN_TOKEN=xxx -a sp-compliance-prod

# Deploy
git push heroku main

# Check logs
heroku logs --tail -a sp-compliance-prod
```

---

## 💰 COST BREAKDOWN (10k DAUs)

| Service | Plan | Cost |
|---------|------|------|
| Heroku Dyno (API) | Basic | $7/mo |
| Heroku Postgres | Mini | $5/mo |
| Heroku Redis | Mini | $3/mo |
| Grok-4 API | Pay-as-you-go | ~$40/mo |
| Papertrail | Choklad | $0 (free) |
| **TOTAL** | | **$55/mo** ✅ |

---

## 🚨 CRITICAL SUCCESS FACTORS

1. **RAG Quality:** Ingest high-quality compliance PDFs (SEC rules, S&P policies)
2. **Rate Limiting:** 30 req/min per user to control costs
3. **Monitoring:** Track Grok-4 token usage daily
4. **Fallback:** If Grok-4 fails, return error (no silent failures)
5. **Audit Trail:** Every query logged with timestamp, user, confidence
6. **Security:** Never log sensitive info (PII, passwords)

---

## 📊 PERFORMANCE TARGETS

- **Cold Start:** <160ms (Granian + preload)
- **RAG Retrieval:** <35ms (Redis vector)
- **Grok-4 Response:** ~2.2s (streamed to Discord)
- **End-to-End:** <3s from Discord command to response
- **Uptime:** >99.5% (Heroku SLA)

---

## 🎯 NEXT STEPS

1. ✅ Create this game plan
2. Build Phase 1 (Foundation files)
3. Build Phase 2 (Database layer)
4. Build Phase 3 (RAG system) **NEW**
5. Build Phase 4-6 (API backend)
6. Build Phase 7 (Discord bot)
7. Build Phase 8 (Deployment)
8. Test locally in Docker
9. Deploy to Heroku staging
10. Deploy to Heroku production

---

**END OF GAME PLAN**
*Ready to build. All specifications from markdown + txt/html merged.*