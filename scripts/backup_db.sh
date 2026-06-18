#!/usr/bin/env bash
# Crea un backup de la base de datos SQLite usando el API de backup de SQLite
# (seguro con WAL mode — no requiere parar el servidor).
#
# Uso:
#   ./scripts/backup_db.sh
#   DB_PATH=/opt/precio-tracker/db/prices.db BACKUP_DIR=/opt/precio-tracker/backups ./scripts/backup_db.sh
#
# Cron sugerido (diario a las 3am, retiene los últimos 7 días):
#   0 3 * * * /opt/precio-tracker/scripts/backup_db.sh >> /var/log/precio-tracker-backup.log 2>&1

set -euo pipefail

DB_PATH="${DB_PATH:-/opt/precio-tracker/db/prices.db}"
BACKUP_DIR="${BACKUP_DIR:-/opt/precio-tracker/backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/prices_${TIMESTAMP}.db"
KEEP_DAYS="${KEEP_DAYS:-7}"

mkdir -p "$BACKUP_DIR"

sqlite3 "$DB_PATH" ".backup '${BACKUP_FILE}'"

echo "[$(date -Iseconds)] Backup creado: ${BACKUP_FILE} ($(du -sh "$BACKUP_FILE" | cut -f1))"

find "$BACKUP_DIR" -name "prices_*.db" -mtime "+${KEEP_DAYS}" -delete
echo "[$(date -Iseconds)] Backups anteriores a ${KEEP_DAYS} días eliminados"
