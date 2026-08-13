# Mordhau Prediction Unit
:D
Mordhau Prediction Unit predicts the likely winning team on Needy's Community Mordhau servers using historical matches, player ratings, and live scoreboard data.

The first version is a small microservice system:

- `data-service` owns Needys API ingestion, match storage, and live scoreboard snapshots
- `prediction-service` builds player ratings and returns win probabilities
- `autobalance-service` generates guarded, dry-run team assignments
- `dashboard` displays the live prediction and top player ratings

The prediction baseline is intentionally explainable: it builds Elo-style player ratings from completed matches, combines both teams' ratings with live scoreboard signals, then returns a probability for each team.

For the formulas behind player rating, team probability, confidence, and the ML model, see [docs/MATHEMATICS.md](docs/MATHEMATICS.md).

## Project Layout

```text
services/
  data-service/        FastAPI service for ingestion and SQLite persistence
  prediction-service/  FastAPI service for ratings and win probabilities
  autobalance-service/ FastAPI service for dry-run team balancing
apps/
  dashboard/           React + Vite dashboard
docker-compose.yml     Local microservice runtime
```

## Local Quick Start

### One-Click Windows Start

Double-click:

```text
Start-MordhauPredictionUnit.bat
```

It creates missing Python virtual environments, installs dependencies, builds the dashboard, starts both APIs, syncs Needys match/player data, serves the dashboard, and opens `http://127.0.0.1:5173`.

To stop everything, double-click:

```text
Stop-MordhauPredictionUnit.bat
```

Logs are written to `.runtime/logs`.

### Manual Start

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
- `GET /stats/sync`

The data service automatically refreshes the 100 most recent matches and 200 most-active
players every 30 seconds. Configure the worker with `MPU_AUTOSYNC_INTERVAL_SECONDS`,
`MPU_AUTOSYNC_MATCH_LIMIT`, and `MPU_AUTOSYNC_PLAYER_LIMIT`; set the interval to `0` to disable it.

The player catalog is restricted to SKM regulars: at least 5 Skirmish appearances during the
30 days preceding the newest stored match. Match history remains intact for model training, while
inactive and aggregate-only rows are removed from the player table. Configure this with
`MPU_ACTIVE_SKM_MIN_MATCHES` and `MPU_ACTIVE_SKM_WINDOW_DAYS`.

Prediction service on `:8002`:

- `GET /health`
- `POST /ingest/history?limit=9999`
- `GET /predict/current`
- `GET /predict/random?team_size=5`
- `GET /ratings?limit=20000`
- `GET /matches/recent?limit=20`
- `POST /model/train`
- `GET /model/status`

Autobalance service on `:8003`:

- `GET /health`
- `POST /balance/preview`
- `POST /balance/apply` (intentionally disabled during the dry-run milestone)

Dashboard quality-of-life controls:

- live Needy's sync freshness, record totals, and next-refresh countdown
- pause/resume for the 30-second dashboard refresh (the preference is remembered)
- partial refresh handling so one unavailable service does not hide healthy data
- configurable dry-run move limit and fairness target
- CSV export for the currently filtered and sorted player list

## Verification

Run the dependency-free unit tests:

```bash
cd services/data-service
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

```bash
cd services/prediction-service
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

```bash
cd services/autobalance-service
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Run the live-service smoke checks after starting the application:

```bash
cd services/data-service
.venv\Scripts\python.exe scripts\smoke_check.py
```

```bash
cd services/prediction-service
.venv\Scripts\python.exe scripts\smoke_check.py
```

```bash
cd services/prediction-service
.venv\Scripts\python.exe scripts\ml_smoke_check.py
```

```bash
cd apps/dashboard
npm run build
```

## Machine Learning

The baseline remains simple and explainable, but the prediction service now has a first real ML training path. It builds a time-aware dataset from completed matches:

```text
team features before match -> eventual winner
```

Training is intentionally leakage-aware: each match row uses ratings and player stats known before that match, then updates player ratings after recording the label.

Train or refresh the saved model:

```bash
curl -X POST "http://127.0.0.1:8002/model/train"
```

The trained model is a small JSON logistic regression model stored under `services/prediction-service/data/`, which is ignored by Git. `GET /model/status` returns train/test accuracy, log loss, Brier score, model-vs-baseline backtesting, and the strongest learned feature weights.

Good next upgrades:

- per-map and per-mode player ratings
- recent form weighting
- stronger models such as gradient boosting once the dataset is larger
- confidence score based on team sample size and live match progress
