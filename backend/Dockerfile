# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:0.13.5 AS uv

FROM python:3.12-slim AS base
COPY --from=uv /uv /uvx /usr/local/bin/
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH" \
    HOME=/home/app
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --create-home app \
    && mkdir -p /app/data /app/projects \
    && chown app:app /app/data /app/projects
COPY --chown=app:app app ./app
COPY --chown=app:app scripts ./scripts

FROM base AS test
COPY --chown=app:app tests ./tests
USER app
CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]

FROM base AS runtime
USER app
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=6 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"]
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
