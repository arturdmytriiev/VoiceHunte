#!/bin/bash
set -e

# PostgreSQL backup script with rotation
# This script creates compressed PostgreSQL backups and rotates old ones

# Configuration
BACKUP_DIR="${BACKUP_DIR:-/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-voicehunte}"
POSTGRES_USER="${POSTGRES_USER:-voicehunte}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-voicehunte}"

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Generate backup filename with timestamp
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/voicehunte_backup_$TIMESTAMP.sql.gz"

echo "[$(date)] Starting PostgreSQL backup..."

# Set PostgreSQL password for pg_dump
export PGPASSWORD="$POSTGRES_PASSWORD"

# Create backup with pg_dump and compress with gzip
pg_dump -h "$POSTGRES_HOST" \
        -p "$POSTGRES_PORT" \
        -U "$POSTGRES_USER" \
        -d "$POSTGRES_DB" \
        --format=plain \
        --no-owner \
        --no-acl \
        --clean \
        --if-exists \
        | gzip > "$BACKUP_FILE"

# Unset password
unset PGPASSWORD

# Check if backup was successful
if [ -f "$BACKUP_FILE" ]; then
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo "[$(date)] Backup created successfully: $BACKUP_FILE ($BACKUP_SIZE)"
else
    echo "[$(date)] ERROR: Backup failed!"
    exit 1
fi

# Rotate old backups (delete files older than RETENTION_DAYS)
echo "[$(date)] Rotating old backups (keeping last $RETENTION_DAYS days)..."
find "$BACKUP_DIR" -name "voicehunte_backup_*.sql.gz" -type f -mtime +$RETENTION_DAYS -delete

# Count remaining backups
BACKUP_COUNT=$(find "$BACKUP_DIR" -name "voicehunte_backup_*.sql.gz" -type f | wc -l)
echo "[$(date)] Total backups: $BACKUP_COUNT"
echo "[$(date)] Backup completed successfully"
