# NOTE: ARG before first FROM is only available in FROM instructions.
# Each stage must redeclare ARG PY_VERSION to use it in COPY/RUN commands.
ARG PY_VERSION=3.12
FROM python:${PY_VERSION}-slim-bookworm AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on

WORKDIR /app
RUN addgroup --system app && adduser --system --ingroup app app

FROM base AS builder
ARG PY_VERSION=3.12  # Redeclare — scoped to this stage
COPY --from=ghcr.io/astral-sh/uv:0.10.0 /uv /bin/uv

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN uv pip install --system --compile-bytecode .

COPY src/ ./src/
COPY aegra.json ./

FROM base AS final
ARG PY_VERSION=3.12  # Redeclare — scoped to this stage
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python${PY_VERSION}/site-packages/ /usr/local/lib/python${PY_VERSION}/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/
COPY src/ ./src/
COPY aegra.json ./

EXPOSE 2026
USER app
CMD ["aegra", "serve"]
