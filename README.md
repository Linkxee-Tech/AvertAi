# AvertAI

AI-driven early warning system for flood/drought risk across the IGAD region. Split into `frontend/`, `backend/`, and `mobile-apk-project/`, connected over a real REST API.

```
avertai-project/
├── frontend/
│   ├── index.html            # NGO/Government admin dashboard (web)
│   └── mobile/               # standalone, installable end-user app (Check/Act/Report)
│       ├── index.html
│       ├── manifest.json      # makes it installable via "Add to Home Screen"
│       ├── service-worker.js  # offline app-shell + API response caching
│       └── icon.svg
├── mobile-apk-project/       # Capacitor wrapper — turns frontend/mobile into a real .apk
└── backend/
    ├── app/                  # production FastAPI backend (pip install + uvicorn)
    └── ml/                   # Machine Learning pipeline (XGBoost)
```

## Two separate apps, one backend

- **`frontend/index.html`** — the NGO/Government console. Login, Overview, Prediction Explorer, Broadcast Center, Crowdsource Moderation, Resource Mapper, User Management, System Health.
- **`frontend/mobile/`** — what an end user (pastoralist, farmer, field agent) actually installs on their phone. Splash → onboarding → OTP login → Home (action card, Listen-aloud, SOS beacon) → Map → Report → Inbox → Settings, with a real bottom tab bar. This is a real installable PWA today (Chrome → "Add to Home Screen" → behaves like a native app icon, works offline), and `mobile-apk-project/` turns the exact same code into a real `.apk`.

Both talk to the same FastAPI backend. A report or SOS submitted from the mobile app is a real POST request that lands in the shared PostgreSQL database, immediately appearing in the admin dashboard's Crowdsource Moderation and Overview pages.

## Real, Functional Architecture

AvertAI is built on modern, scalable cloud infrastructure and free APIs to provide a fully functional hackathon-ready pipeline:

- **Database:** Neon Serverless PostgreSQL with `postgis` (for spatial queries) and `timescaledb` extensions auto-enabled.
- **Cache & Queue:** Upstash Redis for Celery asynchronous task handling (batch predictions & broadcasts).
- **Machine Learning:** A real local XGBoost multi-classification model (Flood/Drought) trained on correlated synthetic weather data (`backend/ml/train_model.py`), running directly on the FastAPI server for fast local inference.
- **Satellite / Weather Data:** Live integration with the free **Open-Meteo API** to pull real-time 7-day precipitation forecasts and soil moisture data for any grid cell to feed into the XGBoost model.
- **Communications:** Real integration with the **Africa's Talking API** for SMS broadcasting.
- **Push Notifications:** Fully modernized **Firebase Admin SDK (V1 API)** push notification system using a GCP Service Account JSON.
- **Hosting:** The frontend is configured for deployment on **Firebase Hosting**.

## Running it locally on Windows

```powershell
# Terminal 1 — backend API (FastAPI)
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend (serves both dashboard and mobile apps)
cd frontend
python -m http.server 8080
```

Open `http://localhost:8080/index.html` for the admin console, or `http://localhost:8080/mobile/index.html` for the mobile app. 

### Generating the Android APK

If you have Android Studio and the Android SDK installed:
```powershell
cd mobile-apk-project/android
.\gradlew.bat assembleDebug
```
The APK will be generated at `mobile-apk-project\android\app\build\outputs\apk\debug\app-debug.apk`.
