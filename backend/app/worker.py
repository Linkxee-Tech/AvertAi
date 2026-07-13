from celery import Celery
import os
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.db.models import Broadcast
from app.services.comms_service import estimate_delivery_counts, send_sms, send_push, send_voice_call
import logging

settings = get_settings()

celery_app = Celery(
    "worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL
)

from celery.schedules import crontab

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "daily-batch-inference": {
            "task": "daily_batch_inference",
            "schedule": crontab(minute=0, hour=0),  # 00:00 UTC daily
        },
    }
)

logger = logging.getLogger("avertai.worker")

@celery_app.task(name="daily_batch_inference")
def daily_batch_inference():
    logger.info("Starting Daily Batch Inference...")
    from app.db.models import GridCell, Prediction
    from app.services.ml_service import generate_prediction
    
    db = SessionLocal()
    try:
        cells = db.query(GridCell).all()
        logger.info(f"Generating predictions for {len(cells)} grid cells.")
        
        predictions_to_insert = []
        for cell in cells:
            for window, day_offset in [("1-day", 1), ("3-day", 3), ("7-day", 7)]:
                flood, drought, code = generate_prediction(cell.id, day_offset=day_offset)
                predictions_to_insert.append(
                    Prediction(
                        grid_id=cell.id,
                        flood_prob=flood,
                        drought_prob=drought,
                        action_code=code,
                        window=window,
                    )
                )
        
        # Bulk save
        # Note: in production, TimescaleDB hypertable bulk inserts should be chunked
        db.bulk_save_objects(predictions_to_insert)
        db.commit()
        logger.info("Daily batch inference completed successfully.")
    except Exception as e:
        logger.error(f"Failed to run batch inference: {e}")
        db.rollback()
    finally:
        db.close()

@celery_app.task(name="dispatch_broadcast")
def dispatch_broadcast(broadcast_id: str):
    logger.info(f"Dispatching broadcast {broadcast_id}")
    db = SessionLocal()
    try:
        row = db.query(Broadcast).filter(Broadcast.id == broadcast_id).first()
        if not row:
            logger.error(f"Broadcast {broadcast_id} not found in DB")
            return

        channels = row.channels.split(",")
        
        # Real dispatcher would query users matching target_filter and fan out
        # We simulate the delivery counts here for the blueprint
        counts = estimate_delivery_counts(target_audience_size=2000)
        
        # If real SMS/Push is configured, we'd loop over users and call send_sms/send_push here
        # For RED alerts, we'd also trigger send_voice_call
        
        row.sent_via_sms_count = counts["sms_delivered"] if "SMS" in channels else 0
        row.sent_via_push_count = counts["push_delivered"] if "Push" in channels else 0
        row.status = "sent"
        
        db.commit()
        logger.info(f"Successfully dispatched broadcast {broadcast_id}")
    except Exception as e:
        logger.error(f"Error dispatching broadcast {broadcast_id}: {e}")
        db.rollback()
        if row:
            row.status = "failed"
            db.commit()
    finally:
        db.close()
