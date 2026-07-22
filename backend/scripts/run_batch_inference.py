import os
import sys
import logging
from datetime import datetime, timedelta

# Ensure we can import app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.db.models import GridCell, Prediction
from app.services.ml_service import generate_prediction

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_batch_inference():
    logger.info("Starting batch inference for all grid cells...")
    
    db: Session = SessionLocal()
    try:
        # 1. Fetch all grids
        grids = db.query(GridCell).all()
        logger.info(f"Fetched {len(grids)} grid cells.")
        
        # 2. Iterate and predict for 3-day window
        for grid in grids:
            try:
                flood, drought, code = generate_prediction(grid.id, day_offset=3)
                
                # Check if prediction already exists for today
                now = datetime.utcnow()
                existing = db.query(Prediction).filter(
                    Prediction.grid_id == grid.id,
                    Prediction.window == "3-day"
                ).order_by(Prediction.predicted_at.desc()).first()
                
                if existing and existing.predicted_at.date() == now.date():
                    # Update today's prediction
                    existing.flood_prob = flood
                    existing.drought_prob = drought
                    existing.action_code = code
                else:
                    # Insert new prediction
                    pred = Prediction(
                        grid_id=grid.id,
                        window="3-day",
                        flood_prob=flood,
                        drought_prob=drought,
                        action_code=code,
                        predicted_at=now,
                        valid_until=now + timedelta(days=3)
                    )
                    db.add(pred)
            except Exception as e:
                logger.error(f"Failed to generate prediction for grid {grid.id}: {e}")
                
        # 3. Commit
        db.commit()
        logger.info("Batch inference completed successfully.")
        
    except Exception as e:
        logger.error(f"Batch inference failed: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    run_batch_inference()
