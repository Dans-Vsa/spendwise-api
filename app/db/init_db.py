"""Create all database tables. Run with: python -m app.db.init_db"""

from sqlalchemy import Engine

from app import models  # noqa: F401  (registers models on Base.metadata)
from app.db.base import Base
from app.db.session import engine as default_engine


def init_db(engine: Engine = default_engine) -> None:
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    init_db()
    print(f"Created tables: {', '.join(sorted(Base.metadata.tables))}")
