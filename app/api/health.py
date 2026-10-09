from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import __version__
from app.config import Settings, get_settings
from app.db.session import get_db

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str
    environment: str
    database: str
    timestamp: datetime


@router.get("/health", response_model=HealthResponse, summary="Service health check")
def health(
    settings: Settings = Depends(get_settings), db: Session = Depends(get_db)
) -> HealthResponse:
    try:
        db.execute(text("SELECT 1"))
        database = "ok"
    except SQLAlchemyError:
        database = "unavailable"
    return HealthResponse(
        status="ok" if database == "ok" else "degraded",
        app=settings.app_name,
        version=__version__,
        environment=settings.environment,
        database=database,
        timestamp=datetime.now(timezone.utc),
    )
