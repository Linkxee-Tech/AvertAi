import os
from datetime import datetime
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, Query, status, File, Form, UploadFile
from sqlalchemy.orm import Session
from PIL import Image

from app.db.session import get_db
from app.db.models import Feedback, User
from app.core.config import get_settings
from app.core.deps import require_roles
from app.services.nlp_service import parse_feedback_text
from app.services.rate_limiter import is_rate_limited
from app.schemas.feedback import (
    FeedbackSubmitResponse,
    FeedbackListResponse, FeedbackVerifyResponse,
)

router = APIRouter(prefix="/feedback", tags=["feedback"])
settings = get_settings()

UPLOAD_DIR = "./uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/submit", response_model=FeedbackSubmitResponse)
async def submit_feedback(
    phone: str = Form(...),
    lat: float = Form(...),
    lon: float = Form(...),
    raw_text: str = Form(...),
    image: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    if is_rate_limited(f"feedback:{phone}", settings.FEEDBACK_RATE_LIMIT_PER_DAY, 86400):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Daily feedback report limit reached for this phone")

    media_url = None
    if image:
        contents = await image.read()
        file_size = len(contents)
        
        # Compress if > 1MB
        if file_size > 1024 * 1024:
            try:
                img = Image.open(BytesIO(contents))
                # Convert to RGB if necessary
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                output = BytesIO()
                # Reduce quality to compress
                img.save(output, format="JPEG", quality=70, optimize=True)
                contents = output.getvalue()
            except Exception as e:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Invalid image file: {e}")

        # Save locally for staging
        filename = f"{phone}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.jpg"
        filepath = os.path.join(UPLOAD_DIR, filename)
        with open(filepath, "wb") as f:
            f.write(contents)
        media_url = f"/uploads/{filename}"

    report_type, intent, confidence, geo_entity = parse_feedback_text(raw_text)
    reference = f"RPT-{datetime.utcnow().year}-{__import__('random').randint(10000, 99999)}"

    row = Feedback(
        phone=phone, lat=lat, lon=lon,
        report_type=report_type, media_url=media_url,
        raw_text=raw_text, parsed_intent=intent, confidence=confidence,
        status="Pending", reference=reference,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return {
        "id": row.id, "reference": reference,
        "parsed_intent": intent, "confidence": confidence, "status": row.status,
    }


@router.get("/admin", response_model=FeedbackListResponse, dependencies=[Depends(require_roles("SuperAdmin", "Moderator"))])
def list_feedback(
    status_filter: str | None = Query(None, alias="status"),
    region: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    q = db.query(Feedback)
    if status_filter:
        q = q.filter(Feedback.status == status_filter)
    total = q.count()
    items = q.order_by(Feedback.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.put("/verify/{feedback_id}", response_model=FeedbackVerifyResponse, dependencies=[Depends(require_roles("SuperAdmin", "Moderator"))])
def verify_feedback(feedback_id: str, db: Session = Depends(get_db)):
    row = db.query(Feedback).filter(Feedback.id == feedback_id).first()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Feedback not found")
    row.status = "Verified"
    row.verified_at = datetime.utcnow()
    db.commit()
    return {"id": row.id, "status": row.status}


@router.delete("/spam/{feedback_id}", dependencies=[Depends(require_roles("SuperAdmin", "Moderator"))])
def mark_spam(feedback_id: str, db: Session = Depends(get_db)):
    row = db.query(Feedback).filter(Feedback.id == feedback_id).first()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Feedback not found")
    row.status = "Spam"
    db.commit()
    return {"id": row.id, "status": row.status}
