"""
Seeds the database with demo grid cells, predictions, users, feedback, and
resources — the same fixture data as backend/dev_server/db.py, so switching
between the two backends is transparent to the frontend.

Run:  python -m app.seed
(the Makefile's `make seed` target wraps this)
"""
import random
import uuid
from datetime import datetime, timedelta

from app.db.session import SessionLocal, Base, engine
from app.db.models import User, GridCell, Prediction, Feedback, Resource, Broadcast
from app.services.ml_service import generate_prediction, action_text_for
from app.core.security import hash_password

import h3

VILLAGES = [
    ("Wajir", "Wajir", "Kenya", 1.7471, 40.0573),
    ("Marsabit", "Marsabit", "Kenya", 2.3284, 37.9899),
    ("Turkana Basin", "Turkana", "Kenya", 3.1190, 35.6000),
    ("Dolo Ado", "Gedo", "Somalia", 4.1800, 42.0800),
    ("Moyale", "Marsabit", "Kenya", 3.5167, 39.0500),
]

def generate_50k_grids(db):
    print("Generating 50,000 H3 grids... This may take a moment.")
    # Central point in East Africa (Kenya/Ethiopia border region)
    center_lat, center_lon = 3.5, 39.0
    center_h3 = h3.latlng_to_cell(center_lat, center_lon, 7) # res 7 is ~5.16 sq km
    
    # k=129 gives ~50,000 cells
    cells = list(h3.grid_disk(center_h3, 129))[:50000]
    
    rnd = random.Random(42)
    soil_types = ["Clay", "Sandy", "Loam", "Silt", "Peat"]
    
    grid_objects = []
    # Create the 50k cells
    for i, cell_id in enumerate(cells):
        lat, lon = h3.cell_to_latlng(cell_id)
        # Assign village name to a few to match our demo users/feedback
        v_name, v_dist, v_country = f"Zone-{i}", "Unknown", "Unknown"
        if i < len(VILLAGES):
            v_name, v_dist, v_country = VILLAGES[i][0], VILLAGES[i][1], VILLAGES[i][2]
            
        g = GridCell(
            id=cell_id, # Use H3 index as ID
            village_name=v_name,
            district=v_dist,
            country=v_country,
            lat=lat,
            lon=lon,
            elevation=rnd.uniform(10.0, 2500.0),
            soil_type=rnd.choice(soil_types)
        )
        grid_objects.append(g)
        
    db.bulk_save_objects(grid_objects)
    db.commit()
    print("50,000 grids saved.")
    
    # Add predictions to a subset to save time in seeding
    print("Generating predictions for a subset of grids...")
    pred_objects = []
    for cell in grid_objects[:1000]: # Only seed predictions for the first 1000 to keep seed fast
        for window, days in [("1-day", 1), ("3-day", 3), ("7-day", 7)]:
            flood, drought, code = generate_prediction(cell.id, days)
            pred_objects.append(Prediction(
                grid_id=cell.id, flood_prob=flood, drought_prob=drought,
                action_code=code, recommendation_text=action_text_for(code),
                window=window, predicted_at=datetime.utcnow(),
                valid_until=datetime.utcnow() + timedelta(days=days),
            ))
            
    # Bulk insert predictions
    for i in range(0, len(pred_objects), 1000):
        db.bulk_save_objects(pred_objects[i:i+1000])
    db.commit()


def run(reset: bool = False):
    if reset:
        Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        if db.query(GridCell).count() > 0:
            print("Already seeded — skipping (pass reset=True to force).")
            return

        generate_50k_grids(db)

        demo_users = [
            ("Amina H.", "+254700000213", "amina@example.org", "Kenya", "Viewer"),
            ("Kato O.", "+256700000441", "kato@example.org", "Uganda", "Moderator"),
            ("Fatuma A.", "+251900000087", "fatuma@example.org", "Ethiopia", "Viewer"),
            ("Deeqa M.", "+252600000311", "deeqa@example.org", "Somalia", "Moderator"),
            ("James K.", "ops@avertai.org".replace("ops", "+254700000940"), "ops@avertai.org", "Kenya", "SuperAdmin"),
            ("Nyaboke S.", "+254700000558", "nyaboke@example.org", "Kenya", "Viewer"),
        ]
        for name, phone, email, region, role in demo_users:
            db.add(User(
                name=name, phone=phone, email=email, region=region, role=role,
                status="Active", password_hash=hash_password("AvertAI2026!"),
            ))

        demo_feedback = [
            ("FLOOD", "+254700000213", "2.5km North of Wajir town - water rising near school", "flood_sighting", 0.92, "Pending"),
            ("CROP", "+251900000087", "OK - sorghum field near Moyale unaffected", "crop_status_ok", 0.87, "Verified"),
            ("DROUGHT", "+254700000940", "Severe - Turkana Basin, borehole dry since Tuesday", "drought_severe", 0.95, "Pending"),
            ("FLOOD", "+252600000311", "Bridge submerged near Dolo Ado crossing", "flood_sighting", 0.90, "Verified"),
            ("CROP", "+252600000702", "Pest sighting - armyworm, Gedo maize plots", "crop_pest_report", 0.81, "Pending"),
            ("DROUGHT", "+254700000558", "Pasture depleted, Marsabit north sector", "drought_severe", 0.63, "Spam"),
        ]
        for report_type, phone, text, intent, conf, status_val in demo_feedback:
            v = VILLAGES[0]
            db.add(Feedback(
                phone=phone, lat=v[3], lon=v[4], report_type=report_type,
                raw_text=text, parsed_intent=intent, confidence=conf, status=status_val,
                reference=f"RPT-2026-{random.randint(10000, 99999)}",
                verified_at=datetime.utcnow() if status_val != "Pending" else None,
            ))

        demo_resources = [
            ("Water Truck — Unit 04", "Water", -0.4536, 39.6401, "4000L", "+254711000001", "Turkana Basin"),
            ("Food Cache — Node 12", "Food", 3.5167, 39.0500, "6.2t maize", "+254711000002", "Dolo Ado"),
            ("Medical Team — Alpha", "Medical", 1.7471, 40.0573, "n/a", "+254711000003", "Wajir"),
        ]
        for name, rtype, lat, lon, capacity, phone, zone in demo_resources:
            db.add(Resource(name=name, type=rtype, lat=lat, lon=lon, capacity=capacity, contact_phone=phone, zone=zone))

        db.add(Broadcast(
            target_filter="risk_level:RED", message_text="Code RED: evacuate Dolo Ado low-lying zones now.",
            channels="SMS,Push,Voice", sent_via_sms_count=1204, sent_via_push_count=3880, status="sent",
        ))
        db.add(Broadcast(
            target_filter="region:Kenya", message_text="Code GREEN: planting window open in Moyale.",
            channels="SMS,Push", sent_via_sms_count=640, sent_via_push_count=1920, status="sent",
        ))

        db.commit()
        print("Seed complete.")
    finally:
        db.close()


if __name__ == "__main__":
    run()
