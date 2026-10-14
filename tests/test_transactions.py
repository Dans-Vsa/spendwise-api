from datetime import date

import pytest

URL = "/api/v1/transactions"


def category_id(client, headers, name):
    categories = client.get("/api/v1/categories", headers=headers).json()
    return next(c["id"] for c in categories if c["name"] == name)


def create(client, headers, **payload):
    body = {"type": "expense", "amount": "12.50", "occurred_on": "2026-10-12", **payload}
    return client.post(URL, headers=headers, json=body)


# --- create -------------------------------------------------------------------


def test_create_transaction(client, auth_headers):
    food = category_id(client, auth_headers, "Food & Drinks")
    response = create(
        client, auth_headers, category_id=food, description="  Lunch   with team ", note="  "
    )
    assert response.status_code == 201
    body = response.json()
    assert body["amount"] == "12.50"
    assert body["type"] == "expense"
    assert body["category_id"] == food
    assert body["description"] == "Lunch with team"
    assert body["note"] is None
    assert body["occurred_on"] == "2026-10-12"

    fetched = client.get(f"{URL}/{body['id']}", headers=auth_headers)
    assert fetched.status_code == 200
    assert fetched.json() == body


def test_create_defaults_to_today_and_uncategorized(client, auth_headers):
    response = client.post(URL, headers=auth_headers, json={"type": "income", "amount": 100})
    assert response.status_code == 201
    assert response.json()["occurred_on"] == date.today().isoformat()
    assert response.json()["category_id"] is None
    assert response.json()["amount"] == "100.00"


@pytest.mark.parametrize(
    "payload",
    [
        {"amount": "0"},
        {"amount": "-5"},
        {"amount": "1.005"},
        {"amount": "10000000000.00"},
        {"amount": "abc"},
        {"type": "transfer"},
        {"occurred_on": "2026-13-01"},
        {"description": "x" * 201},
    ],
)
def test_create_validation_errors(client, auth_headers, payload):
    assert create(client, auth_headers, **payload).status_code == 422


def test_create_rejects_category_of_wrong_kind(client, auth_headers):
    salary = category_id(client, auth_headers, "Salary")
    response = create(client, auth_headers, type="expense", category_id=salary)
    assert response.status_code == 422
    assert "income" in response.json()["error"]["message"]


def test_create_rejects_missing_or_foreign_category(client, make_auth_headers):
    alice = make_auth_headers("alice@example.com")
    bob = make_auth_headers("bob@example.com")
    bob_food = category_id(client, bob, "Food & Drinks")
    assert create(client, alice, category_id=bob_food).status_code == 422
    assert create(client, alice, category_id=99999).status_code == 422


def test_transactions_require_auth(client):
    assert client.get(URL).status_code == 401
    assert client.post(URL, json={"type": "expense", "amount": "1"}).status_code == 401


# --- ownership ------------------------------------------------------------------


def test_users_cannot_see_or_touch_each_others_transactions(client, make_auth_headers):
    alice = make_auth_headers("alice@example.com")
    bob = make_auth_headers("bob@example.com")
    tx_id = create(client, alice).json()["id"]

    assert client.get(f"{URL}/{tx_id}", headers=bob).status_code == 404
    assert client.patch(f"{URL}/{tx_id}", headers=bob, json={"amount": "1"}).status_code == 404
    assert client.delete(f"{URL}/{tx_id}", headers=bob).status_code == 404
    assert client.get(URL, headers=bob).json()["total"] == 0
    assert client.get(URL, headers=alice).json()["total"] == 1


# --- update -------------------------------------------------------------------


def test_update_transaction(client, auth_headers):
    tx_id = create(client, auth_headers, note="old").json()["id"]
    response = client.patch(
        f"{URL}/{tx_id}",
        headers=auth_headers,
        json={"amount": "99.99", "description": "Dinner", "occurred_on": "2026-10-01"},
    )
    assert response.status_code == 200
    body = response.json()
    assert (body["amount"], body["description"], body["occurred_on"]) == (
        "99.99", "Dinner", "2026-10-01",
    )
    assert body["note"] == "old"

    # null clears optional fields and is ignored for required ones.
    response = client.patch(f"{URL}/{tx_id}", headers=auth_headers, json={"note": None, "amount": None})
    assert response.json()["note"] is None
    assert response.json()["amount"] == "99.99"


def test_update_category_and_type_stay_consistent(client, auth_headers):
    food = category_id(client, auth_headers, "Food & Drinks")
    salary = category_id(client, auth_headers, "Salary")
    tx_id = create(client, auth_headers, category_id=food).json()["id"]

    # Switching to income while still in an expense category is rejected...
    assert client.patch(f"{URL}/{tx_id}", headers=auth_headers, json={"type": "income"}).status_code == 422
    # ...but changing both together works.
    response = client.patch(
        f"{URL}/{tx_id}", headers=auth_headers, json={"type": "income", "category_id": salary}
    )
    assert response.status_code == 200
    assert response.json()["type"] == "income"

    # Uncategorize with an explicit null.
    response = client.patch(f"{URL}/{tx_id}", headers=auth_headers, json={"category_id": None})
    assert response.json()["category_id"] is None


def test_update_validation_error(client, auth_headers):
    tx_id = create(client, auth_headers).json()["id"]
    assert client.patch(f"{URL}/{tx_id}", headers=auth_headers, json={"amount": "-1"}).status_code == 422


# --- delete -------------------------------------------------------------------


def test_delete_transaction(client, auth_headers):
    tx_id = create(client, auth_headers).json()["id"]
    assert client.delete(f"{URL}/{tx_id}", headers=auth_headers).status_code == 204
    assert client.get(f"{URL}/{tx_id}", headers=auth_headers).status_code == 404
    assert client.delete(f"{URL}/{tx_id}", headers=auth_headers).status_code == 404
