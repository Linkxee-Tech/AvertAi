from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel


class UserMeResponse(BaseModel):
    id: str
    name: Optional[str]
    phone: str
    email: Optional[str]
    region: Optional[str]
    language: str
    role: str
    notif_push: bool
    notif_sms: bool
    notif_voice: bool
    status: str


class UserPreferencesUpdate(BaseModel):
    language: Optional[str] = None
    fcm_token: Optional[str] = None
    notif_push: Optional[bool] = None
    notif_sms: Optional[bool] = None
    notif_voice: Optional[bool] = None


class AdminUserItem(BaseModel):
    id: str
    name: Optional[str]
    phone: str
    region: Optional[str]
    role: str
    status: str
    last_active: datetime


class AdminUserListResponse(BaseModel):
    total: int
    page: int
    items: List[AdminUserItem]


class BlockToggleResponse(BaseModel):
    id: str
    status: str


class RoleUpdateRequest(BaseModel):
    role: str  # SuperAdmin | Moderator | Viewer


class RoleUpdateResponse(BaseModel):
    id: str
    role: str
