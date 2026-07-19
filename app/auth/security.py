"""Password hashing, JWT issuance/verification, and auth dependencies.

Import boundary: this module is the only place that reads/writes JWTs and
password hashes. `app/auth/router.py` (Phase 2) and every cartera-scoped
router import `get_current_user` / `get_owned_cartera` from here — that
import direction is why this lives in `app/auth/` instead of
`app/routers/auth.py` (see design.md "Auth module boundary").
"""

import os
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Cookie, Depends, HTTPException, status
from passlib.context import CryptContext
from passlib.exc import UnknownHashError
from sqlalchemy.orm import Session

from app import models
from app.database import get_db

_env = os.getenv("ENV", "local")
_jwt_secret = os.getenv("JWT_SECRET_KEY")
if _jwt_secret:
    JWT_SECRET_KEY = _jwt_secret
elif _env == "local":
    JWT_SECRET_KEY = "dev-insecure-secret-change-me-in-production-please"  # noqa: S105
else:
    raise RuntimeError("JWT_SECRET_KEY must be set outside local development")

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_COOKIE_NAME = "access_token"  # noqa: S105 — cookie name, not a credential
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


def hash_password(password: str) -> str:
    """Hash a plaintext password for storage."""
    return str(_pwd_context.hash(password))


def verify_password(password: str, hashed: str) -> bool:
    """Check a plaintext password against a stored bcrypt hash."""
    try:
        return bool(_pwd_context.verify(password, hashed))
    except (ValueError, UnknownHashError):
        return False


def create_access_token(
    user_id: int, expires_minutes: int = ACCESS_TOKEN_EXPIRE_MINUTES
) -> str:
    """Issue a signed JWT carrying the user id (`sub`) and an expiry claim."""
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=expires_minutes),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> int:
    """Decode and validate a JWT, returning the user id.

    Raises `HTTPException(401)` on any invalid, tampered, or expired token —
    callers never need to distinguish the failure reason.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise _unauthorized("Invalid or expired session") from exc
    try:
        return int(payload["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise _unauthorized("Invalid or expired session") from exc


def get_current_user(
    access_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> models.User:
    """Resolve the authenticated user from the `access_token` session cookie."""
    if access_token is None:
        raise _unauthorized("Not authenticated")
    user_id = decode_access_token(access_token)
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise _unauthorized("Not authenticated")
    return user


def get_owned_cartera(
    cartera_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> models.Cartera:
    """Resolve a cartera owned by `current_user`.

    Returns 404 — never 403 — when the cartera is missing or owned by
    someone else, so a foreign cartera's existence is never confirmed.
    """
    cartera = (
        db.query(models.Cartera)
        .filter(
            models.Cartera.id == cartera_id, models.Cartera.user_id == current_user.id
        )
        .first()
    )
    if cartera is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Cartera no encontrada"
        )
    return cartera
