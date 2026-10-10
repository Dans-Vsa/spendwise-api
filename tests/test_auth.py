from datetime import timedelta

import pytest

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.models import User

PASSWORD = "s3cret-pass"


def register(client, email="alice@example.com", password=PASSWORD, **extra):
    return client.post(
        "/api/v1/auth/register", json={"email": email, "password": password, **extra}
    )


def login(client, email="alice@example.com", password=PASSWORD):
    return client.post("/api/v1/auth/login", data={"username": email, "password": password})


def auth_header(client, **kwargs) -> dict[str, str]:
    token = login(client, **kwargs).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# --- security helpers -------------------------------------------------------


def test_password_hash_roundtrip():
    hashed = hash_password(PASSWORD)
    assert hashed != PASSWORD
    assert verify_password(PASSWORD, hashed)
    assert not verify_password("wrong-pass1", hashed)
    assert not verify_password(PASSWORD, "not-a-bcrypt-hash")


def test_token_roundtrip_and_expiry():
    assert decode_access_token(create_access_token(42)) == "42"
    expired = create_access_token(42, expires_delta=timedelta(seconds=-1))
    assert decode_access_token(expired) is None
    assert decode_access_token("garbage.token.value") is None


# --- registration ------------------------------------------------------------


def test_register_creates_user(client, db):
    response = register(client, email="Alice@Example.com", full_name="Alice", currency="idr")
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "alice@example.com"
    assert body["currency"] == "IDR"
    assert body["is_active"] is True
    assert "password" not in body and "hashed_password" not in body

    user = db.get(User, body["id"])
    assert user.hashed_password != PASSWORD


def test_register_duplicate_email_conflicts(client):
    assert register(client).status_code == 201
    response = register(client, email="ALICE@example.com")
    assert response.status_code == 409


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "not-an-email", "password": PASSWORD},
        {"email": "bob@example.com", "password": "short1"},
        {"email": "bob@example.com", "password": "onlyletters"},
        {"email": "bob@example.com", "password": "12345678"},
        {"email": "bob@example.com", "password": PASSWORD, "currency": "12$"},
    ],
)
def test_register_validation_errors(client, payload):
    assert client.post("/api/v1/auth/register", json=payload).status_code == 422


# --- login ------------------------------------------------------------------


def test_login_returns_bearer_token(client):
    register(client)
    response = login(client, email="ALICE@example.com")
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0
    assert decode_access_token(body["access_token"]).isdigit()


@pytest.mark.parametrize(
    ("email", "password"),
    [("alice@example.com", "wrong-pass1"), ("nobody@example.com", PASSWORD)],
)
def test_login_rejects_bad_credentials(client, email, password):
    register(client)
    response = login(client, email=email, password=password)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_login_rejects_inactive_user(client, db):
    user_id = register(client).json()["id"]
    user = db.get(User, user_id)
    user.is_active = False
    db.commit()
    assert login(client).status_code == 403


# --- /users/me ----------------------------------------------------------------


def test_me_requires_token(client):
    assert client.get("/api/v1/users/me").status_code == 401
    bad = {"Authorization": "Bearer invalid"}
    assert client.get("/api/v1/users/me", headers=bad).status_code == 401


def test_me_returns_current_user(client):
    register(client, full_name="Alice")
    response = client.get("/api/v1/users/me", headers=auth_header(client))
    assert response.status_code == 200
    assert response.json()["email"] == "alice@example.com"
    assert response.json()["full_name"] == "Alice"


def test_me_with_token_for_deleted_user(client, db):
    user_id = register(client).json()["id"]
    headers = auth_header(client)
    db.delete(db.get(User, user_id))
    db.commit()
    assert client.get("/api/v1/users/me", headers=headers).status_code == 401


def test_update_me_profile_and_password(client):
    register(client)
    headers = auth_header(client)
    response = client.patch(
        "/api/v1/users/me",
        headers=headers,
        json={"full_name": "Alice Doe", "currency": "eur", "password": "n3w-password"},
    )
    assert response.status_code == 200
    assert response.json()["full_name"] == "Alice Doe"
    assert response.json()["currency"] == "EUR"

    assert login(client).status_code == 401
    assert login(client, password="n3w-password").status_code == 200
