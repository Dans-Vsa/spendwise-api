import pytest

URL = "/api/v1/transactions"


@pytest.fixture
def ledger(client, auth_headers):
    """Seed a small, varied ledger and return {description: id}."""
    categories = {c["name"]: c["id"] for c in client.get("/api/v1/categories", headers=auth_headers).json()}
    rows = [
        ("income", "3000.00", "2026-09-25", "Salary", "September salary", None),
        ("expense", "45.20", "2026-09-28", "Groceries", "Weekly groceries", "supermarket"),
        ("expense", "12.00", "2026-10-01", "Food & Drinks", "Coffee & cake", None),
        ("expense", "800.00", "2026-10-01", "Housing", "October rent", "paid by transfer"),
        ("expense", "60.75", "2026-10-05", "Groceries", "Groceries 100%_fresh", None),
        ("income", "250.00", "2026-10-07", "Freelance", "Logo design gig", None),
        ("expense", "9.99", "2026-10-10", None, "Streaming subscription", None),
    ]
    ids = {}
    for tx_type, amount, day, category, description, note in rows:
        response = client.post(
            URL,
            headers=auth_headers,
            json={
                "type": tx_type,
                "amount": amount,
                "occurred_on": day,
                "category_id": categories.get(category),
                "description": description,
                "note": note,
            },
        )
        assert response.status_code == 201
        ids[description] = response.json()["id"]
    return ids


def descriptions(client, headers, **params):
    response = client.get(URL, headers=headers, params=params)
    assert response.status_code == 200, response.text
    return [t["description"] for t in response.json()["items"]]


def test_default_list_is_newest_first(client, auth_headers, ledger):
    response = client.get(URL, headers=auth_headers)
    body = response.json()
    assert body["total"] == 7
    assert (body["limit"], body["offset"]) == (20, 0)
    dates = [t["occurred_on"] for t in body["items"]]
    assert dates == sorted(dates, reverse=True)


def test_filter_by_type(client, auth_headers, ledger):
    assert set(descriptions(client, auth_headers, type="income")) == {
        "September salary", "Logo design gig",
    }


def test_filter_by_category_and_uncategorized(client, auth_headers, ledger):
    groceries = next(
        c["id"] for c in client.get("/api/v1/categories", headers=auth_headers).json()
        if c["name"] == "Groceries"
    )
    assert set(descriptions(client, auth_headers, category_id=groceries)) == {
        "Weekly groceries", "Groceries 100%_fresh",
    }
    assert descriptions(client, auth_headers, uncategorized=True) == ["Streaming subscription"]


def test_filter_by_inclusive_date_range(client, auth_headers, ledger):
    found = descriptions(client, auth_headers, date_from="2026-10-01", date_to="2026-10-05")
    assert set(found) == {"Coffee & cake", "October rent", "Groceries 100%_fresh"}


def test_filter_by_amount_range(client, auth_headers, ledger):
    found = descriptions(client, auth_headers, min_amount="10", max_amount="100")
    assert set(found) == {"Weekly groceries", "Coffee & cake", "Groceries 100%_fresh"}


def test_search_is_case_insensitive_and_covers_notes(client, auth_headers, ledger):
    assert set(descriptions(client, auth_headers, q="GROCERIES")) == {
        "Weekly groceries", "Groceries 100%_fresh",
    }
    assert descriptions(client, auth_headers, q="transfer") == ["October rent"]


def test_search_treats_wildcards_literally(client, auth_headers, ledger):
    assert descriptions(client, auth_headers, q="100%_") == ["Groceries 100%_fresh"]
    assert descriptions(client, auth_headers, q="%") == ["Groceries 100%_fresh"]


def test_filters_combine(client, auth_headers, ledger):
    found = descriptions(client, auth_headers, type="expense", date_from="2026-10-01", q="o")
    assert set(found) == {"Coffee & cake", "October rent", "Groceries 100%_fresh", "Streaming subscription"}


@pytest.mark.parametrize(
    ("sort", "expected_first"),
    [
        ("-occurred_on", "Streaming subscription"),
        ("occurred_on", "September salary"),
        ("-amount", "September salary"),
        ("amount", "Streaming subscription"),
        ("-created_at", "Streaming subscription"),
        ("created_at", "September salary"),
    ],
)
def test_sorting(client, auth_headers, ledger, sort, expected_first):
    assert descriptions(client, auth_headers, sort=sort)[0] == expected_first


def test_same_day_ties_are_stable(client, auth_headers, ledger):
    # Two transactions on 2026-10-01: newest-first breaks the tie by id, descending.
    found = descriptions(client, auth_headers, date_from="2026-10-01", date_to="2026-10-01")
    assert found == ["October rent", "Coffee & cake"]


def test_pagination(client, auth_headers, ledger):
    everything = descriptions(client, auth_headers, sort="amount")
    first = client.get(URL, headers=auth_headers, params={"sort": "amount", "limit": 3}).json()
    second = client.get(
        URL, headers=auth_headers, params={"sort": "amount", "limit": 3, "offset": 3}
    ).json()
    last = client.get(
        URL, headers=auth_headers, params={"sort": "amount", "limit": 3, "offset": 6}
    ).json()

    assert first["total"] == second["total"] == last["total"] == 7
    paged = [t["description"] for page in (first, second, last) for t in page["items"]]
    assert paged == everything
    assert len(last["items"]) == 1


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
        {"sort": "description"},
        {"type": "transfer"},
        {"date_from": "2026-10-05", "date_to": "2026-10-01"},
        {"min_amount": "50", "max_amount": "10"},
        {"min_amount": "-1"},
        {"category_id": 1, "uncategorized": True},
        {"unknown_param": "x"},
    ],
)
def test_invalid_query_parameters(client, auth_headers, params):
    assert client.get(URL, headers=auth_headers, params=params).status_code == 422
