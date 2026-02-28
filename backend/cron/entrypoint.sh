#!/bin/sh
# Write crontab from env var then start supercronic
CRON_EXPR="${HIVEMIND_BACKUP_CRON:-0 2 * * *}"
echo "${CRON_EXPR} /backup.sh >> /var/log/backup.log 2>&1" > /etc/backup-crontab
exec /usr/local/bin/supercronic /etc/backup-crontab
