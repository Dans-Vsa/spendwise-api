from datetime import date

import pytest

from app.core.months import format_month

URL = "/api/v1/budgets"


def category_id(client, headers, name):
    categories = client.get("/api/v1/categories", headers=headers).json()
    return next(c["id"] for c in categories if c["name"] == name)


def spend(client, headers, amount, category, occurred_on="2026-10-12", type="expense"):
    response = client.post(
        "/api/v1/transactions",
        headers=headers,
        json={"type": type, "amount": amount, "occurred_on": occurred_on, "category_id": category},
    )
    assert response.status_code == 201


def create(client, headers, category, amount="100.00", month="2026-10"):
    return client.post(
        URL, headers=headers, json={"category_id": category, "month": month, "amount": amount}
    )


@pytest.fixture
def food(client, auth_headers):
    return category_id(client, auth_headers, "Food & Drinks")


# --- create -------------------------------------------------------------------


def test_create_budget_reports_progress(client, auth_headers, food):
    spend(client, auth_headers, "30.00", food)
    response = create(client, auth_headers, food, amount="200")
    assert response.status_code == 201
    body = response.json()
    assert body["month"] == "2026-10"
    assert body["amount"] == "200.00"
    assert body["category_name"] == "Food & Drinks"
    assert body["spent"] == "30.00"
    assert body["remaining"] == "170.00"
    assert body["percent_used"] == 15.0
    assert body["status"] == "ok"


def test_month_defaults_to_current(client, auth_headers, food):
    response = client.post(URL, headers=auth_headers, json={"category_id": food, "amount": "50"})
    assert response.status_code == 201
    assert response.json()["month"] == format_month(date.today())


@pytest.mark.parametrize(
    "payload",
    [
        {"amount": "0"},
        {"amount": "-10"},
        {"amount": "1.234"},
        {"month": "2026-13"},
        {"month": "2026-10-01"},
        {"month": "October"},
    ],
)
def test_create_rejects_invalid_values(client, auth_headers, food, payload):
    body = {"category_id": food, "month": "2026-10", "amount": "100", **payload}
    assert client.post(URL, headers=auth_headers, json=body).status_code == 422


def test_budget_needs_an_expense_category(client, auth_headers):
    salary = category_id(client, auth_headers, "Salary")
    response = create(client, auth_headers, salary)
    assert response.status_code == 422
    assert "expense category" in response.json()["error"]["message"]


def test_cannot_budget_other_users_category(client, auth_headers, make_auth_headers, food):
    bob = make_auth_headers("bob@example.com")
    assert create(client, bob, food).status_code == 422
    assert create(client, auth_headers, 9999).status_code == 422


def test_one_budget_per_category_and_month(client, auth_headers, food):
    assert create(client, auth_headers, food).status_code == 201
    duplicate = create(client, auth_headers, food, amount="300")
    assert duplicate.status_code == 409
    assert "2026-10" in duplicate.json()["error"]["message"]
    assert create(client, auth_headers, food, month="2026-11").status_code == 201


# --- progress / status ------------------------------------------------------------


@pytest.mark.parametrize(
    ("spent", "status", "percent_used", "remaining"),
    [
        ("79.99", "ok", 80.0, "20.01"),
        ("80.00", "warning", 80.0, "20.00"),
        ("100.00", "warning", 100.0, "0.00"),
        ("100.01", "over", 100.0, "-0.01"),
        ("150.00", "over", 150.0, "-50.00"),
    ],
)
def test_status_thresholds(client, auth_headers, food, spent, status, percent_used, remaining):
    spend(client, auth_headers, spent, food)
    body = create(client, auth_headers, food, amount="100").json()
    assert body["status"] == status
    assert body["percent_used"] == percent_used
    assert body["remaining"] == remaining


def test_only_matching_expenses_count(client, auth_headers, food):
    transport = category_id(client, auth_headers, "Transport")
    spend(client, auth_headers, "10.00", food, occurred_on="2026-10-01")
    spend(client, auth_headers, "15.00", food, occurred_on="2026-10-31")
    spend(client, auth_headers, "99.00", food, occurred_on="2026-09-30")  # previous month
    spend(client, auth_headers, "99.00", food, occurred_on="2026-11-01")  # next month
    spend(client, auth_headers, "99.00", transport)  # other category
    spend(client, auth_headers, "99.00", None)  # uncategorized
    body = create(client, auth_headers, food).json()
    assert body["spent"] == "25.00"


def test_other_users_spending_is_ignored(client, auth_headers, make_auth_headers, food):
    bob = make_auth_headers("bob@example.com")
    spend(client, bob, "500.00", category_id(client, bob, "Food & Drinks"))
    assert create(client, auth_headers, food).json()["spent"] == "0.00"


