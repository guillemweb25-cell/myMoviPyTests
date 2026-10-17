# Worker de motion graphics (Remotion). Solo CPU: corre en el Debian junto al
# backend, no en la máquina de la GPU.
FROM node:22-bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive TZ=Europe/Madrid

# Dependencias de Chromium headless, que es quien pinta los frames. Remotion trae
# su propio ffmpeg, así que aquí no hace falta.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates fonts-liberation libasound2 libatk-bridge2.0-0 libatk1.0-0 \
        libcairo2 libcups2 libdbus-1-3 libdrm2 libgbm1 libglib2.0-0 libnspr4 \
        libnss3 libpango-1.0-0 libx11-6 libxcb1 libxcomposite1 libxdamage1 \
        libxext6 libxfixes3 libxkbcommon0 libxrandr2 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Capa de dependencias aparte: así tocar el código no reinstala node_modules.
COPY package.json package-lock.json ./
RUN npm ci --omit=dev

# Descarga el Chrome Headless Shell en el build, no en el primer render: si no,
# el primer clip se come la descarga y se pasa de timeout. Se usa la API
# programática y no `npx remotion`, que vive en @remotion/cli (solo dev).
RUN node -e "import('@remotion/renderer').then((m) => m.ensureBrowser())"

COPY tsconfig.json remotion.config.ts ./
COPY src ./src

# Puntos de montaje (ver docker-compose.yml): la fuente Anton, el banco de música
# y los SFX propios del worker.
RUN mkdir -p /app/fonts /app/music /app/assets /tmp/fx-jobs

ENV PORT=3000 FX_JOBS_DIR=/tmp/fx-jobs FX_FONTS_DIR=/app/fonts
EXPOSE 3000

# Sin --reload / --watch a propósito: el watcher sobre un bind-mount dio
# problemas en person_worker. Deploy = rebuild + up -d.
CMD ["node", "--experimental-strip-types", "src/index.ts"]
