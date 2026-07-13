"""
Shared FastAPI dependencies: DB session injection, JWT auth guard, and the
role-based access control used to gate SuperAdmin/Moderator-only routes
(mirrors the dashboard's client-side nav gating, but enforced server-side
where it actually matters).
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.security import decode_token
from app.db.models import User

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    payload = decode_token(creds.credentials)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    user = db.query(User).filter(User.id == payload["sub"]).first()
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    if user.status == "Blocked":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is blocked")
    return user


def require_roles(*allowed_roles: str):
    """Usage: Depends(require_roles("SuperAdmin", "Moderator"))"""
    def _checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"{' or '.join(allowed_roles)} role required",
            )
        return user
    return _checker
