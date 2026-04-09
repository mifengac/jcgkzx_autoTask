from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import timedelta
import hashlib
import hmac
import json
import secrets
from typing import Any

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from autotask_api.config import get_settings
from autotask_api.database import get_db
from autotask_api.models import PlatformUser
from autotask_api.services.time_utils import now_shanghai


settings = get_settings()


def _b64_encode(value: bytes) -> str:
    return urlsafe_b64encode(value).decode("utf-8").rstrip("=")


def _b64_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return urlsafe_b64decode(value + padding)


def hash_password(password: str, salt: str | None = None) -> str:
    password_text = str(password)
    if not password_text:
        raise ValueError("Password cannot be empty.")
    salt_text = salt or secrets.token_hex(16)
    rounds = 120_000
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password_text.encode("utf-8"),
        salt_text.encode("utf-8"),
        rounds,
    )
    return f"pbkdf2_sha256${rounds}${salt_text}${_b64_encode(digest)}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        scheme, rounds_text, salt_text, digest_text = password_hash.split("$", 3)
    except ValueError:
        return False
    if scheme != "pbkdf2_sha256":
        return False
    try:
        rounds = int(rounds_text)
    except ValueError:
        return False
    expected = hashlib.pbkdf2_hmac(
        "sha256",
        str(password).encode("utf-8"),
        salt_text.encode("utf-8"),
        rounds,
    )
    return hmac.compare_digest(_b64_encode(expected), digest_text)


def create_session_token(user: PlatformUser) -> str:
    expires_at = now_shanghai() + timedelta(hours=settings.auth_session_ttl_hours)
    payload = {
        "user_id": user.id,
        "username": user.username,
        "exp": int(expires_at.timestamp()),
    }
    payload_text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    payload_token = _b64_encode(payload_text.encode("utf-8"))
    signature = hmac.new(
        settings.auth_secret_key.encode("utf-8"),
        payload_token.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return f"{payload_token}.{_b64_encode(signature)}"


def decode_session_token(token: str) -> dict[str, Any] | None:
    if not token or "." not in token:
        return None
    payload_token, signature_token = token.split(".", 1)
    expected_signature = hmac.new(
        settings.auth_secret_key.encode("utf-8"),
        payload_token.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(_b64_encode(expected_signature), signature_token):
        return None
    try:
        payload = json.loads(_b64_decode(payload_token).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return None
    if int(payload.get("exp", 0)) < int(now_shanghai().timestamp()):
        return None
    return payload


def set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        max_age=settings.auth_session_ttl_hours * 3600,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(key=settings.auth_cookie_name, path="/")


def user_table_exists(db: Session) -> bool:
    return inspect(db.bind).has_table(PlatformUser.__tablename__, schema=settings.db_schema)


def get_current_user_from_request(request: Request, db: Session) -> PlatformUser | None:
    if not user_table_exists(db):
        return None
    token = request.cookies.get(settings.auth_cookie_name)
    payload = decode_session_token(token or "")
    if not payload:
        return None
    user_id = payload.get("user_id")
    if not user_id:
        return None
    user = db.get(PlatformUser, int(user_id))
    if not user or not user.enabled:
        return None
    return user


def require_authenticated_user(
    request: Request,
    db: Session = Depends(get_db),
) -> PlatformUser:
    user = get_current_user_from_request(request, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录或登录已失效，请重新登录。",
        )
    return user


def authenticate_user(db: Session, username: str, password: str) -> PlatformUser | None:
    user = db.scalar(
        select(PlatformUser).where(PlatformUser.username == str(username).strip())
    )
    if user is None or not user.enabled:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def mark_user_login(db: Session, user: PlatformUser) -> None:
    user.last_login_at = now_shanghai()
    db.add(user)
    db.commit()
    db.refresh(user)


def serialize_user(user: PlatformUser) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "enabled": user.enabled,
        "is_builtin": user.is_builtin,
        "last_login_at": user.last_login_at,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


def ensure_default_platform_user(db: Session) -> None:
    if not user_table_exists(db):
        return
    existing = db.scalar(select(PlatformUser).where(PlatformUser.username == "admin"))
    if existing is not None:
        return
    user = PlatformUser(
        username="admin",
        display_name="系统管理员",
        password_hash=hash_password("qqq"),
        enabled=True,
        is_builtin=True,
    )
    db.add(user)
    db.commit()
