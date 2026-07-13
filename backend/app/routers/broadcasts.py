from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import Broadcast, User
from app.core.deps import require_roles
from app.services.comms_service import estimate_delivery_counts, send_sms, send_push
from app.schemas.broadcasts import (
    BroadcastSendRequest, BroadcastSendResponse, BroadcastHistoryResponse,
)

router = APIRouter(prefix="/broadcast", tags=["broadcasts"])


from app.worker import dispatch_broadcast

@router.post("/send", response_model=BroadcastSendResponse)
def send_broadcast(
    payload: BroadcastSendRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("SuperAdmin", "Moderator")),
):
    """Accepts the target filter + message and pushes to the async dispatcher."""
    is_scheduled = payload.scheduled_at is not None
    row = Broadcast(
        sent_by=user.id,
        target_filter=payload.target_filter or "all",
        message_text=payload.message,
        channels=",".join(payload.channels),
        status="scheduled" if is_scheduled else "queued",
        scheduled_at=payload.scheduled_at,
    )

    row.sent_via_sms_count = 0
    row.sent_via_push_count = 0

    db.add(row)
    db.commit()
    db.refresh(row)

    if not is_scheduled:
        dispatch_broadcast.delay(row.id)

    return {
        "id": row.id, "status": row.status,
        "sms_delivered": row.sent_via_sms_count, "push_delivered": row.sent_via_push_count,
    }


@router.get("/history", response_model=BroadcastHistoryResponse)
def broadcast_history(db: Session = Depends(get_db), user: User = Depends(require_roles("SuperAdmin", "Moderator"))):
    rows = db.query(Broadcast).order_by(Broadcast.created_at.desc()).limit(50).all()
    return {"total": len(rows), "items": rows}
