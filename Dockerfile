FROM ghcr.io/astral-sh/uv:0.13.0 AS uv

FROM node:24-bookworm-slim AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend ./
RUN npm run build

FROM python:3.13-slim

COPY --from=uv /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev
COPY desk ./desk
COPY fixtures ./fixtures
COPY migrations ./migrations
COPY alembic.ini ./
COPY --from=web /web/dist ./frontend/dist

RUN groupadd --system desk && useradd --system --gid desk --no-create-home desk
USER desk
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8080
CMD ["uvicorn", "desk.main:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
