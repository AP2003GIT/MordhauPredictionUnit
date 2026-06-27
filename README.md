# Mordhau Prediction Unit

Mordhau Prediction Unit predicts the likely winning team on Needy's Community Mordhau servers using historical matches, player ratings, and live scoreboard data.

The first version is a small microservice system:

- `data-service` owns Needys API ingestion, match storage, and live scoreboard snapshots
- `prediction-service` builds player ratings and returns win probabilities
- `dashboard` displays the live prediction and top player ratings

The prediction baseline is intentionally explainable: it builds Elo-style player ratings from completed matches, combines both teams' ratings with live scoreboard signals, then returns a probability for each team.

## Project Layout

```text
services/
  data-service/        FastAPI service for ingestion and SQLite persistence
  prediction-service/  FastAPI service for ratings and win probabilities
apps/
  dashboard/           React + Vite dashboard
docker-compose.yml     Local microservice runtime
```

## Local Quick Start

Run each service in its own terminal.

Requires Python 3.12+ and Node.js 20+. If `python` is not available in your terminal, install Python and enable the PATH option during installation.

```bash
cd services/data-service
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001
```

```bash
cd services/prediction-service
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
set DATA_SERVICE_URL=http://127.0.0.1:8001
uvicorn app.main:app --reload --port 8002
```

```bash
cd apps/dashboard
npm install
npm run dev
```

Open `http://127.0.0.1:5173`.

If Vite dev mode has trouble on a Windows/OneDrive path, use the production build with a static server:

```bash
cd apps/dashboard
npm run build
python -m http.server 5173 --bind 127.0.0.1 -d dist
```

## Docker Compose

```bash
docker compose up --build
```

Then open `http://localhost:5173`.

## First Data Load

Once the services are running, ingest historical matches:

```bash
curl -X POST "http://127.0.0.1:8002/ingest/history?limit=9999"
```

The dashboard also has an `Ingest` button that calls the same prediction-service endpoint.

## Service Endpoints

Data service on `:8001`:

- `GET /health`
- `POST /ingest/history?limit=9999`
- `GET /scoreboard/current`
- `GET /matches/history?limit=9999&order=asc`
- `GET /matches/recent?limit=20`
- `GET /players/all?limit=20000`
- `GET /stats/database`

Prediction service on `:8002`:

- `GET /health`
- `POST /ingest/history?limit=9999`
- `GET /predict/current`
- `GET /ratings?limit=20000`
- `GET /matches/recent?limit=20`

## Verification

```bash
cd services/data-service
.venv\Scripts\python.exe scripts\smoke_check.py
```

```bash
cd services/prediction-service
.venv\Scripts\python.exe scripts\smoke_check.py
```

```bash
cd apps/dashboard
npm run build
```

## Model Roadmap

The baseline is intentionally simple and explainable. After collecting live scoreboard snapshots, the next model should train on historical in-match states:

```text
features at time T -> eventual winner
```

Good next upgrades:

- time-aware backtesting instead of random train/test split
- logistic regression or gradient boosting with calibrated probabilities
- per-map and per-mode player ratings
- recent form weighting
- confidence score based on team sample size and live match progress
