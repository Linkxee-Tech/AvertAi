"""
AvertAI — local dev server database layer.

Uses stdlib sqlite3 only (no network access available to pip-install
SQLAlchemy/psycopg2 in this environment). Schema mirrors the PostgreSQL +
PostGIS + TimescaleDB design in the blueprint as closely as SQLite allows:
geometry columns become plain lat/lon floats, TimescaleDB hypertables become
a plain indexed table. See backend/app/db/models.py for the real
SQLAlchemy/PostGIS models intended for production (DigitalOcean Managed
Postgres).
"""
import sqlite3
import json
import random
import uuid
import os
from datetime import datetime, timedelta, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), "avertai.db")

REGIONS = [
    ("Wajir", "Kenya"), ("Marsabit", "Kenya"), ("Turkana Basin", "Kenya"),
    ("Dolo Ado", "Ethiopia"), ("Moyale", "Kenya"), ("Garissa", "Kenya"),
    ("Gedo", "Somalia"), ("Baidoa", "Somalia"), ("Jonglei", "South Sudan"),
    ("Afder", "Ethiopia"),
]

ACTION_TEXT = {
    "GREEN": {
        "en": "Ideal planting window. Apply nitrogen fertilizer today.",
        "sw": "Wakati mzuri wa kupanda. Weka mbolea ya nitrojeni leo.",
        "am": "ተስማሚ የመዝሪያ ወቅት ነው። ዛሬ የናይትሮጅን ማዳበሪያ ይጠቀሙ።",
        "so": "Waqti wanaagsan oo la beero. Maanta isticmaal bacriminta nitrogen-ka.",
    },
    "YELLOW": {
        "en": "Sandbag low-lying areas. Move poultry indoors in 24hrs.",
        "sw": "Weka mifuko ya mchanga maeneo ya chini. Hamisha kuku ndani ya masaa 24.",
        "am": "ዝቅተኛ ቦታዎችን በአሸዋ ከረጢት ይሸፍኑ። የዶሮ እርባታዎን በ24 ሰዓት ውስጥ ወደ ውስጥ ያንቀሳቅሱ።",
        "so": "Meelaha hooseeya ku dabool joonyad ciid ah. Digaagga geli guriga 24 saacadood gudahood.",
    },
    "RED": {
        "en": "Relocate cattle to Zone B immediately. Water reserves will deplete.",
        "sw": "Hamishia ng'ombe eneo B mara moja. Akiba ya maji itaisha.",
        "am": "ከብቶችዎን ወደ ዞን ቢ ወዲያውኑ ያንቀሳቅሱ። የውሃ ክምችት ያልቃል።",
        "so": "Xoolaha u wareeji Zone B isla markiiba. Kaydka biyuhu wuu dhamaan doonaa.",
    },
}


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    name TEXT,
    phone TEXT UNIQUE,
    email TEXT UNIQUE,
    password_hash TEXT,
    region TEXT,
    language TEXT DEFAULT 'en',
    role TEXT DEFAULT 'Viewer',
    fcm_token TEXT,
    notif_push INTEGER DEFAULT 1,
    notif_sms INTEGER DEFAULT 1,
    notif_voice INTEGER DEFAULT 0,
    status TEXT DEFAULT 'Active',
    last_active TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS otp_codes (
    phone TEXT PRIMARY KEY,
    code TEXT,
    expires_at TEXT,
    attempts INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS grid_cells (
    id TEXT PRIMARY KEY,
    village_name TEXT,
    district TEXT,
    country TEXT,
    lat REAL,
    lon REAL
);

CREATE TABLE IF NOT EXISTS predictions (
    id TEXT PRIMARY KEY,
    grid_id TEXT REFERENCES grid_cells(id),
    flood_prob REAL,
    drought_prob REAL,
    action_code TEXT,
    action_text_json TEXT,
    window TEXT,
    predicted_at TEXT,
    valid_until TEXT
);

CREATE TABLE IF NOT EXISTS feedback (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    phone TEXT,
    lat REAL,
    lon REAL,
    report_type TEXT,
    media_url TEXT,
    raw_text TEXT,
    parsed_intent TEXT,
    nlp_confidence REAL,
    status TEXT DEFAULT 'Pending',
    created_at TEXT,
    verified_at TEXT
);

CREATE TABLE IF NOT EXISTS broadcasts (
    id TEXT PRIMARY KEY,
    sent_by TEXT,
    target_filter_json TEXT,
    message_text TEXT,
    channels TEXT,
    sent_via_sms_count INTEGER DEFAULT 0,
    sent_via_push_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'sent',
    scheduled_for TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS resources (
    id TEXT PRIMARY KEY,
    name TEXT,
    type TEXT,
    lat REAL,
    lon REAL,
    capacity TEXT,
    contact_phone TEXT,
    zone TEXT,
    created_at TEXT
);
"""


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def seed_if_empty():
    conn = get_conn()
    cur = conn.cursor()
    cur.executescript(SCHEMA)
    conn.commit()

    cur.execute("SELECT COUNT(*) AS c FROM grid_cells")
    if cur.fetchone()["c"] > 0:
        conn.close()
        return  # already seeded

    rnd = random.Random(42)  # deterministic seed data

    # --- grid cells + predictions ---
    grid_ids = []
    for i in range(128):
        village, country = REGIONS[i % len(REGIONS)]
        gid = f"grid-{1000+i}"
        grid_ids.append(gid)
        lat = 3.0 + rnd.uniform(-4, 4)
        lon = 35.0 + rnd.uniform(-4, 4)
        cur.execute(
            "INSERT INTO grid_cells (id, village_name, district, country, lat, lon) VALUES (?,?,?,?,?,?)",
            (gid, village, f"{village} District", country, lat, lon),
        )
        for window in ("1-day", "3-day", "7-day"):
            flood = round(rnd.uniform(0, 1), 3)
            drought = round(rnd.uniform(0, 1), 3)
            if max(flood, drought) > 0.75:
                code = "RED"
            elif max(flood, drought) > 0.45:
                code = "YELLOW"
            else:
                code = "GREEN"
            cur.execute(
                """INSERT INTO predictions
                   (id, grid_id, flood_prob, drought_prob, action_code, action_text_json, window, predicted_at, valid_until)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    str(uuid.uuid4()), gid, flood, drought, code,
                    json.dumps(ACTION_TEXT[code]), window,
                    now_iso(), (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
                ),
            )

    # --- users ---
    demo_users = [
        ("+254700000213", "Amina H.", "Kenya", "en", "Viewer"),
        ("+256700000441", "Kato O.", "Uganda", "sw", "Moderator"),
        ("+251900000087", "Fatuma A.", "Ethiopia", "am", "Viewer"),
        ("+252600000311", "Deeqa M.", "Somalia", "so", "Moderator"),
        ("+254700000940", "James K.", "Kenya", "en", "SuperAdmin"),
        ("+254700000558", "Nyaboke S.", "Kenya", "sw", "Viewer"),
    ]
    for phone, name, region, lang, role in demo_users:
        cur.execute(
            """INSERT INTO users (id, name, phone, region, language, role, status, last_active, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (str(uuid.uuid4()), name, phone, region, lang, role, "Active", now_iso(), now_iso()),
        )
    # admin login user (email+password, checked in auth.py)
    cur.execute(
        """INSERT INTO users (id, name, email, password_hash, region, language, role, status, last_active, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (str(uuid.uuid4()), "AvertAI Ops", "ops@avertai.org", "demo-hash:AvertAI2026!", "Kenya", "en", "SuperAdmin", "Active", now_iso(), now_iso()),
    )

    # --- feedback ---
    demo_feedback = [
        ("FLOOD", "2.5km North of Wajir town — water rising near school", "flood_sighting", 0.92, "Pending", "+254700000213", 0),
        ("CROP", "OK — sorghum field near Moyale unaffected", "crop_status_ok", 0.87, "Verified", "+251900000087", 0),
        ("DROUGHT", "Severe — Turkana Basin, borehole dry since Tuesday", "drought_severe", 0.95, "Pending", "+254700000940", 0),
        ("FLOOD", "Bridge submerged near Dolo Ado crossing", "flood_sighting", 0.90, "Verified", "+252600000311", 1),
        ("CROP", "Pest sighting — armyworm, Gedo maize plots", "crop_pest_report", 0.81, "Pending", "+252600000311", 1),
        ("DROUGHT", "Pasture depleted, Marsabit north sector", "drought_severe", 0.63, "Spam", "+254700000558", 0),
    ]
    for rtype, text, intent, conf, status, phone, has_img in demo_feedback:
        cur.execute(
            """INSERT INTO feedback (id, phone, lat, lon, report_type, media_url, raw_text, parsed_intent, nlp_confidence, status, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (str(uuid.uuid4()), phone, rnd.uniform(0, 5), rnd.uniform(33, 40), rtype,
             ("https://example.org/media/demo.jpg" if has_img else None), text, intent, conf, status, now_iso()),
        )

    # --- resources ---
    demo_resources = [
        ("Water Truck — Unit 04", "Water", "Garissa", "4000L", "+254711000001"),
        ("Food Cache — Node 12", "Food", "Moyale", "6.2t maize", "+254711000002"),
        ("Medical Team — Alpha", "Medical", "Wajir", "n/a", "+254711000003"),
    ]
    for name, rtype, zone, cap, phone in demo_resources:
        cur.execute(
            "INSERT INTO resources (id, name, type, lat, lon, capacity, contact_phone, zone, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), name, rtype, rnd.uniform(0, 5), rnd.uniform(33, 40), cap, phone, zone, now_iso()),
        )

    # --- broadcasts ---
    cur.execute(
        """INSERT INTO broadcasts (id, sent_by, target_filter_json, message_text, channels, sent_via_sms_count, sent_via_push_count, status, created_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (str(uuid.uuid4()), "ops@avertai.org", json.dumps({"risk": "RED"}),
         "Code RED: evacuate Dolo Ado low-lying zones now.", "SMS,Push,Voice", 1204, 3880, "sent", now_iso()),
    )

    conn.commit()
    conn.close()
