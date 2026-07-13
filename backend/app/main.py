"""
AvertAI backend entrypoint.

Run locally:
    pip install -r requirements.txt
    uvicorn app.main:app --reload --port 8000

The frontend (frontend/index.html) talks to this via API_BASE =
http://localhost:8000/api/v1 (see the API_BASE constant in that file).
CORS is wide open (`*`) here for local development; tighten CORS_ORIGINS in
.env to the real dashboard domain before deploying to DigitalOcean.
"""
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.db.session import Base, engine
from sqlalchemy import text
from app.services.rate_limiter import is_rate_limited
from app.routers import auth, predictions, feedback, broadcasts, users, resources, system, webhooks

settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="AI-driven early warning ecosystem for flood/drought — action-oriented alerts for pastoralists via mobile, SMS, USSD, and voice.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def global_rate_limit(request: Request, call_next):
    """1000 requests/hour per IP, per the blueprint's System & Health spec."""
    client_ip = request.client.host if request.client else "unknown"
    if is_rate_limited(f"ip:{client_ip}", settings.RATE_LIMIT_PER_HOUR, 3600):
        return JSONResponse(status_code=429, content={"error": "Rate limit exceeded — 1000 requests/hour per IP"})
    return await call_next(request)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Log the full exception internally, but return a clean error to the client
    import logging
    logging.getLogger("avertai.error").error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"},
    )


@app.on_event("startup")
def on_startup():
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb;"))
        conn.commit()
    Base.metadata.create_all(bind=engine)
    # Auto-seed only if the table is empty, so repeated restarts don't duplicate data.
    from app.db.session import SessionLocal
    from app.db.models import GridCell
    db = SessionLocal()
    try:
        if db.query(GridCell).count() == 0:
            from app.seed import run as seed_run
            seed_run()
    finally:
        db.close()


app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(predictions.router, prefix=settings.API_V1_PREFIX)
app.include_router(feedback.router, prefix=settings.API_V1_PREFIX)
app.include_router(broadcasts.router, prefix=settings.API_V1_PREFIX)
app.include_router(users.router, prefix=settings.API_V1_PREFIX)
app.include_router(resources.router, prefix=settings.API_V1_PREFIX)
app.include_router(system.router, prefix=settings.API_V1_PREFIX)
app.include_router(webhooks.router, prefix=settings.API_V1_PREFIX)


@app.get("/")
def root():
    return {"name": settings.APP_NAME, "docs": "/docs", "api_base": settings.API_V1_PREFIX}
