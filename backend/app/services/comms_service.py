import logging
import random
import uuid
import time
from datetime import datetime
import redis

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger("avertai.sms")

try:
    redis_client = redis.from_url(settings.REDIS_URL, socket_connect_timeout=1)
except Exception:
    redis_client = None


def inject_template(template: str, variables: dict) -> str:
    """Inject dynamic variables into SMS templates."""
    result = template
    for key, value in variables.items():
        result = result.replace(f"{{{key}}}", str(value))
    return result


def _mock_send(channel: str, to: str, content: str) -> dict:
    logger.info("[MOCK %s] to=%s content=%r", channel, to, content[:120])
    return {
        "provider": "mock",
        "message_id": str(uuid.uuid4()),
        "status": "sent",
        "to": to,
        "sent_at": datetime.utcnow().isoformat(),
    }


def send_sms(to: str, message: str, is_red_alert: bool = False) -> dict:
    # Check circuit breaker
    cb_key = "circuit_breaker:africastalking_sms"
    fails = 0
    if redis_client:
        try:
            fails = int(redis_client.get(cb_key) or 0)
        except Exception:
            pass

    if fails >= 3:
        logger.warning("Circuit breaker OPEN for Africa's Talking. Routing directly to Twilio.")
        return _send_sms_twilio(to, message, is_red_alert)

    if not settings.AFRICAS_TALKING_USERNAME or not settings.AFRICAS_TALKING_API_KEY:
        # Simulate flash sms logging
        channel = "FLASH_SMS" if is_red_alert else "SMS"
        return _mock_send(channel, to, message)

    try:
        import africastalking
        africastalking.initialize(settings.AFRICAS_TALKING_USERNAME, settings.AFRICAS_TALKING_API_KEY)
        sms = africastalking.SMS
        # Use bulkSMSMode=0 for Flash SMS (simulated parameter via keyword args depending on SDK version)
        # Note: Africa's Talking Python SDK might not expose flash directly, but we pass enqueue=0 
        resp = sms.send(message, [to], sender_id=settings.AFRICAS_TALKING_SENDER_ID, enqueue=0)
        
        # Reset circuit breaker on success
        if redis_client:
            try:
                redis_client.delete(cb_key)
            except Exception:
                pass
                
        return {"provider": "africastalking", "status": "sent", "raw": resp}
    except Exception as exc:
        logger.warning("Africa's Talking SMS failed (%s)", exc)
        if redis_client:
            try:
                # Increment failure count, expire in 15 mins
                redis_client.incr(cb_key)
                redis_client.expire(cb_key, 900)
            except Exception:
                pass
        
        # Fallback to Twilio
        twilio_resp = _send_sms_twilio(to, message, is_red_alert)
        
        # Voice Escalation Ladder Logic
        if twilio_resp["status"] == "failed" and is_red_alert:
            logger.error("Both SMS providers failed for RED alert. Escalating to Voice Call.")
            send_voice_call(to, message)
            
        return twilio_resp


def _send_sms_twilio(to: str, message: str, is_red_alert: bool = False) -> dict:
    if not settings.TWILIO_ACCOUNT_SID:
        channel = "FLASH_SMS-fallback" if is_red_alert else "SMS-fallback"
        return _mock_send(channel, to, message)
    try:
        from twilio.rest import Client
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        msg = client.messages.create(body=message, from_=settings.TWILIO_FROM_NUMBER, to=to)
        return {"provider": "twilio", "status": msg.status, "sid": msg.sid}
    except Exception as exc:
        logger.error("Twilio fallback also failed: %s", exc)
        return {"provider": "none", "status": "failed", "error": str(exc)}


def send_voice_call(to: str, message_text: str, language: str = "en") -> dict:
    if not settings.AFRICAS_TALKING_API_KEY:
        return _mock_send("VOICE", to, message_text)
    try:
        import africastalking
        africastalking.initialize(settings.AFRICAS_TALKING_USERNAME, settings.AFRICAS_TALKING_API_KEY)
        voice = africastalking.Voice
        resp = voice.call({"callFrom": settings.AFRICAS_TALKING_SENDER_ID, "callTo": [to]})
        return {"provider": "africastalking", "status": "queued", "raw": resp}
    except Exception as exc:
        logger.warning("Voice call failed: %s", exc)
        return {"provider": "none", "status": "failed", "error": str(exc)}


def send_push(fcm_token: str, title: str, body: str, deep_link: str = None) -> dict:
    if not settings.GOOGLE_APPLICATION_CREDENTIALS or not fcm_token:
        return _mock_send("PUSH", fcm_token or "no-token", f"{title}: {body}")
    try:
        import firebase_admin
        from firebase_admin import credentials, messaging
        
        # Initialize the default app if not already initialized
        if not firebase_admin._apps:
            cred = credentials.Certificate(settings.GOOGLE_APPLICATION_CREDENTIALS)
            firebase_admin.initialize_app(cred)
            
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data={"deep_link": deep_link or ""},
            token=fcm_token,
        )
        
        response = messaging.send(message)
        return {"provider": "fcm", "status": "sent", "message_id": response}
    except Exception as exc:
        logger.warning("FCM push failed: %s", exc)
        return {"provider": "none", "status": "failed", "error": str(exc)}


def estimate_delivery_counts(target_audience_size: int) -> dict:
    delivered_pct = random.uniform(0.85, 0.99)
    return {
        "sms_delivered": int(target_audience_size * delivered_pct),
        "push_delivered": int(target_audience_size * random.uniform(1.5, 3.2)),
    }
