from datetime import date
from decimal import Decimal

import pytest

from app.models import Transaction, TransactionType
from app.services.categories import DEFAULT_CATEGORIES

URL = "/api/v1/categories"


def create(client, headers, **payload):
    body = {"name": "Coffee", "kind": "expense", **payload}
    return client.post(URL, headers=headers, json=body)


# --- default categories -------------------------------------------------------


def test_new_user_gets_default_categories(client, auth_headers):
    response = client.get(URL, headers=auth_headers)
    assert response.status_code == 200
    names = {c["name"] for c in response.json()}
    assert names == {name for name, *_ in DEFAULT_CATEGORIES}


def test_list_filters_by_kind(client, auth_headers):
    income = client.get(URL, headers=auth_headers, params={"kind": "income"}).json()
    expected = sum(1 for _, kind, *_ in DEFAULT_CATEGORIES if kind is TransactionType.INCOME)
    assert len(income) == expected
    assert all(c["kind"] == "income" for c in income)
    assert client.get(URL, headers=auth_headers, params={"kind": "bogus"}).status_code == 422


def test_categories_require_auth(client):
    assert client.get(URL).status_code == 401
    assert client.post(URL, json={"name": "X", "kind": "expense"}).status_code == 401


# --- create -------------------------------------------------------------------


def test_create_category(client, auth_headers):
    response = create(client, auth_headers, name="  Coffee   Shops ", color="#A1B2C3", icon="cup")
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Coffee Shops"
    assert body["color"] == "#a1b2c3"
    assert body["kind"] == "expense"

    fetched = client.get(f"{URL}/{body['id']}", headers=auth_headers)
    assert fetched.status_code == 200
    assert fetched.json() == body


def test_create_duplicate_name_is_case_insensitive(client, auth_headers):
    assert create(client, auth_headers, name="salary", kind="income").status_code == 409
    # Same name is fine for the other kind.
    assert create(client, auth_headers, name="Salary", kind="expense").status_code == 201


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "   "},
        {"name": "x" * 61},
        {"kind": "transfer"},
        {"color": "red"},
        {"color": "#12345"},
    ],
)
def test_create_validation_errors(client, auth_headers, payload):
    assert create(client, auth_headers, **payload).status_code == 422


# --- ownership ------------------------------------------------------------------


def test_users_cannot_see_or_touch_each_others_categories(client, make_auth_headers):
    alice = make_auth_headers("alice@example.com")
    bob = make_auth_headers("bob@example.com")
    alice_cat = create(client, alice, name="Alice only").json()["id"]

    assert client.get(f"{URL}/{alice_cat}", headers=bob).status_code == 404
    assert client.patch(f"{URL}/{alice_cat}", headers=bob, json={"name": "x"}).status_code == 404
    assert client.delete(f"{URL}/{alice_cat}", headers=bob).status_code == 404
    assert "Alice only" not in {c["name"] for c in client.get(URL, headers=bob).json()}


def test_get_missing_category(client, auth_headers):
    assert client.get(f"{URL}/99999", headers=auth_headers).status_code == 404


# --- update -------------------------------------------------------------------


def test_update_category(client, auth_headers):
    cat_id = create(client, auth_headers).json()["id"]
    response = client.patch(
        f"{URL}/{cat_id}", headers=auth_headers, json={"name": "Cafes", "color": "#00FF00"}
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Cafes"
    assert response.json()["color"] == "#00ff00"

    # Clearing an optional field with null works; null for a required field is ignored.
    response = client.patch(f"{URL}/{cat_id}", headers=auth_headers, json={"color": None, "name": None})
    assert response.json()["color"] is None
    assert response.json()["name"] == "Cafes"


def test_update_rename_to_existing_conflicts(client, auth_headers):
    cat_id = create(client, auth_headers).json()["id"]
    response = client.patch(f"{URL}/{cat_id}", headers=auth_headers, json={"name": "groceries"})
    assert response.status_code == 409
    # Renaming to its own name (different case) is allowed.
    response = client.patch(f"{URL}/{cat_id}", headers=auth_headers, json={"name": "COFFEE"})
    assert response.status_code == 200


def test_cannot_change_kind_when_category_has_transactions(client, db, auth_headers):
    cat = create(client, auth_headers).json()
    me = client.get("/api/v1/users/me", headers=auth_headers).json()
    db.add(
        Transaction(
            user_id=me["id"], category_id=cat["id"], type=TransactionType.EXPENSE,
            amount=Decimal("4.50"), occurred_on=date(2026, 10, 11),
        )
    )
    db.commit()

    response = client.patch(f"{URL}/{cat['id']}", headers=auth_headers, json={"kind": "income"})
    assert response.status_code == 409


def test_change_kind_of_unused_category(client, auth_headers):
    cat_id = create(client, auth_headers, name="Refunds").json()["id"]
    response = client.patch(f"{URL}/{cat_id}", headers=auth_headers, json={"kind": "income"})
    assert response.status_code == 200
    assert response.json()["kind"] == "income"


# --- delete -------------------------------------------------------------------


def test_delete_category_keeps_transactions(client, db, auth_headers):
    cat = create(client, auth_headers).json()
    me = client.get("/api/v1/users/me", headers=auth_headers).json()
    tx = Transaction(
        user_id=me["id"], category_id=cat["id"], type=TransactionType.EXPENSE,
        amount=Decimal("3.00"), occurred_on=date(2026, 10, 11),
    )
    db.add(tx)
    db.commit()

    assert client.delete(f"{URL}/{cat['id']}", headers=auth_headers).status_code == 204
    assert client.get(f"{URL}/{cat['id']}", headers=auth_headers).status_code == 404
    db.refresh(tx)
    assert tx.category_id is None
