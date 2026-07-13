from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel


class ResourceItem(BaseModel):
    id: str
    name: str
    type: str
    lat: float
    lon: float
    capacity: Optional[str]
    contact_phone: Optional[str]
    zone: Optional[str]
    created_at: datetime
    distance_km: Optional[float] = None


class ResourceNearbyResponse(BaseModel):
    items: List[ResourceItem]


class ResourceCreateRequest(BaseModel):
    name: str
    type: str
    lat: float
    lon: float
    capacity: Optional[str] = None
    contact_phone: Optional[str] = None
    zone: Optional[str] = None


class ResourceCreateResponse(BaseModel):
    id: str


class ResourceUpdateRequest(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    capacity: Optional[str] = None
    contact_phone: Optional[str] = None
    zone: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    db: str
    redis: str
    gcp: str
    timestamp: datetime
