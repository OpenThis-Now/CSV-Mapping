# CSV Match Assistant

En komplett app för att matcha kunders produktlistor mot valfri CSV-baserad databas-katalog.

## Snabbstart utan Docker
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e backend
uvicorn backend.app.main:app --reload
# Ny terminal:
cd frontend && npm install && npm run dev
```
Öppna http://localhost:5173

## Med Docker
```bash
cp .env.example .env
docker compose up --build
```

## Miljövariabler (.env)
Se `.env.example`. Sätt `OPENAI_API_KEY` om du vill använda AI.
