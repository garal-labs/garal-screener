"""
Tests unitarios para app/auth/security.py — hashing y JWT.
No requieren base de datos: cubren solo las primitivas puras.
"""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import HTTPException

from app.auth.security import (
    JWT_ALGORITHM,
    JWT_SECRET_KEY,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

# ── Password hashing ─────────────────────────────────────────────────────────


class TestPasswordHashing:
    def test_hash_password_produces_a_bcrypt_hash(self):
        hashed = hash_password("supersecret123")
        assert hashed != "supersecret123"
        assert hashed.startswith("$2b$")

    def test_verify_password_accepts_correct_password(self):
        hashed = hash_password("supersecret123")
        assert verify_password("supersecret123", hashed) is True

    def test_verify_password_rejects_wrong_password(self):
        hashed = hash_password("supersecret123")
        assert verify_password("wrong-password", hashed) is False

    def test_hash_password_is_salted(self):
        """Same password hashed twice must produce different hashes (random salt)."""
        assert hash_password("supersecret123") != hash_password("supersecret123")


# ── JWT issue / decode ───────────────────────────────────────────────────────


class TestAccessToken:
    def test_create_and_decode_valid_token(self):
        token = create_access_token(user_id=42)
        assert decode_access_token(token) == 42

    def test_decode_expired_token_raises_401(self):
        now = datetime.now(UTC)
        expired_payload = {
            "sub": "42",
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),
        }
        expired_token = jwt.encode(
            expired_payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM
        )

        with pytest.raises(HTTPException) as exc_info:
            decode_access_token(expired_token)
        assert exc_info.value.status_code == 401

    def test_decode_tampered_token_raises_401(self):
        """Flip a character in the payload segment so the signature no longer matches."""
        token = create_access_token(user_id=42)
        header, payload, signature = token.split(".")
        flip_index = len(payload) // 2
        flipped_char = "A" if payload[flip_index] != "A" else "B"
        tampered_payload = (
            payload[:flip_index] + flipped_char + payload[flip_index + 1 :]
        )
        tampered = f"{header}.{tampered_payload}.{signature}"

        with pytest.raises(HTTPException) as exc_info:
            decode_access_token(tampered)
        assert exc_info.value.status_code == 401

    def test_decode_token_signed_with_wrong_key_raises_401(self):
        payload = {"sub": "42", "exp": datetime.now(UTC) + timedelta(minutes=5)}
        wrong_key_token = jwt.encode(
            payload, "a-completely-different-secret-key", algorithm=JWT_ALGORITHM
        )

        with pytest.raises(HTTPException) as exc_info:
            decode_access_token(wrong_key_token)
        assert exc_info.value.status_code == 401

    def test_decode_token_without_sub_claim_raises_401(self):
        payload = {"exp": datetime.now(UTC) + timedelta(minutes=5)}
        token_without_sub = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

        with pytest.raises(HTTPException) as exc_info:
            decode_access_token(token_without_sub)
        assert exc_info.value.status_code == 401
