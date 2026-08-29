# Waypoint runs as one container: Flask serves the API and the built React app.
#
# It cannot run on a serverless platform. Three things need a real machine:
# the Atlas CLI keeps its credentials in an OS keyring and is authorised through
# an interactive browser flow; Playwright's Chromium is ~350 MB, above the usual
# serverless bundle limit; and a planning run takes 10-20 s. All three are fine
# here.

# ── build the UI from source, so the image never ships a stale bundle ──
FROM node:22-slim AS ui
WORKDIR /ui
COPY web/package.json web/package-lock.json* ./
RUN npm ci --no-audit --no-fund 2>/dev/null || npm install --no-audit --no-fund
COPY web/ ./
# vite.config.js writes to ../src/ui/agent-app
RUN mkdir -p /src/ui && npm run build -- --outDir /out --emptyOutDir


# ── the app ────────────────────────────────────────────────────────────
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright \
    # Atlas stores credentials through python-keyring. There is no desktop
    # keyring in a container, so use the file backend and keep it on the disk
    # mounted at /data, otherwise every deploy would log you out.
    PYTHON_KEYRING_BACKEND=keyrings.alt.file.PlaintextKeyring \
    XDG_DATA_HOME=/data/keyring \
    XDG_CONFIG_HOME=/data/config \
    # Written at runtime; kept on the disk so a restart does not re-fetch
    # everything and burn the metered free RapidAPI tier.
    WAYPOINT_CAPTURE_DIR=/data/captures \
    WAYPOINT_CACHE_DIR=/data/hotel_rates

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir keyrings.alt atlas-flight-booking

# Chromium plus the OS libraries it links against.
RUN playwright install --with-deps chromium

COPY . .
COPY --from=ui /out ./src/ui/agent-app

RUN mkdir -p /data/captures /data/hotel_rates /data/keyring /data/config

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

# Two workers, long timeout: a planning run makes several upstream calls and a
# screenshot can take a few seconds.
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-8000} --workers 2 --threads 4 --timeout 180 --access-logfile - run:app"]
