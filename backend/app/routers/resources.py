from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import Resource, User
from app.core.deps import require_roles
from app.services.geo_utils import haversine_km
from app.schemas.resources import (
    ResourceNearbyResponse, ResourceCreateRequest, ResourceCreateResponse, ResourceUpdateRequest,
)

router = APIRouter(prefix="/resources", tags=["resources"])


from sqlalchemy import func
from app.core.config import get_settings

settings = get_settings()
is_postgres = settings.DATABASE_URL.startswith("postgres")


@router.get("/nearby", response_model=ResourceNearbyResponse)
def resources_nearby(lat: float = Query(...), lon: float = Query(...), limit: int = Query(10, le=50), db: Session = Depends(get_db)):
    if is_postgres:
        # PostGIS query: search within ~50km (approx 0.5 degrees) and sort by distance
        point = f"SRID=4326;POINT({lon} {lat})"
        rows = db.query(Resource, func.ST_Distance(Resource.geom, func.ST_GeomFromEWKT(point)).label("distance")) \
                 .filter(func.ST_DWithin(Resource.geom, func.ST_GeomFromEWKT(point), 0.5)) \
                 .order_by("distance") \
                 .limit(limit) \
                 .all()
        
        enriched = []
        for r, dist_deg in rows:
            # roughly convert degree distance back to km for the schema
            d_km = dist_deg * 111.32
            item = {
                "id": r.id, "name": r.name, "type": r.type, "lat": r.lat, "lon": r.lon,
                "capacity": r.capacity, "contact_phone": r.contact_phone, "zone": r.zone,
                "created_at": r.created_at, "distance_km": round(d_km, 1),
            }
            enriched.append(item)
        return {"items": enriched}
    else:
        # SQLite fallback for local development
        rows = db.query(Resource).all()
        enriched = []
        for r in rows:
            d = haversine_km(lat, lon, r.lat, r.lon)
            item = {
                "id": r.id, "name": r.name, "type": r.type, "lat": r.lat, "lon": r.lon,
                "capacity": r.capacity, "contact_phone": r.contact_phone, "zone": r.zone,
                "created_at": r.created_at, "distance_km": round(d, 1),
            }
            enriched.append(item)
        enriched.sort(key=lambda x: x["distance_km"])
        return {"items": enriched[:limit]}


@router.get("/admin", response_model=ResourceNearbyResponse, dependencies=[Depends(require_roles("SuperAdmin", "Moderator"))])
def list_resources_admin(db: Session = Depends(get_db)):
    rows = db.query(Resource).order_by(Resource.created_at.desc()).all()
    return {"items": [
        {"id": r.id, "name": r.name, "type": r.type, "lat": r.lat, "lon": r.lon,
         "capacity": r.capacity, "contact_phone": r.contact_phone, "zone": r.zone,
         "created_at": r.created_at, "distance_km": None}
        for r in rows
    ]}


@router.post("/admin", response_model=ResourceCreateResponse, dependencies=[Depends(require_roles("SuperAdmin", "Moderator"))])
def add_resource(payload: ResourceCreateRequest, db: Session = Depends(get_db)):
    row = Resource(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id}


@router.put("/admin/{resource_id}", dependencies=[Depends(require_roles("SuperAdmin", "Moderator"))])
def update_resource(resource_id: str, payload: ResourceUpdateRequest, db: Session = Depends(get_db)):
    row = db.query(Resource).filter(Resource.id == resource_id).first()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resource not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    db.commit()
    return {"id": row.id, "updated": True}
