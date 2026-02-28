FROM alpine:3.21

# Install PostgreSQL client for pg_dump + supercronic for cron
RUN apk add --no-cache postgresql16-client

# supercronic: reliable cron for containers (no background daemon needed)
ENV SUPERCRONIC_VERSION=0.2.33
RUN wget -q "https://github.com/aptible/supercronic/releases/download/v${SUPERCRONIC_VERSION}/supercronic-linux-amd64" \
    -O /usr/local/bin/supercronic \
    && chmod +x /usr/local/bin/supercronic

COPY backup.sh /backup.sh
RUN chmod +x /backup.sh

# Default crontab — overridden by HIVEMIND_BACKUP_CRON via entrypoint
COPY crontab /etc/backup-crontab

ENTRYPOINT ["/entrypoint.sh"]
CMD []

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
