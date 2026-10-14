import csv
import io

import pytest

from app.services.csv_io import MAX_IMPORT_ROWS, parse_csv

URL = "/api/v1/transactions"
HEADER = "date,type,amount,category,description,note\n"


def category_id(client, headers, name):
    categories = client.get("/api/v1/categories", headers=headers).json()
    return next(c["id"] for c in categories if c["name"] == name)


def add(client, headers, **payload):
    body = {"type": "expense", "amount": "10.00", "occurred_on": "2026-10-01", **payload}
    response = client.post(URL, headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()


def upload(client, headers, text: str | bytes, **params):
    content = text.encode() if isinstance(text, str) else text
    return client.post(
        f"{URL}/import",
        headers=headers,
        params=params,
        files={"file": ("transactions.csv", content, "text/csv")},
    )


def rows(response) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(response.text)))


def list_all(client, headers) -> list[dict]:
    return client.get(URL, headers=headers, params={"limit": 100}).json()["items"]


# --- export -------------------------------------------------------------------


def test_export_csv(client, auth_headers):
    food = category_id(client, auth_headers, "Food & Drinks")
    add(client, auth_headers, category_id=food, description="Lunch, with team", note="paid cash")
    add(client, auth_headers, type="income", amount="2500", occurred_on="2026-10-05")

    response = client.get(f"{URL}/export", headers=auth_headers)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "transactions.csv" in response.headers["content-disposition"]
    assert response.text.splitlines()[0] == HEADER.strip()
    assert rows(response) == [
        {
            "date": "2026-10-05",
            "type": "income",
            "amount": "2500.00",
            "category": "",
            "description": "",
            "note": "",
        },
        {
            "date": "2026-10-01",
            "type": "expense",
            "amount": "10.00",
            "category": "Food & Drinks",
            "description": "Lunch, with team",
            "note": "paid cash",
        },
    ]


def test_export_applies_filters_and_sort(client, auth_headers):
    add(client, auth_headers, amount="5", description="small")
    add(client, auth_headers, amount="50", description="big")
    add(client, auth_headers, type="income", amount="100")

    response = client.get(
        f"{URL}/export", headers=auth_headers, params={"type": "expense", "sort": "amount"}
    )
    assert [row["description"] for row in rows(response)] == ["small", "big"]


def test_export_rejects_pagination_params(client, auth_headers):
    response = client.get(f"{URL}/export", headers=auth_headers, params={"limit": 5})
    assert response.status_code == 422


def test_export_only_contains_own_transactions(client, make_auth_headers):
    alice, bob = make_auth_headers("alice@example.com"), make_auth_headers("bob@example.com")
    add(client, alice, description="alice's")
    assert rows(client.get(f"{URL}/export", headers=bob)) == []


def test_export_escapes_formulas(client, auth_headers):
    add(client, auth_headers, description="=HYPERLINK(\"http://evil\")", note="@SUM(A1)")
    row = rows(client.get(f"{URL}/export", headers=auth_headers))[0]
    assert row["description"].startswith("'=")
    assert row["note"] == "'@SUM(A1)"


def test_export_requires_auth(client):
    assert client.get(f"{URL}/export").status_code == 401


# --- import -------------------------------------------------------------------


def test_import_csv(client, auth_headers):
    text = HEADER + (
        "2026-10-03,expense,12.5,food & drinks,Lunch,\n"
        "2026-10-04,INCOME,1000,Salary,October pay,bonus included\n"
        "2026-10-05,expense,3.20,,Coffee,\n"
    )
    response = upload(client, auth_headers, text)
    assert response.status_code == 200, response.text
    assert response.json() == {"imported": 3, "dry_run": False, "created_categories": []}

    items = {item["description"]: item for item in list_all(client, auth_headers)}
    assert items["Lunch"]["amount"] == "12.50"
    assert items["Lunch"]["category_id"] == category_id(client, auth_headers, "Food & Drinks")
    assert items["October pay"]["type"] == "income"
    assert items["October pay"]["note"] == "bonus included"
    assert items["Coffee"]["category_id"] is None


