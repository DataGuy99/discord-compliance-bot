# Discord S&P Compliance Bot

AI-powered compliance assistant for Discord using **Grok-4-latest** with **RAG (Retrieval-Augmented Generation)**.

## Architecture

- **FastAPI Backend**: Heroku-hosted API with Grok-4 + RAG
- **Discord Bot**: Slash commands for user interaction
- **PostgreSQL**: User data, query logs, feedback
- **Redis**: Vector storage for RAG (100k+ chunks)
- **Docker**: Isolated development environment

## Features

- 🤖 **Grok-4-latest AI**: Fast, accurate compliance responses
- 📚 **RAG System**: Citation-backed answers from compliance documents
- ⚡ **Hybrid Search**: Vector similarity + BM25 keyword matching
- 📊 **Admin Dashboard**: System stats, flagged queries, audit logs
- 🔒 **Rate Limiting**: 30 req/min per user, configurable daily limits
- 📈 **Observability**: Structured logging, OpenTelemetry tracing
- ✅ **GDPR Compliant**: User data deletion on request

## Tech Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| Python | CPython | 3.12.7 |
| Web Framework | FastAPI | 0.115.2 |
| ASGI Server | granian | 1.5.2 |
| AI Model | Grok-4-latest | xai 1.0.3 |
| Database | PostgreSQL | 16 (asyncpg) |
| Cache/Vectors | Redis | 7 (RediSearch) |
| Embeddings | sentence-transformers | 3.0.1 (thenlper/gte-small) |
| Discord | discord.py | 2.6.3 |
| Container | Docker | 28.4.0+ |

## Quick Start

### Prerequisites

