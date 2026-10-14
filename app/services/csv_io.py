"""CSV export and import of transactions.

The format is the same both ways, so an exported file can be imported back as-is::

    date,type,amount,category,description,note
    2026-10-12,expense,12.50,Food & Drinks,Lunch,
"""

import csv
import io
from dataclasses import dataclass, field

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Category, Transaction, TransactionType, User
from app.schemas.transaction import TransactionCreate, TransactionQuery
from app.services.transactions import sorted_query

COLUMNS = ["date", "type", "amount", "category", "description", "note"]
REQUIRED_COLUMNS = {"date", "type", "amount"}
MAX_IMPORT_ROWS = 5000

# CSV column -> TransactionCreate field.
_FIELD_FOR_COLUMN = {"date": "occurred_on"}
_COLUMN_FOR_FIELD = {value: key for key, value in _FIELD_FOR_COLUMN.items()}

# Spreadsheet apps execute cells starting with these as formulas (CSV injection).
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


class CSVFormatError(ValueError):
    """The file as a whole is unusable (encoding, header, size)."""


def _escape_formula(text: str) -> str:
    return f"'{text}" if text.startswith(_FORMULA_PREFIXES) else text


def _unescape_formula(text: str) -> str:
    return text[1:] if text.startswith("'") and text[1:].startswith(_FORMULA_PREFIXES) else text


# --- export -------------------------------------------------------------------


def export_transactions(db: Session, user: User, query: TransactionQuery) -> str:
    """Render the user's transactions matching `query` as CSV text."""
    query_names = select(Category.id, Category.name).where(Category.user_id == user.id)
    names = dict(db.execute(query_names).tuples().all())
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(COLUMNS)
    for tx in db.scalars(sorted_query(user, query)):
        writer.writerow(
            [
                tx.occurred_on.isoformat(),
                tx.type.value,
                f"{tx.amount:.2f}",
                _escape_formula(names.get(tx.category_id, "")),
                _escape_formula(tx.description),
                _escape_formula(tx.note or ""),
            ]
        )
    return buffer.getvalue()


# --- import -------------------------------------------------------------------


@dataclass
class ParsedImport:
    rows: list[tuple[int, TransactionCreate, str | None]] = field(default_factory=list)
    """Valid rows: (row number, transaction, category name not yet resolved)."""
    errors: list[dict[str, str]] = field(default_factory=list)
    """`{"location": "row 3.amount", "message": ...}` for every invalid cell."""


def _decode(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CSVFormatError("File must be UTF-8 encoded CSV") from exc


def parse_csv(content: bytes) -> ParsedImport:
    """Validate every row of an uploaded CSV without touching the database."""
    reader = csv.DictReader(io.StringIO(_decode(content), newline=""))
    if reader.fieldnames is None:
        raise CSVFormatError("File is empty")
    reader.fieldnames = [(name or "").strip().lower() for name in reader.fieldnames]
    missing = REQUIRED_COLUMNS - set(reader.fieldnames)
    if missing:
        raise CSVFormatError(f"Missing required column(s): {', '.join(sorted(missing))}")

    parsed = ParsedImport()
    # Row numbers match what a spreadsheet shows: the header is row 1.
    for row_number, raw in enumerate(reader, start=2):
        if row_number - 1 > MAX_IMPORT_ROWS:
            raise CSVFormatError(f"Too many rows (max {MAX_IMPORT_ROWS})")
        cells = {key: _unescape_formula((value or "").strip()) for key, value in raw.items() if key}
        if not any(cells.values()):
            continue  # ignore blank lines
        payload = {
            _FIELD_FOR_COLUMN.get(column, column): cells.get(column) or None
            for column in ("date", "type", "amount", "description", "note")
        }
        payload = {key: value for key, value in payload.items() if value is not None}
        if "type" in payload:
            payload["type"] = payload["type"].lower()
        try:
            transaction = TransactionCreate(**payload)
        except ValidationError as exc:
            problems = []
            for error in exc.errors():
                name = str(error["loc"][0]) if error["loc"] else "row"
                problems.append((_COLUMN_FOR_FIELD.get(name, name), error["msg"]))
            # Report problems left to right, in the file's column order.
            problems.sort(key=lambda item: COLUMNS.index(item[0]) if item[0] in COLUMNS else 99)
            parsed.errors.extend(
                {"location": f"row {row_number}.{column}", "message": message}
                for column, message in problems
            )
            continue
        parsed.rows.append((row_number, transaction, cells.get("category") or None))
    return parsed


@dataclass
class ImportResult:
    imported: int
    created_categories: list[str]
    errors: list[dict[str, str]]


def import_transactions(
    db: Session, user: User, content: bytes, *, create_categories: bool, dry_run: bool
) -> ImportResult:
    """Import all rows or none: any invalid row aborts the import and is reported back.

    Categories are matched by name (case-insensitive) and kind. Unknown ones are created
    when `create_categories` is set, otherwise they are reported as errors.
    The caller commits; nothing is added to the session on errors or in a dry run.
    """
    parsed = parse_csv(content)
    known = {
        (category.name.casefold(), category.kind): category.id
        for category in db.scalars(select(Category).where(Category.user_id == user.id))
    }
    # (casefolded name, kind) -> display name of categories to create.
    missing: dict[tuple[str, TransactionType], str] = {}
    errors = list(parsed.errors)
    resolved: list[tuple[TransactionCreate, tuple[str, TransactionType] | None]] = []

    for row_number, transaction, category_name in parsed.rows:
        key = None
        if category_name:
            key = (category_name.casefold(), transaction.type)
            if key not in known and create_categories:
                missing.setdefault(key, category_name[:60])
            elif key not in known:
                errors.append(
                    {
                        "location": f"row {row_number}.category",
                        "message": f"Unknown {transaction.type.value} category '{category_name}'",
                    }
                )
        resolved.append((transaction, key))

    created = sorted(missing.values(), key=str.casefold)
    if errors:
        return ImportResult(imported=0, created_categories=created, errors=errors)
    if dry_run:
        return ImportResult(imported=len(resolved), created_categories=created, errors=[])

    new_categories = {
        key: Category(user_id=user.id, name=name, kind=key[1]) for key, name in missing.items()
    }
    db.add_all(new_categories.values())
    db.flush()  # assign ids to the new categories
    known.update({key: category.id for key, category in new_categories.items()})
    db.add_all(
        Transaction(
            user_id=user.id,
            category_id=known[key] if key else None,
            **transaction.model_dump(exclude={"category_id"}),
        )
        for transaction, key in resolved
    )
    return ImportResult(imported=len(resolved), created_categories=created, errors=[])
