# backend/Dockerfile
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# Build context = backend/, så använd paths utan "backend/"
COPY pyproject.toml /app/pyproject.toml
COPY app /app/app
# Kopiera backend_server.py
COPY backend_server.py /app/backend_server.py

RUN pip install --upgrade pip && pip install -e .

# Skapa tomma mappar om din kod förväntar sig dem
RUN mkdir -p /app/storage/databases /app/storage/imports /app/storage/exports /app/storage/tmp

# Exponera port
EXPOSE 8000

# Din FastAPI-app finns i app/main.py
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8000"]