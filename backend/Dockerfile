FROM python:3.11-slim

WORKDIR /app

# System-Abhängigkeiten
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Venv anlegen + Abhängigkeiten installieren (image layer = Seed für named volume)
COPY requirements.txt .
RUN python -m venv /app/.venv \
    && /app/.venv/bin/pip install --no-cache-dir -r requirements.txt

# Hash-Check: re-installiert nur wenn requirements.txt sich geändert hat
RUN printf '#!/bin/sh\nset -e\nHASH_FILE=/app/.venv/.install-hash\nCURRENT=$(md5sum /app/requirements.txt 2>/dev/null | cut -d" " -f1)\nSTORED=$(cat "$HASH_FILE" 2>/dev/null || echo "")\nif [ "$CURRENT" != "$STORED" ]; then\n  echo "[hivemind] requirements.txt changed -- running pip install..."\n  /app/.venv/bin/pip install --no-cache-dir -r /app/requirements.txt\n  echo "$CURRENT" > "$HASH_FILE"\n  echo "[hivemind] pip install done."\nelse\n  echo "[hivemind] venv up to date."\nfi\nexec "$@"\n' > /dep-check.sh && chmod +x /dep-check.sh

COPY . .
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/dep-check.sh", "/app/entrypoint.sh"]