def test_export_then_import_round_trip(client, make_auth_headers):
    alice, bob = make_auth_headers("alice@example.com"), make_auth_headers("bob@example.com")
    food = category_id(client, alice, "Food & Drinks")
    add(client, alice, category_id=food, description="=1+1", note="multi\nline")
    add(client, alice, type="income", amount="99.99", description="Refund, partial")

    exported = client.get(f"{URL}/export", headers=alice).content
    assert upload(client, bob, exported).json()["imported"] == 2

    def strip(items):
        keys = ("type", "amount", "occurred_on", "description", "note")
        return sorted(tuple(item[key] for key in keys) for item in items)

    assert strip(list_all(client, bob)) == strip(list_all(client, alice))


def test_import_accepts_bom_header_case_and_missing_optional_columns(client, auth_headers):
    text = "﻿Date,Type,Amount\n2026-10-01,expense,7\n\n"
    response = upload(client, auth_headers, text.encode("utf-8"))
    assert response.json()["imported"] == 1


def test_import_is_all_or_nothing(client, auth_headers):
    text = HEADER + (
        "2026-10-01,expense,10,,ok row,\n"
        "2026-13-01,expense,-5,,bad row,\n"
        "2026-10-02,transfer,abc,,worse row,\n"
    )
    response = upload(client, auth_headers, text)
    assert response.status_code == 422
    error = response.json()["error"]
    assert "nothing was imported" in error["message"]
    locations = [field["location"] for field in error["fields"]]
    assert locations == ["row 3.date", "row 3.amount", "row 4.type", "row 4.amount"]
    assert list_all(client, auth_headers) == []


def test_import_unknown_category_fails_by_default(client, auth_headers):
    response = upload(client, auth_headers, HEADER + "2026-10-01,expense,10,Pets,Dog food,\n")
    assert response.status_code == 422
    field = response.json()["error"]["fields"][0]
    assert field == {"location": "row 2.category", "message": "Unknown expense category 'Pets'"}


def test_import_category_must_match_kind(client, auth_headers):
    # "Salary" exists, but only as an income category.
    response = upload(client, auth_headers, HEADER + "2026-10-01,expense,10,Salary,,\n")
    assert response.status_code == 422


def test_import_can_create_missing_categories(client, auth_headers):
    text = HEADER + (
        "2026-10-01,expense,10,Pets,Dog food,\n"
        "2026-10-02,expense,15,pets,Vet,\n"
        "2026-10-03,income,40,Side gigs,Tutoring,\n"
    )
    response = upload(client, auth_headers, text, create_categories=True)
    assert response.status_code == 200, response.text
    assert response.json()["created_categories"] == ["Pets", "Side gigs"]

    categories = client.get("/api/v1/categories", headers=auth_headers).json()
    pets = [c for c in categories if c["name"].lower() == "pets"]
    assert len(pets) == 1 and pets[0]["kind"] == "expense"
    assert {t["category_id"] for t in list_all(client, auth_headers) if t["type"] == "expense"} == {
        pets[0]["id"]
    }


def test_dry_run_saves_nothing(client, auth_headers):
    text = HEADER + "2026-10-01,expense,10,Pets,Dog food,\n"
    response = upload(client, auth_headers, text, create_categories=True, dry_run=True)
    assert response.json() == {"imported": 1, "dry_run": True, "created_categories": ["Pets"]}
    assert list_all(client, auth_headers) == []
    names = {c["name"] for c in client.get("/api/v1/categories", headers=auth_headers).json()}
    assert "Pets" not in names


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"", "File is empty"),
        (b"date,amount\n2026-10-01,5\n", "Missing required column(s): type"),
        ("date,type,amount\n2026-10-01,expense,5,caf\xe9\n".encode("latin-1"), "UTF-8"),
    ],
)
def test_import_rejects_bad_files(client, auth_headers, content, message):
    response = upload(client, auth_headers, content)
    assert response.status_code == 422
    assert message in response.json()["error"]["message"]


def test_import_rejects_large_files(client, auth_headers):
    big = HEADER + "2026-10-01,expense,1,,x,\n" * 60_000  # > 1 MiB
    response = upload(client, auth_headers, big)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


def test_parse_csv_limits_row_count():
    text = "date,type,amount\n" + "2026-10-01,expense,1\n" * (MAX_IMPORT_ROWS + 1)
    with pytest.raises(ValueError, match="Too many rows"):
        parse_csv(text.encode())


def test_parse_csv_unescapes_formula_prefix():
    parsed = parse_csv(b"date,type,amount,description\n2026-10-01,expense,1,'=1+1\n")
    assert parsed.rows[0][1].description == "=1+1"
