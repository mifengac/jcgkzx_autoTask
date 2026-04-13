from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from autotask_api.database import get_db
from autotask_api.schemas import LoginRequest, PlatformUserRead
from autotask_api.services.auth import (
    authenticate_user,
    clear_auth_cookie,
    create_session_token,
    mark_user_login,
    require_authenticated_user,
    serialize_user,
    set_auth_cookie,
    user_table_exists,
)


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=PlatformUserRead)
def login(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> PlatformUserRead:
    if not user_table_exists(db):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="未找到用户表，请先执行 migrations/0408_auth_user.sql。",
        )
    user = authenticate_user(db, payload.username, payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误。",
        )
    mark_user_login(db, user)
    set_auth_cookie(response, create_session_token(user))
    return PlatformUserRead.model_validate(serialize_user(user))


@router.post("/logout")
def logout(response: Response) -> dict[str, str]:
    clear_auth_cookie(response)
    return {"status": "ok"}


@router.get("/me", response_model=PlatformUserRead)
def me(user=Depends(require_authenticated_user)) -> PlatformUserRead:
    return PlatformUserRead.model_validate(serialize_user(user))
