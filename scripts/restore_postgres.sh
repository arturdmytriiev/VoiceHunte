#!/bin/bash
set -e

# PostgreSQL restore script
# This script restores a PostgreSQL database from a compressed backup

# Configuration
BACKUP_DIR="${BACKUP_DIR:-/backups}"
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-voicehunte}"
POSTGRES_USER="${POSTGRES_USER:-voicehunte}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-voicehunte}"

# Check if backup file is provided
if [ -z "$1" ]; then
    echo "Usage: $0 <backup_file>"
    echo ""
    echo "Available backups:"
    ls -lh "$BACKUP_DIR"/voicehunte_backup_*.sql.gz 2>/dev/null || echo "No backups found in $BACKUP_DIR"
    exit 1
fi

BACKUP_FILE="$1"

# Check if backup file exists
if [ ! -f "$BACKUP_FILE" ]; then
    echo "ERROR: Backup file not found: $BACKUP_FILE"
    exit 1
fi

echo "[$(date)] Starting PostgreSQL restore from: $BACKUP_FILE"
echo "WARNING: This will DROP and recreate all tables in database '$POSTGRES_DB'"
read -p "Are you sure you want to continue? (yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo "Restore cancelled"
    exit 0
fi

# Set PostgreSQL password
export PGPASSWORD="$POSTGRES_PASSWORD"

# Restore database
echo "[$(date)] Restoring database..."
gunzip -c "$BACKUP_FILE" | psql -h "$POSTGRES_HOST" \
                                 -p "$POSTGRES_PORT" \
                                 -U "$POSTGRES_USER" \
                                 -d "$POSTGRES_DB" \
                                 -v ON_ERROR_STOP=1

# Unset password
unset PGPASSWORD

echo "[$(date)] Database restored successfully"
echo "[$(date)] Verifying restoration..."

# Simple verification: count tables
export PGPASSWORD="$POSTGRES_PASSWORD"
TABLE_COUNT=$(psql -h "$POSTGRES_HOST" \
                   -p "$POSTGRES_PORT" \
                   -U "$POSTGRES_USER" \
                   -d "$POSTGRES_DB" \
                   -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'")
unset PGPASSWORD

echo "[$(date)] Restored $TABLE_COUNT tables"
echo "[$(date)] Restore completed successfully"
