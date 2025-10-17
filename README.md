# BWB AI Agents — Multi-Agent SMS/Email/Voice Marketing App

## Local
```
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8080
```
Open http://localhost:8080

## Render (Free)
- New Web Service
- Build: `pip install -r requirements.txt`
- Start: `uvicorn app.main:app --host 0.0.0.0 --port 10000`
- Env vars from `.env.example`
- Health check: `/healthz`