FROM python:3.13.5-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements-core.lock requirements-http.lock pyproject.toml ./
RUN python -m pip install --no-cache-dir -r requirements-core.lock -r requirements-http.lock
COPY src ./src
RUN python -m pip install --no-cache-dir --no-deps .
USER 10001:10001
CMD ["python", "-m", "uvicorn", "sazu.http_service:create_app_from_env", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--timeout-keep-alive", "5", "--limit-concurrency", "32"]
