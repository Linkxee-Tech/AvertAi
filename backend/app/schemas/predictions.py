from typing import Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel


class ActionText(BaseModel):
    en: str
    sw: str
    am: str
    so: str


class CurrentPrediction(BaseModel):
    grid_id: str
    village_name: str
    flood_prob: float
    drought_prob: float
    action_code: str
    action_text: Dict[str, str]
    valid_until: datetime


class DayForecast(BaseModel):
    day: int
    flood_prob: float
    drought_prob: float
    action_code: str


class WeekPrediction(BaseModel):
    grid_id: str
    village_name: str
    forecast: List[DayForecast]


class GridHistoryPoint(BaseModel):
    window: str
    flood_prob: float
    drought_prob: float
    action_code: str
    predicted_at: datetime
    valid_until: datetime


class GridHistoryResponse(BaseModel):
    grid_id: str
    village_name: str
    history: List[GridHistoryPoint]


class MosaicCell(BaseModel):
    grid_id: str
    village_name: str
    lat: float
    lon: float
    flood_prob: float
    drought_prob: float
    action_code: str


class MosaicResponse(BaseModel):
    window: str
    cells: List[MosaicCell]
class AlertResponse(BaseModel):
    id: str
    message: str
    action_code: str
    is_read: bool
    created_at: datetime
