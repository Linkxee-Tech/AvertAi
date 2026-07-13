"""
SQLAlchemy models — mirrors backend/dev_server/db.py's schema exactly so the
two backends are drop-in equivalents from the frontend's point of view.

Production note: `grid_cells.geom` should be a PostGIS GEOMETRY(POINT, 4326)
column once DATABASE_URL points at the real Postgres+PostGIS cluster. It's
declared here as plain lat/lon floats plus a commented-out GeoAlchemy2 column
so this still works against SQLite for local development without extra
dependencies; swap the commented block in when deploying.
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Float, Integer, Boolean, DateTime, ForeignKey, Text, JSON
)
from sqlalchemy.orm import relationship
import sqlalchemy.types as types
from app.services.crypto import encrypt_string, decrypt_string

from app.db.session import Base
from app.core.config import get_settings

settings = get_settings()
is_postgres = settings.DATABASE_URL.startswith("postgres")

if is_postgres:
    from geoalchemy2 import Geometry


def gen_uuid():
    return str(uuid.uuid4())


class EncryptedString(types.TypeDecorator):
    """Transparently encrypts strings on write, decrypts on read."""
    impl = types.String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            return encrypt_string(str(value))
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            return decrypt_string(value)
        return value


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=gen_uuid)
    phone = Column(EncryptedString, unique=True, index=True, nullable=False)  # AES-256 at rest
    name = Column(String(120))
    email = Column(String(255))
    password_hash = Column(String(255))  # only set for dashboard (email+password) accounts
    region = Column(String(80))
    language = Column(String(8), default="en")
    fcm_token = Column(String(255))
    role = Column(String(20), default="Viewer")  # SuperAdmin | Moderator | Viewer
    status = Column(String(20), default="Active")  # Active | Blocked
    notif_push = Column(Boolean, default=True)
    notif_sms = Column(Boolean, default=True)
    notif_voice = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow)

    feedback = relationship("Feedback", back_populates="user")


class OTPCode(Base):
    __tablename__ = "otp_codes"

    phone = Column(String(20), primary_key=True)
    code = Column(String(6))
    expires_at = Column(DateTime)
    attempts = Column(Integer, default=0)


class GridCell(Base):
    __tablename__ = "grid_cells"

    id = Column(String, primary_key=True, default=gen_uuid)
    village_name = Column(String(120))
    district = Column(String(120))
    country = Column(String(80))
    lat = Column(Float)
    lon = Column(Float)
    elevation = Column(Float, nullable=True)
    soil_type = Column(String(80), nullable=True)

    if is_postgres:
        geom = Column(Geometry("POINT", srid=4326))

    predictions = relationship("Prediction", back_populates="grid_cell")


class Prediction(Base):
    __tablename__ = "predictions"

    id = Column(String, primary_key=True, default=gen_uuid)
    grid_id = Column(String, ForeignKey("grid_cells.id"), index=True)
    flood_prob = Column(Float)
    drought_prob = Column(Float)
    action_code = Column(String(10))  # GREEN | YELLOW | RED
    recommendation_text = Column(JSON)  # {"en": "...", "sw": "...", "am": "...", "so": "..."}
    window = Column(String(10))  # 1-day | 3-day | 7-day
    predicted_at = Column(DateTime, default=datetime.utcnow)
    valid_until = Column(DateTime)
    model_version = Column(String(20), default="v2.3.1")

    grid_cell = relationship("GridCell", back_populates="predictions")


class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    phone = Column(String(20))
    lat = Column(Float)
    lon = Column(Float)
    report_type = Column(String(20))  # FLOOD | DROUGHT | CROP | PEST | OTHER
    media_url = Column(String(500))
    raw_text = Column(Text)
    parsed_intent = Column(String(50))
    confidence = Column(Float)
    status = Column(String(20), default="Pending")  # Pending | Verified | Spam
    reference = Column(String(30))
    created_at = Column(DateTime, default=datetime.utcnow)
    verified_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="feedback")


class Broadcast(Base):
    __tablename__ = "broadcasts"

    id = Column(String, primary_key=True, default=gen_uuid)
    sent_by = Column(String, ForeignKey("users.id"), nullable=True)
    target_filter = Column(String(255))
    message_text = Column(Text)
    channels = Column(String(80))  # comma-separated: SMS,Push,Voice
    sent_via_sms_count = Column(Integer, default=0)
    sent_via_push_count = Column(Integer, default=0)
    status = Column(String(20), default="sent")  # sent | scheduled | failed
    scheduled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Resource(Base):
    __tablename__ = "resources"

    id = Column(String, primary_key=True, default=gen_uuid)
    name = Column(String(160))
    type = Column(String(40))  # Water | Food | Medical | Shelter
    lat = Column(Float)
    lon = Column(Float)
    capacity = Column(String(80))
    contact_phone = Column(String(20))
    zone = Column(String(120))
    created_at = Column(DateTime, default=datetime.utcnow)

    if is_postgres:
        geom = Column(Geometry("POINT", srid=4326))