- Docker 28.4.0+
- docker-compose v2.39.4+
- xAI API key (get from [x.ai/api](https://x.ai/api))

### Local Development

1. **Clone repository**
```bash
cd ~/Downloads/Projects
git clone https://github.com/yourusername/discord-compliance-bot.git
cd discord-compliance-bot
```

2. **Configure environment**
```bash
# FastAPI backend
cp heroku-api/.env.example heroku-api/.env
# Edit heroku-api/.env and set XAI_API_KEY

# Discord bot
cp discord-bot/.env.example discord-bot/.env
# Edit discord-bot/.env and set DISCORD_BOT_TOKEN
```

3. **Start services**
```bash
docker-compose up -d
```

4. **Run migrations**
```bash
docker-compose exec api alembic upgrade head
```

5. **Verify health**
```bash
curl http://localhost:8000/health/detailed
```

### API Endpoints

**Health Checks**
- `GET /health` - Basic health
- `GET /health/detailed` - Full component checks
- `GET /health/ready` - Kubernetes readiness
- `GET /health/live` - Kubernetes liveness
- `GET /health/metrics` - Prometheus metrics

**Query**
- `POST /api/v1/query` - Submit compliance query
- `POST /api/v1/feedback` - Submit feedback
- `GET /api/v1/history/{user_id}` - Query history

**Admin** (requires `X-Admin-Token` header)
- `GET /admin/stats` - System statistics
- `GET /admin/users` - User management
- `PUT /admin/users/{user_id}` - Update user permissions
- `GET /admin/queries/flagged` - Flagged queries
- `GET /admin/audit-log` - Audit trail
- `POST /admin/model/retrain` - Ingest new documents
- `DELETE /admin/users/{user_id}/queries` - GDPR deletion

### Discord Commands

**User Commands**
- `/ask <question>` - Ask compliance question
- `/history [limit]` - View query history

**Admin Commands**
- `/stats` - System statistics
- `/flagged [limit]` - View flagged queries
- `/sync` - Sync slash commands
- `/botstatus` - Bot connection status

## Deployment

### Heroku (Recommended)

1. **Click Deploy Button**

[![Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy)

2. **Configure add-ons**
   - PostgreSQL: Essential-0 ($5/mo)
   - Redis: Mini ($3/mo)
   - Papertrail: Chokladfabrik (free)

3. **Set environment variables**
   - `XAI_API_KEY` - Your xAI API key
   - `ADMIN_TOKEN` - Generate secure token
   - `CORS_ORIGINS` - `https://discord.com`

4. **Deploy**
```bash
git push heroku main
heroku run alembic upgrade head
heroku logs --tail
```

### Manual Deployment

See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) for detailed instructions.

## Configuration

### Environment Variables

**Required**
- `XAI_API_KEY` - xAI API key for Grok-4
- `DATABASE_URL` - PostgreSQL connection string
- `REDIS_VECTOR_URL` - Redis connection string
- `ADMIN_TOKEN` - Admin authentication token

**Optional**
- `ENVIRONMENT` - `production`, `staging`, `development` (default: `production`)
- `LOG_LEVEL` - `DEBUG`, `INFO`, `WARNING`, `ERROR` (default: `INFO`)
- `CORS_ORIGINS` - Comma-separated allowed origins (default: `https://discord.com`)
- `EMBED_MODEL` - Embedding model (default: `thenlper/gte-small`)
- `CHUNK_SIZE` - RAG chunk size (default: `512`)
- `TOP_K_RAG` - RAG chunks to retrieve (default: `5`)
- `GROK_TEMP` - Grok-4 temperature (default: `0.7`)

## Performance

- **API Response**: ~2.2s (Grok-4 + RAG)
- **Cold Start**: <160ms (granian)
- **RAG Retrieval**: ~35ms (Redis vector search)
- **Embedding**: ~60 chunks/sec (CPU)
- **Throughput**: 30 req/min per user

## Cost Estimate (10k users)

| Service | Plan | Cost |
|---------|------|------|
| Heroku Dyno | Basic | $7/mo |
| PostgreSQL | Essential-0 | $5/mo |
| Redis | Mini | $3/mo |
| Papertrail | Chokladfabrik | Free |
| xAI API | Pay-as-go | ~$40/mo |
| **Total** | | **$55/mo** |

## Development

### Project Structure

```
discord-compliance-bot/
├── heroku-api/              # FastAPI backend
│   ├── app/
│   │   ├── database/        # SQLAlchemy models
│   │   ├── models/          # Pydantic schemas + exceptions
│   │   ├── rag/             # RAG system (splitter, embedder, store, retriever)
│   │   ├── routers/         # API endpoints (health, query, admin)
│   │   └── services/        # Business logic (grok4_rag_service)
│   ├── alembic/             # Database migrations
│   ├── main.py              # FastAPI app entrypoint
│   └── requirements.txt
├── discord-bot/             # Discord bot
│   ├── commands/            # Slash commands (compliance, admin)
│   ├── handlers/            # Event and error handlers
│   ├── utils/               # API client, logger
│   ├── main.py              # Bot entrypoint
│   └── requirements.txt
├── docker-compose.yml       # Local development
├── Dockerfile
├── app.json                 # Heroku deployment
├── .github/workflows/       # CI/CD pipeline
└── PROJECT_LOG.md           # Development progress

45 files total
```

### Testing

```bash
# Run tests with coverage
pytest heroku-api/ -v --cov=heroku-api

# Lint
ruff check heroku-api/

# Format
ruff format heroku-api/
```

### Database Migrations

```bash
# Create migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

## RAG System

### Document Ingestion

1. **Download PDF** from URL
2. **Extract text** with pypdf
3. **Split into chunks** (512 tokens, 50 overlap)
4. **Generate embeddings** (thenlper/gte-small, 384-dim)
5. **Store in Redis** with RediSearch indexing

### Query Flow

1. **Embed query** (same model as documents)
2. **Hybrid search**:
   - Vector similarity (COSINE distance)
   - BM25 keyword matching
   - Reciprocal rank fusion
3. **Retrieve top 5 chunks**
4. **Send to Grok-4** with system prompt
5. **Parse JSON response** (answer, confidence, risk)
6. **Return with citations**

## Security

- ✅ Admin token authentication
- ✅ Rate limiting (per-user and global)
- ✅ CORS protection
- ✅ Input validation (Pydantic)
- ✅ SQL injection prevention (ORM)
- ✅ Audit logging
- ✅ GDPR compliance

## Monitoring

- **Structured Logging**: JSON logs to Papertrail
- **OpenTelemetry**: Distributed tracing (production)
- **Health Endpoints**: `/health/*` for K8s/monitoring
- **Metrics**: Prometheus-compatible `/health/metrics`

## Contributing

1. Fork repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

## License

MIT License - see [LICENSE](LICENSE) for details

## Support

- **Issues**: [GitHub Issues](https://github.com/yourusername/discord-compliance-bot/issues)
- **Documentation**: See [docs/](docs/)
- **Discord**: [Join our server](https://discord.gg/yourinvite)

---

**Built with ❤️ using Grok-4-latest, FastAPI, and discord.py**