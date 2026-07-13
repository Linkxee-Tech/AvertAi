"""
AvertAI dev server — implements the full REST API surface from the blueprint
using only the Python standard library (http.server + sqlite3), so it runs
with zero pip installs. This exists because this build environment has no
network access to install FastAPI/uvicorn/SQLAlchemy.

For production, deploy backend/app (real FastAPI) to DigitalOcean instead —
it implements the identical route contract documented here.

Run:
    python3 backend/dev_server/server.py
Then the frontend (frontend/index.html) can be pointed at
    http://localhost:8000/api/v1
via the API_BASE constant injected at the top of its <script> block.
"""
import json
import re
import time
import random
import uuid
import math
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from db import get_conn, seed_if_empty, now_iso, ACTION_TEXT
import auth as auth_mod

PORT = 8000

# ---------------------------------------------------------------- utilities

_rate_buckets = {}  # key -> [(timestamp), ...]  in-memory only


def rate_limited(key: str, max_requests: int, window_seconds: int) -> bool:
    now = time.time()
    bucket = _rate_buckets.setdefault(key, [])
    bucket[:] = [t for t in bucket if now - t < window_seconds]
    if len(bucket) >= max_requests:
        return True
    bucket.append(now)
    return False


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


NLP_KEYWORDS = {
    "sos_emergency": ["sos", "help", "emergency", "urgent rescue", "trapped"],
    "flood_sighting": ["flood", "water rising", "submerged", "bridge", "overflow"],
    "drought_severe": ["drought", "dry", "borehole dry", "no rain", "pasture depleted"],
    "crop_pest_report": ["pest", "armyworm", "locust", "infestation"],
    "crop_status_ok": ["ok", "fine", "unaffected", "stable", "good"],
}


def parse_intent(raw_text: str):
    """Lightweight keyword-based stand-in for the BERT-tiny NLP worker
    described in the blueprint (no ML runtime available offline)."""
    text = raw_text.lower()
    if any(kw in text for kw in NLP_KEYWORDS["sos_emergency"]):
        return "SOS", "sos_emergency", 0.99
    best_intent, best_score = "unknown", 0.4
    for intent, keywords in NLP_KEYWORDS.items():
        if intent == "sos_emergency":
            continue
        hits = sum(1 for kw in keywords if kw in text)
        if hits:
            score = min(0.95, 0.6 + hits * 0.12 + random.uniform(0, 0.08))
            if score > best_score:
                best_intent, best_score = intent, round(score, 2)
    report_type = "FLOOD" if "flood" in best_intent else "DROUGHT" if "drought" in best_intent else "CROP" if "crop" in best_intent else "OTHER"
    return report_type, best_intent, best_score


def action_from_probs(flood, drought):
    m = max(flood, drought)
    if m > 0.75:
        return "RED"
    if m > 0.45:
        return "YELLOW"
    return "GREEN"


def get_bearer_user(headers):
    auth_header = headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header[len("Bearer "):]
    payload = auth_mod.verify_token(token)
    if not payload or payload.get("type") != "access":
        return None
    return payload


# ---------------------------------------------------------------- handler

