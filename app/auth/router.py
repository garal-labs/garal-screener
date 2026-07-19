"""Auth endpoints: register, login, logout, me.

Session state lives only in the `access_token` httpOnly cookie (see
`app/auth/security.py` for the JWT and cookie-lifetime contract). This
router owns cookie issuance/clearing and delegates all crypto to
`security.py` — it never touches JWT secrets or password hashes directly.
"""

import os

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth.security import (
    ACCESS_TOKEN_COOKIE_NAME,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.database import get_db

router = APIRouter(prefix="/auth", tags=["Auth"])


def _cookie_secure() -> bool:
    """Cookies are Secure everywhere except local dev over plain http.

    Reuses the same `ENV` convention as the JWT secret fail-fast check in
    `app/auth/security.py`: only `ENV=local` gets the relaxed setting.
    """
    return os.getenv("ENV", "local") != "local"


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
    existing = db.query(models.User).filter(models.User.email == data.email).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered"
        )
    user = models.User(
        email=data.email,
        hashed_password=hash_password(data.password),
        nombre=data.nombre,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=schemas.UserOut)
def login(
    data: schemas.LoginRequest, response: Response, db: Session = Depends(get_db)
):
    """Verify credentials and start a session via the `access_token` cookie."""
    user = db.query(models.User).filter(models.User.email == data.email).first()
    if user is None or not verify_password(data.password, user.hashed_password):
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
