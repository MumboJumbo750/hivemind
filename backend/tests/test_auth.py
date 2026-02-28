"""Integration-Tests für Auth-Endpoints (TASK-2-002).

Nutzt httpx.AsyncClient mit dem FastAPI-TestClient-Pattern.
Benötigt eine laufende DB — werden in CI gegen eine Test-DB ausgeführt.
Hier: Unit-Tests die Token-Logik direkt testen ohne HTTP-Stack.
"""
from datetime import datetime, timedelta, timezone

import pytest
from jose import JWTError, jwt

from app.config import settings
from app.services.auth_service import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_hash_and_verify() -> None:
    hashed = hash_password("geheim123")
    assert verify_password("geheim123", hashed) is True
    assert verify_password("falsch", hashed) is False


def test_create_access_token_contains_claims() -> None:
    token = create_access_token("user-123", "developer")
    payload = decode_token(token)
    assert payload["sub"] == "user-123"
    assert payload["role"] == "developer"
    assert "exp" in payload


def test_create_refresh_token_has_type() -> None:
    token = create_refresh_token("user-123")
    payload = decode_token(token)
    assert payload["sub"] == "user-123"
    assert payload["type"] == "refresh"


def test_expired_token_raises() -> None:
    expired = datetime.now(timezone.utc) - timedelta(seconds=1)
    token = jwt.encode(
        {"sub": "x", "role": "developer", "exp": expired},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(JWTError):
        decode_token(token)
