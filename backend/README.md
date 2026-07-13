# AvertAI Backend

This is the production-grade FastAPI backend for AvertAI. It provides all REST API routes for the frontend admin dashboard and mobile app, connecting to a fully functional modern cloud and ML stack.

## Architecture & Integrations

- **Web Framework:** FastAPI with Uvicorn server.
- **Database:** Neon Serverless PostgreSQL with `postgis` (geospatial queries for `GridCell` distance calculations) and `timescaledb` (time-series predictions). These extensions are automatically enabled by the app on startup.
- **ORM:** SQLAlchemy 2.0 with Alembic for migrations.
- **Caching & Async Tasks:** Upstash Redis with Celery for background broadcast dispatching and batch predictions.
- **Machine Learning Inference:** A fully functional, locally running XGBoost multi-classifier pipeline.
    - `ml/train_model.py`: Generates realistically correlated synthetic weather/flood data and trains the `.pkl` artifacts.
    - `app/services/ml_service.py`: Dynamically loads the trained XGBoost models.
- **Satellite Data Ingestion:** Live integration with the **Open-Meteo API**. The backend automatically fetches real-time 7-day precipitation forecasts and soil moisture for any queried `GridCell` coordinates and runs them through the XGBoost model to get exact probabilities.
- **Communications / SMS:** Integrated with Africa's Talking API for real-world SMS alerts (`app/services/comms_service.py`).
- **Push Notifications:** Fully modernized Firebase Admin SDK V1 for sending push notifications using `gcp-service-account.json`.

## Quickstart

```powershell
# 1. Setup environment
cp .env.example .env        # Add your Neon, Upstash, and Africa's Talking credentials here
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. Generate the local AI models
python ml/train_model.py

# 3. Run the server
uvicorn app.main:app --reload --port 8000
# Database migration and dummy data seeding happen automatically on startup!
```

## Folder Structure

```
backend/
├── app/
│   ├── main.py                  # FastAPI app, CORS, router registration, startup hooks
│   ├── seed.py                  # Auto-seeds the Neon database on first run
│   ├── core/
│   │   ├── config.py            # Settings (pydantic-settings), reads .env
│   │   ├── security.py          # JWT create/verify, password hashing
│   │   └── deps.py              # Auth & dependency injection
│   ├── db/
│   │   ├── session.py           # SQLAlchemy engine setup
│   │   └── models.py            # User, GridCell, Prediction, Feedback, Broadcast, Resource
│   ├── schemas/                 # Pydantic request/response models
│   ├── routers/                 # API Endpoints (auth, predictions, broadcasts, etc)
│   └── services/
│       ├── ml_service.py        # XGBoost inference & Open-Meteo API integration
│       ├── nlp_service.py       # Intent parser for crowdsourced feedback
│       ├── comms_service.py     # Africa's Talking and Firebase Admin SDK push notifications
│       └── geo_utils.py         # Haversine distance for spatial queries
├── ml/
│   ├── train_model.py           # Synthetic data generation and XGBoost model training
│   └── artifacts/               # Saved .pkl models
└── requirements.txt             # Python dependencies
```

## Endpoint Coverage

All 18+ endpoints from the blueprint are fully implemented. 
A Postman collection (`postman_collection.json`) is available to import into your workspace to test the endpoints directly. Examples include:
- `/predict/grids` (for the map view)
- `/auth/login` (dashboard JWT auth)
- `/ussd` (Africa's Talking USSD webhook integration)
- `/webhooks/delivery-report` (SMS delivery receipts)

## Testing

Run tests using pytest (uses an in-memory SQLite database by default):

```powershell
pytest tests\
```

For end-to-end integration tests proving the backend talks successfully to both the Admin Dashboard and the Mobile App, run the Playwright tests located in the root of the repository (`test_integration.js`, `test_cross_app.js`).
