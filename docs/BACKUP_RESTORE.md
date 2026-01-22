# PostgreSQL Backup and Restore Guide

This guide explains how to backup and restore the VoiceHunte PostgreSQL database.

## Backup Strategy

The backup system uses `pg_dump` to create compressed SQL dumps of the database with automatic rotation.

### Features

- **Automated backups**: Scheduled via cron or manual execution
- **Compression**: Backups are gzipped to save space
- **Rotation**: Old backups are automatically deleted after N days (default: 7)
- **Full schema**: Includes all tables, data, and constraints
- **No ownership**: Backups are portable across different PostgreSQL instances

### Backup Configuration

Environment variables (with defaults):

```bash
BACKUP_DIR=/backups              # Where to store backups
RETENTION_DAYS=7                 # How many days to keep backups
POSTGRES_HOST=localhost          # PostgreSQL host
POSTGRES_PORT=5432               # PostgreSQL port
POSTGRES_DB=voicehunte           # Database name
POSTGRES_USER=voicehunte         # Database user
POSTGRES_PASSWORD=voicehunte     # Database password
```

## Manual Backup

### Run a backup manually

```bash
# Using default configuration
./scripts/backup_postgres.sh

# With custom configuration
BACKUP_DIR=/custom/path \
RETENTION_DAYS=14 \
./scripts/backup_postgres.sh
```

### Backup output

Backups are saved with timestamps:

```
/backups/voicehunte_backup_20240122_143052.sql.gz
```

## Scheduled Backups

### Using cron (Linux/Unix)

Add to crontab (`crontab -e`):

```bash
# Daily backup at 2 AM
0 2 * * * /path/to/VoiceHunte/scripts/backup_postgres.sh >> /var/log/voicehunte-backup.log 2>&1

# Hourly backup during business hours (9 AM - 5 PM)
0 9-17 * * * /path/to/VoiceHunte/scripts/backup_postgres.sh >> /var/log/voicehunte-backup.log 2>&1
```

### Using Docker Compose

See `docker-compose.yml` for the backup service configuration.

## Restore Database

### List available backups

```bash
./scripts/restore_postgres.sh
```

This will show all available backups in the backup directory.

### Restore from a specific backup

```bash
./scripts/restore_postgres.sh /backups/voicehunte_backup_20240122_143052.sql.gz
```

**WARNING**: This will **DROP and recreate** all tables in the database. You will be prompted for confirmation.

### Restore process

1. Script lists available backups
2. You specify which backup to restore
3. Confirmation prompt (type `yes` to continue)
4. Database is dropped and recreated from backup
5. Table count is verified

## Backup Best Practices

### 1. Regular Schedule

- **Production**: Daily backups at minimum, hourly during critical periods
- **Development**: Daily or weekly backups

### 2. Offsite Storage

Copy backups to remote storage for disaster recovery:

```bash
# Example: Copy to S3
aws s3 sync /backups s3://your-bucket/voicehunte-backups/

# Example: Copy to remote server
rsync -avz /backups/ user@remote-server:/backup/voicehunte/
```

### 3. Test Restores

Periodically test restore process in a non-production environment:

```bash
# Restore to test database
POSTGRES_DB=voicehunte_test \
./scripts/restore_postgres.sh /backups/voicehunte_backup_latest.sql.gz
```

### 4. Monitor Backup Success

Check backup logs regularly:

```bash
tail -f /var/log/voicehunte-backup.log
```

### 5. Retention Policy

Adjust `RETENTION_DAYS` based on your needs:

- **7 days**: Standard for development
- **30 days**: Recommended for production
- **90+ days**: For compliance requirements

## Backup File Management

### Check backup size

```bash
du -h /backups/voicehunte_backup_*.sql.gz
```

### Find latest backup

```bash
ls -lt /backups/voicehunte_backup_*.sql.gz | head -1
```

### Manually delete old backups

```bash
# Delete backups older than 30 days
find /backups -name "voicehunte_backup_*.sql.gz" -type f -mtime +30 -delete
```

## Troubleshooting

### "pg_dump: command not found"

Install PostgreSQL client tools:

```bash
# Ubuntu/Debian
sudo apt-get install postgresql-client

# macOS
brew install postgresql

# RHEL/CentOS
sudo yum install postgresql
```

### "FATAL: password authentication failed"

Check PostgreSQL credentials in environment variables or `.env` file.

### "cannot connect to server"

Ensure PostgreSQL is running and accessible:

```bash
# Check if PostgreSQL is running
pg_isready -h localhost -p 5432

# Test connection
psql -h localhost -p 5432 -U voicehunte -d voicehunte -c "SELECT 1"
```

### Backup file is empty or very small

Check PostgreSQL logs for errors during backup:

```bash
# View PostgreSQL logs (location varies)
tail -f /var/log/postgresql/postgresql-*.log
```

## Recovery Scenarios

### Full Database Loss

1. Set up new PostgreSQL instance
2. Create database and user
3. Run restore script with latest backup
4. Verify data integrity

### Partial Data Loss (specific tables)

For partial restore, extract specific tables from backup:

```bash
# Extract specific table from backup
gunzip -c /backups/voicehunte_backup_20240122.sql.gz | \
  grep -A 10000 "CREATE TABLE calls" | \
  psql -U voicehunte -d voicehunte
```

### Point-in-Time Recovery

For point-in-time recovery, you'll need to:

1. Restore from the latest backup before the incident
2. Apply any transaction logs if available (requires WAL archiving)
3. For VoiceHunte, consider implementing WAL archiving in production

## Advanced: Docker Compose Backup Service

Add to `docker-compose.yml`:

```yaml
services:
  backup:
    image: postgres:15
    environment:
      POSTGRES_HOST: postgres
      POSTGRES_DB: voicehunte
      POSTGRES_USER: voicehunte
      POSTGRES_PASSWORD: voicehunte
      BACKUP_DIR: /backups
      RETENTION_DAYS: 30
    volumes:
      - ./scripts:/scripts
      - ./backups:/backups
    command: >
      sh -c "
        while true; do
          /scripts/backup_postgres.sh
          sleep 86400
        done
      "
    depends_on:
      - postgres
```

This runs daily backups automatically in the background.