# --- list / overview ------------------------------------------------------------------


def test_month_overview(client, auth_headers, food):
    transport = category_id(client, auth_headers, "Transport")
    shopping = category_id(client, auth_headers, "Shopping")
    spend(client, auth_headers, "120.00", food)
    spend(client, auth_headers, "40.00", transport)
    create(client, auth_headers, food, amount="100")
    create(client, auth_headers, transport, amount="50")
    create(client, auth_headers, shopping, amount="80", month="2026-11")

    body = client.get(URL, headers=auth_headers, params={"month": "2026-10"}).json()
    assert body["month"] == "2026-10"
    assert [item["category_name"] for item in body["items"]] == ["Food & Drinks", "Transport"]
    assert [item["status"] for item in body["items"]] == ["over", "warning"]
    assert body["total_budgeted"] == "150.00"
    assert body["total_spent"] == "160.00"
    assert body["total_remaining"] == "-10.00"
    assert body["over_budget"] == 1


def test_overview_for_empty_month(client, auth_headers):
    body = client.get(URL, headers=auth_headers, params={"month": "2020-01"}).json()
    assert body == {
        "month": "2020-01",
        "total_budgeted": "0.00",
        "total_spent": "0.00",
        "total_remaining": "0.00",
        "over_budget": 0,
        "items": [],
    }


def test_overview_rejects_bad_month(client, auth_headers):
    assert client.get(URL, headers=auth_headers, params={"month": "2026-1"}).status_code == 422


def test_overview_only_shows_own_budgets(client, auth_headers, make_auth_headers, food):
    create(client, auth_headers, food)
    bob = make_auth_headers("bob@example.com")
    assert client.get(URL, headers=bob, params={"month": "2026-10"}).json()["items"] == []


# --- read / update / delete -----------------------------------------------------------


def test_read_update_delete(client, auth_headers, food):
    spend(client, auth_headers, "90.00", food)
    budget_id = create(client, auth_headers, food, amount="100").json()["id"]

    assert client.get(f"{URL}/{budget_id}", headers=auth_headers).json()["status"] == "warning"

    updated = client.patch(f"{URL}/{budget_id}", headers=auth_headers, json={"amount": "250"})
    assert updated.status_code == 200
    assert updated.json()["amount"] == "250.00"
    assert updated.json()["status"] == "ok"

    assert client.patch(f"{URL}/{budget_id}", headers=auth_headers, json={}).status_code == 422
    assert client.delete(f"{URL}/{budget_id}", headers=auth_headers).status_code == 204
    assert client.get(f"{URL}/{budget_id}", headers=auth_headers).status_code == 404


def test_other_users_budget_is_not_found(client, auth_headers, make_auth_headers, food):
    budget_id = create(client, auth_headers, food).json()["id"]
    bob = make_auth_headers("bob@example.com")
    assert client.get(f"{URL}/{budget_id}", headers=bob).status_code == 404
    assert client.patch(f"{URL}/{budget_id}", headers=bob, json={"amount": "1"}).status_code == 404
    assert client.delete(f"{URL}/{budget_id}", headers=bob).status_code == 404


def test_deleting_category_deletes_its_budgets(client, auth_headers, food):
    budget_id = create(client, auth_headers, food).json()["id"]
    assert client.delete(f"/api/v1/categories/{food}", headers=auth_headers).status_code == 204
    assert client.get(f"{URL}/{budget_id}", headers=auth_headers).status_code == 404


def test_budgets_require_auth(client):
    assert client.get(URL).status_code == 401


# --- copy -------------------------------------------------------------------------------


def test_copy_budgets_to_next_month(client, auth_headers, food):
    transport = category_id(client, auth_headers, "Transport")
    create(client, auth_headers, food, amount="300")
    create(client, auth_headers, transport, amount="80")
    create(client, auth_headers, transport, amount="120", month="2026-11")  # already set

    response = client.post(
        f"{URL}/copy", headers=auth_headers, json={"source": "2026-10", "target": "2026-11"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["skipped"] == 1
    assert [(b["category_id"], b["month"], b["amount"]) for b in body["created"]] == [
        (food, "2026-11", "300.00")
    ]

    november = client.get(URL, headers=auth_headers, params={"month": "2026-11"}).json()
    amounts = {item["category_name"]: item["amount"] for item in november["items"]}
    assert amounts == {"Food & Drinks": "300.00", "Transport": "120.00"}


def test_copy_requires_different_months(client, auth_headers):
    response = client.post(
        f"{URL}/copy", headers=auth_headers, json={"source": "2026-10", "target": "2026-10"}
    )
    assert response.status_code == 422
