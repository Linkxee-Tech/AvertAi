from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel


class FeedbackSubmitRequest(BaseModel):
    phone: str
    lat: float
    lon: float
    raw_text: str
    media_url: Optional[str] = None  # set after client uploads image via a signed GCS URL


class FeedbackSubmitResponse(BaseModel):
    id: str
    reference: str
    parsed_intent: str
    confidence: float
    status: str


class FeedbackItem(BaseModel):
    id: str
    user_id: Optional[str]
    phone: str
    lat: float
    lon: float
    report_type: str
    media_url: Optional[str]
    raw_text: str
    parsed_intent: str
    confidence: float
    status: str
    created_at: datetime
    verified_at: Optional[datetime]


class FeedbackListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[FeedbackItem]


class FeedbackVerifyResponse(BaseModel):
    id: str
    status: str
