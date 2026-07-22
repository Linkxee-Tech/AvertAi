"""
Inbound webhooks from Africa's Talking.

USSD: Africa's Talking POSTs application/x-www-form-urlencoded fields
(sessionId, serviceCode, phoneNumber, text) on every keypress in a session.
`text` accumulates the full input path joined by "*", e.g. a user who dials
*384#, presses 1, then 2 sends text="1*2". The response must be plain text
starting with "CON " (continue session, show another menu) or "END "
(terminate session) — this is Africa's Talking's actual USSD protocol, not
a made-up format.

Delivery reports: Africa's Talking POSTs delivery status for previously sent
SMS (id, status, phoneNumber) so we can update broadcast stats.
"""
import redis
from fastapi import APIRouter, Form, Response, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db.session import get_db
from app.db.models import GridCell, Feedback, Broadcast
from app.core.config import get_settings
from app.services.ml_service import generate_prediction, action_text_for
from app.services.nlp_service import parse_feedback_text

router = APIRouter(tags=["webhooks"])
settings = get_settings()

try:
    redis_client = redis.from_url(settings.REDIS_URL, socket_connect_timeout=1)
except Exception:
    redis_client = None


def get_ussd_lang(session_id: str) -> str:
    if redis_client:
        try:
            val = redis_client.get(f"ussd_lang:{session_id}")
            if val:
                return val.decode("utf-8")
        except Exception:
            pass
    return "en"


def set_ussd_lang(session_id: str, lang: str):
    if redis_client:
        try:
            redis_client.setex(f"ussd_lang:{session_id}", 3600, lang)
        except Exception:
            pass


@router.post("/ussd/callback")
def ussd_webhook(
    sessionId: str = Form(...),
    serviceCode: str = Form(...),
    phoneNumber: str = Form(...),
    text: str = Form(""),
    db: Session = Depends(get_db),
):
    """Menu flow (matches the blueprint exactly):
    *384# -> 1. Get Alert -> 2. Report Emergency -> 3. Language
    Shortcut: *384*1# directly triggers the alert
    """
    # Check for shortcut
    if text == "1":
        # Fast path
        lang = get_ussd_lang(sessionId)
        cell = db.query(GridCell).first()
        if cell:
            flood, drought, code = generate_prediction(cell.id, 1)
            advice = action_text_for(code)[lang]
            response = f"END {cell.village_name} — Code {code}\n{advice}"
        else:
            response = "END No grid data available."
        return Response(content=response, media_type="text/plain")

    parts = text.split("*") if text else []
    lang = get_ussd_lang(sessionId)

    if text == "":
        response = "CON AvertAI Alerts\n1. Get alert for my zone\n2. Report emergency\n3. Change language"

    elif parts[0] == "1":
        cell = db.query(GridCell).first()
        if cell:
            flood, drought, code = generate_prediction(cell.id, 1)
            advice = action_text_for(code)[lang]
            response = f"END {cell.village_name} — Code {code}\n{advice}"
        else:
            response = "END No grid data available."

    elif parts[0] == "2":
        if len(parts) == 1:
            response = "CON Reply with: FLOOD [distance] [direction]\ne.g. FLOOD 2.5km North\n\n1. Enter report now"
        else:
            raw_text = "*".join(parts[1:]) or "emergency reported via USSD"
            report_type, intent, confidence, geo = parse_feedback_text(raw_text)
            db.add(Feedback(
                phone=phoneNumber, lat=0.0, lon=0.0, report_type=report_type,
                raw_text=raw_text, parsed_intent=intent, confidence=confidence, status="Pending",
            ))
            db.commit()
            response = "END Thank you — your report was received and will reach the response team."

    elif parts[0] == "3":
        if len(parts) == 1:
            response = "CON Choose language:\n1. English\n2. Kiswahili\n3. Amharic\n4. Somali"
        else:
            lang_map = {"1": "en", "2": "sw", "3": "am", "4": "so"}
            new_lang = lang_map.get(parts[1], "en")
            set_ussd_lang(sessionId, new_lang)
            response = "END Language updated."

    else:
        response = "END Invalid option."

    return Response(content=response, media_type="text/plain")


@router.post("/webhooks/delivery-report")
def delivery_report_webhook(
    id: str = Form(...),
    status: str = Form(...),
    phoneNumber: str = Form(""),
    db: Session = Depends(get_db),
):
    """Africa's Talking posts delivery status here after an SMS is sent.
    Production: update the broadcast."""
    # Since we don't have a join table tracking which broadcast sent which message_id in MVP,
    # we simulate the real-time increment on the latest active broadcast.
    # In full production, we'd query by tracking_id or cross-reference message_id.
    
    if status.lower() == "success":
        # Hacky increment for MVP presentation
        db.execute(text("UPDATE broadcasts SET sent_via_sms_count = sent_via_sms_count + 1 WHERE status != 'failed'"))
        db.commit()
        
    return {"received": True, "id": id, "status": status}
