from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel


class BroadcastSendRequest(BaseModel):
    message: str
    channels: List[str]  # subset of ["SMS", "Push", "Voice"]
    target_filter: Optional[str] = "all"  # e.g. "region:Kenya", "risk_level:RED", "language:sw"
    scheduled_at: Optional[datetime] = None


class BroadcastSendResponse(BaseModel):
    id: str
    status: str
    sms_delivered: int
    push_delivered: int


class BroadcastHistoryItem(BaseModel):
    id: str
    target_filter: str
    message_text: str
    channels: str
    sent_via_sms_count: int
    sent_via_push_count: int
    status: str
    scheduled_at: Optional[datetime]
    created_at: datetime


class BroadcastHistoryResponse(BaseModel):
    total: int
    items: List[BroadcastHistoryItem]
