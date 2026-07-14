"""
SQLAlchemy engine/session setup.

DATABASE_URL defaults to local SQLite for zero-config development. Point it
at a DigitalOcean Managed PostgreSQL (with the PostGIS + TimescaleDB
extensions enabled) in production via the environment variable — no code
changes needed beyond the geometry-column note in models.py.
"""
import logging
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.engine import Engine

from app.core.config import get_settings

logger = logging.getLogger("avertai.db")

settings = get_settings()

connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

if settings.DATABASE_URL.startswith("sqlite"):
    engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
else:
    engine = create_engine(
        settings.DATABASE_URL, 
        pool_size=20, 
        max_overflow=0, 
        pool_timeout=30
    )
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


@event.listens_for(Base.metadata, "after_create")
def after_create(target, connection, **kw):
    if settings.DATABASE_URL.startswith("postgres"):
        from sqlalchemy import text
        try:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb;"))
        except Exception as exc:
            logger.warning("Skipping TimescaleDB extension setup: %s", exc)
            return

        try:
            connection.execute(
                text("SELECT create_hypertable('predictions', 'predicted_at', if_not_exists => TRUE);")
            )
        except Exception as exc:
            logger.warning("Skipping predictions hypertable setup: %s", exc)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
