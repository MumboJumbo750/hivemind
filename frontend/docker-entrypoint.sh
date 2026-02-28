#!/bin/sh
set -e

HASH_FILE=/app/node_modules/.install-hash

# Hash über package.json + package-lock.json
CURRENT_HASH=$(md5sum /app/package.json /app/package-lock.json 2>/dev/null | md5sum | cut -d' ' -f1)
STORED_HASH=$(cat "$HASH_FILE" 2>/dev/null || echo "")

if [ "$CURRENT_HASH" != "$STORED_HASH" ]; then
  echo "[hivemind] package.json changed — running npm install..."
  npm install
  echo "$CURRENT_HASH" > "$HASH_FILE"
  echo "[hivemind] npm install done."
else
  echo "[hivemind] node_modules up to date — skipping npm install."
fi

exec "$@"
