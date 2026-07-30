"""Auth endpoints: register, login, logout, me, forgot/reset password.

Session state lives only in the `access_token` httpOnly cookie (see
`app/auth/security.py` for the JWT and cookie-lifetime contract). This
router owns cookie issuance/clearing and delegates all crypto to
`security.py` — it never touches JWT secrets or password hashes directly.
"""

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth.security import (
    ACCESS_TOKEN_COOKIE_NAME,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    DUMMY_PASSWORD_HASH,
    IS_LOCAL_ENV,
    create_access_token,
    generate_reset_token,
    get_current_user,
    hash_password,
    hash_reset_token,
    verify_password,
)
from app.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])

RESET_TOKEN_TTL_MINUTES = 60
DEFAULT_CARTERA_NOMBRE = "Mi Cartera Principal"


def _cookie_secure() -> bool:
    """Cookies are Secure everywhere except local dev over plain http.

    Reuses the same `ENV` convention as the JWT secret fail-fast check in
    `app/auth/security.py`: only `ENV=local` gets the relaxed setting.
    """
    return not IS_LOCAL_ENV


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=_cookie_secure(),
        samesite="lax",
        path="/",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=ACCESS_TOKEN_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=_cookie_secure(),
        samesite="lax",
    )


@router.post(
    "/register", response_model=schemas.UserOut, status_code=status.HTTP_201_CREATED
)
def register(data: schemas.UserCreate, db: Session = Depends(get_db)):
    """Create a new user account. Does not start a session — call `/auth/login` next."""
    normalized_email = data.email.lower()
    existing = (
        db.query(models.User).filter(models.User.email == normalized_email).first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered"
        )
    user = models.User(
        email=normalized_email,
        hashed_password=hash_password(data.password),
        nombre=data.nombre,
    )
    db.add(user)
    # `owner=user` (not `user_id=user.id`) so SQLAlchemy resolves the FK at
    # flush time — `user.id` doesn't exist yet since `user` is still pending.
    # Added to the same session/commit as `user` so account + starter
    # cartera land atomically: a rollback on duplicate email leaves neither.
    cartera = models.Cartera(nombre=DEFAULT_CARTERA_NOMBRE, owner=user)
    db.add(cartera)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered"
        ) from exc
    db.refresh(user)
    return user


@router.post("/login", response_model=schemas.UserOut)
def login(
    data: schemas.LoginRequest, response: Response, db: Session = Depends(get_db)
):
    """Verify credentials and start a session via the `access_token` cookie."""
    normalized_email = data.email.lower()
    user = db.query(models.User).filter(models.User.email == normalized_email).first()
    password_hash = user.hashed_password if user is not None else DUMMY_PASSWORD_HASH
    password_ok = verify_password(data.password, password_hash)
    if user is None or not password_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    token = create_access_token(user.id)
    _set_session_cookie(response, token)
    return user


@router.post("/logout")
def logout(response: Response):
    """Clear the session cookie. Safe to call without an active session."""
    _clear_session_cookie(response)
    return {"ok": True}


@router.get("/me", response_model=schemas.UserOut)
def me(current_user: models.User = Depends(get_current_user)):
    """Return the identity of the currently authenticated user."""
    return current_user


@router.post("/forgot-password")
def forgot_password(data: schemas.ForgotPasswordRequest, db: Session = Depends(get_db)):
    """Issue a password reset token if the email is registered.

    Always returns the same generic response regardless of whether the
    email exists, so account existence is never leaked. There is no email
    provider wired up in dev/CI (real SMTP/provider integration is out of
    scope per proposal.md) — the reset link is logged to the console
    instead as a dev-only stub.
    """
    user = db.query(models.User).filter(models.User.email == data.email).first()
    if user is not None:
        raw_token, token_hash = generate_reset_token()
        reset_token = models.PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=datetime.now(UTC) + timedelta(minutes=RESET_TOKEN_TTL_MINUTES),
        )
        db.add(reset_token)
        db.commit()
        if IS_LOCAL_ENV:
            logger.warning(
                "Password reset requested for user_id=%s — dev reset link: "
                "/reset-password?token=%s",
                user.id,
                raw_token,
            )
    return {"ok": True}


@router.post("/reset-password")
def reset_password(data: schemas.ResetPasswordRequest, db: Session = Depends(get_db)):
    """Consume a reset token and set a new password.

    The consume step is a single conditional `UPDATE` guarded by
    `rowcount == 1` so token lookup, expiry, and single-use enforcement
    happen atomically — a foreign/expired/already-used token always gets
    the same generic error, with no reason leakage.
    """
    invalid_token_error = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid, expired, or already-used token",
    )

    token_hash = hash_reset_token(data.token)
    now = datetime.now(UTC)
    result = db.execute(
        text(
            "UPDATE password_reset_tokens "
            "SET used_at = :now "
            "WHERE token_hash = :hash AND used_at IS NULL AND expires_at > :now"
        ),
        {"now": now, "hash": token_hash},
    )
    if result.rowcount != 1:  # type: ignore[attr-defined]
        db.rollback()
        raise invalid_token_error

    reset_token = (
        db.query(models.PasswordResetToken)
        .filter(models.PasswordResetToken.token_hash == token_hash)
        .first()
    )
    if reset_token is None:
        # Unreachable given rowcount == 1 above; guards mypy narrowing and
        # any theoretical race between the UPDATE and this SELECT.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error processing reset token",
        )

    user = db.query(models.User).filter(models.User.id == reset_token.user_id).first()
    if user is None:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Reset token references a missing user",
        )

    user.hashed_password = hash_password(data.new_password)
    db.commit()
    return {"ok": True}
