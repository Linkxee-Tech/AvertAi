import random
from typing import List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import OrganizationApplication, User
from app.core.deps import get_current_user
from app.core.security import hash_password

router = APIRouter(prefix="/applications", tags=["applications"])


class ApplicationCreate(BaseModel):
    org_name: str
    country: str
    org_type: str
    website: str
    admin_name: str
    admin_title: str
    email: EmailStr
    phone: str
    purpose: str


class ApplicationResponse(BaseModel):
    id: str
    org_name: str
    country: str
    org_type: str
    website: str
    admin_name: str
    admin_title: str
    email: str
    phone: str
    purpose: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


@router.post("/apply", status_code=status.HTTP_201_CREATED)
def apply_for_ngo_access(payload: ApplicationCreate, db: Session = Depends(get_db)):
    """Public endpoint for an NGO to apply for dashboard access."""
    app_obj = OrganizationApplication(
        org_name=payload.org_name,
        country=payload.country,
        org_type=payload.org_type,
        website=payload.website,
        admin_name=payload.admin_name,
        admin_title=payload.admin_title,
        email=payload.email,
        phone=payload.phone,
        purpose=payload.purpose,
        status="Pending"
    )
    db.add(app_obj)
    db.commit()
    return {"message": "Application submitted successfully. Our team will review it shortly."}


@router.get("", response_model=List[ApplicationResponse])
def get_applications(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """SuperAdmin only: List all pending applications."""
    if current_user.role != "super_admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Requires super_admin role")
    return db.query(OrganizationApplication).filter(OrganizationApplication.status == "Pending").all()


@router.post("/{app_id}/approve")
def approve_application(app_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """SuperAdmin only: Approve application and provision Admin account."""
    if current_user.role != "super_admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Requires super_admin role")
    
    app_obj = db.query(OrganizationApplication).filter(OrganizationApplication.id == app_id).first()
    if not app_obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found")
    if app_obj.status != "Pending":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Application already processed")

    app_obj.status = "Approved"
    
    # Check if user already exists
    existing_user = db.query(User).filter(User.email == app_obj.email).first()
    if not existing_user:
        # Create Admin user
        temp_password = f"{random.randint(100000, 999999)}"
        new_admin = User(
            name=app_obj.admin_name,
            email=app_obj.email,
            phone=app_obj.phone,
            password_hash=hash_password(temp_password),
            region=app_obj.country,
            role="admin",
            status="Active"
        )
        db.add(new_admin)
        
        # In a real app, send email with temp_password. Here we just return it for the hackathon demo.
        db.commit()
        return {
            "message": f"Approved! Admin created.",
            "email": app_obj.email,
            "temp_password": temp_password
        }
    
    db.commit()
    return {"message": "Approved, but user email already existed in system."}

@router.post("/{app_id}/reject")
def reject_application(app_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """SuperAdmin only: Reject application."""
    if current_user.role != "super_admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Requires super_admin role")
    
    app_obj = db.query(OrganizationApplication).filter(OrganizationApplication.id == app_id).first()
    if not app_obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found")
    
    app_obj.status = "Rejected"
    db.commit()
    return {"message": "Application rejected."}
