# VoiceHunte

Production-ready voice-based restaurant reservation system powered by Twilio, OpenAI, and FastAPI.

## Features

**Core Functionality**
- 🎙️ Voice-based conversation system (Twilio + OpenAI Whisper STT)
- 🗣️ Text-to-speech responses (OpenAI TTS)
- 📅 Restaurant reservation management (create, update, cancel)
- 🔍 RAG-powered menu question answering (Qdrant vector DB)
- 🌐 Multi-language support (English, Russian, Ukrainian, Slovak)

**Production Features (P1 - Critical)**
- ✅ Retry logic for external APIs (OpenAI, Qdrant, Twilio) with exponential backoff
- ✅ Rate limiting (Twilio webhooks, admin endpoints)
- ✅ Configurable conversation turns (via `MAX_TURNS` env var)
- ✅ Centralized error handling with Twilio-safe responses
- ✅ Call recording with metadata storage
- ✅ Database migrations (Alembic)
- ✅ PostgreSQL backup & restore automation

**Production Features (P2 - Important)**
- ✅ Call history and session tracking
- ✅ Admin API endpoints for call management
- ✅ Prometheus metrics for monitoring
- ✅ Sentry error tracking with PII filtering
- ✅ Comprehensive integration tests

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Qdrant vector database
- Twilio account (for production calls)
- OpenAI API key

### Local Development

```bash
# Install dependencies
poetry install

# Copy environment template
cp .env.example .env
# Edit .env with your credentials

# Run database migrations
poetry run alembic upgrade head

# Start server
poetry run uvicorn app.main:app --reload
```

### Docker Compose

```bash
# Start all services
docker compose up --build

# Run migrations
docker compose exec api alembic upgrade head
```

**Services**:
- API: http://localhost:8000
- PostgreSQL: localhost:5432
- Qdrant: http://localhost:6333

## API Endpoints

### Health & Monitoring

```bash
GET /health          # Simple health check
GET /ready           # Readiness probe (checks dependencies)
GET /metrics         # Prometheus metrics
```

### Twilio Webhooks

```bash
POST /twilio/incoming          # Initial call handler
POST /twilio/voice             # Voice input processing
POST /twilio/status            # Call status updates
POST /twilio/recording-status  # Recording status callbacks
```

### Admin API

```bash
GET  /admin/calls                  # List call sessions (with pagination)
GET  /admin/calls/{call_id}        # Get detailed call session
GET  /admin/recordings/{call_id}   # Get recording URL
```

### MVP Endpoints

```bash
POST /mvp/text      # Text-based conversation (testing)
POST /mvp/audio     # Audio file upload (testing)
POST /tts/stream    # TTS streaming endpoint
```

## Environment Variables

Key configuration options:

```bash
# App
MAX_TURNS=8                    # Max conversation turns
ENABLE_RECORDING=true          # Enable call recording

# Database
POSTGRES_DSN=postgresql+psycopg://user:pass@host:5432/voicehunte
DB_AUTO_CREATE=false           # Disable auto-schema in production

# External APIs
OPENAI_API_KEY=sk-...
QDRANT_URL=http://localhost:6333
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...

# Rate Limiting
TWILIO_RATE_LIMIT=30/minute
ADMIN_RATE_LIMIT=20/minute

# Retry Logic
RETRY_MAX_ATTEMPTS=4
RETRY_BACKOFF_INITIAL=0.5
RETRY_BACKOFF_MAX=8.0

# Monitoring
SENTRY_DSN=https://...
ENABLE_METRICS=true

# Backups
BACKUP_DIR=/backups
RETENTION_DAYS=30
```

See `.env.example` for complete list.

## Database Management

### Migrations

```bash
# Apply all pending migrations
alembic upgrade head

# Create new migration
alembic revision -m "Description"

# Rollback one migration
alembic downgrade -1
```

### Backups

```bash
# Create backup
./scripts/backup_postgres.sh

# Restore from backup
./scripts/restore_postgres.sh /backups/voicehunte_backup_TIMESTAMP.sql.gz
```

See `docs/BACKUP_RESTORE.md` for detailed guide.

## Testing

```bash
# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=app --cov-report=html

# Run specific test file
poetry run pytest tests/test_call_recording.py -v

# Run integration tests
poetry run pytest tests/test_call_sessions.py tests/test_call_recording.py
```

## Architecture

```
VoiceHunte/
├── app/
│   ├── agent/              # Agent orchestration & state management
│   ├── core/               # Core utilities (config, logging, retry, errors)
│   ├── db/                 # Database layer (PostgreSQL)
│   ├── crm/                # CRM integration (reservations)
│   ├── rag/                # RAG system (Qdrant, embeddings)
│   ├── stt/                # Speech-to-text (OpenAI Whisper)
│   ├── tts/                # Text-to-speech (OpenAI TTS)
│   ├── twilio/             # Twilio integration (webhooks, TwiML)
│   └── main.py             # FastAPI application entry point
├── alembic/                # Database migrations
├── scripts/                # Utility scripts (backup, restore)
├── tests/                  # Test suite
├── docs/                   # Documentation
│   ├── PRODUCTION_READINESS.md  # Production features guide
│   └── BACKUP_RESTORE.md        # Backup & restore guide
└── docker-compose.yml      # Docker orchestration
```

## Production Deployment

### Pre-Deployment Checklist

- [ ] Set `ENVIRONMENT=production`
- [ ] Configure `SENTRY_DSN`
- [ ] Set `DB_AUTO_CREATE=false`
- [ ] Run `alembic upgrade head`
- [ ] Configure backup cron job
- [ ] Set up Prometheus scraping
- [ ] Configure strong database password
- [ ] Set API keys (OpenAI, Twilio)
- [ ] Test `/ready` endpoint
- [ ] Run full test suite
- [ ] Test backup/restore

See `docs/PRODUCTION_READINESS.md` for complete guide.

### Monitoring

Monitor these key metrics:

- Request rate and error rate (Prometheus)
- Response time (p50, p95, p99)
- Active calls (`calls.status='in-progress'`)
- Recording success rate
- Retry attempts (logs)
- Database connection pool

### Troubleshooting

```bash
# Check logs
docker compose logs -f api

# Verify database connection
curl http://localhost:8000/ready

# View Prometheus metrics
curl http://localhost:8000/metrics

# Check Sentry for errors
# Visit your Sentry dashboard
```

## Documentation

- **[Production Readiness Guide](docs/PRODUCTION_READINESS.md)**: Complete feature documentation
- **[Backup & Restore](docs/BACKUP_RESTORE.md)**: Database backup guide
- **[P0 Tasks Status](P0_TASKS_STATUS.md)**: Original implementation checklist

## Contributing

1. Create feature branch
2. Write tests for new features
3. Run test suite: `pytest`
4. Create pull request

## License

[Add your license here]

## Support

For issues or questions:

- Review documentation in `docs/`
- Check Sentry for errors
- Verify `/ready` endpoint health
- Review logs: `docker compose logs -f api`