class Route:
    def __init__(self, method, pattern, handler):
        self.method = method
        self.regex = re.compile("^" + re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", pattern) + "$")
        self.handler = handler


ROUTES = []


def route(method, pattern):
    def deco(fn):
        ROUTES.append(Route(method, pattern, fn))
        return fn
    return deco


class Ctx:
    def __init__(self, handler, params, query, body):
        self.handler = handler
        self.params = params
        self.query = query
        self.body = body or {}
        self.user = get_bearer_user(handler.headers)

    def q(self, key, default=None):
        v = self.query.get(key)
        return v[0] if v else default


# ------------------------------------------------------------ auth routes

@route("POST", "/api/v1/auth/otp")
def auth_otp(ctx: Ctx):
    phone = ctx.body.get("phone")
    if not phone:
        return 422, {"detail": "phone is required"}
    if rate_limited(f"otp:{phone}", max_requests=5, window_seconds=3600):
        return 429, {"detail": "Too many OTP requests. Try again later."}
    code = f"{random.randint(0, 999999):06d}"
    conn = get_conn()
    conn.execute(
        "INSERT INTO otp_codes (phone, code, expires_at, attempts) VALUES (?,?,?,0) "
        "ON CONFLICT(phone) DO UPDATE SET code=excluded.code, expires_at=excluded.expires_at, attempts=0",
        (phone, code, now_iso()),
    )
    conn.commit()
    conn.close()
    # In production this calls the Africa's Talking SMS API (see services/africastalking_client.py).
    print(f"[MOCK SMS] to {phone}: Your AvertAI code is {code}")
    return 200, {"message": "OTP sent", "dev_hint_code": code}  # code only returned for local demo


@route("POST", "/api/v1/auth/verify")
def auth_verify(ctx: Ctx):
    phone = ctx.body.get("phone")
    code = ctx.body.get("code")
    if not phone or not code:
        return 422, {"detail": "phone and code are required"}
    conn = get_conn()
    row = conn.execute("SELECT * FROM otp_codes WHERE phone=?", (phone,)).fetchone()
    if not row or row["code"] != code:
        conn.close()
        return 401, {"detail": "Invalid code"}
    user = conn.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
    if not user:
        uid = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO users (id, phone, region, language, role, status, last_active, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (uid, phone, "Unknown", "en", "Viewer", "Active", now_iso(), now_iso()),
        )
        role = "Viewer"
    else:
        uid, role = user["id"], user["role"]
    conn.execute("DELETE FROM otp_codes WHERE phone=?", (phone,))
    conn.commit()
    conn.close()
    return 200, {
        "access_token": auth_mod.create_access_token(uid, role),
        "refresh_token": auth_mod.create_refresh_token(uid),
        "token_type": "bearer",
    }


@route("POST", "/api/v1/auth/refresh")
def auth_refresh(ctx: Ctx):
    token = ctx.body.get("refresh_token")
    payload = auth_mod.verify_token(token) if token else None
    if not payload or payload.get("type") != "refresh":
        return 401, {"detail": "Invalid or expired refresh token"}
    conn = get_conn()
    user = conn.execute("SELECT * FROM users WHERE id=?", (payload["sub"],)).fetchone()
    conn.close()
    role = user["role"] if user else "Viewer"
    return 200, {"access_token": auth_mod.create_access_token(payload["sub"], role), "token_type": "bearer"}


@route("POST", "/api/v1/auth/login")
def auth_login(ctx: Ctx):
    """Dashboard email+password login (2FA code checked client-side demo-style
    here; production verifies a TOTP against the user's authenticator secret)."""
    email = ctx.body.get("email")
    password = ctx.body.get("password")
    totp_code = ctx.body.get("totp_code", "")
    conn = get_conn()
    user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    conn.close()
    if not user or not auth_mod.verify_password(password or "", user["password_hash"] or ""):
        return 401, {"detail": "Invalid email or password"}
    if len(totp_code) != 6:
        return 401, {"detail": "Invalid 2FA code"}
    return 200, {
        "access_token": auth_mod.create_access_token(user["id"], user["role"]),
        "refresh_token": auth_mod.create_refresh_token(user["id"]),
        "role": user["role"],
        "token_type": "bearer",
    }


# ------------------------------------------------------------ predictions

@route("GET", "/api/v1/predict/current")
def predict_current(ctx: Ctx):
    lat, lon = float(ctx.q("lat", 1.0)), float(ctx.q("lon", 37.0))
    conn = get_conn()
    cells = conn.execute("SELECT * FROM grid_cells").fetchall()
    nearest = min(cells, key=lambda c: haversine_km(lat, lon, c["lat"], c["lon"]))
    pred = conn.execute(
        "SELECT * FROM predictions WHERE grid_id=? AND window='1-day' ORDER BY predicted_at DESC LIMIT 1",
        (nearest["id"],),
    ).fetchone()
    conn.close()
    if not pred:
        return 404, {"detail": "No prediction available for this location"}
    return 200, {
        "grid_id": nearest["id"],
        "village_name": nearest["village_name"],
        "flood_prob": pred["flood_prob"],
        "drought_prob": pred["drought_prob"],
        "action_code": pred["action_code"],
        "action_text": json.loads(pred["action_text_json"]),
        "valid_until": pred["valid_until"],
    }


@route("GET", "/api/v1/predict/week")
def predict_week(ctx: Ctx):
    lat, lon = float(ctx.q("lat", 1.0)), float(ctx.q("lon", 37.0))
    conn = get_conn()
    cells = conn.execute("SELECT * FROM grid_cells").fetchall()
    nearest = min(cells, key=lambda c: haversine_km(lat, lon, c["lat"], c["lon"]))
    rnd = random.Random(hash(nearest["id"]) % (2**31))
    days = []
    base_flood, base_drought = rnd.uniform(0.2, 0.6), rnd.uniform(0.2, 0.6)
    for d in range(7):
        flood = max(0, min(1, base_flood + rnd.uniform(-0.15, 0.2)))
        drought = max(0, min(1, base_drought + rnd.uniform(-0.15, 0.2)))
        days.append({"day": d + 1, "flood_prob": round(flood, 2), "drought_prob": round(drought, 2),
                      "action_code": action_from_probs(flood, drought)})
    conn.close()
    return 200, {"grid_id": nearest["id"], "village_name": nearest["village_name"], "forecast": days}


@route("GET", "/api/v1/predict/grid/{grid_id}")
def predict_grid(ctx: Ctx):
    grid_id = ctx.params["grid_id"]
    conn = get_conn()
    cell = conn.execute("SELECT * FROM grid_cells WHERE id=?", (grid_id,)).fetchone()
    if not cell:
        conn.close()
        return 404, {"detail": "Grid cell not found"}
    preds = conn.execute("SELECT * FROM predictions WHERE grid_id=? ORDER BY window", (grid_id,)).fetchall()
    conn.close()
    return 200, {
        "grid_id": grid_id,
        "village_name": cell["village_name"],
        "country": cell["country"],
        "predictions": [
            {"window": p["window"], "flood_prob": p["flood_prob"], "drought_prob": p["drought_prob"],
             "action_code": p["action_code"], "action_text": json.loads(p["action_text_json"]),
             "predicted_at": p["predicted_at"], "valid_until": p["valid_until"]}
            for p in preds
        ],
    }


@route("GET", "/api/v1/predict/grids")
def predict_grids(ctx: Ctx):
    """Bulk endpoint used by the dashboard's heatmap/grid mosaic — not in the
    original 18 but needed so the frontend can render the whole grid in one call
    instead of 128 round trips."""
    window = ctx.q("window", "3-day")
    conn = get_conn()
    rows = conn.execute(
        """SELECT g.id as grid_id, g.village_name, g.lat, g.lon, p.flood_prob, p.drought_prob, p.action_code
           FROM grid_cells g JOIN predictions p ON p.grid_id = g.id WHERE p.window = ?""",
        (window,),
    ).fetchall()
    conn.close()
    return 200, {"window": window, "cells": [dict(r) for r in rows]}


# -------------------------------------------------------------- feedback

@route("POST", "/api/v1/feedback/submit")
def feedback_submit(ctx: Ctx):
    phone = ctx.body.get("phone", "unknown")
    if rate_limited(f"feedback:{phone}", max_requests=3, window_seconds=86400):
        return 429, {"detail": "Daily feedback report limit reached (3/day)"}
    raw_text = ctx.body.get("raw_text", "")
    lat, lon = ctx.body.get("lat"), ctx.body.get("lon")
    media_url = ctx.body.get("media_url")
    report_type, intent, confidence = parse_intent(raw_text or ctx.body.get("report_type", ""))
    report_type = ctx.body.get("report_type", report_type)
    fid = str(uuid.uuid4())
    conn = get_conn()
    conn.execute(
        """INSERT INTO feedback (id, phone, lat, lon, report_type, media_url, raw_text, parsed_intent, nlp_confidence, status, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (fid, phone, lat, lon, report_type, media_url, raw_text, intent, confidence, "Pending", now_iso()),
    )
    conn.commit()
    conn.close()
    return 201, {"id": fid, "reference": f"RPT-{time.strftime('%Y')}-{random.randint(10000,99999)}",
                 "parsed_intent": intent, "confidence": confidence, "status": "Pending"}


@route("GET", "/api/v1/feedback/admin")
def feedback_admin(ctx: Ctx):
    if not ctx.user:
        return 401, {"detail": "Authentication required"}
    status = ctx.q("status")
    report_type = ctx.q("report_type")
    page = int(ctx.q("page", 1))
    page_size = int(ctx.q("page_size", 20))
    conn = get_conn()
    q = "SELECT * FROM feedback WHERE 1=1"
    args = []
    if status:
        q += " AND status=?"; args.append(status)
    if report_type:
        q += " AND report_type=?"; args.append(report_type)
    total = conn.execute(f"SELECT COUNT(*) c FROM ({q})", args).fetchone()["c"]
    q += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    args += [page_size, (page - 1) * page_size]
    rows = conn.execute(q, args).fetchall()
    conn.close()
    return 200, {"total": total, "page": page, "page_size": page_size, "items": [dict(r) for r in rows]}


@route("PUT", "/api/v1/feedback/verify/{id}")
def feedback_verify(ctx: Ctx):
    if not ctx.user or ctx.user.get("role") not in ("SuperAdmin", "Moderator"):
        return 403, {"detail": "Moderator or SuperAdmin role required"}
    conn = get_conn()
    conn.execute("UPDATE feedback SET status='Verified', verified_at=? WHERE id=?", (now_iso(), ctx.params["id"]))
    conn.commit()
    conn.close()
    return 200, {"id": ctx.params["id"], "status": "Verified"}


@route("DELETE", "/api/v1/feedback/spam/{id}")
def feedback_spam(ctx: Ctx):
    if not ctx.user or ctx.user.get("role") not in ("SuperAdmin", "Moderator"):
        return 403, {"detail": "Moderator or SuperAdmin role required"}
    conn = get_conn()
    conn.execute("UPDATE feedback SET status='Spam' WHERE id=?", (ctx.params["id"],))
    conn.commit()
    conn.close()
    return 200, {"id": ctx.params["id"], "status": "Spam"}


# ------------------------------------------------------------- broadcasts

@route("POST", "/api/v1/broadcast/send")
def broadcast_send(ctx: Ctx):
    if not ctx.user or ctx.user.get("role") not in ("SuperAdmin", "Moderator"):
        return 403, {"detail": "Moderator or SuperAdmin role required"}
    message = ctx.body.get("message_text", "")
    channels = ctx.body.get("channels", ["SMS"])
    target_filter = ctx.body.get("target_filter", {})
    scheduled_for = ctx.body.get("scheduled_for")
    bid = str(uuid.uuid4())

    conn = get_conn()
    audience = conn.execute("SELECT COUNT(*) c FROM users WHERE status='Active'").fetchone()["c"]
    is_future = bool(scheduled_for)
    sms_count = 0 if is_future else random.randint(200, max(200, min(2000, audience * 4 or 2000)))
    push_count = 0 if is_future else random.randint(500, max(500, min(4000, audience * 8 or 4000)))
    status = "scheduled" if is_future else "sent"
    conn.execute(
        """INSERT INTO broadcasts (id, sent_by, target_filter_json, message_text, channels,
           sent_via_sms_count, sent_via_push_count, status, scheduled_for, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (bid, ctx.user["sub"], json.dumps(target_filter), message, ",".join(channels),
         sms_count, push_count, status, scheduled_for, now_iso()),
    )
    conn.commit()
    conn.close()
    # In production: services/africastalking_client.py dispatches to SMS/Voice,
    # services/fcm_client.py dispatches to Push, via an async Celery worker.
    print(f"[MOCK DISPATCH] broadcast {bid} -> {channels} -> {target_filter}: {message[:60]}")
    return 201, {"id": bid, "status": status, "sms_delivered": sms_count, "push_delivered": push_count}


@route("GET", "/api/v1/broadcast/history")
def broadcast_history(ctx: Ctx):
    if not ctx.user:
        return 401, {"detail": "Authentication required"}
    conn = get_conn()
    rows = conn.execute("SELECT * FROM broadcasts ORDER BY created_at DESC LIMIT 50").fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["target_filter"] = json.loads(d.pop("target_filter_json"))
        out.append(d)
    return 200, {"items": out}


# ------------------------------------------------------------------ users

@route("GET", "/api/v1/users/me")
def users_me(ctx: Ctx):
    if not ctx.user:
        return 401, {"detail": "Authentication required"}
    conn = get_conn()
    row = conn.execute("SELECT id, name, phone, email, region, language, role, notif_push, notif_sms, notif_voice, status FROM users WHERE id=?",
                        (ctx.user["sub"],)).fetchone()
    conn.close()
    if not row:
        return 404, {"detail": "User not found"}
    return 200, dict(row)


@route("PUT", "/api/v1/users/preferences")
def users_preferences(ctx: Ctx):
    if not ctx.user:
        return 401, {"detail": "Authentication required"}
    fields, args = [], []
    for key, col in [("language", "language"), ("fcm_token", "fcm_token"),
                      ("notif_push", "notif_push"), ("notif_sms", "notif_sms"), ("notif_voice", "notif_voice")]:
        if key in ctx.body:
            fields.append(f"{col}=?"); args.append(ctx.body[key])
    if not fields:
        return 400, {"detail": "No fields to update"}
    args.append(ctx.user["sub"])
    conn = get_conn()
    conn.execute(f"UPDATE users SET {', '.join(fields)} WHERE id=?", args)
    conn.commit()
    conn.close()
    return 200, {"updated": True}


@route("GET", "/api/v1/users/admin")
def users_admin(ctx: Ctx):
    if not ctx.user or ctx.user.get("role") != "SuperAdmin":
        return 403, {"detail": "SuperAdmin role required"}
    region = ctx.q("region")
    status = ctx.q("status")
    page = int(ctx.q("page", 1)); page_size = int(ctx.q("page_size", 20))
    conn = get_conn()
    q = "SELECT id, name, phone, email, region, language, role, status, last_active FROM users WHERE 1=1"
    args = []
    if region and region != "All regions":
        q += " AND region=?"; args.append(region)
    if status and status != "ALL":
        q += " AND status=?"; args.append(status)
    total = conn.execute(f"SELECT COUNT(*) c FROM ({q})", args).fetchone()["c"]
    q += " LIMIT ? OFFSET ?"; args += [page_size, (page - 1) * page_size]
    rows = conn.execute(q, args).fetchall()
    conn.close()
    return 200, {"total": total, "page": page, "items": [dict(r) for r in rows]}


@route("PUT", "/api/v1/users/block/{id}")
def users_block(ctx: Ctx):
    if not ctx.user or ctx.user.get("role") != "SuperAdmin":
        return 403, {"detail": "SuperAdmin role required"}
    conn = get_conn()
    row = conn.execute("SELECT status FROM users WHERE id=?", (ctx.params["id"],)).fetchone()
    if not row:
        conn.close()
        return 404, {"detail": "User not found"}
    new_status = "Blocked" if row["status"] == "Active" else "Active"
    conn.execute("UPDATE users SET status=? WHERE id=?", (new_status, ctx.params["id"]))
    conn.commit()
    conn.close()
    return 200, {"id": ctx.params["id"], "status": new_status}


@route("PUT", "/api/v1/users/role/{id}")
def users_role(ctx: Ctx):
    """Role assignment — extra endpoint beyond the base 18, needed for the
    dashboard's User Management role dropdown."""
    if not ctx.user or ctx.user.get("role") != "SuperAdmin":
        return 403, {"detail": "SuperAdmin role required"}
    role = ctx.body.get("role")
    if role not in ("SuperAdmin", "Moderator", "Viewer"):
        return 422, {"detail": "role must be SuperAdmin, Moderator, or Viewer"}
    conn = get_conn()
    conn.execute("UPDATE users SET role=? WHERE id=?", (role, ctx.params["id"]))
    conn.commit()
    conn.close()
    return 200, {"id": ctx.params["id"], "role": role}


@route("DELETE", "/api/v1/users/me")
def users_delete_me(ctx: Ctx):
    if not ctx.user:
        return 401, {"detail": "Authentication required"}
    conn = get_conn()
    conn.execute("DELETE FROM users WHERE id=?", (ctx.user["sub"],))
    conn.commit()
    conn.close()
    return 200, {"deleted": True}


# -------------------------------------------------------------- resources

@route("GET", "/api/v1/resources/nearby")
def resources_nearby(ctx: Ctx):
    lat, lon = float(ctx.q("lat", 1.0)), float(ctx.q("lon", 37.0))
    conn = get_conn()
    rows = conn.execute("SELECT * FROM resources").fetchall()
    conn.close()
    ranked = sorted(
        (dict(r, distance_km=round(haversine_km(lat, lon, r["lat"], r["lon"]), 1)) for r in rows),
        key=lambda r: r["distance_km"],
    )
    return 200, {"items": ranked[:10]}


@route("GET", "/api/v1/resources/admin")
def resources_list(ctx: Ctx):
    if not ctx.user:
        return 401, {"detail": "Authentication required"}
    conn = get_conn()
    rows = conn.execute("SELECT * FROM resources ORDER BY created_at DESC").fetchall()
    conn.close()
    return 200, {"items": [dict(r) for r in rows]}


@route("POST", "/api/v1/resources/admin")
def resources_create(ctx: Ctx):
    if not ctx.user or ctx.user.get("role") not in ("SuperAdmin", "Moderator"):
        return 403, {"detail": "Moderator or SuperAdmin role required"}
    rid = str(uuid.uuid4())
    conn = get_conn()
    conn.execute(
        "INSERT INTO resources (id, name, type, lat, lon, capacity, contact_phone, zone, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (rid, ctx.body.get("name"), ctx.body.get("type"), ctx.body.get("lat", 0), ctx.body.get("lon", 0),
         ctx.body.get("capacity"), ctx.body.get("contact_phone"), ctx.body.get("zone", "Unassigned"), now_iso()),
    )
    conn.commit()
    conn.close()
    return 201, {"id": rid}


@route("PUT", "/api/v1/resources/admin/{id}")
def resources_update(ctx: Ctx):
    if not ctx.user or ctx.user.get("role") not in ("SuperAdmin", "Moderator"):
        return 403, {"detail": "Moderator or SuperAdmin role required"}
    fields, args = [], []
    for key in ("name", "type", "lat", "lon", "capacity", "contact_phone", "zone"):
        if key in ctx.body:
            fields.append(f"{key}=?"); args.append(ctx.body[key])
    if not fields:
        return 400, {"detail": "No fields to update"}
    args.append(ctx.params["id"])
    conn = get_conn()
    conn.execute(f"UPDATE resources SET {', '.join(fields)} WHERE id=?", args)
    conn.commit()
    conn.close()
    return 200, {"id": ctx.params["id"], "updated": True}


# ---------------------------------------------------------- system/health

@route("GET", "/api/v1/health")
def health(ctx: Ctx):
    conn = get_conn()
    try:
        conn.execute("SELECT 1")
        db_ok = True
    except Exception:
        db_ok = False
    conn.close()
    return 200, {
        "status": "ok" if db_ok else "degraded",
        "db": "ok" if db_ok else "error",
        "redis": "not_configured_in_dev_server",
        "gcp": "not_configured_in_dev_server",
        "timestamp": now_iso(),
    }


# ----------------------------------------------------------------- webhooks

_session_lang = {}


@route("POST", "/api/v1/ussd")
def ussd_webhook(ctx: Ctx):
    """Africa's Talking USSD protocol: form-encoded sessionId/serviceCode/
    phoneNumber/text in, plain 'CON ...'/'END ...' text out. Menu flow
    matches the blueprint: *384# -> 1 Get Alert -> 2 Report -> 3 Language."""
    session_id = ctx.body.get("sessionId", "")
    phone = ctx.body.get("phoneNumber", "")
    text = ctx.body.get("text", "")
    parts = text.split("*") if text else []
    lang = _session_lang.get(session_id, "en")

    if text == "":
        return 200, "CON AvertAI Alerts\n1. Get alert for my zone\n2. Report emergency\n3. Change language"

    if parts[0] == "1":
        conn = get_conn()
        cell = conn.execute("SELECT * FROM grid_cells LIMIT 1").fetchone()
        conn.close()
        if not cell:
            return 200, "END No grid data available."
        flood, drought, code = _rule_based_prediction_local(cell["id"], 1)
        advice = ACTION_TEXT[code][lang]
        return 200, f"END {cell['village_name']} \u2014 Code {code}\n{advice}"

    if parts[0] == "2":
        if len(parts) == 1:
            return 200, "CON Reply with: FLOOD [distance] [direction]\ne.g. FLOOD 2.5km North\n\n1. Enter report now"
        raw_text = "*".join(parts[1:]) or "emergency reported via USSD"
        report_type, intent, confidence = parse_intent(raw_text)
        conn = get_conn()
        conn.execute(
            """INSERT INTO feedback (id, user_id, phone, lat, lon, report_type, raw_text, parsed_intent, nlp_confidence, status, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (str(uuid.uuid4()), None, phone, 0.0, 0.0, report_type, raw_text, intent, confidence, "Pending", now_iso()),
        )
        conn.commit()
        conn.close()
        return 200, "END Thank you \u2014 your report was received and will reach the response team."

    if parts[0] == "3":
        if len(parts) == 1:
            return 200, "CON Choose language:\n1. English\n2. Kiswahili\n3. Amharic\n4. Somali"
        lang_map = {"1": "en", "2": "sw", "3": "am", "4": "so"}
        _session_lang[session_id] = lang_map.get(parts[1], "en")
        return 200, "END Language updated."

    return 200, "END Invalid option."


@route("POST", "/api/v1/webhooks/delivery-report")
def delivery_report_webhook(ctx: Ctx):
    return 200, {"received": True, "id": ctx.body.get("id"), "status": ctx.body.get("status")}


def _rule_based_prediction_local(seed_key, day_offset=0):
    rnd = random.Random(str(seed_key) + str(day_offset))
    flood = round(rnd.uniform(0.02, 0.95), 2)
    drought = round(rnd.uniform(0.02, 0.95), 2)
    return flood, drought, action_from_probs(flood, drought)


# ------------------------------------------------------------------ HTTP

class Handler(BaseHTTPRequestHandler):
    server_version = "AvertAIDevServer/1.0"

    def _cors(self):
        origin = self.headers.get("Origin", "*")
        self.send_header("Access-Control-Allow-Origin", origin if origin != "null" else "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def _send(self, status, payload):
        if isinstance(payload, str):
            body = payload.encode()
            content_type = "text/plain"
        else:
            body = json.dumps(payload).encode()
            content_type = "application/json"
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def _dispatch(self, method):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        body = None
        length = int(self.headers.get("Content-Length", 0) or 0)
        content_type = self.headers.get("Content-Type", "")
        if length:
            raw = self.rfile.read(length)
            if "application/x-www-form-urlencoded" in content_type:
                parsed_form = parse_qs(raw.decode())
                body = {k: v[0] for k, v in parsed_form.items()}
            else:
                try:
                    body = json.loads(raw or b"{}")
                except json.JSONDecodeError:
                    return self._send(400, {"detail": "Invalid JSON body"})

        if rate_limited(f"ip:{self.client_address[0]}", max_requests=1000, window_seconds=3600):
            return self._send(429, {"detail": "Rate limit exceeded (1000 req/hour per IP)"})

        for r in ROUTES:
            if r.method != method:
                continue
            m = r.regex.match(parsed.path)
            if m:
                ctx = Ctx(self, m.groupdict(), query, body)
                try:
                    status, payload = r.handler(ctx)
                except Exception as e:
                    return self._send(500, {"detail": f"Internal error: {e}"})
                return self._send(status, payload)
        self._send(404, {"detail": f"No route for {method} {parsed.path}"})

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_DELETE(self):
        self._dispatch("DELETE")

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {self.command} {self.path} -> {args[-1] if args else ''}")


def run(port=PORT):
    seed_if_empty()
    httpd = ThreadingHTTPServer(("localhost", port), Handler)
    print(f"AvertAI dev server listening on http://localhost:{port}")
    print(f"Registered {len(ROUTES)} routes.")
    httpd.serve_forever()


if __name__ == "__main__":
    run()
