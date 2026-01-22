# VoiceHunte Production Readiness Guide

This document outlines all production-ready features implemented in VoiceHunte for stable, scalable deployment.

## Table of Contents

1. [Retry Logic for External APIs](#retry-logic-for-external-apis)
2. [Rate Limiting](#rate-limiting)
3. [Configurable Max Turns](#configurable-max-turns)
4. [Centralized Error Handling](#centralized-error-handling)
5. [Call Recording](#call-recording)
6. [Database Migrations](#database-migrations)
7. [PostgreSQL Backups](#postgresql-backups)
8. [Call History and Sessions](#call-history-and-sessions)
9. [Metrics and Monitoring](#metrics-and-monitoring)
10. [Error Tracking (Sentry)](#error-tracking-sentry)
11. [Testing](#testing)

---

## Retry Logic for External APIs

**Status**: ✅ Implemented (P1)

### Overview

All external API calls (OpenAI, Qdrant, Twilio REST) are wrapped with tenacity-based retry logic for resilience against transient failures.

### Features

- **Exponential backoff with jitter**: Prevents thundering herd problem
- **Configurable max attempts**: Default 4 attempts
- **Selective retries**: Only retries on:
  - Timeouts
  - 429 (Rate limit)
  - 5xx (Server errors)
- **No retry on client errors**: 4xx errors (except 429) fail immediately
- **Detailed logging**: Logs every retry attempt with reason

### Configuration

Environment variables:

```bash
RETRY_MAX_ATTEMPTS=4          # Maximum retry attempts
RETRY_BACKOFF_INITIAL=0.5     # Initial backoff in seconds
RETRY_BACKOFF_MAX=8.0         # Maximum backoff in seconds
```

### Usage

The retry logic is automatically applied to:

- OpenAI TTS: `app/tts/openai_tts.py`
- OpenAI STT (Whisper): `app/stt/whisper.py`
- Qdrant operations: `app/rag/qdrant_repo.py`

### Example

```python
from app.core.retry import retryable, raise_for_retryable_status

@retryable("my_service")
def call_external_api():
    response = requests.get("https://api.example.com/data")
    raise_for_retryable_status(response, "my_service")
    return response.json()
```

### Testing

Simulate failures:

```bash
# 429 rate limit
pytest tests/test_metrics_and_monitoring.py::test_retry_logic_on_429 -v

# 5xx server error
pytest tests/test_metrics_and_monitoring.py::test_retry_logic_on_5xx -v

# Timeout
pytest tests/test_metrics_and_monitoring.py::test_retry_logic_on_timeout -v
```

---

## Rate Limiting

**Status**: ✅ Implemented (P1)

### Overview

Rate limiting protects against spam, brute force, and accidental loops using slowapi (in-memory) with support for Redis-based limiting.

### Rate Limits

| Endpoint Type | Default Limit | Key |
|--------------|---------------|-----|
| Twilio webhooks | 30/minute | From phone number |
| Admin/API endpoints | 20/minute | IP address |

### Configuration

```bash
TWILIO_RATE_LIMIT=30/minute   # Twilio webhook rate limit
ADMIN_RATE_LIMIT=20/minute    # Admin endpoint rate limit
```

### Behavior

When rate limit is exceeded:

- **API endpoints**: Returns `429 Too Many Requests` with JSON error
- **Twilio webhooks**: Returns `429` with valid TwiML error message

### Upgrading to Redis

For multi-worker deployments, upgrade to Redis-based limiting:

1. Add Redis to `docker-compose.yml`
2. Update `app/main.py` limiter to use Redis storage
3. Set `REDIS_URL` environment variable

---

## Configurable Max Turns

**Status**: ✅ Implemented (P1)

### Overview

The maximum number of conversation turns is configurable via environment variable, allowing flexible conversation length without code changes.

### Configuration

```bash
MAX_TURNS=8  # Default: 8 turns per call
```

### Location

- Configuration: `app/core/config.py`
- Usage: `app/agent/graph.py:run_agent()`

### Testing

```bash
pytest tests/test_agent_turns.py::test_run_agent_respects_max_turns_setting -v
```

---

## Centralized Error Handling

**Status**: ✅ Implemented (P1)

### Overview

Global exception handlers ensure that all errors are handled gracefully, with Twilio-safe responses for webhook endpoints.

### Handled Error Types

| Error Type | HTTP Status | Twilio Response |
|-----------|-------------|-----------------|
| `RequestValidationError` | 422 | TwiML error message |
| `ValidationError` | 422 | TwiML error message |
| `ExternalAPIError` | 503 | TwiML fallback message |
| `RateLimitExceeded` | 429 | TwiML rate limit message |
| `Exception` (unhandled) | 500 | TwiML generic error |

### Features

- **No stack traces exposed**: All errors return user-friendly messages
- **Twilio-safe**: Webhook endpoints always return valid TwiML
- **Detailed logging**: All errors logged with context
- **Correlation IDs**: request_id and call_id tracked in logs

### Error Messages

Default fallback messages (Russian):

```
"Извините, произошла ошибка. Попробуйте позже."
```

Customize in `app/main.py` error handlers.

---

## Call Recording

**Status**: ✅ Implemented (P1)

### Overview

Automatic call recording via Twilio with metadata storage in PostgreSQL.

### Features

- **Automatic recording**: Enabled via `ENABLE_RECORDING=True` (default)
- **Metadata storage**: Stores recording SID, URL, from/to numbers
- **Admin API**: Retrieve recording URLs via REST API
- **Webhook handling**: Processes recording status callbacks

### Database Schema

```sql
CREATE TABLE recordings (
    call_id TEXT PRIMARY KEY,
    recording_sid TEXT NOT NULL,
    recording_url TEXT NOT NULL,
    from_number TEXT,
    to_number TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Configuration

```bash
ENABLE_RECORDING=true  # Enable/disable recording
```

### API Endpoints

```bash
# Get recording for a call
GET /admin/recordings/{call_id}
```

### Response Example

```json
{
  "call_id": "CAxxxx",
  "recording_sid": "RExxxx",
  "recording_url": "https://api.twilio.com/2010-04-01/Accounts/.../Recordings/RExxxx",
  "from_number": "+1234567890",
  "to_number": "+0987654321",
  "created_at": "2024-01-22T10:30:00Z",
  "updated_at": "2024-01-22T10:30:00Z"
}
```

### Testing

```bash
pytest tests/test_call_recording.py -v
```

---

## Database Migrations

**Status**: ✅ Implemented (P1)

### Overview

Alembic-based database migrations for predictable, version-controlled schema changes.

### Structure

```
alembic/
  ├── env.py                  # Alembic environment configuration
  ├── script.py.mako          # Migration template
  └── versions/
      └── 001_initial_schema.py  # Initial baseline migration
```

### Commands

```bash
# Apply all pending migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# Show current version
alembic current

# Show migration history
alembic history
```

### Creating New Migrations

```bash
# Auto-generate migration from model changes
alembic revision --autogenerate -m "Add new column"

# Create empty migration
alembic revision -m "Manual migration"
```

### Disabling Auto-Create

For production, disable auto-schema creation:

```bash
DB_AUTO_CREATE=false
```

Then rely solely on Alembic migrations.

### Integration

- Docker: Run `alembic upgrade head` in entrypoint script
- CI/CD: Run migrations before deploying new code

---

## PostgreSQL Backups

**Status**: ✅ Implemented (P1)

### Overview

Automated PostgreSQL backups with compression and rotation.

### Features

- **Compressed backups**: Uses gzip for space efficiency
- **Automatic rotation**: Deletes backups older than N days
- **Scheduled backups**: Via cron or Docker Compose
- **Easy restore**: One-command restore process

### Scripts

- `scripts/backup_postgres.sh`: Create backup
- `scripts/restore_postgres.sh`: Restore from backup

### Configuration

```bash
BACKUP_DIR=/backups           # Backup storage directory
RETENTION_DAYS=7              # Keep backups for 7 days
POSTGRES_HOST=localhost
POSTGRES_DB=voicehunte
POSTGRES_USER=voicehunte
POSTGRES_PASSWORD=voicehunte
```

### Usage

```bash
# Manual backup
./scripts/backup_postgres.sh

# Scheduled (add to crontab)
0 2 * * * /path/to/scripts/backup_postgres.sh >> /var/log/backup.log 2>&1

# Restore
./scripts/restore_postgres.sh /backups/voicehunte_backup_20240122_143052.sql.gz
```

### Documentation

See `docs/BACKUP_RESTORE.md` for full guide.

---

## Call History and Sessions

**Status**: ✅ Implemented (P2)

### Overview

Complete call session tracking with turns, metadata, and transcripts.

### Database Schema

Enhanced `calls` table:

```sql
CREATE TABLE calls (
    call_id TEXT PRIMARY KEY,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    language TEXT,
    from_number TEXT,
    to_number TEXT,
    status TEXT DEFAULT 'active'
);
```

### API Endpoints

```bash
# List all calls (with pagination)
GET /admin/calls?limit=50&offset=0

# Filter by phone number
GET /admin/calls?from_number=+1234567890

# Filter by status
GET /admin/calls?status=completed

# Get detailed call session
GET /admin/calls/{call_id}
```

### Response Example

```json
{
  "call_id": "CAxxxx",
  "started_at": "2024-01-22T10:00:00Z",
  "ended_at": "2024-01-22T10:05:00Z",
  "language": "en",
  "from_number": "+1234567890",
  "to_number": "+0987654321",
  "status": "completed",
  "recording_url": "https://...",
  "turns": [
    {
      "turn_id": 1,
      "user_text": "I want to make a reservation",
      "intent": "create_reservation",
      "assistant_text": "Sure! For how many people?",
      "tool_calls": [...],
      "created_at": "2024-01-22T10:00:30Z"
    }
  ],
  "transcript": "User: I want to make a reservation\nAssistant: Sure! For how many people?\n..."
}
```

### Testing

```bash
pytest tests/test_call_sessions.py -v
```

---

## Metrics and Monitoring

**Status**: ✅ Implemented (P2)

### Overview

Prometheus metrics for observability and performance monitoring.

### Features

- **HTTP metrics**: Request count, duration, status codes
- **In-progress requests**: Track concurrent requests
- **Auto-instrumentation**: FastAPI requests automatically tracked
- **Correlation IDs**: request_id and call_id in logs

### Endpoints

```bash
# Prometheus metrics
GET /metrics

# Health check
GET /health

# Readiness probe (checks dependencies)
GET /ready
```

### Metrics Example

```
# HELP http_requests_total Total HTTP requests
# TYPE http_requests_total counter
http_requests_total{method="POST",path="/twilio/voice",status="200"} 1523

# HELP http_request_duration_seconds HTTP request latency
# TYPE http_request_duration_seconds histogram
http_request_duration_seconds_bucket{le="0.5"} 1450
```

### Configuration

```bash
ENABLE_METRICS=true  # Enable metrics collection
```

### Integration

Scrape with Prometheus:

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'voicehunte'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'
```

---

## Error Tracking (Sentry)

**Status**: ✅ Implemented (P2)

### Overview

Sentry integration for real-time error tracking with PII filtering.

### Features

- **Automatic error capture**: All unhandled exceptions
- **PII filtering**: Phone numbers and sensitive data masked
- **Correlation tags**: call_sid, request_id, service, environment
- **Stack traces**: Full context for debugging
- **Breadcrumbs**: Request/response trail

### Configuration

```bash
SENTRY_DSN=https://...@sentry.io/...
SENTRY_ENVIRONMENT=production
```

### PII Masking

Phone numbers automatically masked:

```
Before: "Call from +1234567890 failed"
After:  "Call from [PHONE_REDACTED] failed"
```

### Testing

Trigger test error:

```python
import sentry_sdk
sentry_sdk.capture_message("Test error")
```

### Integration

See `app/core/sentry.py` for implementation.

---

## Testing

**Status**: ✅ Implemented (P2)

### Test Coverage

- **Unit tests**: Core functionality
- **Integration tests**: API endpoints, database operations
- **E2E tests**: Complete workflows (recording, sessions, etc.)

### Test Files

```
tests/
  ├── test_call_recording.py       # Recording functionality
  ├── test_call_sessions.py        # Call history and sessions
  ├── test_metrics_and_monitoring.py # Metrics, retry, error handling
  ├── test_twilio_integration.py   # Twilio webhooks
  ├── test_twilio_security.py      # Signature verification
  └── ... (existing tests)
```

### Running Tests

```bash
# All tests
pytest

# Specific test file
pytest tests/test_call_recording.py -v

# With coverage
pytest --cov=app --cov-report=html

# Integration tests only
pytest tests/test_call_sessions.py tests/test_call_recording.py -v
```

### Test Database

Tests use `clean_db` fixture which:

- Creates fresh tables before each test
- Truncates tables after each test
- Ensures isolation between tests

---

## Environment Variables Reference

Complete list of production configuration:

```bash
# App Configuration
APP_NAME=VoiceHunte
ENVIRONMENT=production
LOG_LEVEL=INFO
MAX_TURNS=8

# Database
POSTGRES_DSN=postgresql+psycopg://user:pass@host:5432/voicehunte
POSTGRES_POOL_SIZE=5
POSTGRES_POOL_MAX_OVERFLOW=5
DB_AUTO_CREATE=false

# External APIs
OPENAI_API_KEY=sk-...
QDRANT_URL=http://qdrant:6333
QDRANT_API_KEY=...

# Twilio
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_PHONE_NUMBER=+1...
ENABLE_RECORDING=true

# Rate Limiting
TWILIO_RATE_LIMIT=30/minute
ADMIN_RATE_LIMIT=20/minute

# Retry Logic
RETRY_MAX_ATTEMPTS=4
RETRY_BACKOFF_INITIAL=0.5
RETRY_BACKOFF_MAX=8.0

# Monitoring
SENTRY_DSN=https://...
SENTRY_ENVIRONMENT=production
ENABLE_METRICS=true

# Backups
BACKUP_DIR=/backups
RETENTION_DAYS=30
```

---

## Deployment Checklist

Before deploying to production:

- [ ] Set `ENVIRONMENT=production`
- [ ] Configure `SENTRY_DSN` for error tracking
- [ ] Set `DB_AUTO_CREATE=false`
- [ ] Run `alembic upgrade head`
- [ ] Configure backup cron job
- [ ] Set up Prometheus scraping
- [ ] Configure proper `POSTGRES_DSN` with strong password
- [ ] Set `OPENAI_API_KEY` and `TWILIO_*` credentials
- [ ] Enable `ENABLE_RECORDING=true` if needed
- [ ] Review and adjust `MAX_TURNS` based on use case
- [ ] Test `/ready` endpoint returns 200
- [ ] Verify `/metrics` endpoint is accessible
- [ ] Run full test suite: `pytest`
- [ ] Test backup/restore process
- [ ] Configure log aggregation (e.g., CloudWatch, Datadog)

---

## Monitoring Dashboard

Recommended metrics to monitor:

1. **Request Rate**: `http_requests_total` by endpoint
2. **Error Rate**: `http_requests_total{status=~"5..")}`
3. **Response Time**: `http_request_duration_seconds` p50/p95/p99
4. **Active Calls**: Count of `calls` with `status='in-progress'`
5. **Recording Success**: Count of `recordings` per day
6. **Retry Attempts**: Log analysis for retry events
7. **Database Connections**: PostgreSQL connection pool metrics

---

## Support and Maintenance

For issues or questions:

- Review logs: `docker-compose logs -f api`
- Check Sentry for errors
- Verify `/ready` endpoint health
- Review Prometheus metrics
- Consult `docs/BACKUP_RESTORE.md` for recovery

---

**Last Updated**: 2024-01-22
