#!/usr/bin/env bash
#
# restore.sh — restore the most recent PostgreSQL backup from ./backups/.
#
# Restores the newest file by modification time. The chosen file is printed
# before the restore begins so it is visible in the terminal and on video.
#
# This OVERWRITES the current contents of the database. The dump is taken
# with --clean --if-exists, so existing tables are dropped and recreated.

set -euo pipefail

PROJECT="barq-assessment"
CONTAINER="postgres"
DB_USER="barq_app"
DB_NAME="barq_tasks"
BACKUP_DIR="./backups"

# Find the most recent backup.
#   ls -1t   list one per line, sorted by modification time, newest first
#   2>/dev/null  suppress the error if the directory does not exist
#   head -1  take the newest
LATEST="$(ls -1t "${BACKUP_DIR}"/*.sql 2>/dev/null | head -1 || true)"

# -z tests for an empty string. No backups means nothing to restore, and
# exiting non-zero matters so CI does not treat this as a success.
if [ -z "$LATEST" ]; then
  echo "FAIL: no backup files found in ${BACKUP_DIR}"
  echo "Run ./backup.sh first."
  exit 1
fi

echo "Restoring from: ${LATEST}"
echo "  size: $(du -h "$LATEST" | cut -f1)"
echo "  taken: $(date -r "$LATEST" '+%Y-%m-%d %H:%M:%S')"
echo
echo "This will REPLACE the current contents of ${DB_NAME}."
# A short pause rather than a prompt: visible to a human watching, but does
# not block CI, which cannot answer an interactive question.
sleep 3

echo "Restoring..."

# psql reads the dump from standard input and executes it.
#   -T on exec is required so the redirected input reaches psql intact.
#   -v ON_ERROR_STOP=1 makes psql abort on the first SQL error. Without it,
#      psql reports success even when individual statements failed, which
#      would mean a restore that silently did nothing.
#   -q  quiet, suppresses per-statement output
docker compose -p "$PROJECT" exec -T "$CONTAINER" \
  sh -c "PGPASSWORD=\"\$POSTGRES_PASSWORD\" psql -U ${DB_USER} -d ${DB_NAME} -v ON_ERROR_STOP=1 -q" \
  < "$LATEST"

echo
echo "PASS: restored from ${LATEST}"
echo
echo "Verify with:"
echo "  curl -s http://127.0.0.1:8080/records"
