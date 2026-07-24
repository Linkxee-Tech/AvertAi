"""
Prediction service — the interface the routers call for flood/drought
probabilities and the resulting action code.

`generate_prediction()` is currently a deterministic rule-based stand-in
(identical logic to backend/dev_server for parity) since no trained model
artifact exists in this environment. In production this function's body is
replaced with:

    1. Load the active XGBoost + LSTM + meta-learner bundle from
       MODEL_REGISTRY_PATH (see app/core/config.py: MODEL_REGISTRY_PATH,
       ACTIVE_MODEL_VERSION) — the .pkl/.h5 files written by the GCP Vertex AI
       training job described in the blueprint.
    2. Pull the grid cell's latest feature row from Redis (6h TTL cache) or
       BigQuery/Postgres feature store if the cache misses.
    3. Run XGBoost on the static features + LSTM on the 10-day sequential
       window, then the logistic-regression meta-learner to combine them.
    4. Return (flood_prob, drought_prob).

The Probability -> Action Code mapping (`action_from_probs`) and the
multi-language text generator are the "Translational Logic Engine" from the
blueprint and are intentionally kept separate from the model itself so the
rule matrix can be tuned without retraining.
"""
import os
import random
import logging
from typing import Tuple

logger = logging.getLogger("ml_service")

ACTION_TEXT = {
    "GREEN": {
        "en": "Ideal planting window. Apply nitrogen fertilizer today.",
        "sw": "Wakati mzuri wa kupanda. Weka mbolea ya naitrojeni leo.",
        "am": '%^^>^s <"^~%S"< <^%.% S?<?? <>^ <"S"<- %^rO.S  ^><3%^< <-O"^?^c?',
        "so": "Waa xilli wax ku beeraan wanaagsan. Maanta geli bacrinta nitrogen-ka.",
    },
    "YELLOW": {
        "en": "Sandbag low-lying areas. Move poultry indoors in 24hrs.",
        "sw": "Weka mifuko ya mchanga maeneo ya chini. Hamishia kuku ndani ya masaa 24.",
        "am": '<?%.%S> %ݠ%3<Z%S  %S^,<< S"^"O% <-^,??S`? <"< ^r S^-%%3S  %24 ^<"% <?^O <^< <?^O <S %?^3%.^?',
        "so": "Aagagga hooseeya sanduuqyo ciid ah ku daboo. Digaagga 24 saacadood gudahood gudaha u wareeji.",
    },
    "RED": {
        "en": "Relocate cattle to Zone B immediately. Water reserves will deplete.",
        "sw": "Hamishia ng'ombe eneo B mara moja. Akiba ya maji itaisha.",
        "am": 'S"%% %S  <^< <zS  % <^<<<?S` <S %?^3%.^? <"<?^ S-^?%% <^?%^??',
        "so": "Xoolaha u wareeji Aagga B isla markiiba. Kaydka biyuhu wuu dhamaan doonaa.",
    },
}

# Lazy-loaded models
_xgb_flood = None
_xgb_drought = None

def _load_models():
    global _xgb_flood, _xgb_drought
    if _xgb_flood is not None:
        return True
    try:
        import pickle
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        flood_path = os.path.join(base_dir, 'ml', 'artifacts', 'xgboost_flood.pkl')
        drought_path = os.path.join(base_dir, 'ml', 'artifacts', 'xgboost_drought.pkl')
        
        with open(flood_path, 'rb') as f:
            _xgb_flood = pickle.load(f)
        with open(drought_path, 'rb') as f:
            _xgb_drought = pickle.load(f)
        return True
    except Exception as e:
        logger.warning(f"Could not load XGBoost models: {e}")
        return False

def action_from_probs(flood_prob: float, drought_prob: float) -> str:
    """The Rule Matrix from the blueprint's Translational Logic Engine."""
    top = max(flood_prob, drought_prob)
    if top > 0.75:
        return "RED"
    if top > 0.45:
        return "YELLOW"
    return "GREEN"

def fetch_weather_features(lat: float, lon: float) -> Tuple[float, float]:
    """Fetch real-time data from Open-Meteo for the given lat/lon."""
    try:
        import requests
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=soil_moisture_3_9cm,precipitation&forecast_days=7"
        resp = requests.get(url, timeout=5)
        data = resp.json()
        
        # Calculate 7-day total precipitation
        precip = sum(data['hourly']['precipitation'])
        # Get current soil moisture (average)
        moisture = sum(data['hourly']['soil_moisture_3_9cm']) / len(data['hourly']['soil_moisture_3_9cm'])
        # Open-Meteo soil moisture is usually 0-1 (m3/m3), scale it to 0-100 to match our synthetic data
        moisture = moisture * 100.0
        
        return moisture, precip
    except Exception as e:
        logger.error(f"Weather API failed: {e}")
        return None, None

def generate_prediction(grid_id: str, day_offset: int = 0, bulk: bool = False) -> Tuple[float, float, str]:
    """Uses Open-Meteo and local XGBoost models if available, otherwise falls back to pseudo-random."""
    flood_prob = None
    drought_prob = None
    
    if _load_models():
        try:
            from app.db.session import SessionLocal
            from app.db.models import GridCell
            import xgboost as xgb
            import numpy as np
            
            with SessionLocal() as db:
                cell = db.query(GridCell).filter(GridCell.id == grid_id).first()
            
            if cell and cell.lat and cell.lon:
                if bulk:
                    # Bypass Open-Meteo for bulk requests to prevent timeouts
                    rnd = random.Random(f"{grid_id}:{day_offset}")
                    moisture = rnd.uniform(10.0, 90.0)
                    precip = rnd.uniform(0.0, 150.0)
                else:
                    moisture, precip = fetch_weather_features(cell.lat, cell.lon)
                
                if moisture is not None and precip is not None:
                    # Features: soil_moisture, precipitation_7d, elevation
                    elevation = cell.elevation or 100.0
                    X = np.array([[moisture, precip, elevation]])
                    dmatrix = xgb.DMatrix(X)
                    
                    flood_prob = float(_xgb_flood.predict(dmatrix)[0])
                    drought_prob = float(_xgb_drought.predict(dmatrix)[0])
        except Exception as e:
            logger.error(f"ML inference failed: {e}")
            
    if flood_prob is None or drought_prob is None:
        # Fallback to deterministic pseudo-random
        rnd = random.Random(f"{grid_id}:{day_offset}")
        flood_prob = round(rnd.uniform(0.02, 0.95), 2)
        drought_prob = round(rnd.uniform(0.02, 0.95), 2)
        
    action_code = action_from_probs(flood_prob, drought_prob)
    return round(flood_prob, 2), round(drought_prob, 2), action_code


def action_text_for(action_code: str) -> dict:
    return ACTION_TEXT[action_code]
