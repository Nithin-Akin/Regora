FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.5@sha256:e85be844203885286c60ffad8a858d48afb6c5a5c237ca0e67f12e74b8f174b1 /uv /usr/local/bin/uv
RUN apt-get update && apt-get install -y --no-install-recommends git curl libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml uv.lock ./
ENV UV_LINK_MODE=copy UV_HTTP_TIMEOUT=120
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev
COPY app ./app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
