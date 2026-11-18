from typing import Optional

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.dependencies import client_ip, get_current_user, user_agent
from app.database.database import get_db
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest, ForgotPasswordRequest, LoginRequest, LoginResponse, LogoutRequest,
    ResetPasswordRequest, UserSummary,
)
from app.schemas.common import Message
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    return auth_service.authenticate(
        db, payload.email, payload.password, client_ip(request), user_agent(request),
        payload.selfie_data, payload.late_login_reason, payload.work_period
    )


@router.post("/logout", response_model=Message)
def logout(
    request: Request,
    payload: Optional[LogoutRequest] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    auth_service.logout(
        db, current_user, client_ip(request), user_agent(request),
        payload.selfie_data if payload else None, payload.logout_reason if payload else None,
    )
    return Message(detail="Signed out.")


@router.post("/forgot-password", response_model=Message)
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    auth_service.request_password_reset(db, payload.email)
    # Deliberately identical whether or not the account exists.
    return Message(
        detail="If that email is registered, a reset link is on its way."
    )


@router.post("/reset-password", response_model=Message)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    auth_service.reset_password(db, payload.token, payload.new_password)
    return Message(detail="Password updated. You can sign in now.")


@router.post("/change-password", response_model=Message)
def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    auth_service.change_password(
        db, current_user, payload.current_password, payload.new_password
    )
    return Message(detail="Password changed.")


@router.get("/me", response_model=UserSummary)
def me(current_user: User = Depends(get_current_user)):
    return UserSummary(**auth_service.user_summary(current_user))
