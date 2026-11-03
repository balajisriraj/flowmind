FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY flowmind ./flowmind
COPY fixtures ./fixtures
RUN uv sync --frozen --no-dev && useradd --create-home app && mkdir -p /app/data && chown -R app /app
USER app
VOLUME /app/data
EXPOSE 8000
# The bundled MCP servers run as stdio child processes of the API, so one container holds them all.
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"
CMD ["uv", "run", "--no-sync", "flowmind", "serve", "--host", "0.0.0.0", "--port", "8000"]
