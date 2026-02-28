#!/bin/sh
set -e

BACKUP_DIR="${HIVEMIND_BACKUP_DIR:-/backups}"
RETAIN_DAILY="${HIVEMIND_BACKUP_RETAIN_DAILY:-7}"
RETAIN_WEEKLY="${HIVEMIND_BACKUP_RETAIN_WEEKLY:-4}"
RETAIN_MONTHLY="${HIVEMIND_BACKUP_RETAIN_MONTHLY:-3}"

mkdir -p "${BACKUP_DIR}/daily" "${BACKUP_DIR}/weekly" "${BACKUP_DIR}/monthly"

DATE=$(date -u +"%Y-%m-%d")
DOW=$(date -u +"%u")    # 1=Mon … 7=Sun
DOM=$(date -u +"%d")    # 01–31

FILENAME="hivemind_${DATE}.pgdump"

echo "[backup] Starting pg_dump → ${BACKUP_DIR}/daily/${FILENAME}"
pg_dump \
  --host="${POSTGRES_HOST:-postgres}" \
  --port="${POSTGRES_PORT:-5432}" \
  --username="${POSTGRES_USER:-hivemind}" \
  --dbname="${POSTGRES_DB:-hivemind}" \
  --format=custom \
  --file="${BACKUP_DIR}/daily/${FILENAME}"

echo "[backup] pg_dump completed."

# Promote to weekly (every Sunday = DOW 7)
if [ "$DOW" = "7" ]; then
  cp "${BACKUP_DIR}/daily/${FILENAME}" "${BACKUP_DIR}/weekly/${FILENAME}"
  echo "[backup] Promoted to weekly."
fi

# Promote to monthly (1st of month)
if [ "$DOM" = "01" ]; then
  cp "${BACKUP_DIR}/daily/${FILENAME}" "${BACKUP_DIR}/monthly/${FILENAME}"
  echo "[backup] Promoted to monthly."
fi

# Retention: remove old backups beyond limits
# daily: keep newest $RETAIN_DAILY
ls -1t "${BACKUP_DIR}/daily/"*.pgdump 2>/dev/null | tail -n +$((RETAIN_DAILY + 1)) | xargs -r rm -f
# weekly: keep newest $RETAIN_WEEKLY
ls -1t "${BACKUP_DIR}/weekly/"*.pgdump 2>/dev/null | tail -n +$((RETAIN_WEEKLY + 1)) | xargs -r rm -f
# monthly: keep newest $RETAIN_MONTHLY
ls -1t "${BACKUP_DIR}/monthly/"*.pgdump 2>/dev/null | tail -n +$((RETAIN_MONTHLY + 1)) | xargs -r rm -f

echo "[backup] Retention cleanup done. Backups:"
ls -lh "${BACKUP_DIR}/daily/" 2>/dev/null | tail -5
echo "[backup] Done."
