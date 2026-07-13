from datetime import datetime

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from app.db.session import engine
from app.core.config import get_settings
from app.schemas.resources import HealthResponse

router = APIRouter(tags=["system"])
settings = get_settings()


@router.get("/health", response_model=HealthResponse)
def health_check():
    db_status = "ok"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        db_status = f"error: {exc}"

    redis_status = "ok" if _check_redis() else "not_configured"
    gcp_status = "ok" if settings.GCP_PROJECT_ID else "not_configured"

    if db_status != "ok" or redis_status != "ok" or gcp_status != "ok":
        # Check if they are just unconfigured vs actually failed
        if redis_status == "error" or db_status.startswith("error"):
            raise HTTPException(status_code=503, detail={
                "status": "error",
                "db": db_status,
                "redis": redis_status,
                "gcp": gcp_status,
                "timestamp": datetime.utcnow().isoformat()
            })

    return {
        "status": "ok",
        "db": db_status,
        "redis": redis_status,
        "gcp": gcp_status,
        "timestamp": datetime.utcnow(),
    }


def _check_redis() -> bool:
    try:
        import redis  # pip install redis
        r = redis.from_url(settings.REDIS_URL, socket_connect_timeout=1)
        return r.ping()
    except Exception:
        return False
