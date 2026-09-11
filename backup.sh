#!/usr/bin/env bash
#
# backup.sh — take a logical backup of the PostgreSQL database.
#
# Uses pg_dump, which produces a portable SQL dump rather than a copy of the
# data files. A file-level copy would be faster but is unsafe on a running
# database and is locked to the exact PostgreSQL version that wrote it.
#
# Writes to ./backups/ which is gitignored — a dump contains every row in the
# database and must never be committed.

# set -euo pipefail makes bash fail loudly instead of limping on:
#   -e  exit immediately if any command returns non-zero
#   -u  treat an unset variable as an error rather than an empty string
#   -o pipefail  a pipeline fails if ANY command in it fails, not just the last
# Without these, a failed pg_dump could still leave a zero-byte file behind
# and the script would report success.
set -euo pipefail

PROJECT="barq-assessment"
CONTAINER="postgres"
DB_USER="barq_app"
DB_NAME="barq_tasks"
BACKUP_DIR="./backups"

# date +%Y%m%d-%H%M%S produces e.g. 20260911-041530, so filenames sort
# chronologically and never collide.
STAMP="$(date +%Y%m%d-%H%M%S)"
OUTFILE="${BACKUP_DIR}/${DB_NAME}-${STAMP}.sql"

# mkdir -p creates the directory and does nothing if it already exists.
# Required because git does not track empty directories, so backups/ will
# not exist on a fresh clone or in CI.
mkdir -p "$BACKUP_DIR"

echo "Backing up ${DB_NAME} from container ${CONTAINER}..."

# docker compose exec -T runs a command in the container.
#   -T disables TTY allocation, which is required when redirecting output —
#      without it the dump would be corrupted by terminal control characters.
# PGPASSWORD passes the password non-interactively. It is read from the
#   container's own environment, so the password never appears in this script
#   or in your shell history.
# pg_dump flags:
#   -U  connect as this user
#   -d  dump this database
#   --clean          include DROP statements, so a restore replaces rather
#                    than merges into existing data
#   --if-exists      makes those DROP statements safe on an empty database
#   --no-owner       omit ownership commands, so the dump restores cleanly
#                    even if the target uses a different role
docker compose -p "$PROJECT" exec -T "$CONTAINER" \
  sh -c "PGPASSWORD=\"\$POSTGRES_PASSWORD\" pg_dump -U ${DB_USER} -d ${DB_NAME} --clean --if-exists --no-owner" \
  > "$OUTFILE"

# A dump that exists but is empty is worse than no dump, because it looks
# like a backup. Verify the file has content before claiming success.
# [ ! -s FILE ] is true when the file is empty or missing.
if [ ! -s "$OUTFILE" ]; then
  echo "FAIL: backup file is empty: $OUTFILE"
  rm -f "$OUTFILE"
  exit 1
fi

# Confirm the dump actually contains table data, not just schema.
# grep -c counts matching lines. COPY is how pg_dump writes table contents.
ROWS="$(grep -c '^COPY ' "$OUTFILE" || true)"
SIZE="$(du -h "$OUTFILE" | cut -f1)"

echo "PASS: backup written to ${OUTFILE} (${SIZE}, ${ROWS} table(s) with data)"
echo
echo "Restore this backup with:"
echo "  ./restore.sh"
