import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
import redis

from app.db.session import get_db
from app.db.models import GridCell, Prediction
from app.core.config import get_settings
from app.services.ml_service import generate_prediction, action_text_for
from app.services.geo_utils import haversine_km
from app.schemas.predictions import (
    CurrentPrediction, WeekPrediction, DayForecast,
    GridHistoryResponse, GridHistoryPoint, MosaicResponse, MosaicCell,
)

router = APIRouter(prefix="/predict", tags=["predictions"])
settings = get_settings()

try:
    redis_client = redis.from_url(settings.REDIS_URL, socket_connect_timeout=1)
except Exception:
    redis_client = None


def _nearest_grid(db: Session, lat: float, lon: float) -> GridCell:
    cells = db.query(GridCell).all()
    if not cells:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No grid cells seeded")
    return min(cells, key=lambda c: haversine_km(lat, lon, c.lat, c.lon))


@router.get("/current", response_model=CurrentPrediction)
def predict_current(lat: float = Query(...), lon: float = Query(...), db: Session = Depends(get_db)):
    grid = _nearest_grid(db, lat, lon)
    cache_key = f"predict:current:{grid.id}"

    if redis_client:
        try:
            cached = redis_client.get(cache_key)
            if cached:
                data = json.loads(cached)
                data["valid_until"] = datetime.fromisoformat(data["valid_until"])
                return data
        except Exception:
            pass

    flood, drought, code = generate_prediction(grid.id, day_offset=0)
    result = {
        "grid_id": grid.id,
        "village_name": grid.village_name,
        "flood_prob": flood,
        "drought_prob": drought,
        "action_code": code,
        "action_text": action_text_for(code),
        "valid_until": (datetime.utcnow() + timedelta(days=1)).isoformat()
    }

    if redis_client:
        try:
            redis_client.setex(cache_key, settings.PREDICTION_CACHE_TTL_SECONDS, json.dumps(result))
        except Exception:
            pass

    result["valid_until"] = datetime.fromisoformat(result["valid_until"])
    return result


@router.get("/week", response_model=WeekPrediction)
def predict_week(lat: float = Query(...), lon: float = Query(...), db: Session = Depends(get_db)):
    grid = _nearest_grid(db, lat, lon)
    forecast = []
    for day in range(1, 8):
        # Gracefully handle missing data - simulation of historical data check
        try:
            flood, drought, code = generate_prediction(grid.id, day_offset=day)
        except Exception:
            # If generation or DB query fails, fallback to nulls
            flood, drought, code = None, None, "UNKNOWN"
        forecast.append({"day": day, "flood_prob": flood, "drought_prob": drought, "action_code": code})
    return {"grid_id": grid.id, "village_name": grid.village_name, "forecast": forecast}


@router.get("/grid/{grid_id}", response_model=GridHistoryResponse)
def predict_grid_history(grid_id: str, db: Session = Depends(get_db)):
    grid = db.query(GridCell).filter(GridCell.id == grid_id).first()
    if not grid:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Grid cell not found")
    rows = db.query(Prediction).filter(Prediction.grid_id == grid_id).order_by(Prediction.predicted_at.desc()).limit(30).all()
    history = [
        {
            "window": r.window, "flood_prob": r.flood_prob, "drought_prob": r.drought_prob,
            "action_code": r.action_code, "predicted_at": r.predicted_at, "valid_until": r.valid_until,
        }
        for r in rows
    ]
    return {"grid_id": grid.id, "village_name": grid.village_name, "history": history}


@router.get("/grids", response_model=MosaicResponse)
def predict_mosaic(window: str = Query("3-day"), db: Session = Depends(get_db)):
    """Powers the Prediction Explorer / Overview heatmap grid-cell mosaic."""
    days_map = {"1-day": 1, "3-day": 3, "7-day": 7}
    day_offset = days_map.get(window, 3)
    cells = db.query(GridCell).all()
    result = []
    for cell in cells:
        flood, drought, code = generate_prediction(cell.id, day_offset=day_offset)
        result.append({
            "grid_id": cell.id, "village_name": cell.village_name,
            "lat": cell.lat, "lon": cell.lon,
            "flood_prob": flood, "drought_prob": drought, "action_code": code,
        })
    return {"window": window, "cells": result}
