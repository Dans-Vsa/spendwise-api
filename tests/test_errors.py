import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from app.core.errors import error_code
from app.main import create_app


def assert_error(response, status_code: int, code: str) -> dict:
    assert response.status_code == status_code
    body = response.json()
    assert set(body) == {"error"}
    error = body["error"]
    assert error["status"] == status_code
    assert error["code"] == code
    assert isinstance(error["message"], str) and error["message"]
    return error


def test_not_found_uses_error_schema(client, auth_headers):
    response = client.get("/api/v1/transactions/999", headers=auth_headers)
    error = assert_error(response, 404, "not_found")
    assert error["message"] == "Transaction not found"
    assert error["fields"] == []


def test_unknown_route_uses_error_schema(client):
    assert_error(client.get("/api/v1/nope"), 404, "not_found")


def test_unauthorized_keeps_www_authenticate_header(client):
    response = client.get("/api/v1/users/me")
    assert_error(response, 401, "unauthorized")
    assert response.headers["www-authenticate"] == "Bearer"


def test_conflict(client):
    payload = {"email": "dup@example.com", "password": "s3cret-pass"}
    client.post("/api/v1/auth/register", json=payload)
    error = assert_error(client.post("/api/v1/auth/register", json=payload), 409, "conflict")
    assert "already registered" in error["message"]


def test_method_not_allowed(client):
    assert_error(client.put("/api/v1/health"), 405, "method_not_allowed")


def test_validation_errors_list_each_field(client, auth_headers):
    response = client.post(
        "/api/v1/transactions",
        headers=auth_headers,
        json={"type": "transfer", "amount": "-1"},
    )
    error = assert_error(response, 422, "validation_error")
    assert error["message"] == "Request validation failed"
    locations = {field["location"] for field in error["fields"]}
    assert locations == {"body.type", "body.amount"}
    assert all(field["message"] for field in error["fields"])


def test_query_validation_errors(client, auth_headers):
    response = client.get("/api/v1/transactions?limit=0", headers=auth_headers)
    error = assert_error(response, 422, "validation_error")
    assert error["fields"][0]["location"] == "query.limit"


def test_unhandled_exceptions_become_500():
    app = create_app()
    router = APIRouter()

    @router.get("/boom")
    def boom() -> None:
        raise RuntimeError("secret internals")

    app.include_router(router)
    with TestClient(app, raise_server_exceptions=False) as test_client:
        response = test_client.get("/boom")
    error = assert_error(response, 500, "internal_error")
    assert "secret" not in error["message"]


@pytest.mark.parametrize(
    ("status_code", "code"),
    [(404, "not_found"), (429, "too_many_requests"), (418, "i'm_a_teapot"), (599, "error")],
)
def test_error_code(status_code, code):
    assert error_code(status_code) == code


def test_openapi_documents_error_schema(client):
    schema = client.get("/openapi.json").json()
    assert "ErrorResponse" in schema["components"]["schemas"]
