# syntax=docker/dockerfile:1.6
FROM python:3.11-slim

ENV INSTALL_TARGET=docker \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps.
# - build-essential / libpq-dev: compile Python extensions
# - libgl1 / libosmesa6: pyrender headless 3D thumbnail rendering (Tier 1)
# - git / jq / unzip / wget / sqlite3 / netcat-openbsd / mosquitto-clients: setup.sh parity + container debug
# - Node 20: npx-based MCP servers
# - tini: clean PID-1 signal handling
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
        ca-certificates \
        tini \
        libgl1 \
        libosmesa6 \
        libxrender1 \
        git \
        jq \
        unzip \
        wget \
        sqlite3 \
        netcat-openbsd \
        mosquitto-clients \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first so the layer is cached when only source changes.
COPY requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

# Application source (overridden by bind mount in docker-compose for dev).
COPY . .

# Log directory used by aot-app / aot_daemon
RUN mkdir -p /var/log/aot

EXPOSE 80

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "aot/start_flask_ui.py", "-s", "-p", "80"]
