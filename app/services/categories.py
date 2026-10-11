"""Category helpers shared by the auth and category routers."""

from sqlalchemy.orm import Session

from app.models import Category, TransactionType, User

# (name, kind, color, icon) seeded for every new account so the app is usable right away.
DEFAULT_CATEGORIES: list[tuple[str, TransactionType, str, str]] = [
    ("Salary", TransactionType.INCOME, "#43a047", "briefcase"),
    ("Freelance", TransactionType.INCOME, "#1e88e5", "laptop"),
    ("Investments", TransactionType.INCOME, "#8e24aa", "trending-up"),
    ("Gifts", TransactionType.INCOME, "#f06292", "gift"),
    ("Food & Drinks", TransactionType.EXPENSE, "#ff7043", "utensils"),
    ("Groceries", TransactionType.EXPENSE, "#7cb342", "shopping-cart"),
    ("Transport", TransactionType.EXPENSE, "#29b6f6", "bus"),
    ("Housing", TransactionType.EXPENSE, "#8d6e63", "home"),
    ("Bills & Utilities", TransactionType.EXPENSE, "#ffca28", "zap"),
    ("Health", TransactionType.EXPENSE, "#ef5350", "heart"),
    ("Entertainment", TransactionType.EXPENSE, "#ab47bc", "film"),
    ("Shopping", TransactionType.EXPENSE, "#26a69a", "shopping-bag"),
    ("Education", TransactionType.EXPENSE, "#5c6bc0", "book"),
    ("Other", TransactionType.EXPENSE, "#9e9e9e", "more-horizontal"),
]


def seed_default_categories(db: Session, user: User) -> list[Category]:
    """Attach the default categories to `user`. The caller is responsible for committing."""
    categories = [
        Category(user=user, name=name, kind=kind, color=color, icon=icon)
        for name, kind, color, icon in DEFAULT_CATEGORIES
    ]
    db.add_all(categories)
    return categories
