# VoiceHunte

Base FastAPI service scaffold for VoiceHunte.

## Quickstart

```bash
poetry install
poetry run uvicorn app.main:app --reload
```

Health endpoint:

```bash
curl http://localhost:8000/health
```

## Docker Compose

```bash
docker compose up --build
```

Services:
- API: http://localhost:8000/health
- Postgres: localhost:5432
- Qdrant: http://localhost:6333

## Environment

See `.env.example` for required variables.
