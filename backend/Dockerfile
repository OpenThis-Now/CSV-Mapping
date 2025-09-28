# backend/Dockerfile
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

WORKDIR /app

# -- Build context är backend/, så använd paths utan "backend/"
COPY pyproject.toml /app/pyproject.toml
COPY app /app/app
# (Om du har andra moduler/filer, kopiera dem också:)
COPY backend_server.py /app/backend_server.py
COPY storage /app/storage

RUN pip install --upgrade pip && pip install -e .

# Skapa mappar om din kod förväntar sig dem
RUN mkdir -p /app/storage/databases /app/storage/imports /app/storage/exports /app/storage/tmp

# START – välj en av dessa beroende på var din FastAPI-app bor:
# 1) Om filen heter backend_server.py i backend/
CMD ["sh","-c","uvicorn backend_server:app --host 0.0.0.0 --port ${PORT}"]

# 2) Om appen ligger i app/main.py som `app = FastAPI()`
# CMD ["sh","-c","uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]