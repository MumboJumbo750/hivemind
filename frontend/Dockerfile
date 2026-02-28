FROM node:20-slim AS base
WORKDIR /app

# Install dependencies (image layer = Seed für das named volume)
COPY package.json package-lock.json* ./
RUN npm install

# Entrypoint: re-installiert npm-Pakete nur wenn package.json sich geändert hat
RUN printf '#!/bin/sh\nset -e\nHASH_FILE=/app/node_modules/.install-hash\nCURRENT=$(md5sum /app/package.json /app/package-lock.json 2>/dev/null | md5sum | cut -d" " -f1)\nSTORED=$(cat "$HASH_FILE" 2>/dev/null || echo "")\nif [ "$CURRENT" != "$STORED" ]; then\n  echo "[hivemind] package.json changed -- running npm install..."\n  npm install\n  echo "$CURRENT" > "$HASH_FILE"\n  echo "[hivemind] npm install done."\nelse\n  echo "[hivemind] node_modules up to date."\nfi\nexec "$@"\n' > /docker-entrypoint.sh && chmod +x /docker-entrypoint.sh

COPY . .

EXPOSE 5173
ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["npm", "run", "dev"]
