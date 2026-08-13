# syntax=docker/dockerfile:1.7
FROM ghcr.io/astral-sh/uv:0.12.3 AS uv

FROM python:3.13.9-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY --from=uv /uv /usr/local/bin/uv
COPY requirements.lock ./
RUN uv venv --python /usr/local/bin/python /app/.venv \
    && uv pip sync --python /app/.venv/bin/python --require-hashes requirements.lock \
    && rm -rf /root/.cache/uv

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY automation ./automation
COPY context ./context
COPY demo_payloads ./demo_payloads
COPY evals ./evals
COPY mcp_server ./mcp_server
COPY metabase ./metabase
COPY observability ./observability
COPY scripts ./scripts

RUN groupadd --gid 10001 northstar \
    && useradd --uid 10001 --gid northstar --create-home --home-dir /home/northstar northstar \
    && chown -R northstar:northstar /app /home/northstar

USER 10001:10001

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
