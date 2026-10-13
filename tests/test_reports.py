from datetime import date

import pytest

from app.core.months import format_month, shift_months

URL = "/api/v1/reports"


def category_id(client, headers, name):
    categories = client.get("/api/v1/categories", headers=headers).json()
    return next(c["id"] for c in categories if c["name"] == name)


def add(client, headers, type, amount, occurred_on, category=None):
    response = client.post(
        "/api/v1/transactions",
        headers=headers,
        json={"type": type, "amount": amount, "occurred_on": occurred_on, "category_id": category},
    )
    assert response.status_code == 201


@pytest.fixture
def october(client, auth_headers):
    """A small but realistic month of data for alice."""
    cat = lambda name: category_id(client, auth_headers, name)  # noqa: E731
    add(client, auth_headers, "income", "3000.00", "2026-10-01", cat("Salary"))
    add(client, auth_headers, "income", "500.00", "2026-10-15", cat("Freelance"))
    add(client, auth_headers, "expense", "0.10", "2026-10-02", cat("Food & Drinks"))
    add(client, auth_headers, "expense", "0.20", "2026-10-03", cat("Food & Drinks"))
    add(client, auth_headers, "expense", "299.70", "2026-10-20", cat("Food & Drinks"))
    add(client, auth_headers, "expense", "150.00", "2026-10-05", cat("Transport"))
    add(client, auth_headers, "expense", "100.00", "2026-10-31")  # uncategorized
    add(client, auth_headers, "expense", "999.00", "2026-09-30", cat("Transport"))
    add(client, auth_headers, "expense", "999.00", "2026-11-01", cat("Transport"))


# --- monthly summary ------------------------------------------------------------------


def test_monthly_summary(client, auth_headers, october):
    response = client.get(f"{URL}/summary", headers=auth_headers, params={"month": "2026-10"})
    assert response.status_code == 200
    body = response.json()
    assert body["month"] == "2026-10"
    assert body["income"] == "3500.00"
    assert body["expense"] == "550.00"  # 0.10 + 0.20 stays exact
    assert body["net"] == "2950.00"
    assert body["savings_rate"] == 84.3
    assert body["transaction_count"] == 7
    assert body["daily_average_expense"] == "17.74"  # 550 / 31 days
    assert body["top_expense_category"]["name"] == "Food & Drinks"
    assert body["top_expense_category"]["total"] == "300.00"


def test_summary_of_empty_month(client, auth_headers):
    body = client.get(f"{URL}/summary", headers=auth_headers, params={"month": "2020-02"}).json()
    assert body["income"] == body["expense"] == body["net"] == "0.00"
    assert body["savings_rate"] is None
    assert body["transaction_count"] == 0
    assert body["top_expense_category"] is None


def test_summary_defaults_to_current_month(client, auth_headers):
    add(client, auth_headers, "income", "10", date.today().isoformat())
    body = client.get(f"{URL}/summary", headers=auth_headers).json()
    assert body["month"] == format_month(date.today())
    assert body["income"] == "10.00"


def test_negative_savings_rate(client, auth_headers):
    add(client, auth_headers, "income", "100", "2026-10-01")
    add(client, auth_headers, "expense", "150", "2026-10-02")
    body = client.get(f"{URL}/summary", headers=auth_headers, params={"month": "2026-10"}).json()
    assert body["net"] == "-50.00"
    assert body["savings_rate"] == -50.0


# --- category breakdown ------------------------------------------------------------------


def test_expense_breakdown(client, auth_headers, october):
    body = client.get(f"{URL}/categories", headers=auth_headers, params={"month": "2026-10"}).json()
    assert body["type"] == "expense"
    assert body["total"] == "550.00"
    rows = [(i["name"], i["total"], i["count"], i["share"]) for i in body["items"]]
    assert rows == [
        ("Food & Drinks", "300.00", 3, 54.5),
        ("Transport", "150.00", 1, 27.3),
        ("Uncategorized", "100.00", 1, 18.2),
    ]
    assert body["items"][2]["category_id"] is None
    assert body["items"][0]["color"].startswith("#")


def test_income_breakdown(client, auth_headers, october):
    body = client.get(
        f"{URL}/categories", headers=auth_headers, params={"month": "2026-10", "type": "income"}
    ).json()
    shares = [(i["name"], i["share"]) for i in body["items"]]
    assert shares == [("Salary", 85.7), ("Freelance", 14.3)]


def test_breakdown_is_per_user(client, auth_headers, make_auth_headers, october):
    bob = make_auth_headers("bob@example.com")
    body = client.get(f"{URL}/categories", headers=bob, params={"month": "2026-10"}).json()
    assert body["total"] == "0.00"
    assert body["items"] == []


# --- trend ----------------------------------------------------------------------------------


def test_trend_zero_fills_missing_months(client, auth_headers, october):
    response = client.get(
        f"{URL}/trend", headers=auth_headers, params={"end": "2026-11", "months": 4}
    )
    assert response.status_code == 200
    body = response.json()
    assert (body["start"], body["end"]) == ("2026-08", "2026-11")
    assert [(i["month"], i["income"], i["expense"], i["net"]) for i in body["items"]] == [
        ("2026-08", "0.00", "0.00", "0.00"),
        ("2026-09", "0.00", "999.00", "-999.00"),
        ("2026-10", "3500.00", "550.00", "2950.00"),
        ("2026-11", "0.00", "999.00", "-999.00"),
    ]
    assert body["totals"] == {"income": "3500.00", "expense": "2548.00", "net": "952.00"}
    assert body["monthly_average"] == {"income": "875.00", "expense": "637.00", "net": "238.00"}


def test_trend_across_year_boundary(client, auth_headers):
    add(client, auth_headers, "expense", "5", "2025-12-31")
    add(client, auth_headers, "expense", "7", "2026-01-01")
    body = client.get(
        f"{URL}/trend", headers=auth_headers, params={"end": "2026-01", "months": 2}
    ).json()
    assert [(i["month"], i["expense"]) for i in body["items"]] == [
        ("2025-12", "5.00"),
        ("2026-01", "7.00"),
    ]


def test_trend_defaults(client, auth_headers):
    body = client.get(f"{URL}/trend", headers=auth_headers).json()
    this_month = date.today().replace(day=1)
    assert len(body["items"]) == 6
    assert body["end"] == format_month(this_month)
    assert body["start"] == format_month(shift_months(this_month, -5))


@pytest.mark.parametrize("params", [{"months": 0}, {"months": 25}, {"end": "2026-13"}])
def test_trend_rejects_bad_params(client, auth_headers, params):
    assert client.get(f"{URL}/trend", headers=auth_headers, params=params).status_code == 422


@pytest.mark.parametrize("path", ["summary", "categories", "trend"])
def test_reports_require_auth(client, path):
    assert client.get(f"{URL}/{path}").status_code == 401
